"""Polymarket CLOB user stream adapter (WebSocket listener).

Per flows.mdc §10: User stream adapter normalizes venue WebSocket messages
to canonical events and publishes them to EventBus.

This adapter:
- Connects to Polymarket WebSocket API
- Authenticates using API credentials from clob_client
- Subscribes to "user" channel for order updates
- Normalizes venue messages to canonical models
- Publishes canonical events to EventBus
- Handles reconnection with exponential backoff
- Emits structured logs for debugging

Per architecture.mdc §H: Adapters contain IO only, no business logic.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import websockets

if TYPE_CHECKING:
    from websockets.asyncio.client import ClientConnection

from polytrader.adapters.polymarket.models import (
    CanonicalCancel,
    CanonicalFill,
    CanonicalOrderAck,
    OrderMessage,
    TradeMessage,
    parse_websocket_message,
)
from polytrader.clob import IClobClient
from polytrader.events.bus import EventBus

# Note: User stream adapter publishes canonical events, not OMS events
# OMS will subscribe and convert canonical events to OMS events
from polytrader.logging_config import logger

# Polymarket WebSocket endpoint
# Per Polymarket CLOB WebSocket API:
# https://docs.polymarket.com/developers/CLOB/websocket/wss-overview
WS_BASE_URL = "wss://ws-subscriptions-clob.polymarket.com"
WS_USER_URL = f"{WS_BASE_URL}/ws/user"

# WebSocket protocol messages (plain text, not JSON)
# Per Polymarket API: send "PING" every 10 seconds, respond to "PING" with "PONG"
WS_PING = "PING"
WS_PONG = "PONG"

# Reconnection settings
INITIAL_RECONNECT_DELAY = 1.0  # seconds
MAX_RECONNECT_DELAY = 60.0  # seconds
RECONNECT_BACKOFF_MULTIPLIER = 2.0


class UserStreamAdapter:
    """Adapter for Polymarket user stream WebSocket.

    Per flows.mdc §10: Listens to venue user stream and normalizes messages
    to canonical events (ack, reject, fill, cancel).

    Attributes:
        clob_client: CLOB client for API credentials
        bus: Event bus for publishing canonical events
        _running: Flag to control async loop
        _ws: WebSocket connection (None when disconnected)
        _reconnect_delay: Current reconnect delay (exponential backoff)
    """

    def __init__(self, clob_client: IClobClient, bus: EventBus) -> None:
        """Initialize user stream adapter.

        Args:
            clob_client: CLOB client instance (for API credentials)
            bus: Event bus for publishing canonical events
        """
        self.clob_client = clob_client
        self.bus = bus
        self._running = False
        if TYPE_CHECKING:
            self._ws: ClientConnection | None = None
        else:
            self._ws: Any = None
        self._reconnect_delay = INITIAL_RECONNECT_DELAY

    async def run(self) -> None:
        """Start user stream adapter async loop.

        Connects to WebSocket, subscribes to "user" channel, and processes
        incoming messages. Handles reconnection automatically on disconnect.
        """
        self._running = True

        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                logger.info("User stream adapter cancelled")
                break
            except Exception as e:
                logger.exception(
                    "User stream adapter error, reconnecting",
                    error_type=type(e).__name__,
                    error=str(e),
                )
                if self._running:
                    await self._wait_before_reconnect()
                else:
                    break

        # Clean shutdown
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._running = False
        logger.info("User stream adapter stopped")

    def stop(self) -> None:
        """Stop user stream adapter async loop."""
        self._running = False

    async def _connect_and_listen(self) -> None:
        """Connect to WebSocket and listen for messages.

        Raises:
            ConnectionClosed: If WebSocket connection is closed
            WebSocketException: If WebSocket error occurs
        """
        # Get API credentials from clob_client
        api_creds = self.clob_client.create_or_derive_api_creds()

        # Try to extract apiKey, secret, and passphrase
        # ApiCreds might be a dict, dataclass, or object with attributes
        if isinstance(api_creds, dict):
            api_key = api_creds.get("apiKey") or api_creds.get("api_key")
            api_secret = (
                api_creds.get("secret") or api_creds.get("apiSecret") or api_creds.get("api_secret")
            )
            api_passphrase = api_creds.get("passphrase") or api_creds.get("api_passphrase")
        else:
            # Try as attributes (camelCase or snake_case)
            api_key = getattr(api_creds, "apiKey", None) or getattr(api_creds, "api_key", None)
            api_secret = (
                getattr(api_creds, "secret", None)
                or getattr(api_creds, "apiSecret", None)
                or getattr(api_creds, "api_secret", None)
            )
            api_passphrase = getattr(api_creds, "passphrase", None) or getattr(
                api_creds, "api_passphrase", None
            )
            # If still not found, try to convert to dict if possible
            if not api_key or not api_secret:
                try:
                    if hasattr(api_creds, "__dict__"):
                        api_key = api_creds.__dict__.get("apiKey") or api_creds.__dict__.get(
                            "api_key"
                        )
                        api_secret = (
                            api_creds.__dict__.get("secret")
                            or api_creds.__dict__.get("apiSecret")
                            or api_creds.__dict__.get("api_secret")
                        )
                        api_passphrase = api_creds.__dict__.get(
                            "passphrase"
                        ) or api_creds.__dict__.get("api_passphrase")
                except Exception:
                    pass

        if not api_key or not api_secret:
            raise ValueError("API credentials not available from clob_client")

        # Connect to WebSocket
        logger.info("Connecting to Polymarket user stream WebSocket", url=WS_USER_URL)
        async with websockets.connect(WS_USER_URL) as ws:
            self._ws = ws
            self._reconnect_delay = INITIAL_RECONNECT_DELAY  # Reset on successful connect

            # Subscribe to user channel with authentication
            # Per Polymarket API: send subscription message with auth on connection
            subscribe_message = {
                "type": "user",
                "markets": [],  # Empty array subscribes to all markets
                "auth": {
                    "apiKey": api_key,
                    "secret": api_secret,
                    "passphrase": api_passphrase or "",  # Passphrase may be optional
                },
            }
            await ws.send(json.dumps(subscribe_message))
            logger.info("Subscribed to user channel with authentication")

            # Start ping task to keep connection alive (every 10 seconds)
            ping_task = asyncio.create_task(self._ping_loop(ws))

            try:
                # Listen for messages
                async for message in ws:
                    if not self._running:
                        break
                    try:
                        # Convert bytes to str if needed
                        message_str = (
                            message if isinstance(message, str) else message.decode("utf-8")
                        )
                        await self._handle_message(message_str)
                    except Exception as e:
                        logger.exception(
                            "Error handling user stream message",
                            error_type=type(e).__name__,
                            error=str(e),
                            message_preview=str(message)[:200],
                        )
            finally:
                # Cancel ping task on disconnect
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass

    async def _handle_message(self, raw_message: str) -> None:
        """Handle incoming WebSocket message.

        Parses venue message using Pydantic models and normalizes to canonical
        model, then publishes to EventBus.

        Args:
            raw_message: Raw message from WebSocket (may be JSON or plain text like "PING")
        """
        # Handle plain text PING/PONG messages (not JSON)
        message_stripped = raw_message.strip()
        if message_stripped == WS_PING:
            # Respond to ping with pong (plain text, not JSON)
            if self._ws:
                await self._ws.send(WS_PONG)
            logger.debug("Received PING, sent PONG")
            return
        elif message_stripped == WS_PONG:
            # Server response to our PING - just acknowledge
            logger.debug("Received PONG (response to our PING)")
            return

        try:
            data = json.loads(raw_message)
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse user stream message as JSON",
                error=str(e),
                message_preview=raw_message[:200],
                message_repr=repr(raw_message),
            )
            return

        # Parse using Pydantic models
        parsed_message = parse_websocket_message(data)
        if parsed_message is None:
            logger.debug(
                "Unknown or unparseable message type",
                event_type=data.get("event_type"),
                data=data,
            )
            return

        # Handle based on message type
        if isinstance(parsed_message, OrderMessage):
            await self._handle_order_message(parsed_message)
        elif isinstance(parsed_message, TradeMessage):
            await self._handle_trade_message(parsed_message)
        else:
            logger.debug(
                "Unhandled message type in user channel",
                message_type=type(parsed_message).__name__,
                event_type=data.get("event_type"),
            )

    async def _handle_order_message(self, order_msg: OrderMessage) -> None:
        """Handle order message from user channel.

        Per Polymarket API:
        - PLACEMENT: Order was placed (this is our acknowledgment)
        - UPDATE: Order was partially filled
        - CANCELLATION: Order was canceled

        Note: Polymarket doesn't send client_order_id in OrderMessage.
        We match orders by venue_order_id (order_msg.id).

        Args:
            order_msg: Parsed OrderMessage from WebSocket
        """
        venue_order_id = order_msg.id
        timestamp = order_msg.timestamp

        # Convert Unix timestamp (seconds) to ISO format
        try:
            # Polymarket timestamps are in seconds (not milliseconds)
            ts_float = float(timestamp)
            iso_timestamp = datetime.fromtimestamp(ts_float, tz=UTC).isoformat()
        except (ValueError, OSError):
            # Fallback to current time if timestamp parsing fails
            iso_timestamp = datetime.now(UTC).isoformat()

        if order_msg.type == "PLACEMENT":
            # Order placement = acknowledgment
            # Note: We don't have client_order_id, so OMS must match by venue_order_id
            canonical_ack = CanonicalOrderAck(
                client_order_id="",  # Not provided by Polymarket
                venue_order_id=venue_order_id,
                timestamp=iso_timestamp,
            )

            # Publish canonical ack to user stream topic
            from polytrader.events import USER_STREAM_ACKS

            await self.bus.publish(USER_STREAM_ACKS, canonical_ack)
            logger.info(
                "Published order acknowledgment (PLACEMENT)",
                venue_order_id=venue_order_id,
                market=order_msg.market,
                side=order_msg.side,
                price=order_msg.price,
            )

        elif order_msg.type == "CANCELLATION":
            # Order cancellation
            canonical_cancel = CanonicalCancel(
                client_order_id=None,  # Not provided by Polymarket
                venue_order_id=venue_order_id,
                timestamp=iso_timestamp,
            )

            # Publish canonical cancel to user stream topic
            from polytrader.events import USER_STREAM_CANCELS

            await self.bus.publish(USER_STREAM_CANCELS, canonical_cancel)
            logger.info(
                "Published order cancellation",
                venue_order_id=venue_order_id,
                market=order_msg.market,
            )

        elif order_msg.type == "UPDATE":
            # Order update (partial fill) - we don't emit a separate event for this
            # The actual fill will come via TradeMessage
            logger.debug(
                "Order update (partial fill)",
                venue_order_id=venue_order_id,
                size_matched=order_msg.size_matched,
                original_size=order_msg.original_size,
            )
        else:
            logger.warning(
                "Unknown order message type",
                type=order_msg.type,
                venue_order_id=venue_order_id,
            )

    async def _handle_trade_message(self, trade_msg: TradeMessage) -> None:
        """Handle trade message from user channel.

        Per Polymarket API: TradeMessage is emitted when:
        - A market order is matched ("MATCHED")
        - A limit order for the user is included in a trade ("MATCHED")
        - Subsequent status changes for trade ("MINED", "CONFIRMED", "RETRYING", "FAILED")

        We emit FillEvent for MATCHED trades. Other statuses are logged but not emitted.

        Note: Polymarket doesn't send client_order_id in TradeMessage.
        We match orders by venue_order_id (taker_order_id or maker_orders[].order_id).

        Args:
            trade_msg: Parsed TradeMessage from WebSocket
        """
        # Only process MATCHED trades as fills
        if trade_msg.status != "MATCHED":
            logger.debug(
                "Trade message with non-MATCHED status",
                trade_id=trade_msg.id,
                status=trade_msg.status,
            )
            return

        # Convert timestamp (Unix seconds) to ISO format
        try:
            ts_float = float(trade_msg.timestamp)
            iso_timestamp = datetime.fromtimestamp(ts_float, tz=UTC).isoformat()
        except (ValueError, OSError):
            iso_timestamp = datetime.now(UTC).isoformat()

        # Convert string numbers to floats
        try:
            fill_size = float(trade_msg.size)
            fill_price = float(trade_msg.price)
        except (ValueError, TypeError) as e:
            logger.warning(
                "Failed to parse trade size/price",
                trade_id=trade_msg.id,
                size=trade_msg.size,
                price=trade_msg.price,
                error=str(e),
            )
            return

        # Validate price range (0-1 for Polymarket)
        if fill_price <= 0 or fill_price > 1:
            logger.warning(
                "Invalid fill price",
                trade_id=trade_msg.id,
                price=fill_price,
            )
            return

        # Fee is not provided in TradeMessage, default to 0
        # (Fee might be calculated separately or available in other messages)
        fill_fee = 0.0

        # Publish fill for taker order
        # Note: We only emit for taker. For maker orders, we'd need to compare
        # trade_msg.owner or maker_order.owner with our API key to determine
        # if we're the maker. Since we don't store API key in adapter, we only
        # handle taker fills here. Maker fills will be handled when we're the
        # taker in the opposite trade, or we can enhance this later with API key.
        taker_venue_order_id = trade_msg.taker_order_id
        if taker_venue_order_id:
            await self._publish_fill_event(
                venue_order_id=taker_venue_order_id,
                fill_id=trade_msg.id,
                size=fill_size,
                price=fill_price,
                fee=fill_fee,
                timestamp=iso_timestamp,
                side=trade_msg.side,
                market=trade_msg.market,
            )

        # TODO: Handle maker orders
        # To properly handle maker orders, we need to:
        # 1. Store our API key in the adapter (or get it from clob_client)
        # 2. Compare maker_order.owner with our API key
        # 3. Only emit fills for maker orders that belong to us
        # For now, maker orders are not handled here

    async def _publish_fill_event(
        self,
        venue_order_id: str,
        fill_id: str,
        size: float,
        price: float,
        fee: float,
        timestamp: str,
        side: str,
        market: str,
    ) -> None:
        """Publish a fill event for a trade.

        Args:
            venue_order_id: Venue order ID
            fill_id: Unique fill ID
            size: Fill size
            price: Fill price
            fee: Fill fee
            timestamp: ISO timestamp
            side: Trade side (BUY/SELL)
            market: Market identifier
        """
        # Create canonical fill
        canonical_fill = CanonicalFill(
            client_order_id=None,  # Not provided by Polymarket
            venue_order_id=venue_order_id,
            fill_id=fill_id,
            size=size,
            price=price,
            fee=fee,
            timestamp=timestamp,
        )

        # Publish canonical fill to user stream topic
        from polytrader.events import USER_STREAM_FILLS

        await self.bus.publish(USER_STREAM_FILLS, canonical_fill)
        logger.info(
            "Published fill event (trade MATCHED)",
            fill_id=canonical_fill.fill_id,
            venue_order_id=canonical_fill.venue_order_id,
            size=canonical_fill.size,
            price=canonical_fill.price,
            side=side,
            market=market,
        )

    async def _ping_loop(self, ws: Any) -> None:
        """Send PING messages every 10 seconds to keep connection alive.

        Per Polymarket WebSocket API: send "PING" (not JSON) every 10 seconds.

        Args:
            ws: WebSocket connection
        """
        try:
            while self._running:
                await asyncio.sleep(10.0)  # Send ping every 10 seconds
                if self._running and ws:
                    await ws.send(WS_PING)
                    logger.debug("Sent PING to keep connection alive")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Error in ping loop", error=str(e))

    async def _wait_before_reconnect(self) -> None:
        """Wait before attempting reconnection (exponential backoff)."""
        delay = min(self._reconnect_delay, MAX_RECONNECT_DELAY)
        logger.info(
            "Waiting before reconnection",
            delay_seconds=delay,
            max_delay=MAX_RECONNECT_DELAY,
        )
        await asyncio.sleep(delay)
        self._reconnect_delay *= RECONNECT_BACKOFF_MULTIPLIER
