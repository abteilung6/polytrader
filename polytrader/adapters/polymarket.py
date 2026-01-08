"""Polymarket market data adapter."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from py_clob_client.client import ClobClient  # type: ignore[import-untyped]
from py_clob_client.clob_types import BookParams  # type: ignore[import-untyped]
from py_clob_client.exceptions import PolyApiException  # type: ignore[import-untyped]

from polytrader.adapters import IMarketDataAdapter
from polytrader.adapters.prices import unmarshall_token_prices
from polytrader.config import CHAIN_ID, CLOB_API_URL, PolymarketSecrets
from polytrader.gamma import GammaClient
from polytrader.types import MarketTick, Outcome

logger = logging.getLogger(__name__)


@dataclass
class PolymarketAdapterConfig:
    market_slug: str
    secrets: PolymarketSecrets
    outcomes: list[Outcome] = field(default_factory=lambda: ["UP", "DOWN"])
    polling_frequency_hz: float = 1.0


class PolymarketMarketDataAdapter(IMarketDataAdapter):
    """Market data adapter for Polymarket using POST /prices endpoint.

    Fetches bid/ask prices for multiple outcomes using batched API calls.
    """

    def __init__(self, config: PolymarketAdapterConfig) -> None:
        self.config = config
        self.market_slug = config.market_slug
        self.outcomes = config.outcomes
        self.polling_frequency = config.polling_frequency_hz

        self.gamma = GammaClient()
        self._token_ids: dict[Outcome, str] = {}

        self.client = ClobClient(
            host=CLOB_API_URL,
            key=config.secrets.private_key.get_secret_value(),
            chain_id=CHAIN_ID,
            signature_type=config.secrets.signature_type,
            funder=config.secrets.funder,
        )

        try:
            creds = self.client.create_or_derive_api_creds()
            self.client.set_api_creds(creds)
        except Exception as e:
            logger.warning(f"Could not set API credentials: {e}")

    def _get_token_ids(self) -> dict[Outcome, str]:
        """Get token IDs for all configured outcomes.

        Returns:
            Dictionary mapping outcome to token_id
        """
        if not self._token_ids:
            market = self.gamma.get_market_by_slug(self.market_slug)
            for outcome in self.outcomes:
                self._token_ids[outcome] = market.get_token_id(outcome)
        return self._token_ids

    async def ticks(self) -> AsyncIterator[MarketTick]:
        """Yield market ticks asynchronously for all configured outcomes.

        Polls the Polymarket API at the configured frequency and yields
        MarketTick objects for each outcome with bid/ask prices.

        Yields:
            MarketTick: Market data updates (one per outcome per polling cycle)

        Raises:
            ValueError: If market or any outcome not found
        """
        token_ids = self._get_token_ids()

        while True:
            try:
                # Batch request for all outcomes
                params = []
                for token_id in token_ids.values():
                    params.extend(
                        [
                            BookParams(token_id=token_id, side="BUY"),
                            BookParams(token_id=token_id, side="SELL"),
                        ]
                    )

                response = await asyncio.to_thread(self.client.get_prices, params)

                # Yield one tick per outcome
                for outcome, token_id in token_ids.items():
                    token_prices = unmarshall_token_prices(response, token_id)
                    if token_prices is None:
                        logger.warning(
                            f"No prices found for token_id {token_id} (outcome: {outcome})"
                        )
                        continue

                    best_bid = token_prices.get_best_bid()
                    best_ask = token_prices.get_best_ask()

                    yield MarketTick(
                        ts=time.time(),
                        market_slug=self.market_slug,
                        outcome=outcome,
                        best_bid=best_bid,
                        best_ask=best_ask,
                    )

            except PolyApiException as e:
                error_msg = str(e)
                if e.status_code == 404 or "No orderbook exists" in error_msg:
                    logger.warning(
                        f"Market inactive or no orderbook: {self.market_slug}. "
                        "Skipping tick, will retry."
                    )
                else:
                    logger.error(f"API error fetching prices: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"Unexpected error fetching prices: {e}", exc_info=True)

            await asyncio.sleep(1.0 / self.polling_frequency)
