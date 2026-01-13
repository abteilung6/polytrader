"""Polymarket venue-specific models.

Per architecture.mdc §H: Adapters normalize venue responses to canonical format.
"""

from typing import Any, Literal, cast

from pydantic import BaseModel, Field, field_validator

OrderStatus = Literal["FILLED", "CANCELLED", "OPEN", "PENDING", "UNKNOWN"]
OrderSide = Literal["BUY", "SELL"]


class ExternalOrder(BaseModel):
    """External order from Polymarket CLOB API.

    Handles multiple field name variations in the API response:
    - token_id: Can be 'token_id', 'asset_id', or nested in 'asset.token_id'
    - status: Can be 'status' or 'state'
    - side: Order side (BUY or SELL)
    - size: Can be 'size' or 'amount'
    - order_id: Can be 'order_id' or 'id'

    Attributes:
        token_id: Token ID for the market outcome
        status: Order status (FILLED, CANCELLED, OPEN, etc.)
        side: Order side (BUY or SELL)
        size: Order size in USD
        order_id: Order ID from the API
    """

    token_id: str = Field(..., description="Token ID for the market outcome")
    status: OrderStatus = Field(..., description="Order status")
    side: OrderSide = Field(..., description="Order side (BUY or SELL)")
    size: float = Field(..., description="Order size in USD", ge=0)
    order_id: str = Field(..., description="Order ID from the API")

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "ExternalOrder | None":
        """Parse external order from API response.

        Handles multiple field name variations in the API response.

        Args:
            data: Raw order dictionary from Polymarket API

        Returns:
            ExternalOrder if parseable, None otherwise
        """
        # Extract token_id (could be 'token_id', 'asset_id', or nested)
        token_id = data.get("token_id") or data.get("asset_id")
        if not token_id and isinstance(data.get("asset"), dict):
            token_id = data.get("asset", {}).get("token_id")

        if not token_id:
            return None

        # Extract status (could be 'status' or 'state')
        status_raw = (data.get("status") or data.get("state") or "UNKNOWN").upper()
        # Validate status
        valid_statuses: tuple[OrderStatus, ...] = (
            "FILLED",
            "CANCELLED",
            "OPEN",
            "PENDING",
            "UNKNOWN",
        )
        status: OrderStatus = (
            cast(OrderStatus, status_raw) if status_raw in valid_statuses else "UNKNOWN"
        )

        # Extract side
        side_raw = (data.get("side") or "").upper()
        side: OrderSide = "BUY" if side_raw == "BUY" else "SELL" if side_raw == "SELL" else "BUY"

        # Extract size (could be 'size' or 'amount')
        size = float(data.get("size") or data.get("amount") or 0)

        # Extract order_id (could be 'order_id' or 'id')
        order_id = str(data.get("order_id") or data.get("id") or "unknown")

        try:
            return cls(
                token_id=str(token_id),
                status=status,
                side=side,
                size=size,
                order_id=order_id,
            )
        except Exception:
            return None

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: Any) -> str:
        """Normalize status to uppercase."""
        if isinstance(v, str):
            return v.upper()
        return str(v).upper()

    @field_validator("side", mode="before")
    @classmethod
    def validate_side(cls, v: Any) -> str:
        """Normalize side to uppercase."""
        if isinstance(v, str):
            return v.upper()
        return str(v).upper()


class VenueResponse(BaseModel):
    """Normalized venue response from Polymarket CLOB API.

    Per architecture.mdc §H: Adapters normalize venue responses.
    This model provides a canonical format for venue responses.

    Attributes:
        venue_order_id: Order ID assigned by venue
        status: Order status
        raw_response: Raw response from venue (for debugging)
    """

    venue_order_id: str = Field(..., description="Order ID assigned by venue")
    status: str = Field(..., description="Order status from venue")
    raw_response: dict[str, Any] = Field(..., description="Raw response from venue")


class VenueError(Exception):
    """Venue error with classification.

    Attributes:
        error_type: Type of error (retryable or fatal)
        message: Error message
        raw_error: Raw error from venue (for debugging)
    """

    def __init__(
        self,
        error_type: Literal["retryable", "fatal"],
        message: str,
        raw_error: Any,
    ) -> None:
        """Initialize venue error.

        Args:
            error_type: Type of error (retryable or fatal)
            message: Error message
            raw_error: Raw error from venue (for debugging)
        """
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.raw_error = raw_error


