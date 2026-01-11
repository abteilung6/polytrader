from typing import Any

from polytrader.adapters.polymarket.market_data import GammaClient
from polytrader.adapters.polymarket.trading import ClobVenueAdapter
from polytrader.clob import create_clob_client_factory
from polytrader.config import PolymarketSecrets
from polytrader.events.types import OrderIntentEvent


async def buy_task(
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
        Order response dictionary (raw_response from VenueResponse)

    Raises:
        ValueError: If market or outcome not found
        RuntimeError: If order placement fails
    """
    if secrets is None:
        secrets = PolymarketSecrets()

    # Create CLOB client factory
    clob_client_factory = create_clob_client_factory(secrets)
    clob_client = clob_client_factory()

    # Create adapter
    gamma_client = GammaClient()
    adapter = ClobVenueAdapter(clob_client=clob_client, gamma_client=gamma_client)

    # Create order intent
    intent = OrderIntentEvent(
        market_slug=market_slug,
        outcome=outcome,
        side="BUY",
        target_price=0.5,  # Not used for market orders
        limit_price=0.5,  # Not used for market orders
        size=amount,
        reason="Manual buy order",
        ttl_s=60.0,
    )

    # Submit order via adapter
    client_order_id = f"buy-{market_slug}-{outcome}-{amount}"
    venue_response = await adapter.submit_order(client_order_id=client_order_id, intent=intent)

    # Return raw response for backward compatibility
    return venue_response.raw_response
