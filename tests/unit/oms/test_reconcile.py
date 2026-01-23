"""Tests for OMS reconciliation service.

Per Phase 6 Commit 5: Test ReconciliationService functionality including:
- No divergence detection
- Phantom order detection
- Orphan order detection
- Fill mismatch detection
- Multiple divergences
- Error handling
"""

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from polytrader.events import RECONCILE
from polytrader.events.bus import EventBus
from polytrader.events.types import OrderIntentEvent
from polytrader.oms.fsm import transition_order_state
from polytrader.oms.models import OrderState
from polytrader.oms.reconcile import ReconciliationService
from polytrader.oms.store import InMemoryOrderStore


class FakeVenueAdapter:
    """Fake venue adapter for testing."""

    def __init__(self, orders: list[dict[str, Any]] | None = None) -> None:
        self._orders = orders or []

    async def get_open_orders(
        self,
        market_slug: str | None = None,
        token_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get fake open orders."""
        return self._orders

    async def submit_order(self, client_order_id: str, intent: OrderIntentEvent) -> Any:
        """Not used in reconciliation tests."""
        raise NotImplementedError

    async def cancel_order(self, client_order_id: str, venue_order_id: str) -> Any:
        """Not used in reconciliation tests."""
        raise NotImplementedError


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def store(bus: EventBus) -> InMemoryOrderStore:
    return InMemoryOrderStore(bus)


@pytest.fixture
def venue_adapter() -> FakeVenueAdapter:
    return FakeVenueAdapter()


@pytest.fixture
def reconcile_service(
    store: InMemoryOrderStore, venue_adapter: FakeVenueAdapter, bus: EventBus
) -> ReconciliationService:
    return ReconciliationService(store=store, venue_adapter=venue_adapter, bus=bus)


class TestReconciliationService:
    @pytest.mark.asyncio
    async def test_reconcile_no_divergence(
        self,
        reconcile_service: ReconciliationService,
        store: InMemoryOrderStore,
        venue_adapter: FakeVenueAdapter,
        bus: EventBus,
    ) -> None:
        """Test reconciliation with no divergences."""
        # Create an order in OMS
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
            strategy_id="simple_threshold",
        )
        order = await store.create_order(intent, "client-123")
        # Simulate order being submitted and acked with venue_order_id
        order = transition_order_state(order, OrderState.PENDING_SUBMIT)
        store.update_order(order)
        order = transition_order_state(order, OrderState.SUBMITTED)
        store.update_order(order)
        order = transition_order_state(order, OrderState.ACKED)
        order = order.model_copy(update={"venue_order_id": "venue-456"})
        store.update_order(order)

        # Create matching venue order
        venue_adapter._orders = [
            {
                "order_id": "venue-456",
                "token_id": "token-123",
                "status": "OPEN",
                "side": "BUY",
                "size": 1.0,
            }
        ]

        reconcile_queue = bus.subscribe(RECONCILE)
        events = await reconcile_service.reconcile()

        # Should have no divergence events
        assert len(events) == 0

        # Check that no events were published
        try:
            await asyncio.wait_for(reconcile_queue.get(), timeout=0.1)
            raise AssertionError("Should not have published any reconcile events")
        except TimeoutError:
            pass

    @pytest.mark.asyncio
    async def test_reconcile_phantom_order(
        self,
        reconcile_service: ReconciliationService,
        store: InMemoryOrderStore,
        venue_adapter: FakeVenueAdapter,
        bus: EventBus,
    ) -> None:
        """Test detection of phantom order (OMS has order, venue doesn't)."""
        # Create an order in OMS with venue_order_id
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
            strategy_id="simple_threshold",
        )
        order = await store.create_order(intent, "client-123")
        # Simulate order being submitted and acked with venue_order_id
        order = transition_order_state(order, OrderState.PENDING_SUBMIT)
        store.update_order(order)
        order = transition_order_state(order, OrderState.SUBMITTED)
        store.update_order(order)
        order = transition_order_state(order, OrderState.ACKED)
        order = order.model_copy(update={"venue_order_id": "venue-456"})
        store.update_order(order)

        # Venue has no orders
        venue_adapter._orders = []

        reconcile_queue = bus.subscribe(RECONCILE)
        events = await reconcile_service.reconcile()

        # Should detect phantom order
        assert len(events) == 1
        event = events[0]
        assert event.divergence_type == "phantom_order"
        assert event.order_id == order.order_id
        assert event.venue_order_id == "venue-456"
        assert event.severity == "WARNING"
        assert "oms_state" in event.details

        # Check that event was published
        published_event = await asyncio.wait_for(reconcile_queue.get(), timeout=1.0)
        assert published_event == event

    @pytest.mark.asyncio
    async def test_reconcile_orphan_order(
        self,
        reconcile_service: ReconciliationService,
        store: InMemoryOrderStore,
        venue_adapter: FakeVenueAdapter,
        bus: EventBus,
    ) -> None:
        """Test detection of orphan order (venue has order, OMS doesn't)."""
        # OMS has no orders
        # Venue has an order we don't know about
        venue_adapter._orders = [
            {
                "order_id": "venue-789",
                "token_id": "token-123",
                "status": "OPEN",
                "side": "BUY",
                "size": 1.0,
            }
        ]

        reconcile_queue = bus.subscribe(RECONCILE)
        events = await reconcile_service.reconcile()

        # Should detect orphan order
        assert len(events) == 1
        event = events[0]
        assert event.divergence_type == "orphan_order"
        assert event.venue_order_id == "venue-789"
        assert event.order_id is None
        assert event.severity == "WARNING"
        assert "venue_status" in event.details

        # Check that event was published
        published_event = await asyncio.wait_for(reconcile_queue.get(), timeout=1.0)
        assert published_event == event

    @pytest.mark.asyncio
    async def test_reconcile_fill_mismatch_venue_filled(
        self,
        reconcile_service: ReconciliationService,
        store: InMemoryOrderStore,
        venue_adapter: FakeVenueAdapter,
        bus: EventBus,
    ) -> None:
        """Test detection of fill mismatch (venue says FILLED, OMS doesn't)."""
        # Create an order in OMS that's not filled
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
            strategy_id="simple_threshold",
        )
        order = await store.create_order(intent, "client-123")
        # Simulate order being submitted and acked with venue_order_id
        order = transition_order_state(order, OrderState.PENDING_SUBMIT)
        store.update_order(order)
        order = transition_order_state(order, OrderState.SUBMITTED)
        store.update_order(order)
        order = transition_order_state(order, OrderState.ACKED)
        order = order.model_copy(update={"venue_order_id": "venue-456"})
        store.update_order(order)

        # Venue says order is FILLED
        venue_adapter._orders = [
            {
                "order_id": "venue-456",
                "token_id": "token-123",
                "status": "FILLED",
                "side": "BUY",
                "size": 1.0,
            }
        ]

        reconcile_queue = bus.subscribe(RECONCILE)
        events = await reconcile_service.reconcile()

        # Should detect fill mismatch
        assert len(events) == 1
        event = events[0]
        assert event.divergence_type == "fill_mismatch"
        assert event.order_id == order.order_id
        assert event.venue_order_id == "venue-456"
        assert event.severity == "ERROR"
        assert event.details["venue_status"] == "FILLED"
        assert event.details["oms_state"] == "ACKED"

        # Check that event was published
        published_event = await asyncio.wait_for(reconcile_queue.get(), timeout=1.0)
        assert published_event == event

    @pytest.mark.asyncio
    async def test_reconcile_fill_mismatch_venue_open_oms_has_fills(
        self,
        reconcile_service: ReconciliationService,
        store: InMemoryOrderStore,
        venue_adapter: FakeVenueAdapter,
        bus: EventBus,
    ) -> None:
        """Test detection of fill mismatch (venue says OPEN, OMS has fills)."""
        # Create an order in OMS with fills
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
            strategy_id="simple_threshold",
        )
        order = await store.create_order(intent, "client-123")
        # Simulate order being submitted, acked, and partially filled
        order = transition_order_state(order, OrderState.PENDING_SUBMIT)
        store.update_order(order)
        order = transition_order_state(order, OrderState.SUBMITTED)
        store.update_order(order)
        order = transition_order_state(order, OrderState.ACKED)
        store.update_order(order)
        order = transition_order_state(order, OrderState.PARTIALLY_FILLED)
        order = order.model_copy(update={"venue_order_id": "venue-456", "filled_size": 0.5})
        store.update_order(order)

        # Venue says order is OPEN
        venue_adapter._orders = [
            {
                "order_id": "venue-456",
                "token_id": "token-123",
                "status": "OPEN",
                "side": "BUY",
                "size": 1.0,
            }
        ]

        reconcile_queue = bus.subscribe(RECONCILE)
        events = await reconcile_service.reconcile()

        # Should detect fill mismatch (WARNING severity)
        assert len(events) == 1
        event = events[0]
        assert event.divergence_type == "fill_mismatch"
        assert event.order_id == order.order_id
        assert event.venue_order_id == "venue-456"
        assert event.severity == "WARNING"
        assert event.details["venue_status"] == "OPEN"
        assert event.details["oms_filled_size"] == 0.5

        # Check that event was published
        published_event = await asyncio.wait_for(reconcile_queue.get(), timeout=1.0)
        assert published_event == event

    @pytest.mark.asyncio
    async def test_reconcile_multiple_divergences(
        self,
        reconcile_service: ReconciliationService,
        store: InMemoryOrderStore,
        venue_adapter: FakeVenueAdapter,
        bus: EventBus,
    ) -> None:
        """Test detection of multiple divergences."""
        # Create two orders in OMS
        intent1 = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
            strategy_id="simple_threshold",
        )
        order1 = await store.create_order(intent1, "client-123")
        # Simulate order1 being submitted and acked
        order1 = transition_order_state(order1, OrderState.PENDING_SUBMIT)
        store.update_order(order1)
        order1 = transition_order_state(order1, OrderState.SUBMITTED)
        store.update_order(order1)
        order1 = transition_order_state(order1, OrderState.ACKED)
        order1 = order1.model_copy(update={"venue_order_id": "venue-456"})
        store.update_order(order1)

        intent2 = OrderIntentEvent(
            market_slug="test-market",
            outcome="DOWN",
            side="SELL",
            size=2.0,
            target_price=0.45,
            limit_price=0.45,
            reason="Test",
            ttl_s=60.0,
            strategy_id="simple_threshold",
        )
        order2 = await store.create_order(intent2, "client-789")
        # Simulate order2 being submitted and acked
        order2 = transition_order_state(order2, OrderState.PENDING_SUBMIT)
        store.update_order(order2)
        order2 = transition_order_state(order2, OrderState.SUBMITTED)
        store.update_order(order2)
        order2 = transition_order_state(order2, OrderState.ACKED)
        order2 = order2.model_copy(update={"venue_order_id": "venue-999"})
        store.update_order(order2)

        # Venue has one order (orphan) and is missing one OMS order (phantom)
        venue_adapter._orders = [
            {
                "order_id": "venue-999",  # Matches order2
                "token_id": "token-123",
                "status": "FILLED",  # But OMS says ACKED (fill mismatch)
                "side": "SELL",
                "size": 2.0,
            },
            {
                "order_id": "venue-orphan",  # Orphan order
                "token_id": "token-456",
                "status": "OPEN",
                "side": "BUY",
                "size": 0.5,
            },
        ]

        reconcile_queue = bus.subscribe(RECONCILE)
        events = await reconcile_service.reconcile()

        # Should detect:
        # 1. Phantom order (order1 not in venue)
        # 2. Fill mismatch (order2: venue FILLED, OMS ACKED)
        # 3. Orphan order (venue-orphan)
        assert len(events) == 3

        # Check phantom order
        phantom_event = next(e for e in events if e.divergence_type == "phantom_order")
        assert phantom_event.order_id == order1.order_id

        # Check fill mismatch
        fill_mismatch_event = next(e for e in events if e.divergence_type == "fill_mismatch")
        assert fill_mismatch_event.order_id == order2.order_id
        assert fill_mismatch_event.severity == "ERROR"

        # Check orphan order
        orphan_event = next(e for e in events if e.divergence_type == "orphan_order")
        assert orphan_event.venue_order_id == "venue-orphan"

        # Check that all events were published
        published_events = []
        for _ in range(3):
            published_events.append(await asyncio.wait_for(reconcile_queue.get(), timeout=1.0))
        assert len(published_events) == 3

    @pytest.mark.asyncio
    async def test_reconcile_fetch_error(
        self,
        reconcile_service: ReconciliationService,
        store: InMemoryOrderStore,
        venue_adapter: FakeVenueAdapter,
        bus: EventBus,
    ) -> None:
        """Test error handling when venue fetch fails."""

        # Make venue adapter raise an error
        async def failing_get_open_orders(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            raise Exception("Network error")

        reconcile_queue = bus.subscribe(RECONCILE)
        with patch.object(venue_adapter, "get_open_orders", side_effect=failing_get_open_orders):
            events = await reconcile_service.reconcile()

        # Should emit error-level ReconcileEvent
        assert len(events) == 1
        event = events[0]
        assert event.divergence_type == "none"
        assert event.severity == "ERROR"
        assert "error" in event.details
        assert event.details["error"] == "Failed to fetch venue orders"

        # Check that event was published
        published_event = await asyncio.wait_for(reconcile_queue.get(), timeout=1.0)
        assert published_event == event

    @pytest.mark.asyncio
    async def test_reconcile_ignores_orders_without_venue_id(
        self,
        reconcile_service: ReconciliationService,
        store: InMemoryOrderStore,
        venue_adapter: FakeVenueAdapter,
        bus: EventBus,
    ) -> None:
        """Test that orders without venue_order_id are ignored in comparison."""
        # Create an order in OMS without venue_order_id
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
            strategy_id="simple_threshold",
        )
        order = await store.create_order(intent, "client-123")
        # Order is in SUBMITTED state, no venue_order_id yet
        assert order.venue_order_id is None

        # Venue has no orders
        venue_adapter._orders = []

        reconcile_queue = bus.subscribe(RECONCILE)
        events = await reconcile_service.reconcile()

        # Should not detect phantom order (order has no venue_order_id)
        # Should have no divergence events
        assert len(events) == 0

        # Check that no events were published
        try:
            await asyncio.wait_for(reconcile_queue.get(), timeout=0.1)
            raise AssertionError("Should not have published any reconcile events")
        except TimeoutError:
            pass