# Canonical User Stream Event Models
# These models normalize venue WebSocket messages to a canonical format.
# Per flows.mdc §10: User stream adapter normalizes venue messages to canonical events.


class CanonicalOrderAck(BaseModel):
    """Canonical order acknowledgment from venue user stream.

    Per flows.mdc §10: User stream adapter normalizes venue ack messages
    to this canonical format before publishing to EventBus.

    Attributes:
        client_order_id: Our idempotency key (from order submission)
        venue_order_id: Venue-assigned order ID
        timestamp: Timestamp from venue (ISO format UTC)
    """

    client_order_id: str = Field(..., description="Our idempotency key")
    venue_order_id: str = Field(..., description="Venue-assigned order ID")
    timestamp: str = Field(..., description="Timestamp from venue (ISO format UTC)")


class CanonicalOrderReject(BaseModel):
    """Canonical order rejection from venue user stream.

    Per flows.mdc §10: User stream adapter normalizes venue reject messages
    to this canonical format before publishing to EventBus.

    Attributes:
        client_order_id: Our idempotency key (from order submission)
        reason: Rejection reason from venue
        timestamp: Timestamp from venue (ISO format UTC)
    """

    client_order_id: str = Field(..., description="Our idempotency key")
    reason: str = Field(..., description="Rejection reason from venue")
    timestamp: str = Field(..., description="Timestamp from venue (ISO format UTC)")


class CanonicalFill(BaseModel):
    """Canonical fill event from venue user stream.

    Per flows.mdc §10: User stream adapter normalizes venue fill messages
    to this canonical format before publishing to EventBus.

    Attributes:
        client_order_id: Our idempotency key (optional, may not be present)
        venue_order_id: Venue-assigned order ID (optional, may not be present)
        fill_id: Venue-assigned fill ID (for deduplication)
        size: Fill size in USD
        price: Fill price (0-1 range)
        fee: Fee amount for this fill
        timestamp: Timestamp from venue (ISO format UTC)
    """

    client_order_id: str | None = Field(
        default=None, description="Our idempotency key (may not be present)"
    )
    venue_order_id: str | None = Field(
        default=None, description="Venue-assigned order ID (may not be present)"
    )
    fill_id: str = Field(..., description="Venue-assigned fill ID (for deduplication)")
    size: float = Field(gt=0, description="Fill size in USD")
    price: float = Field(gt=0, le=1, description="Fill price (0-1 range)")
    fee: float = Field(ge=0, description="Fee amount for this fill")
    timestamp: str = Field(..., description="Timestamp from venue (ISO format UTC)")


class CanonicalCancel(BaseModel):
    """Canonical cancel confirmation from venue user stream.

    Per flows.mdc §10: User stream adapter normalizes venue cancel messages
    to this canonical format before publishing to EventBus.

    Attributes:
        client_order_id: Our idempotency key (optional, may not be present)
        venue_order_id: Venue-assigned order ID (required)
        timestamp: Timestamp from venue (ISO format UTC)
    """

    client_order_id: str | None = Field(
        default=None, description="Our idempotency key (may not be present)"
    )
    venue_order_id: str = Field(..., description="Venue-assigned order ID")
    timestamp: str = Field(..., description="Timestamp from venue (ISO format UTC)")


# ============================================================================
# Polymarket WebSocket Message Schemas
# ============================================================================
# These models represent the raw WebSocket messages from Polymarket.
# They are used for parsing and validation before normalization to canonical models.
# Per Polymarket CLOB WebSocket API documentation.
# ============================================================================


# User Channel Messages
# =====================


class MakerOrder(BaseModel):
    """Maker order details in a trade message.

    Attributes:
        asset_id: Asset ID of the maker order
        matched_amount: Amount of maker order matched in trade
        order_id: Maker order ID
        outcome: Outcome (e.g., "YES", "NO")
        owner: Owner of maker order (API key)
        price: Price of maker order
    """

    asset_id: str = Field(..., description="Asset ID of the maker order")
    matched_amount: str = Field(..., description="Amount of maker order matched in trade")
    order_id: str = Field(..., description="Maker order ID")
    outcome: str = Field(..., description="Outcome (e.g., 'YES', 'NO')")
    owner: str = Field(..., description="Owner of maker order (API key)")
    price: str = Field(..., description="Price of maker order")


