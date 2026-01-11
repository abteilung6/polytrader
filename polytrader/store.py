from collections import deque
from typing import Protocol

from polytrader.events.types import MarketDataEvent
from polytrader.types import Outcome


class IMarketDataStore(Protocol):
    """Protocol for market data store implementations."""

    def add(self, event: MarketDataEvent) -> None:
        """Add a market data event to the store."""
        ...

    def latest(self, market_slug: str, outcome: Outcome) -> MarketDataEvent | None:
        """Get the latest market data event for a market/outcome."""
        ...

    def history(self, market_slug: str, outcome: Outcome) -> list[MarketDataEvent]:
        """Get history of market data events for a market/outcome."""
        ...


class MemoryMarketDataStore(IMarketDataStore):
    """In-memory store for market data events.

    Stores MarketDataEvent instances keyed by market_slug and outcome.
    Provides efficient access to latest market data for portfolio construction.
    """

    def __init__(self, window: int = 3000) -> None:
        """Initialize the market data store.

        Args:
            window: Maximum number of events to keep per market/outcome
        """
        self.window = window
        self._events: dict[tuple[str, Outcome], deque[MarketDataEvent]] = {}

    def add(self, event: MarketDataEvent) -> None:
        """Add a market data event to the store.

        Args:
            event: Market data event to store
        """
        key = (event.market_slug, event.outcome)
        self._events.setdefault(key, deque(maxlen=self.window)).append(event)

    def latest(self, market_slug: str, outcome: Outcome) -> MarketDataEvent | None:
        """Get the latest market data event for a market/outcome.

        Args:
            market_slug: Market identifier
            outcome: Market outcome

        Returns:
            Latest market data event, or None if no events exist
        """
        key = (market_slug, outcome)
        d = self._events.get(key)
        return d[-1] if d else None

    def history(self, market_slug: str, outcome: Outcome) -> list[MarketDataEvent]:
        """Get history of market data events for a market/outcome.

        Args:
            market_slug: Market identifier
            outcome: Market outcome

        Returns:
            List of market data events (oldest first)
        """
        key = (market_slug, outcome)
        return list(self._events.get(key, []))
