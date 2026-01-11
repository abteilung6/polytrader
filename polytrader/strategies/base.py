"""Base strategy protocol for fast, stateless signal generation."""

from typing import Protocol, runtime_checkable

from polytrader.events.types import SignalEvent
from polytrader.types import MarketDataEvent, Position


@runtime_checkable
class IStrategy(Protocol):
    """Strategy protocol for fast, stateless signal generation.

    Per flows.mdc §4: Alpha/Signal Layer produces probabilistic scores.
    Strategies are stateless by default and evaluated on-demand.

    Performance:
    - evaluate() should be fast (< 1ms for simple strategies)
    - No async overhead unless strategy needs it
    - Pure functions where possible (deterministic, testable)

    Design:
    - Synchronous evaluate() for fast path (no async overhead)
    - Optional run()/stop() only if strategy needs background tasks
    - Stateless by default (deterministic, testable)
    """

    def evaluate(
        self,
        market_data: MarketDataEvent,
        positions: dict[tuple[str, str], Position] | None = None,
    ) -> SignalEvent | None:
        """Evaluate market data and produce signal.

        This is a FAST, STATELESS function called on-demand by the supervisor.
        It should complete in < 1ms for simple strategies.

        Args:
            market_data: Current market data snapshot
            positions: Current positions dict: (market_slug, outcome) -> Position
                      (optional, for context only, not for decision-making)

        Returns:
            SignalEvent if signal generated, None otherwise

        Note:
            - This is NOT async to minimize overhead (fast path)
            - Strategy should be stateless (deterministic)
            - If strategy needs async operations, it should handle them internally
            - Supervisor controls evaluation frequency (can throttle/skip)
        """
        ...

    async def run(self) -> None:
        """Start the strategy (optional, only if strategy needs background tasks).

        Most strategies don't need this. Only implement if strategy needs:
        - Background model updates (ML models)
        - Periodic data fetching
        - WebSocket subscriptions

        Default implementation: no-op (strategy is stateless)
        """
        ...

    def stop(self) -> None:
        """Stop the strategy (optional, only if strategy has background tasks).

        Default implementation: no-op (strategy is stateless)
        """
        ...