class TradeMessage(BaseModel):
    """Trade message from user channel.

    Emitted when:
    - A market order is matched ("MATCHED")
    - A limit order for the user is included in a trade ("MATCHED")
    - Subsequent status changes for trade ("MINED", "CONFIRMED", "RETRYING", "FAILED")

    Attributes:
        asset_id: Asset ID (token ID) of order (market order)
        event_type: Always "trade"
        id: Trade ID
        last_update: Time of last update to trade
        maker_orders: Array of maker order details
        market: Market identifier (condition ID)
        matchtime: Time trade was matched
        outcome: Outcome
        owner: API key of event owner
        price: Price
        side: BUY/SELL
        size: Size
        status: Trade status
        taker_order_id: ID of taker order
        timestamp: Time of event
        trade_owner: API key of trade owner
        type: Always "TRADE"
    """

    asset_id: str = Field(..., description="Asset ID (token ID) of order")
    event_type: Literal["trade"] = Field(..., description="Event type")
    id: str = Field(..., description="Trade ID")
    last_update: str = Field(..., description="Time of last update to trade")
    maker_orders: list[MakerOrder] = Field(..., description="Array of maker order details")
    market: str = Field(..., description="Market identifier (condition ID)")
    matchtime: str = Field(..., description="Time trade was matched")
    outcome: str = Field(..., description="Outcome")
    owner: str = Field(..., description="API key of event owner")
    price: str = Field(..., description="Price")
    side: Literal["BUY", "SELL"] = Field(..., description="Side")
    size: str = Field(..., description="Size")
    status: str = Field(..., description="Trade status")
    taker_order_id: str = Field(..., description="ID of taker order")
    timestamp: str = Field(..., description="Time of event")
    trade_owner: str = Field(..., description="API key of trade owner")
    type: Literal["TRADE"] = Field(..., description="Type")


class OrderMessage(BaseModel):
    """Order message from user channel.

    Emitted when:
    - An order is placed (PLACEMENT)
    - An order is updated (some of it is matched) (UPDATE)
    - An order is canceled (CANCELLATION)

    Attributes:
        asset_id: Asset ID (token ID) of order
        associate_trades: Array of IDs referencing trades that the order has been included in
        event_type: Always "order"
        id: Order ID
        market: Condition ID of market
        order_owner: Owner of order
        original_size: Original order size
        outcome: Outcome
        owner: Owner of orders
        price: Price of order
        side: BUY/SELL
        size_matched: Size of order that has been matched
        timestamp: Time of event
        type: PLACEMENT/UPDATE/CANCELLATION
    """

    asset_id: str = Field(..., description="Asset ID (token ID) of order")
    associate_trades: list[str] | None = Field(
        default=None, description="Array of trade IDs associated with this order"
    )
    event_type: Literal["order"] = Field(..., description="Event type")
    id: str = Field(..., description="Order ID")
    market: str = Field(..., description="Condition ID of market")
    order_owner: str = Field(..., description="Owner of order")
    original_size: str = Field(..., description="Original order size")
    outcome: str = Field(..., description="Outcome")
    owner: str = Field(..., description="Owner of orders")
    price: str = Field(..., description="Price of order")
    side: Literal["BUY", "SELL"] = Field(..., description="Side")
    size_matched: str = Field(..., description="Size of order that has been matched")
    timestamp: str = Field(..., description="Time of event")
    type: Literal["PLACEMENT", "UPDATE", "CANCELLATION"] = Field(
        ..., description="Order event type"
    )


# Market Channel Messages
# =======================


class OrderSummary(BaseModel):
    """Order summary for book levels.

    Attributes:
        price: Price of the orderbook level
        size: Size available at that price level
    """

    price: str = Field(..., description="Price of the orderbook level")
    size: str = Field(..., description="Size available at that price level")


class BookMessage(BaseModel):
    """Book message from market channel.

    Emitted when:
    - First subscribed to a market
    - When there is a trade that affects the book

    Attributes:
        event_type: Always "book"
        asset_id: Asset ID (token ID)
        market: Condition ID of market
        timestamp: Unix timestamp in milliseconds
        hash: Hash summary of the orderbook content
        buys: List of (size, price) aggregate book levels for buys
        sells: List of (size, price) aggregate book levels for sells
    """

    event_type: Literal["book"] = Field(..., description="Event type")
    asset_id: str = Field(..., description="Asset ID (token ID)")
    market: str = Field(..., description="Condition ID of market")
    timestamp: str = Field(..., description="Unix timestamp in milliseconds")
    hash: str = Field(..., description="Hash summary of the orderbook content")
    buys: list[OrderSummary] = Field(..., description="List of buy levels")
    sells: list[OrderSummary] = Field(..., description="List of sell levels")


