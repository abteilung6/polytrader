"""Execution Router: Converts OMS commands to venue actions.

This module provides factory functions for creating ExecutionRouter instances.
The ExecutionRouter replaces the old OrderManager and subscribes to OMS commands.
"""

from collections.abc import Callable

from polytrader.adapters.polymarket.market_data import GammaClient
from polytrader.clob import IClobClientFactory
from polytrader.events import PROPOSALS, EventBus
from polytrader.execution import ExecutionRouter
from polytrader.logging_config import logger


def create_execution_router_factory(
    bus: EventBus,
    clob_client_factory: IClobClientFactory,
    gamma_client: GammaClient | None = None,
) -> Callable[[], ExecutionRouter]:
    """Create a factory function for ExecutionRouter.

    Args:
        bus: Event bus for publishing events
        clob_client_factory: Factory for creating CLOB clients
        gamma_client: Gamma API client (optional)

    Returns:
        Factory function that returns ExecutionRouter
    """
    from polytrader.adapters.polymarket.market_data import GammaClient
    from polytrader.adapters.polymarket.trading import ClobVenueAdapter

    def factory() -> ExecutionRouter:
        # Create venue adapter
        clob_client = clob_client_factory()
        gamma = gamma_client or GammaClient()
        adapter = ClobVenueAdapter(clob_client, gamma)

        # Create execution router
        return ExecutionRouter(bus=bus, adapter=adapter)

    return factory


class NoOpOrderManager:
    """No-op order manager that consumes proposals without executing orders.

    Used in predict mode to prevent order execution while still consuming
    proposals from the event bus so they don't accumulate.

    Note: This is kept for backward compatibility. In the new architecture,
    execution is handled by ExecutionRouter which subscribes to OMS commands.
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


def create_noop_order_manager_factory(bus: EventBus) -> Callable[[], NoOpOrderManager]:
    """Create a factory function for a no-op order manager (predict mode).

    The no-op order manager consumes proposals but does not execute orders.
    This is used in predict mode to prevent order execution while still
    consuming proposals from the event bus.

    Args:
        bus: Event bus for subscribing to proposals

    Returns:
        Factory function that returns a no-op order manager
    """

    def factory() -> NoOpOrderManager:
        return NoOpOrderManager(bus=bus)

    return factory


# Backward compatibility aliases
def create_order_manager_factory(
    bus: EventBus,
    clob_client_factory: IClobClientFactory,
    gamma_client: GammaClient | None = None,
    max_trades_per_market: int = 1,  # Ignored, kept for compatibility
) -> Callable[[], ExecutionRouter]:
    """Create a factory function for ExecutionRouter (backward compatibility).

    This function is kept for backward compatibility. It creates an ExecutionRouter
    instead of the old OrderManager.

    Args:
        bus: Event bus for publishing events
        clob_client_factory: Factory for creating CLOB clients
        gamma_client: Gamma API client (optional)
        max_trades_per_market: Ignored (kept for compatibility)

    Returns:
        Factory function that returns ExecutionRouter
    """
    return create_execution_router_factory(bus, clob_client_factory, gamma_client)
