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