class PriceChange(BaseModel):
    """Price change object in price_change message.

    Attributes:
        asset_id: Asset ID (token ID)
        price: Price level affected
        size: New aggregate size for price level
        side: "BUY" or "SELL"
        hash: Hash of the order
        best_bid: Current best bid price
        best_ask: Current best ask price
    """

    asset_id: str = Field(..., description="Asset ID (token ID)")
    price: str = Field(..., description="Price level affected")
    size: str = Field(..., description="New aggregate size for price level")
    side: Literal["BUY", "SELL"] = Field(..., description="Side")
    hash: str = Field(..., description="Hash of the order")
    best_bid: str = Field(..., description="Current best bid price")
    best_ask: str = Field(..., description="Current best ask price")


class PriceChangeMessage(BaseModel):
    """Price change message from market channel.

    Emitted when:
    - A new order is placed
    - An order is cancelled

    Attributes:
        event_type: Always "price_change"
        market: Condition ID of market
        price_changes: Array of price change objects
        timestamp: Unix timestamp in milliseconds
    """

    event_type: Literal["price_change"] = Field(..., description="Event type")
    market: str = Field(..., description="Condition ID of market")
    price_changes: list[PriceChange] = Field(..., description="Array of price change objects")
    timestamp: str = Field(..., description="Unix timestamp in milliseconds")


class TickSizeChangeMessage(BaseModel):
    """Tick size change message from market channel.

    Emitted when:
    - The minimum tick size of the market changes (price > 0.96 or price < 0.04)

    Attributes:
        event_type: Always "tick_size_change"
        asset_id: Asset ID (token ID)
        market: Condition ID of market
        old_tick_size: Previous minimum tick size
        new_tick_size: Current minimum tick size
        side: buy/sell
        timestamp: Time of event
    """

    event_type: Literal["tick_size_change"] = Field(..., description="Event type")
    asset_id: str = Field(..., description="Asset ID (token ID)")
    market: str = Field(..., description="Condition ID of market")
    old_tick_size: str = Field(..., description="Previous minimum tick size")
    new_tick_size: str = Field(..., description="Current minimum tick size")
    side: str = Field(..., description="buy/sell")
    timestamp: str = Field(..., description="Time of event")


class LastTradePriceMessage(BaseModel):
    """Last trade price message from market channel.

    Emitted when:
    - A maker and taker order is matched creating a trade event

    Attributes:
        asset_id: Asset ID (token ID)
        event_type: Always "last_trade_price"
        fee_rate_bps: Fee rate in basis points
        market: Condition ID of market
        price: Price
        side: BUY/SELL
        size: Size
        timestamp: Unix timestamp in milliseconds
    """

    asset_id: str = Field(..., description="Asset ID (token ID)")
    event_type: Literal["last_trade_price"] = Field(..., description="Event type")
    fee_rate_bps: str = Field(..., description="Fee rate in basis points")
    market: str = Field(..., description="Condition ID of market")
    price: str = Field(..., description="Price")
    side: Literal["BUY", "SELL"] = Field(..., description="Side")
    size: str = Field(..., description="Size")
    timestamp: str = Field(..., description="Unix timestamp in milliseconds")


class BestBidAskMessage(BaseModel):
    """Best bid ask message from market channel.

    Emitted when:
    - The best bid and ask prices for a market change
    - (This message is behind the custom_feature_enabled flag)

    Attributes:
        event_type: Always "best_bid_ask"
        market: Condition ID of market
        asset_id: Asset ID (token ID)
        best_bid: Current best bid price
        best_ask: Current best ask price
        spread: Spread between best bid and ask
        timestamp: Unix timestamp in milliseconds
    """

    event_type: Literal["best_bid_ask"] = Field(..., description="Event type")
    market: str = Field(..., description="Condition ID of market")
    asset_id: str = Field(..., description="Asset ID (token ID)")
    best_bid: str = Field(..., description="Current best bid price")
    best_ask: str = Field(..., description="Current best ask price")
    spread: str = Field(..., description="Spread between best bid and ask")
    timestamp: str = Field(..., description="Unix timestamp in milliseconds")


