"""Integration tests for posttrade metrics (positions and unrealized PnL).

Per Commit 15: Add posttrade metrics for positions and unrealized PnL.
Per observability.mdc §4: Position and PnL metrics are critical for risk monitoring.
"""

import asyncio

import pytest

from polytrader.events import FILLS, MARKET_DATA
from polytrader.events.bus import EventBus
from polytrader.events.store import MemoryEventStore
from polytrader.events.types import FillEvent, MarketDataEvent, OrderIntentEvent
from polytrader.obs.metrics import (
    MemoryMetricsCollector,
    set_metrics_collector,
)
from polytrader.oms.store import InMemoryOrderStore
from polytrader.position_manager.paper import PaperPositionManager
from polytrader.types import Outcome


@pytest.fixture
def bus() -> EventBus:
    """Create an event bus for testing."""
    return EventBus(store=MemoryEventStore())


@pytest.fixture
def metrics_collector() -> MemoryMetricsCollector:
    """Create a metrics collector for testing."""
    collector = MemoryMetricsCollector()
    set_metrics_collector(collector)
    return collector


@pytest.fixture
def order_store(bus: EventBus) -> InMemoryOrderStore:
    """Create an order store for testing."""
    return InMemoryOrderStore(bus)


@pytest.fixture
def position_manager(bus: EventBus, order_store: InMemoryOrderStore) -> PaperPositionManager:
    """Create a position manager for testing."""
    return PaperPositionManager(bus=bus, store=order_store, starting_equity=1000.0)


