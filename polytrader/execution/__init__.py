"""Execution layer: Converts OMS commands to venue-specific actions.

Per flows.mdc §8: Execution applies tactics and routes to venue adapters.
"""

from collections.abc import Callable
from typing import Any

from polytrader.adapters.polymarket.market_data import GammaClient
from polytrader.clob import IClobClientFactory
from polytrader.events import EventBus
from polytrader.execution.adapter import IVenueAdapter
from polytrader.execution.fill_models import FillModel
from polytrader.execution.paper import PaperExecutionAdapter
from polytrader.execution.router import ExecutionRouter

__all__ = [
    "ExecutionRouter",
    "FillModel",
    "IVenueAdapter",
    "PaperExecutionAdapter",
    "create_execution_router_factory",
]


def create_execution_router_factory(
    bus: EventBus,
    clob_client_factory: IClobClientFactory,
    gamma_client: GammaClient | None = None,
    execution_control: Any | None = None,
) -> Callable[[], ExecutionRouter]:
    """Create a factory function for ExecutionRouter.

    Args:
        bus: Event bus for publishing events
        clob_client_factory: Factory for creating CLOB clients
        gamma_client: Gamma API client (optional)
        execution_control: Execution control for checking execution_enabled (optional)

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

        # Create execution router with execution control
        return ExecutionRouter(bus=bus, adapter=adapter, execution_control=execution_control)

    return factory
