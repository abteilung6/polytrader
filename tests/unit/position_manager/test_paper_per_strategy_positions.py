"""Unit tests for PaperPositionManager.get_positions_for_strategy.

Per unit_testing_technical.mdc:
- Component under test: PaperPositionManager (position_manager/paper.py)
- Contract: get_positions_for_strategy(strategy_id) returns only positions
  opened by that strategy; strategies must not see each other's positions.
"""

from __future__ import annotations

import pytest

from polytrader.events import EventBus
from polytrader.events.types import FillEvent, OrderIntentEvent
from polytrader.oms.models import OrderState
from polytrader.oms.store import InMemoryOrderStore
from polytrader.position_manager.paper import PaperPositionManager
from polytrader.types import Outcome


class TestPaperPositionManagerGetPositionsForStrategy:
    """PaperPositionManager get_positions_for_strategy contract and filtering."""

    @pytest.mark.asyncio
    async def test_returns_only_positions_opened_by_given_strategy(
        self,
        order_store: InMemoryOrderStore,
        position_manager: PaperPositionManager,
    ) -> None:
        """When two strategies have positions, each sees only its own."""
        # Open position (test-market, UP) as vfmr-demo
        intent_vfmr = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.50,
            limit_price=0.30,
            reason="Test",
            ttl_s=60.0,
            strategy_id="vfmr-demo",
        )
        order_vfmr = await order_store.create_order(intent_vfmr, "client-vfmr")
        order_vfmr.state = OrderState.FILLED
        order_store.update_order(order_vfmr)
        await position_manager._handle_fill(
            FillEvent(
                order_id=order_vfmr.order_id,
                fill_id="fill-vfmr",
                size=1.0,
                price=0.30,
                fee=0.0,
                venue_fill_id="v1",
                correlation_id=intent_vfmr.correlation_id,
            )
        )

        # Open position (test-market, DOWN) as market-data-collector
        intent_mdc = OrderIntentEvent(
            market_slug="test-market",
            outcome="DOWN",
            side="BUY",
            size=2.0,
            target_price=0.50,
            limit_price=0.25,
            reason="Test",
            ttl_s=60.0,
            strategy_id="market-data-collector",
        )
        order_mdc = await order_store.create_order(intent_mdc, "client-mdc")
        order_mdc.state = OrderState.FILLED
        order_store.update_order(order_mdc)
        await position_manager._handle_fill(
            FillEvent(
                order_id=order_mdc.order_id,
                fill_id="fill-mdc",
                size=2.0,
                price=0.25,
                fee=0.0,
                venue_fill_id="v2",
                correlation_id=intent_mdc.correlation_id,
            )
        )

        all_positions = position_manager.get_positions()
        assert all_positions is not None
        assert len(all_positions) == 2

        key_up: tuple[str, Outcome] = ("test-market", "UP")
        key_down: tuple[str, Outcome] = ("test-market", "DOWN")

        vfmr_positions = position_manager.get_positions_for_strategy("vfmr-demo")
        assert vfmr_positions is not None
        assert len(vfmr_positions) == 1
        assert key_up in vfmr_positions

        mdc_positions = position_manager.get_positions_for_strategy("market-data-collector")
        assert mdc_positions is not None
        assert len(mdc_positions) == 1
        assert key_down in mdc_positions

        other_positions = position_manager.get_positions_for_strategy("other")
        assert other_positions is not None
        assert len(other_positions) == 0

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_positions(
        self,
        position_manager: PaperPositionManager,
    ) -> None:
        """When manager has no positions, get_positions_for_strategy returns empty."""
        result = position_manager.get_positions_for_strategy("any-strategy")
        assert result is not None
        assert result == {}


@pytest.fixture
def bus() -> EventBus:
    """Event bus for tests."""
    return EventBus()


@pytest.fixture
def order_store(bus: EventBus) -> InMemoryOrderStore:
    """Order store for tests."""
    return InMemoryOrderStore(bus)


@pytest.fixture
def position_manager(bus: EventBus, order_store: InMemoryOrderStore) -> PaperPositionManager:
    """Paper position manager for tests."""
    return PaperPositionManager(bus=bus, store=order_store, starting_equity=1000.0)