class EventMessage(BaseModel):
    """Event message object in new_market and market_resolved messages.

    Attributes:
        id: Event message ID
        ticker: Event message ticker
        slug: Event message slug
        title: Event message title
        description: Event message description
    """

    id: str = Field(..., description="Event message ID")
    ticker: str = Field(..., description="Event message ticker")
    slug: str = Field(..., description="Event message slug")
    title: str = Field(..., description="Event message title")
    description: str = Field(..., description="Event message description")


class NewMarketMessage(BaseModel):
    """New market message from market channel.

    Emitted when:
    - A new market is created
    - (This message is behind the custom_feature_enabled flag)

    Attributes:
        id: Market ID
        question: Market question
        market: Condition ID of market
        slug: Market slug
        description: Market description
        assets_ids: List of asset IDs
        outcomes: List of outcomes
        event_message: Event message object
        timestamp: Unix timestamp in milliseconds
        event_type: Always "new_market"
    """

    id: str = Field(..., description="Market ID")
    question: str = Field(..., description="Market question")
    market: str = Field(..., description="Condition ID of market")
    slug: str = Field(..., description="Market slug")
    description: str = Field(..., description="Market description")
    assets_ids: list[str] = Field(..., description="List of asset IDs")
    outcomes: list[str] = Field(..., description="List of outcomes")
    event_message: EventMessage = Field(..., description="Event message object")
    timestamp: str = Field(..., description="Unix timestamp in milliseconds")
    event_type: Literal["new_market"] = Field(..., description="Event type")


class MarketResolvedMessage(BaseModel):
    """Market resolved message from market channel.

    Emitted when:
    - A market is resolved
    - (This message is behind the custom_feature_enabled flag)

    Attributes:
        id: Market ID
        question: Market question
        market: Condition ID of market
        slug: Market slug
        description: Market description
        assets_ids: List of asset IDs
        outcomes: List of outcomes
        winning_asset_id: Winning asset ID
        winning_outcome: Winning outcome
        event_message: Event message object
        timestamp: Unix timestamp in milliseconds
        event_type: Always "market_resolved"
    """

    id: str = Field(..., description="Market ID")
    question: str = Field(..., description="Market question")
    market: str = Field(..., description="Condition ID of market")
    slug: str = Field(..., description="Market slug")
    description: str = Field(..., description="Market description")
    assets_ids: list[str] = Field(..., description="List of asset IDs")
    outcomes: list[str] = Field(..., description="List of outcomes")
    winning_asset_id: str = Field(..., description="Winning asset ID")
    winning_outcome: str = Field(..., description="Winning outcome")
    event_message: EventMessage = Field(..., description="Event message object")
    timestamp: str = Field(..., description="Unix timestamp in milliseconds")
    event_type: Literal["market_resolved"] = Field(..., description="Event type")


# Union type for all WebSocket messages
WebSocketMessage = (
    TradeMessage
    | OrderMessage
    | BookMessage
    | PriceChangeMessage
    | TickSizeChangeMessage
    | LastTradePriceMessage
    | BestBidAskMessage
    | NewMarketMessage
    | MarketResolvedMessage
)


def parse_websocket_message(data: dict[str, Any]) -> WebSocketMessage | None:
    """Parse a WebSocket message based on event_type.

    This function attempts to parse a raw WebSocket message dictionary
    into the appropriate Pydantic model based on the event_type field.

    Args:
        data: Raw message dictionary from WebSocket

    Returns:
        Parsed WebSocket message model, or None if event_type is unknown
        or parsing fails

    Example:
        >>> msg = {"event_type": "trade", "id": "123", ...}
        >>> parsed = parse_websocket_message(msg)
        >>> assert isinstance(parsed, TradeMessage)
    """
    event_type = data.get("event_type")
    if not event_type:
        return None

    try:
        if event_type == "trade":
            return TradeMessage(**data)
        elif event_type == "order":
            return OrderMessage(**data)
        elif event_type == "book":
            return BookMessage(**data)
        elif event_type == "price_change":
            return PriceChangeMessage(**data)
        elif event_type == "tick_size_change":
            return TickSizeChangeMessage(**data)
        elif event_type == "last_trade_price":
            return LastTradePriceMessage(**data)
        elif event_type == "best_bid_ask":
            return BestBidAskMessage(**data)
        elif event_type == "new_market":
            return NewMarketMessage(**data)
        elif event_type == "market_resolved":
            return MarketResolvedMessage(**data)
        else:
            return None
    except Exception:
        # If parsing fails, return None
        return None
