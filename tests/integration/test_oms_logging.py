"""Integration tests for structured logging in OMS core.

Per Commit 6: Enforce structured logging in OMS core.
Per observability.mdc §2: Every log line must include correlation_id when applicable.
"""

from unittest.mock import MagicMock, patch

import pytest

from polytrader.events.bus import EventBus
from polytrader.events.store import MemoryEventStore
from polytrader.events.types import OrderIntentEvent
from polytrader.oms.core import OMSCore
from polytrader.oms.idempotency import IdempotencyStore
from polytrader.oms.store import InMemoryOrderStore


@pytest.fixture
def bus() -> EventBus:
    """Create an event bus for testing."""
    return EventBus(store=MemoryEventStore())


@pytest.fixture
def store(bus: EventBus) -> InMemoryOrderStore:
    """Create an order store for testing."""
    return InMemoryOrderStore(bus)


@pytest.fixture
def oms_core(bus: EventBus, store: InMemoryOrderStore) -> OMSCore:
    """Create an OMS core instance for testing."""
    idempotency_store = IdempotencyStore()
    return OMSCore(bus=bus, store=store, idempotency_store=idempotency_store)


@pytest.fixture
def sample_intent() -> OrderIntentEvent:
    """Create a sample order intent for testing."""
    return OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        size=100.0,
        target_price=0.55,
        limit_price=0.55,
        reason="Test intent",
        ttl_s=60.0,
    )


