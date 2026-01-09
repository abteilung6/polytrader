import asyncio
from collections.abc import Callable
from typing import Any, Protocol

from polytrader.clob import IClobClientFactory, place_market_order, verify_usdc_balance
from polytrader.events import APPROVED_PROPOSALS, ORDERS, PROPOSALS, EventBus
from polytrader.gamma import GammaClient
from polytrader.logging_config import logger
from polytrader.types import OrderExecutedEvent, OrderIntentEvent, Outcome


class IOrderManager(Protocol):
    """Protocol for order manager components."""

    async def run(self) -> None:
        """Start the order manager."""
        ...

    def stop(self) -> None:
        """Stop the order manager."""
        ...


def create_order_manager_factory(
    bus: EventBus,
    clob_client_factory: IClobClientFactory,
    gamma_client: GammaClient | None = None,
    max_trades_per_market: int = 1,
) -> Callable[[], IOrderManager]:
    """Create a factory function for IOrderManager.

    Args:
        bus: Event bus for publishing orders
        clob_client_factory: Factory for creating CLOB clients
        gamma_client: Gamma API client (optional)
        max_trades_per_market: Maximum trades per market/outcome

    Returns:
        Factory function that returns order manager
    """

    def factory() -> IOrderManager:
        return OrderManager(
            bus=bus,
            clob_client_factory=clob_client_factory,
            gamma_client=gamma_client,
            max_trades_per_market=max_trades_per_market,
        )

    return factory


def create_noop_order_manager_factory(bus: EventBus) -> Callable[[], IOrderManager]:
    """Create a factory function for a no-op order manager (predict mode).

    The no-op order manager consumes proposals but does not execute orders.
    This is used in predict mode to prevent order execution while still
    consuming proposals from the event bus.

    Args:
        bus: Event bus for subscribing to proposals

    Returns:
        Factory function that returns a no-op order manager
    """

    def factory() -> IOrderManager:
        return NoOpOrderManager(bus=bus)

    return factory


