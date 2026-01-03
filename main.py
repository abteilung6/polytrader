from polytrader.config import PolymarketSecrets
from polytrader.gamma import GammaClient

# TODO: get live market slug
MARKET_SLUG = "bitcoin-up-or-down-january-3-1pm-et"
OUTCOME = "Up"


if __name__ == "__main__":
    secrets = PolymarketSecrets()
    print("Secrets loaded successfully!")

    gamma = GammaClient()
    market = gamma.get_market_by_slug(MARKET_SLUG)
    token_id = market.get_token_id(OUTCOME)
    print(f"Token ID for '{OUTCOME}': {token_id}")
