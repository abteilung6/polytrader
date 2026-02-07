"""Risk engine: orchestrates all risk policies and aggregates results.

Per flows.mdc §6:
- Evaluate deterministic policies in fixed order
- Output RiskResult(allowed, reasons, projections)
- Emit RiskCheckEvent ALWAYS (in Commit 8)

Per architecture.mdc §1.C:
- risk/engine.py runs policies, aggregates result

Per observability.mdc §2, §3:
- All logs must include correlation_id when applicable
- Structured logging with required fields
"""

import asyncio
from typing import Any

from polytrader.events import APPROVED_PROPOSALS, ORDERS, PROPOSALS, RISK_CHECKS, EventBus
from polytrader.events.types import OrderIntentEvent, RiskCheckEvent
from polytrader.logging_config import logger
from polytrader.obs.metrics import (
    record_projected_exposure,
    record_risk_check,
    record_risk_denial,
)
from polytrader.risk.models import RiskContext, RiskLimits, RiskReasonCode, RiskResult
from polytrader.risk.policies import (
    Clock,
    check_data_freshness,
    check_max_trades_per_market,
    check_position_limits,
    check_price_sanity,
    check_proposal_validity,
    check_rate_limits,
    check_strategy_activation,
    check_system_health,
    check_token_ownership,
)
from polytrader.store import IMarketDataStore
from polytrader.types import Outcome

# No rebuild needed - no circular dependency anymore

# Type for risk policy functions
# Policies can have either (context, limits) -> RiskResult or
# (context, limits, clock) -> RiskResult. We handle the difference at runtime.
RiskPolicy = Any


class RiskEngine:
    """Risk engine that runs all risk policies and aggregates results.

    Per flows.mdc §6:
    - Evaluate deterministic policies in fixed order
    - Output RiskResult(allowed, reasons, projections)
    - Emit RiskCheckEvent ALWAYS (in Commit 8)

    Per architecture.mdc §1.C:
    - risk/engine.py runs policies, aggregates result

    Attributes:
        limits: Risk limits configuration
        clock: Optional clock for deterministic time (for testing)
        policies: List of policy functions to run (in fixed order per flows.mdc §6)
    """

    def __init__(self, limits: RiskLimits, clock: Clock | None = None) -> None:
        """Initialize risk engine.

        Args:
            limits: Risk limits configuration
            clock: Optional clock for deterministic time (for testing)
        """
        self.limits = limits
        self.clock = clock
        # Default policy set in fixed order per flows.mdc §6 (can be customized)
        self.policies: list[RiskPolicy] = [
            check_proposal_validity,  # First: basic validity
            check_system_health,  # Second: system health gates
            check_data_freshness,  # Third: data freshness
            check_token_ownership,  # Fourth: token ownership
            check_strategy_activation,  # Fifth: strategy activation (paper vs live)
            check_max_trades_per_market,  # Sixth: max trades
            check_position_limits,  # Seventh: position limits
            check_price_sanity,  # Eighth: price sanity
            check_rate_limits,  # Last: rate limits
        ]

    def check(self, context: RiskContext) -> RiskResult:
        """Run all risk policies in fixed order and aggregate results per flows.mdc §6.

        Policies are run in order. If any policy denies, the final result
        is denied. All policy results are aggregated (reason codes, projections, metadata).

        Args:
            context: Risk context with order intent and current state

        Returns:
            Aggregated RiskResult with final decision and all reason codes
        """
        all_reasons: list[RiskReasonCode] = []
        all_projections: dict[str, Any] = {}
        all_metadata: dict[str, Any] = {}
        allowed = True

        # Run all policies in fixed order per flows.mdc §6
        for policy in self.policies:
            # Pass clock to policies that need it
            if policy in (check_proposal_validity, check_data_freshness):
                result = policy(context, self.limits, self.clock)
            else:
                result = policy(context, self.limits)

            # Aggregate results
            all_reasons.extend(result.reason_codes)
            all_projections.update(result.projections)
            all_metadata.update(result.metadata)

            # If any policy denies, final result is denied
            if not result.allowed:
                allowed = False
                # Continue running policies for complete audit trail

        # Remove duplicate reason codes (keep order, first occurrence)
        unique_reasons = []
        seen = set()
        for reason in all_reasons:
            if reason not in seen:
                unique_reasons.append(reason)
                seen.add(reason)

        return RiskResult(
            allowed=allowed,
            reason_codes=unique_reasons,
            projections=all_projections,
            metadata=all_metadata,
        )