class TestPositionMetrics:
    """Tests for position_net gauge in position manager."""

    @pytest.mark.asyncio
    async def test_buy_fill_emits_position_metric(
        self,
        position_manager: PaperPositionManager,
        order_store: InMemoryOrderStore,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that BUY fill emits position_net gauge."""
        # Create an order
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=100.0,
            limit_price=0.5,
            target_price=0.5,
            reason="Test order",
            correlation_id="corr-123",
            strategy_id="simple_threshold",
        )
        order = await order_store.create_order(intent, "client-123")

        # Create fill event
        fill_event = FillEvent(
            order_id=order.order_id,
            fill_id="fill-123",
            size=100.0,
            price=0.5,
            fee=0.0,
            correlation_id="corr-123",
            strategy_id="simple_threshold",
        )

        # Start position manager
        manager_task = None
        try:
            manager_task = asyncio.create_task(position_manager.run())
            await asyncio.sleep(0.05)

            # Publish fill event
            await position_manager._bus.publish(FILLS, fill_event)

            # Wait for processing
            await asyncio.sleep(0.5)

            # Verify position metric was emitted
            assert (
                metrics_collector.get_gauge(
                    "position_net", labels={"market": "test-market", "outcome": "UP"}
                )
                == 100.0
            )
        finally:
            if manager_task:
                position_manager.stop()
                manager_task.cancel()
                try:
                    await manager_task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_sell_fill_updates_position_metric(
        self,
        position_manager: PaperPositionManager,
        order_store: InMemoryOrderStore,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that SELL fill updates position_net gauge."""
        # Create BUY order
        buy_intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=100.0,
            limit_price=0.5,
            target_price=0.5,
            reason="Test buy order",
            correlation_id="corr-123",
            strategy_id="simple_threshold",
        )
        buy_order = await order_store.create_order(buy_intent, "client-123")

        # Create BUY fill event
        buy_fill = FillEvent(
            order_id=buy_order.order_id,
            fill_id="fill-123",
            size=100.0,
            price=0.5,
            fee=0.0,
            correlation_id="corr-123",
            strategy_id="simple_threshold",
        )

        # Create SELL order
        sell_intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="SELL",
            size=50.0,
            limit_price=0.6,
            target_price=0.6,
            reason="Test sell",
            correlation_id="corr-456",
            strategy_id="simple_threshold",
        )
        sell_order = await order_store.create_order(sell_intent, "client-456")

        # Create SELL fill event
        sell_fill = FillEvent(
            order_id=sell_order.order_id,
            fill_id="fill-456",
            size=50.0,
            price=0.6,
            fee=0.0,
            correlation_id="corr-456",
            strategy_id="simple_threshold",
        )

        # Start position manager
        manager_task = None
        try:
            manager_task = asyncio.create_task(position_manager.run())
            await asyncio.sleep(0.05)

            # Publish BUY fill
            await position_manager._bus.publish(FILLS, buy_fill)
            await asyncio.sleep(0.2)

            # Verify initial position
            assert (
                metrics_collector.get_gauge(
                    "position_net", labels={"market": "test-market", "outcome": "UP"}
                )
                == 100.0
            )

            # Publish SELL fill
            await position_manager._bus.publish(FILLS, sell_fill)
            await asyncio.sleep(0.2)

            # Verify position updated (100 - 50 = 50)
            assert (
                metrics_collector.get_gauge(
                    "position_net", labels={"market": "test-market", "outcome": "UP"}
                )
                == 50.0
            )
        finally:
            if manager_task:
                position_manager.stop()
                manager_task.cancel()
                try:
                    await manager_task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_position_closed_emits_zero_metric(
        self,
        position_manager: PaperPositionManager,
        order_store: InMemoryOrderStore,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that closing a position emits position_net gauge = 0."""
        # Create BUY order
        buy_intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=100.0,
            limit_price=0.5,
            target_price=0.5,
            reason="Test buy",
            correlation_id="corr-123",
            strategy_id="simple_threshold",
        )
        buy_order = await order_store.create_order(buy_intent, "client-123")

        # Create SELL order (full close)
        sell_intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="SELL",
            size=100.0,
            limit_price=0.6,
            target_price=0.6,
            reason="Test sell",
            correlation_id="corr-456",
            strategy_id="simple_threshold",
        )
        sell_order = await order_store.create_order(sell_intent, "client-456")

        # Create fills
        buy_fill = FillEvent(
            order_id=buy_order.order_id,
            fill_id="fill-123",
            size=100.0,
            price=0.5,
            fee=0.0,
            correlation_id="corr-123",
            strategy_id="simple_threshold",
        )
        sell_fill = FillEvent(
            order_id=sell_order.order_id,
            fill_id="fill-456",
            size=100.0,
            price=0.6,
            fee=0.0,
            correlation_id="corr-456",
            strategy_id="simple_threshold",
        )

        # Start position manager
        manager_task = None
        try:
            manager_task = asyncio.create_task(position_manager.run())
            await asyncio.sleep(0.05)

            # Publish BUY fill
            await position_manager._bus.publish(FILLS, buy_fill)
            await asyncio.sleep(0.2)

            # Publish SELL fill (closes position)
            await position_manager._bus.publish(FILLS, sell_fill)
            await asyncio.sleep(0.2)

            # Verify position is zero (closed)
            assert (
                metrics_collector.get_gauge(
                    "position_net", labels={"market": "test-market", "outcome": "UP"}
                )
                == 0.0
            )
        finally:
            if manager_task:
                position_manager.stop()
                manager_task.cancel()
                try:
                    await manager_task
                except asyncio.CancelledError:
                    pass


class TestUnrealizedPnLMetrics:
    """Tests for pnl_unrealized gauge in position manager."""

    @pytest.mark.asyncio
    async def test_calculate_unrealized_pnl_emits_metric(
        self,
        position_manager: PaperPositionManager,
        order_store: InMemoryOrderStore,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that calculate_unrealized_pnl emits pnl_unrealized gauge."""
        # Create BUY order
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=100.0,
            limit_price=0.5,
            target_price=0.5,
            reason="Test order",
            correlation_id="corr-123",
            strategy_id="simple_threshold",
        )
        order = await order_store.create_order(intent, "client-123")

        # Create fill event
        fill_event = FillEvent(
            order_id=order.order_id,
            fill_id="fill-123",
            size=100.0,
            price=0.5,  # Entry price
            fee=0.0,
            correlation_id="corr-123",
            strategy_id="simple_threshold",
        )

        # Start position manager
        manager_task = None
        try:
            manager_task = asyncio.create_task(position_manager.run())
            await asyncio.sleep(0.05)

            # Publish fill event
            await position_manager._bus.publish(FILLS, fill_event)
            await asyncio.sleep(0.2)

            # Calculate unrealized PnL with current price > entry price (profit)
            current_prices: dict[tuple[str, Outcome], float] = {
                ("test-market", "UP"): 0.6
            }  # Current price > entry price
            unrealized_pnl = position_manager.calculate_unrealized_pnl(
                current_prices=current_prices
            )

            # Verify unrealized PnL metric was emitted
            # Expected: (0.6 - 0.5) * 100 = 10.0
            assert metrics_collector.get_gauge("pnl_unrealized") == pytest.approx(10.0)

            # Verify calculation is correct
            assert unrealized_pnl == pytest.approx(10.0)
        finally:
            if manager_task:
                position_manager.stop()
                manager_task.cancel()
                try:
                    await manager_task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_unrealized_pnl_updates_on_price_change(
        self,
        position_manager: PaperPositionManager,
        order_store: InMemoryOrderStore,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that unrealized PnL metric updates when price changes."""
        # Create BUY order
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=100.0,
            limit_price=0.5,
            target_price=0.5,
            reason="Test order",
            correlation_id="corr-123",
            strategy_id="simple_threshold",
        )
        order = await order_store.create_order(intent, "client-123")

        # Create fill event
        fill_event = FillEvent(
            order_id=order.order_id,
            fill_id="fill-123",
            size=100.0,
            price=0.5,  # Entry price
            fee=0.0,
            correlation_id="corr-123",
            strategy_id="simple_threshold",
        )

        # Start position manager
        manager_task = None
        try:
            manager_task = asyncio.create_task(position_manager.run())
            await asyncio.sleep(0.05)

            # Publish fill event
            await position_manager._bus.publish(FILLS, fill_event)
            await asyncio.sleep(0.2)

            # Update price via market data event (price increases)
            md_event = MarketDataEvent(
                market_slug="test-market",
                outcome="UP",
                best_bid=0.59,
                best_ask=0.61,
                correlation_id="corr-md-1",
            )
            await position_manager._bus.publish(MARKET_DATA, md_event)
            await asyncio.sleep(0.2)

            # Calculate unrealized PnL (should use latest market price)
            # This will emit the metric
            position_manager.calculate_unrealized_pnl()

            # Verify metric was updated
            # Expected: (0.6 - 0.5) * 100 = 10.0 (using mid price from market data)
            assert metrics_collector.get_gauge("pnl_unrealized") == pytest.approx(10.0)
        finally:
            if manager_task:
                position_manager.stop()
                manager_task.cancel()
                try:
                    await manager_task
                except asyncio.CancelledError:
                    pass
