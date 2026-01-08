from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from polytrader.types import MarketTick, Outcome

if TYPE_CHECKING:
    from polytrader.events import EventBus
    from polytrader.store import ITickStore


class ITradingModel(Protocol):
    async def run(self) -> None:
        """Start the trading model."""
        ...

    async def on_tick(self, tick: MarketTick) -> None:
        """Process a market tick."""
        ...

    def stop(self) -> None:
        """Stop the trading model."""
        ...


def create_model_factory(
    bus: "EventBus",
    store: "ITickStore",
    buy_threshold: float = 0.30,
    sell_threshold: float = 0.50,
    size: float = 1.0,
    min_history: int = 30,
    outcomes: set[Outcome] | None = None,
    outcome_thresholds: dict[Outcome, dict[str, float]] | None = None,
) -> Callable[[str], ITradingModel]:
    """Create a factory function for ITradingModel.

    Args:
        bus: Event bus for publishing proposals
        store: Tick store for historical data
        buy_threshold: Buy threshold price
        sell_threshold: Sell threshold price
        size: Trade size in USD
        min_history: Minimum history ticks required
        outcomes: Set of outcomes to trade (default: {"UP", "DOWN"})
        outcome_thresholds: Outcome-specific thresholds

    Returns:
        Factory function that takes market_slug and returns model
    """
    from polytrader.models.simple_threshold import SimpleThresholdModel

    def factory(market_slug: str) -> ITradingModel:
        return SimpleThresholdModel(
            bus=bus,
            store=store,
            market_slug=market_slug,
            outcomes=outcomes,
            buy_threshold=buy_threshold,
            sell_threshold=sell_threshold,
            size=size,
            min_history=min_history,
            outcome_thresholds=outcome_thresholds,
        )

    return factory
