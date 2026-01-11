"""Execution layer: Converts OMS commands to venue-specific actions.

Per flows.mdc §8: Execution applies tactics and routes to venue adapters.
"""

from collections.abc import Callable

from polytrader.adapters.polymarket.market_data import GammaClient
from polytrader.clob import IClobClientFactory
from polytrader.events import EventBus
from polytrader.execution.router import ExecutionRouter

__all__ = ["ExecutionRouter", "create_execution_router_factory"]


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