class OrderManager(IOrderManager):
    def __init__(
        self,
        bus: EventBus,
        clob_client_factory: IClobClientFactory,
        gamma_client: GammaClient | None = None,
        max_trades_per_market: int = 1,
    ) -> None:
        self.bus = bus
        self.clob_client_factory = clob_client_factory
        self.gamma_client = gamma_client or GammaClient()
        self.max_trades_per_market = max_trades_per_market
        self._executed_trades: set[tuple[str, Outcome]] = set()
        self._owned_tokens: set[tuple[str, Outcome]] = set()
        self._running = False

    async def run(self) -> None:
        """Start the order manager.

        Subscribes to APPROVED_PROPOSALS (proposals that passed risk checks).
        Per flows.mdc §6: Risk runs before OMS submission, so OrderManager
        only receives approved proposals.
        """
        self._running = True
        # Subscribe to APPROVED_PROPOSALS instead of PROPOSALS
        # Risk checks run before proposals reach OrderManager
        proposal_queue = self.bus.subscribe(APPROVED_PROPOSALS)

        try:
            while self._running:
                proposal = await proposal_queue.get()
                await self._process_proposal(proposal)
        except Exception:
            logger.exception("OrderManager error")
            raise
        finally:
            self._running = False

    async def _process_proposal(self, proposal: OrderIntentEvent) -> None:
        """Process an approved proposal (execution only).

        Per flows.mdc §6: Risk checks run before proposals reach OrderManager.
        This method only handles execution - all risk logic has been moved to RiskChecker.

        Args:
            proposal: Approved order intent (passed risk checks)
        """

        try:
            logger.bind(
                market_slug=proposal.market_slug,
                outcome=proposal.outcome,
                side=proposal.side,
            ).info(
                "Processing {side} proposal: {reason}",
                side=proposal.side,
                reason=proposal.reason,
            )

            response = await self._execute_order(proposal)
            # Only track BUY orders in _executed_trades (to enforce max_trades limit)
            # SELL orders don't count against the limit
            if proposal.side == "BUY":
                self._executed_trades.add((proposal.market_slug, proposal.outcome))

            if proposal.side == "BUY":
                self._owned_tokens.add((proposal.market_slug, proposal.outcome))
                logger.bind(market_slug=proposal.market_slug, outcome=proposal.outcome).debug(
                    "Added to owned tokens"
                )
            elif proposal.side == "SELL":
                self._owned_tokens.discard((proposal.market_slug, proposal.outcome))
                logger.bind(market_slug=proposal.market_slug, outcome=proposal.outcome).debug(
                    "Removed from owned tokens"
                )

            order = OrderExecutedEvent(
                market_slug=proposal.market_slug,
                outcome=proposal.outcome,
                side=proposal.side,
                size=proposal.size,
                target_price=proposal.target_price if proposal.side == "BUY" else None,
                proposal_reason=proposal.reason,
                response=response,
                correlation_id=proposal.correlation_id,  # Propagate from OrderIntentEvent
            )
            await self.bus.publish(ORDERS, order)

            order_id = (
                response.get("order_id") or response.get("id", "unknown")
                if isinstance(response, dict)
                else "unknown"
            )
            logger.bind(
                market_slug=proposal.market_slug,
                outcome=proposal.outcome,
                side=proposal.side,
                order_id=order_id,
            ).info(
                "✅ Successfully executed {side} order (ID: {order_id}): {reason}",
                side=proposal.side,
                order_id=order_id,
                reason=proposal.reason,
            )
        except Exception as e:
            error_msg = str(e)
            if "not enough balance" in error_msg.lower() or "allowance" in error_msg.lower():
                if proposal.side == "SELL":
                    logger.bind(market_slug=proposal.market_slug, outcome=proposal.outcome).warning(
                        "Cannot sell: insufficient token balance. Error: {error}",
                        error=error_msg,
                    )
                else:
                    logger.bind(
                        market_slug=proposal.market_slug,
                        outcome=proposal.outcome,
                        side=proposal.side,
                    ).error(
                        "Balance/allowance error executing {side} order: {error}. "
                        "Please check your USDC balance and allowance.",
                        side=proposal.side,
                        error=error_msg,
                    )
            else:
                logger.exception("Failed to execute order")

    def _has_traded(self, market_slug: str, outcome: Outcome) -> bool:
        """Check if we have executed a trade for this market/outcome.

        This is kept for tracking purposes only. Risk validation is handled by RiskChecker.
        """
        return (market_slug, outcome) in self._executed_trades

    def _has_tokens(self, market_slug: str, outcome: Outcome) -> bool:
        """Check if we own tokens for this market/outcome.

        This is kept for tracking purposes only. Risk validation is handled by RiskChecker.
        """
        return (market_slug, outcome) in self._owned_tokens

    async def _execute_order(self, proposal: OrderIntentEvent) -> dict[str, Any]:
        market = await asyncio.to_thread(self.gamma_client.get_market_by_slug, proposal.market_slug)
        token_id = market.get_token_id(proposal.outcome)

        client = self.clob_client_factory()

        if proposal.side == "BUY":
            await asyncio.to_thread(
                lambda: verify_usdc_balance(client, required_amount=proposal.size)
            )

        response = await asyncio.to_thread(
            lambda: place_market_order(
                client,
                token_id=token_id,
                amount=proposal.size,
                side=proposal.side,
            )
        )
        return response

    def stop(self) -> None:
        self._running = False

    def reset_trades(self) -> None:
        """Reset executed trades tracking. Useful for testing."""
        self._executed_trades.clear()
        self._owned_tokens.clear()

    def reset_owned_tokens(self) -> None:
        """Reset owned tokens tracking. Useful for testing."""
        self._owned_tokens.clear()


class NoOpOrderManager(IOrderManager):
    """No-op order manager that consumes proposals without executing orders.

    Used in predict mode to prevent order execution while still consuming
    proposals from the event bus so they don't accumulate.
    """

    def __init__(self, bus: EventBus) -> None:
        """Initialize the no-op order manager.

        Args:
            bus: Event bus for subscribing to proposals
        """
        self.bus = bus
        self._running = False

    async def run(self) -> None:
        """Start consuming proposals without executing orders."""
        self._running = True
        proposal_queue = self.bus.subscribe(PROPOSALS)

        try:
            while self._running:
                proposal = await proposal_queue.get()
                # Consume proposal but don't execute
                logger.bind(
                    market_slug=proposal.market_slug,
                    outcome=proposal.outcome,
                    side=proposal.side,
                ).info(
                    "Predict mode: consuming proposal (no execution) - "
                    "{side} {outcome} for {market_slug}",
                    side=proposal.side,
                    outcome=proposal.outcome,
                    market_slug=proposal.market_slug,
                )
        except Exception:
            logger.exception("NoOpOrderManager error")
            raise
        finally:
            self._running = False

    def stop(self) -> None:
        """Stop the no-op order manager."""
        self._running = False
