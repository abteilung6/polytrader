"""Factory function for simple threshold strategy.

Per architecture.mdc: Factory functions create strategy instances from config.
Factory signature matches registry contract:
    factory(config: dict[str, object], store: IMarketDataStore) -> Callable[[str], IStrategy]
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

from polytrader.strategies.base import IStrategy

if TYPE_CHECKING:
    from polytrader.store import IMarketDataStore


def create_simple_threshold_factory(
    config: dict[str, object],
    store: "IMarketDataStore",
) -> Callable[[str], IStrategy]:
    """Create a factory function for SimpleThresholdStrategy.

    Args:
        config: Strategy configuration dictionary (validated against schema)
        store: Market data store for history

    Returns:
        Factory function that takes market_slug and returns IStrategy

    Note:
        Config keys: buy_threshold (float, optional, default=0.30),
                     min_history (int, optional, default=30)
    """
    from polytrader.strategies.simple_threshold.strategy import (
        SimpleThresholdStrategy,
    )

    # Extract parameters with defaults
    # Type assertions are safe because schema validation ensures correct types
    buy_threshold_raw = config.get("buy_threshold", 0.30)
    buy_threshold = (
        float(buy_threshold_raw) if isinstance(buy_threshold_raw, (int, float)) else 0.30
    )

    min_history_raw = config.get("min_history", 30)
    min_history = int(min_history_raw) if isinstance(min_history_raw, (int, float)) else 30

    def factory(market_slug: str) -> IStrategy:
        return SimpleThresholdStrategy(
            market_slug=market_slug,
            store=store,
            buy_threshold=buy_threshold,
            min_history=min_history,
        )

    return factory