class RiskChecker:
    """Component that checks orders and emits RiskCheckEvent per flows.mdc §6.

    This component subscribes to PROPOSALS, runs risk checks,
    and publishes RISK_CHECKS events. Approved orders are published
    to APPROVED_PROPOSALS topic.

    Per flows.mdc §6:
    - Input: OrderIntent + Context
    - Output: RiskResult(allowed, reasons, projections)
    - Emit RiskCheckEvent ALWAYS
    - If denied: stop (no OMS entry)
    - If allowed: publish to APPROVED_PROPOSALS

    Attributes:
        bus: Event bus for publishing events
        engine: Risk engine for running checks
        store: Optional market data store for building context
        _executed_trades: Set of (strategy_id, market_slug, outcome) tuples for executed trades
        _approved_trades: Set of (strategy_id, market_slug, outcome) tuples for approved BUY orders
        _order_count_last_minute: Number of orders in the last minute (simple counter)
        _running: Whether the checker is running
    """

    def __init__(
        self,
        bus: EventBus,
        engine: RiskEngine,
        store: IMarketDataStore | None = None,
    ) -> None:
        """Initialize risk checker.

        Args:
            bus: Event bus for publishing events
            engine: Risk engine for running checks
            store: Optional market data store for building context
        """
        self.bus = bus
        self.engine = engine
        self.store = store
        self._executed_trades: set[tuple[str, str, Outcome]] = set()
        self._approved_trades: set[tuple[str, str, Outcome]] = set()
        # Maps correlation_id → (strategy_id, market_slug, outcome) for approved trades
        # so we can match OrderExecutedEvent (which lacks strategy_id) back to the right key
        self._approved_correlation: dict[str, tuple[str, str, Outcome]] = {}
        self._order_count_last_minute = 0
        self._running = False

    async def check(self, intent: OrderIntentEvent, context: RiskContext) -> bool:
        """Check an order intent and emit RiskCheckEvent per flows.mdc §6.

        This is the pure method that accepts context as parameter.
        Use this for explicit checks with full control over context.

        Per observability.mdc §2, §3:
        - All logs include correlation_id
        - Structured logging with required fields

        Args:
            intent: Order intent to check
            context: Risk context with current state

        Returns:
            True if allowed, False if denied
        """
        # Build structured log context with correlation_id per observability.mdc §2
        log_context = logger.bind(
            correlation_id=intent.correlation_id,
            market_slug=intent.market_slug,
            outcome=intent.outcome,
            side=intent.side,
            event_type="RiskCheck",
        )

        log_context.debug("Starting risk check for order intent")

        result = self.engine.check(context)

        # Emit metrics per observability.mdc §4
        record_risk_check(allowed=result.allowed)

        if not result.allowed:
            # Record denial reason(s) per observability.mdc §4
            for reason_code in result.reason_codes:
                if reason_code != RiskReasonCode.RISK_ALLOWED:
                    record_risk_denial(reason=reason_code.value)

            # Log denial with correlation_id and reason codes per observability.mdc §2, §3
            # Filter out RISK_ALLOWED from denial messages (it's confusing to show both)
            denial_reasons = [
                rc.value for rc in result.reason_codes if rc != RiskReasonCode.RISK_ALLOWED
            ]
            reason_codes_str = ", ".join(denial_reasons)
            log_context.warning(
                "Risk check denied: {reason_codes}",
                reason_codes=reason_codes_str,
            )
        else:
            # Log allowance with correlation_id per observability.mdc §2, §3
            log_context.info("Risk check allowed")

        # Record projected exposure if available per observability.mdc §4
        if "projected_exposure" in result.projections:
            record_projected_exposure(exposure=result.projections["projected_exposure"])

        # Emit RiskCheckEvent ALWAYS per flows.mdc §6
        event = RiskCheckEvent(
            intent=intent,
            result=result,
            correlation_id=intent.correlation_id,  # Propagate per observability.mdc §2
        )
        await self.bus.publish(RISK_CHECKS, event)

        # If allowed, publish to APPROVED_PROPOSALS per flows.mdc §6
        if result.allowed:
            await self.bus.publish(APPROVED_PROPOSALS, intent)
            self._order_count_last_minute += 1
            # Track approved BUY orders immediately to prevent race condition
            # where multiple orders pass risk checks before first one executes
            if intent.side == "BUY":
                key = (intent.strategy_id, intent.market_slug, intent.outcome)
                self._approved_trades.add(key)
                self._approved_correlation[intent.correlation_id] = key
                log_context.debug(
                    "Tracked approved BUY for max_trades: {strategy_id}/{market_slug}/{outcome}",
                    strategy_id=intent.strategy_id,
                    market_slug=intent.market_slug,
                    outcome=intent.outcome,
                )
            log_context.debug("Published approved proposal to APPROVED_PROPOSALS")
        else:
            log_context.debug("Proposal denied, not publishing to APPROVED_PROPOSALS")

        return result.allowed

    async def run(self) -> None:
        """Subscribe to PROPOSALS and process them.

        This method runs as an async task and processes proposals
        from the event bus, building RiskContext from available sources.

        Per flows.mdc §6: Risk runs before OMS submission.
        Per observability.mdc §2, §3: All logs include correlation_id.
        """
        self._running = True
        proposal_queue = self.bus.subscribe(PROPOSALS)
        orders_queue = self.bus.subscribe(ORDERS)  # Track executed trades

        logger.info("RiskChecker started, subscribing to PROPOSALS")

        async def track_orders() -> None:
            """Track executed orders for context building."""
            while self._running:
                try:
                    order = await orders_queue.get()
                    if order.side == "BUY":
                        # Match via correlation_id to find the strategy_id
                        # (OrderExecutedEvent does not carry strategy_id)
                        approved_key = self._approved_correlation.pop(order.correlation_id, None)
                        if approved_key is not None:
                            key = approved_key
                            self._approved_trades.discard(key)
                        else:
                            # Fallback: no approved match (e.g., restart with in-flight orders)
                            strategy_id = getattr(order, "strategy_id", "unknown")
                            key = (strategy_id, order.market_slug, order.outcome)
                        self._executed_trades.add(key)
                        logger.bind(
                            correlation_id=order.correlation_id,
                            strategy_id=key[0],
                            market_slug=order.market_slug,
                            outcome=order.outcome,
                            event_type="RiskCheck",
                        ).debug("Tracked executed BUY order for risk context")
                except asyncio.CancelledError:
                    break

        orders_task = asyncio.create_task(track_orders())

        try:
            while self._running:
                proposal = await proposal_queue.get()

                # Build RiskContext from available sources
                context = self._build_context(proposal)

                # Check and emit event (logging happens inside check() with correlation_id)
                await self.check(proposal, context)
        except asyncio.CancelledError:
            logger.info("RiskChecker cancelled")
        except Exception:
            logger.exception("RiskChecker error")
            raise
        finally:
            self._running = False
            orders_task.cancel()
            try:
                await orders_task
            except asyncio.CancelledError:
                pass
            logger.info("RiskChecker stopped")

    def _build_context(self, intent: OrderIntentEvent) -> RiskContext:
        """Build RiskContext from available sources.

        For Phase 2, this builds context from:
        - Executed trades (from ORDERS subscription)
        - Market data (from store if available)
        - System health (defaults for Phase 2)

        In Phase 3 (OMS), context will come from OMS state.

        Args:
            intent: Order intent being checked

        Returns:
            RiskContext with current state
        """
        # Get market data from store (if available)
        market_data = None
        if self.store:
            market_data = self.store.latest(intent.market_slug, intent.outcome)

        # Build owned tokens from executed trades (simplified for Phase 2)
        # In Phase 3, this will come from OMS state
        # owned_tokens is (market_slug, outcome) — global across strategies
        owned_tokens: set[tuple[str, Outcome]] = set()
        for _sid, mkt, out in self._executed_trades:
            owned_tokens.add((mkt, out))

        # Calculate current positions (simplified for Phase 2)
        # In Phase 3, this will come from OMS/PostTrade projections
        current_positions: dict[tuple[str, Outcome], float] = {}
        for _sid, market_slug, outcome in self._executed_trades:
            # Simplified: assume 1.0 USD per executed trade
            # In Phase 3, this will be accurate from OMS state
            current_positions[(market_slug, outcome)] = (
                current_positions.get((market_slug, outcome), 0.0) + 1.0
            )

        global_position = sum(current_positions.values())

        # Combine executed and approved trades for max_trades_per_market check
        # Keyed by (strategy_id, market_slug, outcome) — per-instance scoping
        all_trades = self._executed_trades | self._approved_trades

        return RiskContext(
            intent=intent,
            current_positions=current_positions,
            global_position=global_position,
            executed_trades=all_trades,  # Include both executed and approved
            market_data=market_data,
            owned_tokens=owned_tokens,
            # System health defaults for Phase 2 (will be implemented in Phase 3)
            kill_switch_active=False,
            circuit_breaker_active=False,
            reconciliation_healthy=True,
            order_count_last_minute=self._order_count_last_minute,
            cancel_count_last_minute=0,  # TODO: Track cancels in Phase 3
            limits_version=self.engine.limits.version,
        )

    def stop(self) -> None:
        """Stop the risk checker."""
        self._running = False
