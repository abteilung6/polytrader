from typing import Any

from py_clob_client.client import ClobClient  # type: ignore[import-untyped]
from py_clob_client.order_builder.constants import BUY  # type: ignore[import-untyped]

from polytrader.adapters.polymarket.market_data import GammaClient
from polytrader.clob import place_market_order, verify_usdc_balance
from polytrader.config import CHAIN_ID, CLOB_API_URL, PolymarketSecrets


def buy_task(
    market_slug: str,
    outcome: str,
    amount: float,
    secrets: PolymarketSecrets | None = None,
) -> dict[str, Any]:
    """Place a single buy order.

    Args:
        market_slug: Market slug to trade
        outcome: Outcome name (e.g., 'Up', 'Down')
        amount: Order amount in USDC
        secrets: Polymarket secrets (defaults to loading from env)

    Returns:
        Order response dictionary

    Raises:
        ValueError: If market or outcome not found
        RuntimeError: If order placement fails
    """
    if secrets is None:
        secrets = PolymarketSecrets()

    gamma = GammaClient()
    market = gamma.get_market_by_slug(market_slug)
    token_id = market.get_token_id(outcome)

    client = ClobClient(
        host=CLOB_API_URL,
        key=secrets.private_key.get_secret_value(),
        chain_id=CHAIN_ID,
        signature_type=secrets.signature_type,
        funder=secrets.funder,
    )

    creds = client.create_or_derive_api_creds()
    client.set_api_creds(creds)

    verify_usdc_balance(client, required_amount=amount)

    response = place_market_order(client, token_id=token_id, amount=amount, side=BUY)
    return response
