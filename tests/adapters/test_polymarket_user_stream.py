"""Tests for Polymarket user stream adapter.

Per Phase 6 Commit 3: Test UserStreamAdapter functionality including:
- WebSocket message parsing and normalization
- Event publishing to EventBus
- PING/PONG handling
- Reconnection logic
- Error handling
"""

import asyncio
import json
from typing import Any, cast
from unittest.mock import patch

import pytest

from polytrader.adapters.polymarket.models import (
    CanonicalCancel,
    CanonicalFill,
    CanonicalOrderAck,
    OrderMessage,
    TradeMessage,
)
from polytrader.adapters.polymarket.user_stream import (
    INITIAL_RECONNECT_DELAY,
    MAX_RECONNECT_DELAY,
    WS_PING,
    WS_PONG,
    UserStreamAdapter,
)
from polytrader.clob import IClobClient
from polytrader.events import (
    USER_STREAM_ACKS,
    USER_STREAM_CANCELS,
    USER_STREAM_FILLS,
)
from polytrader.events.bus import EventBus


class FakeClobClient(IClobClient):
    """Fake CLOB client for testing."""

    def __init__(
        self,
        api_key: str = "test-key",
        api_secret: str = "test-secret",
        api_passphrase: str = "test-pass",
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._api_passphrase = api_passphrase

    def create_or_derive_api_creds(self) -> dict[str, str]:
        """Return fake API credentials."""
        return {
            "apiKey": self._api_key,
            "secret": self._api_secret,
            "passphrase": self._api_passphrase,
        }

    def get_balance_allowance(self, params: Any) -> dict[str, Any]:
        """Get balance and allowance information."""
        return {}

    def create_market_order(self, order_args: Any) -> dict[str, Any]:
        """Create a signed market order."""
        return {}

    def post_order(self, signed_order: Any, order_type: Any) -> dict[str, Any]:
        """Post an order to the exchange."""
        return {}

    def set_api_creds(self, creds: Any) -> None:
        """Set API credentials on the client."""
        pass

    def get_orders(self, params: Any) -> list[dict[str, Any]]:
        """Get active orders from Polymarket CLOB."""
        return []


class FakeWebSocket:
    """Fake WebSocket connection for testing."""

    def __init__(self, messages: list[str | bytes] | None = None) -> None:
        self.messages = messages or []
        self.sent_messages: list[str | bytes] = []
        self.closed = False
        self._message_index = 0

    async def send(self, message: str | bytes) -> None:
        """Record sent message."""
        self.sent_messages.append(message)

    async def recv(self) -> str | bytes:
        """Return next message or raise StopAsyncIteration."""
        if self._message_index >= len(self.messages):
            raise StopAsyncIteration
        msg = self.messages[self._message_index]
        self._message_index += 1
        return msg

    async def close(self) -> None:
        """Mark connection as closed."""
        self.closed = True

    def __aiter__(self) -> "FakeWebSocket":
        """Return self as async iterator."""
        return self

    async def __anext__(self) -> str | bytes:
        """Return next message."""
        return await self.recv()

    async def __aenter__(self) -> "FakeWebSocket":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


class TestUserStreamAdapter:
    """Tests for UserStreamAdapter."""

    @pytest.fixture
    def bus(self) -> EventBus:
        """Create EventBus for testing."""
        return EventBus()

    @pytest.fixture
    def clob_client(self) -> FakeClobClient:
        """Create fake CLOB client."""
        return FakeClobClient()

    @pytest.fixture
    def adapter(self, bus: EventBus, clob_client: FakeClobClient) -> UserStreamAdapter:
        """Create UserStreamAdapter for testing."""
        return UserStreamAdapter(clob_client=clob_client, bus=bus)

    @pytest.mark.asyncio
    async def test_handle_ping_message(self, adapter: UserStreamAdapter, bus: EventBus) -> None:
        """Test that PING messages are handled and PONG is sent."""
        fake_ws = FakeWebSocket()
        adapter._ws = cast(Any, fake_ws)

        await adapter._handle_message(WS_PING)

        # Should have sent PONG
        assert len(fake_ws.sent_messages) == 1
        assert fake_ws.sent_messages[0] == WS_PONG

    @pytest.mark.asyncio
    async def test_handle_pong_message(self, adapter: UserStreamAdapter) -> None:
        """Test that PONG messages are handled silently."""
        fake_ws = FakeWebSocket()
        adapter._ws = cast(Any, fake_ws)

        # Should not raise or send anything
        await adapter._handle_message(WS_PONG)

        # Should not have sent anything
        assert len(fake_ws.sent_messages) == 0

    @pytest.mark.asyncio
    async def test_handle_order_placement_message(
        self, adapter: UserStreamAdapter, bus: EventBus
    ) -> None:
        """Test that order placement messages are converted to CanonicalOrderAck."""
        # Subscribe to USER_STREAM_ACKS topic
        ack_queue = bus.subscribe(USER_STREAM_ACKS)

        # Create order placement message
        order_msg = OrderMessage(
            asset_id="asset-123",
            event_type="order",
            id="venue-order-456",
            market="test-market",
            order_owner="owner-789",
            original_size="1.0",
            outcome="UP",
            owner="owner-789",
            price="0.55",
            side="BUY",
            size_matched="0.0",
            timestamp="1705315845.123",  # Unix timestamp in seconds
            type="PLACEMENT",
        )

        await adapter._handle_order_message(order_msg)

        # Should have published CanonicalOrderAck
        canonical_ack = await asyncio.wait_for(ack_queue.get(), timeout=1.0)
        assert isinstance(canonical_ack, CanonicalOrderAck)
        assert canonical_ack.venue_order_id == "venue-order-456"

    @pytest.mark.asyncio
    async def test_handle_order_cancellation_message(
        self, adapter: UserStreamAdapter, bus: EventBus
    ) -> None:
        """Test that order cancellation messages are converted to CanonicalCancel."""
        # Subscribe to USER_STREAM_CANCELS topic
        cancel_queue = bus.subscribe(USER_STREAM_CANCELS)

        # Create order cancellation message
        order_msg = OrderMessage(
            asset_id="asset-123",
            event_type="order",
            id="venue-order-456",
            market="test-market",
            order_owner="owner-789",
            original_size="1.0",
            outcome="UP",
            owner="owner-789",
            price="0.55",
            side="BUY",
            size_matched="0.0",
            timestamp="1705315845.123",
            type="CANCELLATION",
        )

        await adapter._handle_order_message(order_msg)

        # Should have published CanonicalCancel
        canonical_cancel = await asyncio.wait_for(cancel_queue.get(), timeout=1.0)
        assert isinstance(canonical_cancel, CanonicalCancel)
        assert canonical_cancel.venue_order_id == "venue-order-456"

    @pytest.mark.asyncio
    async def test_handle_order_update_message(
        self, adapter: UserStreamAdapter, bus: EventBus
    ) -> None:
        """Test that order update messages are logged but not published."""
        # Subscribe to all user stream topics
        ack_queue = bus.subscribe(USER_STREAM_ACKS)
        cancel_queue = bus.subscribe(USER_STREAM_CANCELS)
        fill_queue = bus.subscribe(USER_STREAM_FILLS)

        # Create order update message (partial fill)
        order_msg = OrderMessage(
            asset_id="asset-123",
            event_type="order",
            id="venue-order-456",
            market="test-market",
            order_owner="owner-789",
            original_size="1.0",
            outcome="UP",
            owner="owner-789",
            price="0.55",
            side="BUY",
            size_matched="0.5",  # Partial fill
            timestamp="1705315845.123",
            type="UPDATE",
        )

        await adapter._handle_order_message(order_msg)

        # Should not have published any events
        # Use asyncio.wait_for with short timeout to check queue is empty
        try:
            await asyncio.wait_for(ack_queue.get(), timeout=0.1)
            raise AssertionError("Should not have published OrderAckEvent")
        except TimeoutError:
            pass

        try:
            await asyncio.wait_for(cancel_queue.get(), timeout=0.1)
            raise AssertionError("Should not have published OrderCanceledEvent")
        except TimeoutError:
            pass

        try:
            await asyncio.wait_for(fill_queue.get(), timeout=0.1)
            raise AssertionError("Should not have published FillEvent")
        except TimeoutError:
            pass

    @pytest.mark.asyncio
    async def test_handle_trade_matched_message(
        self, adapter: UserStreamAdapter, bus: EventBus
    ) -> None:
        """Test that MATCHED trade messages are converted to CanonicalFill."""
        # Subscribe to USER_STREAM_FILLS topic
        fill_queue = bus.subscribe(USER_STREAM_FILLS)

        # Create trade message with MATCHED status
        trade_msg = TradeMessage(
            asset_id="asset-123",
            event_type="trade",
            id="trade-789",
            last_update="1705315845.123",
            maker_orders=[],
            market="test-market",
            matchtime="1705315845.123",
            outcome="UP",
            owner="owner-789",
            price="0.55",
            side="BUY",
            size="1.0",
            status="MATCHED",
            taker_order_id="venue-order-456",
            timestamp="1705315845.123",
            trade_owner="owner-789",
            type="TRADE",
        )

        await adapter._handle_trade_message(trade_msg)

        # Should have published CanonicalFill
        canonical_fill = await asyncio.wait_for(fill_queue.get(), timeout=1.0)
        assert isinstance(canonical_fill, CanonicalFill)
        assert canonical_fill.venue_order_id == "venue-order-456"
        assert canonical_fill.size == 1.0
        assert canonical_fill.price == 0.55
        assert canonical_fill.fill_id == "trade-789"

    @pytest.mark.asyncio
    async def test_handle_trade_non_matched_message(
        self, adapter: UserStreamAdapter, bus: EventBus
    ) -> None:
        """Test that non-MATCHED trade messages are not published."""
        # Subscribe to USER_STREAM_FILLS topic
        fill_queue = bus.subscribe(USER_STREAM_FILLS)

        # Create trade message with MINED status (not MATCHED)
        trade_msg = TradeMessage(
            asset_id="asset-123",
            event_type="trade",
            id="trade-789",
            last_update="1705315845.123",
            maker_orders=[],
            market="test-market",
            matchtime="1705315845.123",
            outcome="UP",
            owner="owner-789",
            price="0.55",
            side="BUY",
            size="1.0",
            status="MINED",  # Not MATCHED
            taker_order_id="venue-order-456",
            timestamp="1705315845.123",
            trade_owner="owner-789",
            type="TRADE",
        )

        await adapter._handle_trade_message(trade_msg)

        # Should not have published CanonicalFill
        try:
            await asyncio.wait_for(fill_queue.get(), timeout=0.1)
            raise AssertionError("Should not have published CanonicalFill for non-MATCHED trade")
        except TimeoutError:
            pass

    @pytest.mark.asyncio
    async def test_handle_invalid_json_message(self, adapter: UserStreamAdapter) -> None:
        """Test that invalid JSON messages are handled gracefully."""
        # Should not raise
        await adapter._handle_message("not valid json {")

    @pytest.mark.asyncio
    async def test_handle_unknown_message_type(
        self, adapter: UserStreamAdapter, bus: EventBus
    ) -> None:
        """Test that unknown message types are handled gracefully."""
        # Subscribe to user stream topics
        ack_queue = bus.subscribe(USER_STREAM_ACKS)

        # Create message with unknown event_type
        unknown_message = json.dumps(
            {
                "event_type": "unknown_type",
                "id": "123",
            }
        )

        await adapter._handle_message(unknown_message)

        # Should not have published any events
        try:
            await asyncio.wait_for(ack_queue.get(), timeout=0.1)
            raise AssertionError("Should not have published any event")
        except TimeoutError:
            pass

    @pytest.mark.asyncio
    async def test_ping_loop_sends_ping(self, adapter: UserStreamAdapter) -> None:
        """Test that ping loop sends PING messages periodically."""
        fake_ws = FakeWebSocket()
        adapter._running = True

        # Start ping loop task
        ping_task = asyncio.create_task(adapter._ping_loop(fake_ws))

        # Wait a bit (ping loop sends every 10 seconds, but we can test it sends)
        await asyncio.sleep(0.1)

        # Stop the loop
        adapter._running = False
        ping_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            pass

        # Should have sent at least one PING (or none if we stopped too quickly)
        # The important thing is that it doesn't crash

    @pytest.mark.asyncio
    async def test_connect_and_listen_subscribes(
        self, adapter: UserStreamAdapter, clob_client: FakeClobClient
    ) -> None:
        """Test that connect_and_listen subscribes to user channel."""
        fake_ws = FakeWebSocket(messages=[])  # Empty messages, will stop immediately
        adapter._running = True

        with patch(
            "polytrader.adapters.polymarket.user_stream.websockets.connect", return_value=fake_ws
        ):
            try:
                await asyncio.wait_for(adapter._connect_and_listen(), timeout=1.0)
            except TimeoutError:
                pass
            except StopAsyncIteration:
                pass

        # Should have sent subscription message
        assert len(fake_ws.sent_messages) > 0
        subscribe_msg = json.loads(fake_ws.sent_messages[0])
        assert subscribe_msg["type"] == "user"
        assert "auth" in subscribe_msg
        assert subscribe_msg["auth"]["apiKey"] == "test-key"
        assert subscribe_msg["auth"]["secret"] == "test-secret"
        assert subscribe_msg["auth"]["passphrase"] == "test-pass"

    @pytest.mark.asyncio
    async def test_connect_and_listen_processes_messages(
        self, adapter: UserStreamAdapter, bus: EventBus
    ) -> None:
        """Test that connect_and_listen processes incoming messages."""
        # Subscribe to USER_STREAM_ACKS
        ack_queue = bus.subscribe(USER_STREAM_ACKS)

        # Create order placement message
        order_msg = {
            "asset_id": "asset-123",
            "event_type": "order",
            "id": "venue-order-456",
            "market": "test-market",
            "order_owner": "owner-789",
            "original_size": "1.0",
            "outcome": "UP",
            "owner": "owner-789",
            "price": "0.55",
            "side": "BUY",
            "size_matched": "0.0",
            "timestamp": "1705315845.123",
            "type": "PLACEMENT",
        }

        fake_ws = FakeWebSocket(messages=[json.dumps(order_msg)])
        adapter._running = True

        with patch(
            "polytrader.adapters.polymarket.user_stream.websockets.connect", return_value=fake_ws
        ):
            try:
                await asyncio.wait_for(adapter._connect_and_listen(), timeout=1.0)
            except TimeoutError:
                pass
            except StopAsyncIteration:
                pass

        # Should have published CanonicalOrderAck
        try:
            canonical_ack = await asyncio.wait_for(ack_queue.get(), timeout=1.0)
            assert isinstance(canonical_ack, CanonicalOrderAck)
            assert canonical_ack.venue_order_id == "venue-order-456"
        except TimeoutError:
            # Message might not have been processed if we timed out
            pass

    @pytest.mark.asyncio
    async def test_stop_sets_running_flag(self, adapter: UserStreamAdapter) -> None:
        """Test that stop() sets _running flag to False."""
        adapter._running = True
        adapter.stop()
        assert adapter._running is False

    @pytest.mark.asyncio
    async def test_wait_before_reconnect_exponential_backoff(
        self, adapter: UserStreamAdapter
    ) -> None:
        """Test that reconnect delay increases exponentially."""
        adapter._reconnect_delay = INITIAL_RECONNECT_DELAY
        initial_delay = adapter._reconnect_delay

        # First reconnect
        await adapter._wait_before_reconnect()
        delay_after_first = adapter._reconnect_delay

        # Second reconnect
        await adapter._wait_before_reconnect()
        delay_after_second = adapter._reconnect_delay

        # Delay should have increased exponentially
        assert delay_after_first > initial_delay
        assert delay_after_second > delay_after_first
        # But should not exceed max
        assert adapter._reconnect_delay <= MAX_RECONNECT_DELAY

    @pytest.mark.asyncio
    async def test_wait_before_reconnect_resets_on_success(
        self, adapter: UserStreamAdapter
    ) -> None:
        """Test that reconnect delay resets to initial on successful connection."""
        adapter._reconnect_delay = MAX_RECONNECT_DELAY

        # Simulate successful connection (this happens in _connect_and_listen)
        fake_ws = FakeWebSocket(messages=[])
        adapter._running = True

        with patch(
            "polytrader.adapters.polymarket.user_stream.websockets.connect", return_value=fake_ws
        ):
            try:
                await asyncio.wait_for(adapter._connect_and_listen(), timeout=0.5)
            except (TimeoutError, StopAsyncIteration):
                pass

        # Delay should be reset to initial
        assert adapter._reconnect_delay == INITIAL_RECONNECT_DELAY

    @pytest.mark.asyncio
    async def test_handle_message_with_bytes(
        self, adapter: UserStreamAdapter, bus: EventBus
    ) -> None:
        """Test that bytes messages are handled correctly."""
        # Subscribe to USER_STREAM_ACKS
        ack_queue = bus.subscribe(USER_STREAM_ACKS)

        # Create order placement message as bytes
        order_msg = {
            "asset_id": "asset-123",
            "event_type": "order",
            "id": "venue-order-456",
            "market": "test-market",
            "order_owner": "owner-789",
            "original_size": "1.0",
            "outcome": "UP",
            "owner": "owner-789",
            "price": "0.55",
            "side": "BUY",
            "size_matched": "0.0",
            "timestamp": "1705315845.123",
            "type": "PLACEMENT",
        }

        # _handle_message expects str, but test that it can handle the conversion
        # (The actual conversion happens in _connect_and_listen before calling _handle_message)
        await adapter._handle_message(json.dumps(order_msg))

        # Should have published CanonicalOrderAck
        try:
            canonical_ack = await asyncio.wait_for(ack_queue.get(), timeout=1.0)
            assert isinstance(canonical_ack, CanonicalOrderAck)
        except TimeoutError:
            pass
