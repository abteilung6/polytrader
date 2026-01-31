"""Per-strategy performance tracking.

Per Platform_Proposal.md §3.2: Track positions and PnL per strategy
using key (strategy_id, market_slug, outcome).
"""

from typing import TYPE_CHECKING

from polytrader.events.types import FillEvent, MarketDataEvent
from polytrader.obs.metrics import get_metrics_collector
from polytrader.position_manager.outcome_tracker import ClosedPosition, OutcomeTracker
from polytrader.position_manager.performance_metrics import PerformanceMetrics
from polytrader.types import Outcome, Position

if TYPE_CHECKING:
    from polytrader.oms.models import Order


class PerStrategyPerformanceTracker:
    """Tracks performance metrics per strategy.

    Per Platform_Proposal.md §3.2:
    - Track positions per strategy (key: (strategy_id, market_slug, outcome))
    - Calculate PnL per strategy
    - Emit metrics per strategy (strategy_id label)

    Attributes:
        _positions: Dict mapping (strategy_id, market_slug, outcome) -> Position
        _trackers: Dict mapping strategy_id -> OutcomeTracker
        _metrics: Dict mapping strategy_id -> PerformanceMetrics
        _latest_prices: Dict mapping (market_slug, outcome) -> current_mid_price
        _metrics_collector: Metrics collector for emitting metrics
    """

    def __init__(self, starting_equity: float = 1000.0) -> None:
        """Initialize per-strategy performance tracker.

        Args:
            starting_equity: Initial equity for performance metrics calculation
        """
        self._starting_equity = starting_equity

        # Track positions per strategy: (strategy_id, market_slug, outcome) -> Position
        self._positions: dict[tuple[str, str, Outcome], Position] = {}

        # Track cumulative fills per position for partial fills
        # (strategy_id, market_slug, outcome) -> (total_size, total_cost)
        self._position_fills: dict[tuple[str, str, Outcome], tuple[float, float]] = {}

        # Track latest market prices for unrealized P&L calculation
        # (market_slug, outcome) -> current_mid_price
        self._latest_prices: dict[tuple[str, Outcome], float] = {}

        # Outcome trackers and performance metrics per strategy
        self._trackers: dict[str, OutcomeTracker] = {}
        self._metrics: dict[str, PerformanceMetrics] = {}

        self._metrics_collector = get_metrics_collector()

    def get_tracker(self, strategy_id: str) -> OutcomeTracker:
        """Get or create outcome tracker for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            OutcomeTracker for the strategy
        """
        if strategy_id not in self._trackers:
            self._trackers[strategy_id] = OutcomeTracker()
        return self._trackers[strategy_id]

    def get_metrics(self, strategy_id: str) -> PerformanceMetrics:
        """Get or create performance metrics for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            PerformanceMetrics for the strategy
        """
        if strategy_id not in self._metrics:
            tracker = self.get_tracker(strategy_id)
            self._metrics[strategy_id] = PerformanceMetrics(tracker)
        return self._metrics[strategy_id]

    def update_market_price(self, market_data: MarketDataEvent) -> None:
        """Update latest market price for unrealized P&L calculation.

        Args:
            market_data: Market data event with current prices
        """
        key = (market_data.market_slug, market_data.outcome)
        self._latest_prices[key] = market_data.mid

    def record_buy_fill(
        self,
        strategy_id: str,
        market_slug: str,
        outcome: Outcome,
        fill_event: FillEvent,
        order: "Order",
    ) -> None:
        """Record a BUY fill and update position.

        Args:
            strategy_id: Strategy identifier
            market_slug: Market identifier
            outcome: Market outcome
            fill_event: Fill event
            order: Order that was filled
        """
        key = (strategy_id, market_slug, outcome)

        # Update cumulative fills
        if key in self._position_fills:
            total_size, total_cost = self._position_fills[key]
            total_size += fill_event.size
            total_cost += fill_event.size * fill_event.price
        else:
            total_size = fill_event.size
            total_cost = fill_event.size * fill_event.price

        self._position_fills[key] = (total_size, total_cost)

        # Calculate average entry price
        avg_entry_price = total_cost / total_size if total_size > 0 else fill_event.price

        # Get target price from order intent
        target_price = order.intent.target_price

        # Create or update position
        was_existing = key in self._positions
        if was_existing:
            # Update existing position (partial fill)
            position = self._positions[key]
            position.size = total_size
            position.entry_price = avg_entry_price
            # Keep original entry_time and order_id from first fill
        else:
            # Create new position
            position = Position(
                market_slug=market_slug,
                outcome=outcome,
                size=total_size,
                target_price=target_price,
                entry_price=avg_entry_price,
                entry_time=fill_event.ts_mono,
                order_id=order.order_id,
            )
            self._positions[key] = position

        # Emit position metric per strategy per observability.mdc §4
        from polytrader.obs.metrics import set_position_net

        set_position_net(
            market_slug=market_slug,
            outcome=outcome,
            net_position=total_size,
            strategy_id=strategy_id,  # Per-strategy metric
        )

    def record_sell_fill(
        self,
        strategy_id: str,
        market_slug: str,
        outcome: Outcome,
        fill_event: FillEvent,
        order: "Order",
    ) -> tuple[str, ClosedPosition, str, str] | None:
        """Record a SELL fill and close position.

        Args:
            strategy_id: Strategy identifier
            market_slug: Market identifier
            outcome: Market outcome
            fill_event: Fill event
            order: Order that was filled

        Returns:
            (strategy_id, closed_position, order_id, fill_id) when a position
            was closed, else None. Caller may use this to emit StrategyClosedTradeEvent.
        """
        key = (strategy_id, market_slug, outcome)

        if key not in self._positions:
            # No position to close (shouldn't happen, but handle gracefully)
            return None

        position = self._positions.pop(key)
        self._position_fills.pop(key, None)

        # Calculate realized P&L
        exit_price = fill_event.price
        pnl = (exit_price - position.entry_price) * position.size

        # Record closed position in outcome tracker
        tracker = self.get_tracker(strategy_id)
        closed_position = tracker.record_closed_position(
            market_slug=market_slug,
            outcome=outcome,
            entry_price=position.entry_price,
            exit_price=exit_price,
            size=position.size,
            entry_time=position.entry_time,
            exit_time=fill_event.ts_mono,
        )

        # Update performance metrics
        metrics = self.get_metrics(strategy_id)
        metrics.update_metrics()

        # Emit PnL metric per strategy per observability.mdc §4
        from polytrader.obs.metrics import record_pnl_realized

        record_pnl_realized(
            pnl=pnl,
            strategy_id=strategy_id,  # Per-strategy metric
        )

        # Emit position metric (position closed)
        from polytrader.obs.metrics import set_position_net

        set_position_net(
            market_slug=market_slug,
            outcome=outcome,
            net_position=0.0,
            strategy_id=strategy_id,
        )

        return (strategy_id, closed_position, order.order_id, fill_event.fill_id)

    def calculate_unrealized_pnl(self, strategy_id: str) -> float:
        """Calculate unrealized P&L for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            Total unrealized P&L for the strategy
        """
        unrealized = 0.0
        for (sid, market_slug, outcome), position in self._positions.items():
            if sid != strategy_id:
                continue

            # Get current price
            price_key = (market_slug, outcome)
            current_price = self._latest_prices.get(price_key, position.entry_price)

            # Calculate unrealized P&L
            unrealized += (current_price - position.entry_price) * position.size

        return unrealized

    def calculate_realized_pnl(self, strategy_id: str) -> float:
        """Calculate realized P&L for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            Total realized P&L for the strategy
        """
        metrics = self.get_metrics(strategy_id)
        return metrics.get_total_realized_pnl()

    def get_positions(self, strategy_id: str) -> dict[tuple[str, Outcome], Position]:
        """Get all positions for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            Dict mapping (market_slug, outcome) -> Position
        """
        positions: dict[tuple[str, Outcome], Position] = {}
        for (sid, market_slug, outcome), position in self._positions.items():
            if sid == strategy_id:
                positions[(market_slug, outcome)] = position
        return positions

    def get_performance_summary(
        self, strategy_id: str, starting_equity: float | None = None
    ) -> dict[str, float | int | None]:
        """Get performance summary for a strategy.

        Args:
            strategy_id: Strategy identifier
            starting_equity: Starting equity (defaults to instance default)

        Returns:
            Dictionary with performance summary metrics
        """
        equity = starting_equity if starting_equity is not None else self._starting_equity
        metrics = self.get_metrics(strategy_id)
        unrealized = self.calculate_unrealized_pnl(strategy_id)
        return metrics.get_summary(starting_equity=equity, unrealized_pnl=unrealized)

    def list_strategies(self) -> list[str]:
        """List all strategies with tracked positions or closed trades.

        Returns:
            List of strategy IDs
        """
        strategies = set()
        # Add strategies with open positions
        for strategy_id, _, _ in self._positions.keys():
            strategies.add(strategy_id)
        # Add strategies with closed trades
        for strategy_id in self._trackers.keys():
            strategies.add(strategy_id)
        return sorted(strategies)
