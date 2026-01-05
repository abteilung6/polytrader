from collections.abc import AsyncIterator
from typing import Protocol

from polytrader.types import MarketTick


class IMarketDataAdapter(Protocol):
    """Protocol for market data adapters.

    Adapters provide a stream of market ticks asynchronously.
    """

    async def ticks(self) -> AsyncIterator[MarketTick]:
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
