"""Unit tests for create_execution_router_factory."""

import pytest

from polytrader.adapters.polymarket.trading import ClobVenueAdapter
from polytrader.events import (
    CANCEL_ORDER_COMMANDS_LIVE,
    EventBus,
    SUBMIT_ORDER_COMMANDS_LIVE,
)
from polytrader.execution import ExecutionRouter, create_execution_router_factory


def test_factory_returns_router_with_live_params() -> None:
    """Factory with is_paper_mode=False returns router with correct adapter and topics."""
    bus = EventBus()

    class FakeClobClient:
        pass

    def clob_factory() -> FakeClobClient:
        return FakeClobClient()

    factory = create_execution_router_factory(
        bus=bus,
        clob_client_factory=clob_factory,
        execution_control=None,
        active_strategies=set(),
        is_paper_mode=False,
        submit_commands_topic=SUBMIT_ORDER_COMMANDS_LIVE,
        cancel_commands_topic=CANCEL_ORDER_COMMANDS_LIVE,
    )
    router = factory()
    assert isinstance(router, ExecutionRouter)
    assert router._is_paper_mode is False
    assert isinstance(router.get_adapter(), ClobVenueAdapter)
    assert router._submit_commands_topic.name == SUBMIT_ORDER_COMMANDS_LIVE.name
    assert router._cancel_commands_topic.name == CANCEL_ORDER_COMMANDS_LIVE.name
