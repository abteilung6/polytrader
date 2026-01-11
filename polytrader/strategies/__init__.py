"""Strategy layer per flows.mdc §4.

Strategies produce SignalEvent (probabilistic scores), not orders.
Optimized for fast decision-making in high-frequency trading scenarios.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

from polytrader.strategies.base import IStrategy
from polytrader.strategies.simple_threshold import SimpleThresholdStrategy

if TYPE_CHECKING:
    from polytrader.store import IMarketDataStore

__all__ = ["IStrategy", "SimpleThresholdStrategy", "create_simple_threshold_factory"]


def create_simple_threshold_factory(
    store: "IMarketDataStore",
    buy_threshold: float = 0.30,
    min_history: int = 30,
) -> Callable[[str], IStrategy]:
    """Create a factory function for SimpleThresholdStrategy.

    Args:
        store: Market data store for history
        buy_threshold: Price threshold for BUY signals (0.0 to 1.0)
        min_history: Minimum history ticks required before generating signals

    Returns:
        Factory function that takes market_slug and returns IStrategy
    """

    def factory(market_slug: str) -> IStrategy:
        return SimpleThresholdStrategy(
            market_slug=market_slug,
            store=store,
            buy_threshold=buy_threshold,
            min_history=min_history,
        )

    return factory