class TestOMSStructuredLogging:
    """Tests for structured logging with correlation_id in OMS core."""

    @pytest.mark.asyncio
    @patch("polytrader.oms.core.logger")
    async def test_create_order_logs_correlation_id(
        self, mock_logger: MagicMock, oms_core: OMSCore, sample_intent: OrderIntentEvent
    ) -> None:
        """Test that create_order logs include correlation_id and event_type."""
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        order = await oms_core.create_order(sample_intent)

        # Verify bind_order_context was called (via bind)
        assert mock_logger.bind.called

        # Get the last call (for the OrderCreated log)
        call_args = mock_logger.bind.call_args_list
        order_created_call = None
        for call in call_args:
            kwargs = call.kwargs
            if kwargs.get("event_type") == "OrderCreated":
                order_created_call = kwargs
                break

        assert order_created_call is not None, "OrderCreated log not found"

        # Verify required fields per observability.mdc §2, §3
        assert "correlation_id" in order_created_call
        assert order_created_call["correlation_id"] == sample_intent.correlation_id
        assert "order_id" in order_created_call
        assert order_created_call["order_id"] == order.order_id
        assert "client_order_id" in order_created_call
        assert "market_slug" in order_created_call
        assert order_created_call["market_slug"] == "test-market"
        assert "event_type" in order_created_call
        assert order_created_call["event_type"] == "OrderCreated"
        assert "latency_ms" in order_created_call

        # Verify info was called
        mock_bound_logger.info.assert_called()

    @pytest.mark.asyncio
    @patch("polytrader.oms.core.logger")
    async def test_handle_venue_ack_logs_correlation_id(
        self,
        mock_logger: MagicMock,
        oms_core: OMSCore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that handle_venue_ack logs include correlation_id and event_type."""
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        # Create order first
        order = await oms_core.create_order(sample_intent)

        # Clear previous bind calls
        mock_logger.bind.reset_mock()
        mock_bound_logger.reset_mock()

        # Handle venue ack
        await oms_core.handle_venue_ack(order.client_order_id, "venue-123")

        # Verify bind_order_context was called
        assert mock_logger.bind.called

        call_kwargs = mock_logger.bind.call_args.kwargs

        # Verify required fields per observability.mdc §2, §3
        assert "correlation_id" in call_kwargs
        assert call_kwargs["correlation_id"] == order.correlation_id
        assert "order_id" in call_kwargs
        assert call_kwargs["order_id"] == order.order_id
        assert "client_order_id" in call_kwargs
        assert "venue_order_id" in call_kwargs
        assert call_kwargs["venue_order_id"] == "venue-123"
        assert "market_slug" in call_kwargs
        assert "event_type" in call_kwargs
        assert call_kwargs["event_type"] == "OrderAcked"
        assert "latency_ms" in call_kwargs

        # Verify info was called
        mock_bound_logger.info.assert_called()

    @pytest.mark.asyncio
    @patch("polytrader.oms.core.logger")
    async def test_handle_venue_reject_logs_correlation_id(
        self,
        mock_logger: MagicMock,
        oms_core: OMSCore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that handle_venue_reject logs include correlation_id and event_type."""
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        # Create order first
        order = await oms_core.create_order(sample_intent)

        # Clear previous bind calls
        mock_logger.bind.reset_mock()
        mock_bound_logger.reset_mock()

        # Handle venue reject
        await oms_core.handle_venue_reject(order.client_order_id, "Insufficient funds")

        # Verify bind_order_context was called
        assert mock_logger.bind.called

        call_kwargs = mock_logger.bind.call_args.kwargs

        # Verify required fields per observability.mdc §2, §3
        assert "correlation_id" in call_kwargs
        assert call_kwargs["correlation_id"] == order.correlation_id
        assert "order_id" in call_kwargs
        assert "client_order_id" in call_kwargs
        assert "market_slug" in call_kwargs
        assert "event_type" in call_kwargs
        assert call_kwargs["event_type"] == "OrderRejected"
        assert "reason" in call_kwargs
        assert "latency_ms" in call_kwargs
        assert "error_class" in call_kwargs

        # Verify warning was called
        mock_bound_logger.warning.assert_called()

    @pytest.mark.asyncio
    @patch("polytrader.oms.core.logger")
    async def test_handle_fill_logs_correlation_id(
        self,
        mock_logger: MagicMock,
        oms_core: OMSCore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that handle_fill logs include correlation_id and event_type."""
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        # Create order first
        order = await oms_core.create_order(sample_intent)

        # Clear previous bind calls
        mock_logger.bind.reset_mock()
        mock_bound_logger.reset_mock()

        # Handle fill
        await oms_core.handle_fill(
            order.client_order_id, size=50.0, price=0.55, fee=0.5, venue_fill_id="fill-123"
        )

        # Verify bind_order_context was called
        assert mock_logger.bind.called

        call_kwargs = mock_logger.bind.call_args.kwargs

        # Verify required fields per observability.mdc §2, §3
        assert "correlation_id" in call_kwargs
        assert call_kwargs["correlation_id"] == order.correlation_id
        assert "order_id" in call_kwargs
        assert "client_order_id" in call_kwargs
        assert "venue_order_id" in call_kwargs
        assert "market_slug" in call_kwargs
        assert "event_type" in call_kwargs
        assert call_kwargs["event_type"] == "OrderFilled"
        assert "fill_size" in call_kwargs
        assert "fill_price" in call_kwargs
        assert "fee" in call_kwargs
        assert "latency_ms" in call_kwargs

        # Verify info was called
        mock_bound_logger.info.assert_called()

    @pytest.mark.asyncio
    @patch("polytrader.oms.core.logger")
    async def test_handle_cancel_logs_correlation_id(
        self,
        mock_logger: MagicMock,
        oms_core: OMSCore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that handle_cancel logs include correlation_id and event_type."""
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        # Create order first
        order = await oms_core.create_order(sample_intent)

        # Ack the order first (required for cancel transition: SUBMITTED → ACKED → CANCELLED)
        await oms_core.handle_venue_ack(order.client_order_id, "venue-123")

        # Clear previous bind calls
        mock_logger.bind.reset_mock()
        mock_bound_logger.reset_mock()

        # Handle cancel
        await oms_core.handle_cancel(order.client_order_id, reason="User requested")

        # Verify bind_order_context was called
        assert mock_logger.bind.called

        call_kwargs = mock_logger.bind.call_args.kwargs

        # Verify required fields per observability.mdc §2, §3
        assert "correlation_id" in call_kwargs
        assert call_kwargs["correlation_id"] == order.correlation_id
        assert "order_id" in call_kwargs
        assert "client_order_id" in call_kwargs
        assert "venue_order_id" in call_kwargs
        assert "market_slug" in call_kwargs
        assert "event_type" in call_kwargs
        assert call_kwargs["event_type"] == "OrderCanceled"
        assert "reason" in call_kwargs
        assert "latency_ms" in call_kwargs

        # Verify info was called
        mock_bound_logger.info.assert_called()

    @pytest.mark.asyncio
    @patch("polytrader.oms.core.logger")
    async def test_error_logs_include_event_type_when_order_not_found(
        self, mock_logger: MagicMock, oms_core: OMSCore
    ) -> None:
        """Test that error logs include event_type even when order not found."""
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        # Try to handle ack for non-existent order
        with pytest.raises(ValueError, match="Order not found"):
            await oms_core.handle_venue_ack("nonexistent-client-id", "venue-123")

        # Verify bind_correlation_context was called (not bind_order_context)
        assert mock_logger.bind.called

        call_kwargs = mock_logger.bind.call_args.kwargs

        # Verify required fields per observability.mdc §2, §3
        assert "client_order_id" in call_kwargs
        assert call_kwargs["client_order_id"] == "nonexistent-client-id"
        assert "event_type" in call_kwargs
        assert call_kwargs["event_type"] == "OrderAckFailed"
        assert "error_class" in call_kwargs

        # Verify error was called
        mock_bound_logger.error.assert_called()

    @pytest.mark.asyncio
    @patch("polytrader.oms.core.logger")
    async def test_duplicate_order_logs_correlation_id(
        self,
        mock_logger: MagicMock,
        oms_core: OMSCore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that duplicate order detection logs include correlation_id."""
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger

        # Create order first
        order1 = await oms_core.create_order(sample_intent)

        # Clear previous bind calls
        mock_logger.bind.reset_mock()
        mock_bound_logger.reset_mock()

        # Try to create duplicate order (same intent)
        order2 = await oms_core.create_order(sample_intent)

        # Should return existing order
        assert order2.order_id == order1.order_id

        # Verify bind_order_context was called for duplicate detection
        assert mock_logger.bind.called

        # Find the OrderDuplicate log call
        duplicate_call = None
        for call in mock_logger.bind.call_args_list:
            kwargs = call.kwargs
            if kwargs.get("event_type") == "OrderDuplicate":
                duplicate_call = kwargs
                break

        assert duplicate_call is not None, "OrderDuplicate log not found"

        # Verify required fields
        assert "correlation_id" in duplicate_call
        assert duplicate_call["correlation_id"] == sample_intent.correlation_id
        assert "order_id" in duplicate_call
        assert "client_order_id" in duplicate_call
        assert "event_type" in duplicate_call
        assert duplicate_call["event_type"] == "OrderDuplicate"

        # Verify debug was called
        mock_bound_logger.debug.assert_called()
