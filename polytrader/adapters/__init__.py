from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Protocol

from polytrader.types import MarketTick

if TYPE_CHECKING:
    from polytrader.config import PolymarketSecrets


class IMarketDataAdapter(Protocol):
    """Protocol for market data adapters.

    Adapters provide a stream of market ticks asynchronously.
    """

    def ticks(self) -> AsyncIterator[MarketTick]:
        """Yield market ticks asynchronously.

        This is an async generator that yields MarketTick objects
        continuously. The adapter should handle its own connection
        management, error handling, and retry logic.

        Yields:
            MarketTick: Market data updates

        Raises:
            AdapterError: If connection fails and cannot recover
        """
        ...


def create_adapter_factory(
    secrets: "PolymarketSecrets",
    polling_frequency_hz: float = 1.0,
) -> Callable[[str], IMarketDataAdapter]:
    """Create a factory function for IMarketDataAdapter.

    Args:
        secrets: Polymarket secrets configuration
        polling_frequency_hz: Polling frequency in Hz

    Returns:
        Factory function that takes market_slug and returns adapter
    """
    from polytrader.adapters.polymarket import (
        PolymarketAdapterConfig,
        PolymarketMarketDataAdapter,
    )

    def factory(market_slug: str) -> IMarketDataAdapter:
        config = PolymarketAdapterConfig(
            market_slug=market_slug,
            polling_frequency_hz=polling_frequency_hz,
            secrets=secrets,
        )
        return PolymarketMarketDataAdapter(config)

    return factory
