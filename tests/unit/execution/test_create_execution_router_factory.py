"""Unit tests for create_execution_router_factory."""

from typing import Any

from polytrader.adapters.polymarket.trading import ClobVenueAdapter
from polytrader.clob import IClobClient, IClobClientFactory
from polytrader.events import (
    CANCEL_ORDER_COMMANDS_LIVE,
    SUBMIT_ORDER_COMMANDS_LIVE,
    EventBus,
)
from polytrader.execution import ExecutionRouter, create_execution_router_factory


def _make_fake_clob_factory() -> IClobClientFactory:
    """Minimal IClobClient implementation so factory satisfies IClobClientFactory."""

    class FakeClobClient:
        """Minimal IClobClient for tests; only router/adapter wiring is asserted."""

        def get_balance_allowance(self, params: Any) -> dict[str, Any]:
            return {}

        def create_market_order(self, order_args: Any) -> dict[str, Any]:
            return {}

        def post_order(self, signed_order: Any, order_type: Any) -> dict[str, Any]:
            return {}

        def create_or_derive_api_creds(self) -> Any:
            return None

        def set_api_creds(self, creds: Any) -> None:
            pass

        def get_orders(self, params: Any) -> list[dict[str, Any]]:
            return []

    def factory() -> IClobClient:
        return FakeClobClient()

    return factory


def test_factory_returns_router_with_live_params() -> None:
    """Factory with is_paper_mode=False returns router with correct adapter and topics."""
    bus = EventBus()
    clob_factory = _make_fake_clob_factory()

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
