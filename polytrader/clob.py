from typing import Any, Literal, Protocol, cast

from py_clob_client.client import ClobClient  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, field_validator

from polytrader.config import CHAIN_ID, CLOB_API_URL, PolymarketSecrets

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


class IClobClient(Protocol):
    """Protocol for CLOB client operations used by the trading system."""

    def get_balance_allowance(self, params: Any) -> dict[str, Any]:
        """Get balance and allowance information."""
        ...

    def create_market_order(self, order_args: Any) -> dict[str, Any]:
        """Create a signed market order."""
        ...

    def post_order(self, signed_order: Any, order_type: Any) -> dict[str, Any]:
        """Post an order to the exchange."""
        ...

    def create_or_derive_api_creds(self) -> Any:
        """Create or derive API credentials."""
        ...

    def set_api_creds(self, creds: Any) -> None:
        """Set API credentials on the client."""
        ...

    def get_orders(self, params: Any) -> list[dict[str, Any]]:
        """Get active orders from Polymarket CLOB.

        Args:
            params: OpenOrderParams with optional filters:
                - market: condition_id
                - id: order_id
                - asset_id: token_id
        Returns:
            List of open order dictionaries
        """
        ...


class IClobClientFactory(Protocol):
    """Protocol for creating CLOB client instances."""

    def __call__(self) -> IClobClient: ...


def create_clob_client_factory(secrets: PolymarketSecrets) -> IClobClientFactory:
    """Create a factory function for ClobClient instances."""

    def factory() -> ClobClient:
        client = ClobClient(
            host=CLOB_API_URL,
            key=secrets.private_key.get_secret_value(),
            chain_id=CHAIN_ID,
            signature_type=secrets.signature_type,
            funder=secrets.funder,
        )
        creds = client.create_or_derive_api_creds()
        client.set_api_creds(creds)
        return client

    return factory
