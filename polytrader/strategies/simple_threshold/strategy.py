"""Simple threshold strategy implementation."""

from polytrader.events.types import SignalEvent
from polytrader.store import IMarketDataStore
from polytrader.strategies.base import IStrategy
from polytrader.types import MarketDataEvent, Position


class SimpleThresholdStrategy(IStrategy):
    """Simple threshold-based strategy.

    Generates BUY signals when price is below threshold.
    Per flows.mdc §4: Produces SignalEvent (probabilistic scores), not orders.

    This is a stateless, fast strategy optimized for high-frequency trading.
    Evaluation is synchronous and should complete in < 1ms.
    """

    def __init__(
        self,
        market_slug: str,
        store: IMarketDataStore,
        buy_threshold: float = 0.30,
        min_history: int = 30,
    ) -> None:
        """Initialize strategy.

        Args:
            market_slug: Market to trade
            store: Market data store for history
            buy_threshold: Price threshold for BUY signals (0.0 to 1.0)
            min_history: Minimum history ticks required before generating signals
        """
        if not 0.0 <= buy_threshold <= 1.0:
            raise ValueError(f"buy_threshold must be between 0.0 and 1.0, got {buy_threshold}")
        if min_history < 0:
            raise ValueError(f"min_history must be >= 0, got {min_history}")

        self.market_slug = market_slug
        self.store = store
        self.buy_threshold = buy_threshold
        self.min_history = min_history

    def evaluate(
        self,
        market_data: MarketDataEvent,
        positions: dict[tuple[str, str], Position] | None = None,
    ) -> SignalEvent | None:
        """Evaluate market data and produce signal.

        Fast, synchronous evaluation (< 1ms).

        Args:
            market_data: Current market data snapshot
            positions: Current positions (for context, not used in decision)

        Returns:
            SignalEvent if signal generated, None otherwise
        """
        # Filter by market
        if market_data.market_slug != self.market_slug:
            return None

        # Check history requirement
        history = self.store.history(market_data.market_slug, market_data.outcome)
        if len(history) < self.min_history:
            return None

        mid_price = market_data.mid

        # Generate signal if price is attractive (below threshold)
        if mid_price < self.buy_threshold:
            # Calculate probabilities
            # If price is low, UP is more likely to win
            # Simple model: p_up = 1 - price, p_down = price
            p_up = 1.0 - mid_price
            p_down = mid_price

            # Ensure probabilities sum to 1.0 and are in valid range
            p_up = max(0.0, min(1.0, p_up))
            p_down = max(0.0, min(1.0, p_down))
            # Normalize to ensure sum = 1.0
            total = p_up + p_down
            if total > 0:
                p_up = p_up / total
                p_down = p_down / total

            # Calculate edge (how far below threshold)
            edge = self.buy_threshold - mid_price

            # Calculate confidence (normalized edge, clamped to [0, 1])
            # Confidence = edge / threshold (how much below threshold as fraction)
            confidence = min(edge / self.buy_threshold, 1.0) if self.buy_threshold > 0 else 0.0

            return SignalEvent(
                market_slug=market_data.market_slug,
                outcome="UP",  # Always UP for BUY signals
                p_up=p_up,
                p_down=p_down,
                edge=edge,
                confidence=confidence,
                model_id="simple_threshold",
                model_version="1.0.0",
                rationale=(
                    f"Price {mid_price:.4f} below buy threshold {self.buy_threshold:.4f} "
                    f"(edge: {edge:.4f}, confidence: {confidence:.4f})"
                ),
                correlation_id=market_data.correlation_id,
            )

        return None  # No signal

    async def run(self) -> None:
        """Optional background tasks (not needed for stateless strategy)."""
        pass  # No-op

    def stop(self) -> None:
        """Stop background tasks (not needed for stateless strategy)."""
        pass  # No-op
