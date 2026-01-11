"""Polymarket market data adapter."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from py_clob_client.client import ClobClient  # type: ignore[import-untyped]
from py_clob_client.clob_types import BookParams  # type: ignore[import-untyped]
from py_clob_client.exceptions import PolyApiException  # type: ignore[import-untyped]

from polytrader.adapters import IMarketDataAdapter
from polytrader.adapters.polymarket.market_data import GammaClient
from polytrader.adapters.prices import unmarshall_token_prices
from polytrader.config import CHAIN_ID, CLOB_API_URL, PolymarketSecrets
from polytrader.events.types import MarketDataEvent
from polytrader.logging_config import logger
from polytrader.types import Outcome


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
        self._consecutive_failures = 0
        self._max_failures = 5  # Emit warning after 5 consecutive 404s

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
            logger.warning("Could not set API credentials: {error}", error=e)

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

    async def ticks(self) -> AsyncIterator[MarketDataEvent]:
        """Yield market data events asynchronously for all configured outcomes.

        Polls the Polymarket API at the configured frequency and yields
        MarketDataEvent objects for each outcome with bid/ask prices.

        Yields:
            MarketDataEvent: Market data updates (one per outcome per polling cycle)

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
                success_count = 0
                for outcome, token_id in token_ids.items():
                    token_prices = unmarshall_token_prices(response, token_id)
                    if token_prices is None:
                        logger.bind(market_slug=self.market_slug, outcome=outcome).warning(
                            "No prices found for token_id {token_id}", token_id=token_id
                        )
                        continue

                    best_bid = token_prices.get_best_bid()
                    best_ask = token_prices.get_best_ask()

                    yield MarketDataEvent(
                        market_slug=self.market_slug,
                        outcome=outcome,
                        best_bid=best_bid,
                        best_ask=best_ask,
                    )
                    success_count += 1

                # Reset failure count on successful tick
                if success_count > 0:
                    self._consecutive_failures = 0

            except PolyApiException as e:
                error_msg = str(e)
                if e.status_code == 404 or "No orderbook exists" in error_msg:
                    self._consecutive_failures += 1
                    if self._consecutive_failures >= self._max_failures:
                        logger.bind(market_slug=self.market_slug).warning(
                            "Market appears expired ({failures} consecutive 404s). "
                            "Supervisor should handle transition.",
                            failures=self._consecutive_failures,
                        )
                    else:
                        logger.bind(market_slug=self.market_slug).debug(
                            "Market inactive or no orderbook. "
                            "Failure count: {current}/{max}. Skipping tick, will retry.",
                            current=self._consecutive_failures,
                            max=self._max_failures,
                        )
                else:
                    self._consecutive_failures = 0  # Reset on non-404 errors
                    logger.exception("API error fetching prices")
            except Exception:
                self._consecutive_failures = 0  # Reset on unexpected errors
                logger.exception("Unexpected error fetching prices")

            await asyncio.sleep(1.0 / self.polling_frequency)
