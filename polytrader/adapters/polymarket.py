"""Polymarket market data adapter."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

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
    outcome: Outcome
    secrets: PolymarketSecrets
    polling_frequency_hz: float = 1.0


class PolymarketMarketDataAdapter(IMarketDataAdapter):
    """Market data adapter for Polymarket using POST /prices endpoint.

    Fetches bid/ask prices using a single API call per tick.
    """

    def __init__(self, config: PolymarketAdapterConfig) -> None:
        self.config = config
        self.market_slug = config.market_slug
        self.outcome = config.outcome
        self.polling_frequency = config.polling_frequency_hz

        self.gamma = GammaClient()
        self._token_id: str | None = None

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

    def _get_token_id(self) -> str:
        if self._token_id is None:
            market = self.gamma.get_market_by_slug(self.market_slug)
            self._token_id = market.get_token_id(self.outcome)
        return self._token_id

    async def ticks(self) -> AsyncIterator[MarketTick]:
        """Yield market ticks asynchronously.

        Polls the Polymarket API at the configured frequency and yields
        MarketTick objects with bid/ask prices.

        Yields:
            MarketTick: Market data updates

        Raises:
            ValueError: If market or outcome not found
        """
        token_id = self._get_token_id()

        while True:
            try:
                params = [
                    BookParams(token_id=token_id, side="BUY"),
                    BookParams(token_id=token_id, side="SELL"),
                ]
                response = await asyncio.to_thread(self.client.get_prices, params)

                token_prices = unmarshall_token_prices(response, token_id)
                if token_prices is None:
                    logger.warning(f"No prices found for token_id {token_id}")
                    await asyncio.sleep(1.0 / self.polling_frequency)
                    continue

                best_bid = token_prices.get_best_bid()
                best_ask = token_prices.get_best_ask()

                yield MarketTick(
                    ts=time.time(),
                    market_id=self.market_slug,
                    outcome=self.outcome,
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
