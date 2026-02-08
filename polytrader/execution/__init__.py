"""Execution layer: Converts OMS commands to venue-specific actions.

Per flows.mdc §8: Execution applies tactics and routes to venue adapters.
"""

from collections.abc import Callable
from typing import Any

from polytrader.adapters.polymarket.market_data import GammaClient
from polytrader.clob import IClobClientFactory
from polytrader.events import EventBus
from polytrader.events.bus import Topic
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
    active_strategies: set[str] | None = None,
    is_paper_mode: bool = True,
    submit_commands_topic: Topic[object] | None = None,
    cancel_commands_topic: Topic[object] | None = None,
) -> Callable[[], ExecutionRouter]:
    """Create a factory function for ExecutionRouter.

    Args:
        bus: Event bus for publishing events
        clob_client_factory: Factory for creating CLOB clients
        gamma_client: Gamma API client (optional)
        execution_control: Execution control for checking execution_enabled (optional)
        active_strategies: Set of active strategy IDs for live (optional)
        is_paper_mode: Whether router is for paper (default: True)
        submit_commands_topic: Topic for submit commands (optional, default single topic)
        cancel_commands_topic: Topic for cancel commands (optional, default single topic)

    Returns:
        Factory function that returns ExecutionRouter
    """

    from polytrader.adapters.polymarket.market_data import GammaClient
    from polytrader.adapters.polymarket.trading import ClobVenueAdapter

    def factory() -> ExecutionRouter:
        clob_client = clob_client_factory()
        gamma = gamma_client or GammaClient()
        adapter = ClobVenueAdapter(clob_client, gamma)
        return ExecutionRouter(
            bus=bus,
            adapter=adapter,
            execution_control=execution_control,
            active_strategies=active_strategies or set(),
            is_paper_mode=is_paper_mode,
            submit_commands_topic=submit_commands_topic,
            cancel_commands_topic=cancel_commands_topic,
        )

    return factory
