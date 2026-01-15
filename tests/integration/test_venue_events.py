"""Integration tests for venue connection/disconnection events.

Per Commit 19: Add VenueConnectedEvent and VenueDisconnectedEvent.
Per observability.mdc §6: Venue connection events enable replayability checks.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from polytrader.adapters.polymarket.user_stream import UserStreamAdapter
from polytrader.clob import IClobClient
from polytrader.events import VENUE_CONNECTED, VENUE_DISCONNECTED, EventBus
from polytrader.events.store import MemoryEventStore
from polytrader.events.types import VenueConnectedEvent, VenueDisconnectedEvent


@pytest.fixture
def bus() -> EventBus:
    """Create an event bus for testing."""
    return EventBus(store=MemoryEventStore())


@pytest.fixture
def mock_clob_client() -> IClobClient:
    """Create a mock CLOB client for testing."""
    client = MagicMock(spec=IClobClient)
    client.create_or_derive_api_creds.return_value = {
        "apiKey": "test-key",
        "secret": "test-secret",
        "passphrase": "test-passphrase",
    }
    return client


@pytest.fixture
def adapter(bus: EventBus, mock_clob_client: IClobClient) -> UserStreamAdapter:
    """Create a user stream adapter for testing."""
    return UserStreamAdapter(clob_client=mock_clob_client, bus=bus)


class TestVenueConnectedEvent:
    """Tests for VenueConnectedEvent emission."""

    @pytest.mark.asyncio
    async def test_venue_connected_event_emitted_on_connect(
        self, bus: EventBus, adapter: UserStreamAdapter
    ) -> None:
        """Test that VenueConnectedEvent is emitted when WebSocket connects."""
        # Subscribe to venue connected events
        connected_queue = bus.subscribe(VENUE_CONNECTED)

        # Mock websockets.connect to avoid actual connection
        with patch("polytrader.adapters.polymarket.user_stream.websockets.connect") as mock_connect:
            # Create a mock WebSocket connection
            mock_ws = AsyncMock()
            mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
            mock_ws.__aexit__ = AsyncMock(return_value=None)
            mock_ws.send = AsyncMock()
            mock_ws.__aiter__ = AsyncMock(return_value=iter([]))  # Empty message stream

            mock_connect.return_value = mock_ws

            # Start adapter in background
            adapter_task = asyncio.create_task(adapter.run())

            # Wait for connection event
            await asyncio.sleep(0.2)

            # Stop adapter
            adapter.stop()
            try:
                await adapter_task
            except asyncio.CancelledError:
                pass

            # Check that VenueConnectedEvent was emitted
            assert not connected_queue.empty(), "VenueConnectedEvent was not emitted"
            connected_event = await connected_queue.get()

            assert isinstance(connected_event, VenueConnectedEvent)
            assert connected_event.venue == "polymarket"
            assert connected_event.connection_type == "websocket"
            assert connected_event.url is not None
            assert "wss://" in connected_event.url

    @pytest.mark.asyncio
    async def test_venue_connected_event_fields(
        self, bus: EventBus, adapter: UserStreamAdapter
    ) -> None:
        """Test that VenueConnectedEvent has correct fields."""
        # Subscribe to venue connected events
        connected_queue = bus.subscribe(VENUE_CONNECTED)

        # Mock websockets.connect
        with patch("polytrader.adapters.polymarket.user_stream.websockets.connect") as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
            mock_ws.__aexit__ = AsyncMock(return_value=None)
            mock_ws.send = AsyncMock()
            mock_ws.__aiter__ = AsyncMock(return_value=iter([]))

            mock_connect.return_value = mock_ws

            # Start adapter
            adapter_task = asyncio.create_task(adapter.run())
            await asyncio.sleep(0.2)

            # Stop adapter
            adapter.stop()
            try:
                await adapter_task
            except asyncio.CancelledError:
                pass

            # Verify event fields
            connected_event = await connected_queue.get()
            assert connected_event.source.value == "adapter"
            assert connected_event.event_id is not None
            assert connected_event.ts_wall is not None
            assert connected_event.ts_mono > 0
            assert connected_event.correlation_id is not None


class TestVenueDisconnectedEvent:
    """Tests for VenueDisconnectedEvent emission."""

    @pytest.mark.asyncio
    async def test_venue_disconnected_event_emitted_on_disconnect(
        self, bus: EventBus, adapter: UserStreamAdapter
    ) -> None:
        """Test that VenueDisconnectedEvent is emitted when WebSocket disconnects."""
        # Subscribe to venue disconnected events
        disconnected_queue = bus.subscribe(VENUE_DISCONNECTED)

        # Mock websockets.connect
        with patch("polytrader.adapters.polymarket.user_stream.websockets.connect") as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
            mock_ws.__aexit__ = AsyncMock(return_value=None)
            mock_ws.send = AsyncMock()
            mock_ws.__aiter__ = AsyncMock(return_value=iter([]))

            mock_connect.return_value = mock_ws

            # Start adapter
            adapter_task = asyncio.create_task(adapter.run())
            await asyncio.sleep(0.3)  # Give time for connection and event emission

            # Stop adapter (triggers disconnect)
            adapter.stop()
            try:
                await adapter_task
            except asyncio.CancelledError:
                pass

            # Wait for event processing
            await asyncio.sleep(0.2)

            # Check that VenueDisconnectedEvent was emitted
            assert not disconnected_queue.empty(), "VenueDisconnectedEvent was not emitted"
            disconnected_event = await disconnected_queue.get()

            assert isinstance(disconnected_event, VenueDisconnectedEvent)
            assert disconnected_event.venue == "polymarket"
            assert disconnected_event.connection_type == "websocket"
            assert disconnected_event.reason is not None

    @pytest.mark.asyncio
    async def test_venue_disconnected_event_on_error(
        self, bus: EventBus, adapter: UserStreamAdapter
    ) -> None:
        """Test that VenueDisconnectedEvent is emitted on connection error."""
        # Subscribe to venue disconnected events
        disconnected_queue = bus.subscribe(VENUE_DISCONNECTED)

        # Mock websockets.connect to raise an error
        with patch("polytrader.adapters.polymarket.user_stream.websockets.connect") as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")

            # Start adapter (will fail and emit disconnect event)
            adapter_task = asyncio.create_task(adapter.run())
            await asyncio.sleep(0.5)  # Give time for error handling and event emission

            # Stop adapter
            adapter.stop()
            try:
                await adapter_task
            except asyncio.CancelledError:
                pass

            # Wait for event processing
            await asyncio.sleep(0.2)

            # Check that VenueDisconnectedEvent was emitted with error reason
            assert not disconnected_queue.empty(), "VenueDisconnectedEvent was not emitted"
            disconnected_event = await disconnected_queue.get()

            assert isinstance(disconnected_event, VenueDisconnectedEvent)
            assert disconnected_event.venue == "polymarket"
            assert disconnected_event.connection_type == "websocket"
            assert disconnected_event.reason is not None
            assert "Error" in disconnected_event.reason

    @pytest.mark.asyncio
    async def test_venue_disconnected_event_fields(
        self, bus: EventBus, adapter: UserStreamAdapter
    ) -> None:
        """Test that VenueDisconnectedEvent has correct fields."""
        # Subscribe to venue disconnected events
        disconnected_queue = bus.subscribe(VENUE_DISCONNECTED)

        # Mock websockets.connect
        with patch("polytrader.adapters.polymarket.user_stream.websockets.connect") as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
            mock_ws.__aexit__ = AsyncMock(return_value=None)
            mock_ws.send = AsyncMock()
            mock_ws.__aiter__ = AsyncMock(return_value=iter([]))

            mock_connect.return_value = mock_ws

            # Start adapter
            adapter_task = asyncio.create_task(adapter.run())
            await asyncio.sleep(0.2)

            # Stop adapter
            adapter.stop()
            try:
                await adapter_task
            except asyncio.CancelledError:
                pass

            # Wait for event processing
            await asyncio.sleep(0.1)

            # Verify event fields
            disconnected_event = await disconnected_queue.get()
            assert disconnected_event.source.value == "adapter"
            assert disconnected_event.event_id is not None
            assert disconnected_event.ts_wall is not None
            assert disconnected_event.ts_mono > 0
            assert disconnected_event.correlation_id is not None


class TestVenueEventSequence:
    """Tests for venue event sequencing."""

    @pytest.mark.asyncio
    async def test_connect_then_disconnect_sequence(
        self, bus: EventBus, adapter: UserStreamAdapter
    ) -> None:
        """Test that connect and disconnect events are emitted in sequence."""
        # Subscribe to both topics
        connected_queue = bus.subscribe(VENUE_CONNECTED)
        disconnected_queue = bus.subscribe(VENUE_DISCONNECTED)

        # Mock websockets.connect
        with patch("polytrader.adapters.polymarket.user_stream.websockets.connect") as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
            mock_ws.__aexit__ = AsyncMock(return_value=None)
            mock_ws.send = AsyncMock()
            mock_ws.__aiter__ = AsyncMock(return_value=iter([]))

            mock_connect.return_value = mock_ws

            # Start adapter
            adapter_task = asyncio.create_task(adapter.run())
            await asyncio.sleep(0.2)

            # Verify connected event
            assert not connected_queue.empty(), "VenueConnectedEvent was not emitted"
            connected_event = await connected_queue.get()
            assert isinstance(connected_event, VenueConnectedEvent)

            # Stop adapter
            adapter.stop()
            try:
                await adapter_task
            except asyncio.CancelledError:
                pass

            # Wait for disconnect event
            await asyncio.sleep(0.1)

            # Verify disconnected event
            assert not disconnected_queue.empty(), "VenueDisconnectedEvent was not emitted"
            disconnected_event = await disconnected_queue.get()
            assert isinstance(disconnected_event, VenueDisconnectedEvent)

            # Verify event ordering (connect should happen before disconnect)
            assert connected_event.ts_mono < disconnected_event.ts_mono
