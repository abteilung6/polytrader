from typing import Any, Protocol

from py_clob_client.client import ClobClient  # type: ignore[import-untyped]
from py_clob_client.clob_types import (  # type: ignore[import-untyped]
    AssetType,
    BalanceAllowanceParams,
    MarketOrderArgs,
    OrderType,
)

from polytrader.config import CHAIN_ID, CLOB_API_URL, PolymarketSecrets


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


def verify_usdc_balance(client: IClobClient, *, required_amount: float) -> float:
    """Verify USDC balance is sufficient for the order.

    Args:
        client: Initialized ClobClient instance
        required_amount: Minimum USDC amount required

    Returns:
        Current USDC balance

    Raises:
        ValueError: If balance is insufficient
    """
    print("\nChecking USDC balance...")
    balance_params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
    balance_info = client.get_balance_allowance(balance_params)
    balance = float(balance_info.get("balance", "0") or "0")

    print(f"Balance: {balance} USDC")
    print("Allowance: Auto-managed (Magic wallet)")

    if balance < required_amount:
        raise ValueError(
            f"Insufficient balance: {balance} USDC < {required_amount} USDC required. "
            "Please deposit USDC to your wallet."
        )

    return balance


def place_market_order(
    client: IClobClient,
    *,
    token_id: str,
    amount: float,
    side: str,
) -> dict[str, Any]:
    """Place a market order on Polymarket.

    Args:
        client: Initialized ClobClient instance
        token_id: Token ID for the market outcome
        amount: Dollar amount to spend (for BUY orders)
        side: Order side (BUY or SELL)

    Returns:
        Order response from the API
    """
    print(f"\nPlacing market order: {amount} USDC...")
    market_order = MarketOrderArgs(
        token_id=token_id,
        amount=amount,
        side=side,
        order_type=OrderType.FOK,
    )
    signed_order = client.create_market_order(market_order)
    response: dict[str, Any] = client.post_order(signed_order, OrderType.FOK)
    return response


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
