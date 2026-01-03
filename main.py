from py_clob_client.client import ClobClient  # type: ignore[import-untyped]
from py_clob_client.order_builder.constants import BUY  # type: ignore[import-untyped]

from polytrader.clob import place_market_order, verify_usdc_balance
from polytrader.config import CHAIN_ID, CLOB_API_URL, PolymarketSecrets
from polytrader.gamma import GammaClient

MARKET_SLUG = "btc-updown-15m-1767466800"
OUTCOME = "Up"
ORDER_AMOUNT = 1.0


if __name__ == "__main__":
    secrets = PolymarketSecrets()
    print("Secrets loaded successfully!")

    gamma = GammaClient()
    market = gamma.get_market_by_slug(MARKET_SLUG)
    token_id = market.get_token_id(OUTCOME)
    print(f"Token ID for '{OUTCOME}': {token_id}")

    client = ClobClient(
        host=CLOB_API_URL,
        key=secrets.private_key.get_secret_value(),
        chain_id=CHAIN_ID,
        signature_type=secrets.signature_type,
        funder=secrets.funder,
    )

    creds = client.create_or_derive_api_creds()
    client.set_api_creds(creds)

    verify_usdc_balance(client, required_amount=ORDER_AMOUNT)

    response = place_market_order(client, token_id=token_id, amount=ORDER_AMOUNT, side=BUY)
    print(f"Order placed! Response: {response}")
