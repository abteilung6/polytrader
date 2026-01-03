from typing import Any

from py_clob_client.client import ClobClient  # type: ignore[import-untyped]
from py_clob_client.clob_types import (  # type: ignore[import-untyped]
    AssetType,
    BalanceAllowanceParams,
    MarketOrderArgs,
    OrderType,
)


def verify_usdc_balance(client: ClobClient, *, required_amount: float) -> float:
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
    client: ClobClient,
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
