"""Risk engine: orchestrates all risk policies and aggregates results.

Per flows.mdc §6:
- Evaluate deterministic policies in fixed order
- Output RiskResult(allowed, reasons, projections)
- Emit RiskCheckEvent ALWAYS (in Commit 8)

Per architecture.mdc §1.C:
- risk/engine.py runs policies, aggregates result
"""

import asyncio
from typing import Any

from polytrader.events import APPROVED_PROPOSALS, ORDERS, PROPOSALS, RISK_CHECKS, EventBus
from polytrader.events.types import RiskCheckEvent
from polytrader.risk.models import RiskContext, RiskLimits, RiskReasonCode, RiskResult
from polytrader.risk.policies import (
    Clock,
    check_data_freshness,
    check_max_trades_per_market,
    check_position_limits,
    check_price_sanity,
    check_proposal_validity,
    check_rate_limits,
    check_system_health,
    check_token_ownership,
)
from polytrader.store import IMarketDataStore
from polytrader.types import OrderIntentEvent, Outcome

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
            check_max_trades_per_market,  # Fifth: max trades
            check_position_limits,  # Sixth: position limits
            check_price_sanity,  # Seventh: price sanity
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
        _executed_trades: Set of (market_slug, outcome) tuples for executed trades
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
        self._executed_trades: set[tuple[str, Outcome]] = set()
        self._order_count_last_minute = 0
        self._running = False

    async def check(self, intent: OrderIntentEvent, context: RiskContext) -> bool:
        """Check an order intent and emit RiskCheckEvent per flows.mdc §6.

        This is the pure method that accepts context as parameter.
        Use this for explicit checks with full control over context.

        Args:
            intent: Order intent to check
            context: Risk context with current state

        Returns:
            True if allowed, False if denied
        """
        result = self.engine.check(context)

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

        return result.allowed

    async def run(self) -> None:
        """Subscribe to PROPOSALS and process them.

        This method runs as an async task and processes proposals
        from the event bus, building RiskContext from available sources.

        Per flows.mdc §6: Risk runs before OMS submission.
        """
        self._running = True
        proposal_queue = self.bus.subscribe(PROPOSALS)
        orders_queue = self.bus.subscribe(ORDERS)  # Track executed trades

        async def track_orders() -> None:
            """Track executed orders for context building."""
            while self._running:
                try:
                    order = await orders_queue.get()
                    if order.side == "BUY":
                        self._executed_trades.add((order.market_slug, order.outcome))
                except asyncio.CancelledError:
                    break

        orders_task = asyncio.create_task(track_orders())

        try:
            while self._running:
                proposal = await proposal_queue.get()

                # Build RiskContext from available sources
                context = self._build_context(proposal)

                # Check and emit event
                await self.check(proposal, context)
        finally:
            self._running = False
            orders_task.cancel()
            try:
                await orders_task
            except asyncio.CancelledError:
                pass

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
        owned_tokens = self._executed_trades.copy()

        # Calculate current positions (simplified for Phase 2)
        # In Phase 3, this will come from OMS/PostTrade projections
        current_positions: dict[tuple[str, Outcome], float] = {}
        for market_slug, outcome in self._executed_trades:
            # Simplified: assume 1.0 USD per executed trade
            # In Phase 3, this will be accurate from OMS state
            current_positions[(market_slug, outcome)] = 1.0

        global_position = sum(current_positions.values())

        return RiskContext(
            intent=intent,
            current_positions=current_positions,
            global_position=global_position,
            executed_trades=self._executed_trades,
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
