"""Performance metrics calculation for paper trading.

Calculates aggregate performance statistics from closed positions:
- Win rate
- Average P&L (winning and losing trades)
- Total realized P&L
- Drawdown
- Best/worst trade
- Sharpe ratio (simplified)

Per Commit 4: Outcome Tracker and Performance Metrics
Per observability.mdc §4: Posttrade metrics (pnl_realized, drawdown)
"""

from polytrader.obs.metrics import get_metrics_collector
from polytrader.position_manager.outcome_tracker import ClosedPosition, OutcomeTracker


class PerformanceMetrics:
    """Calculates and tracks performance metrics from closed positions.

    Integrates with metrics system to emit gauges per observability.mdc §4:
    - pnl_realized (gauge)
    - drawdown (gauge)

    Attributes:
        _tracker: Outcome tracker providing closed positions data
        _metrics: Metrics collector for emitting metrics
        _peak_equity: Peak equity value for drawdown calculation
    """

    def __init__(self, tracker: OutcomeTracker) -> None:
        """Initialize performance metrics.

        Args:
            tracker: Outcome tracker to get closed positions from
        """
        self._tracker = tracker
        self._metrics = get_metrics_collector()
        self._peak_equity = 0.0

    def update_metrics(self) -> None:
        """Update all performance metrics and emit to metrics system.

        Should be called after each position close or periodically.
        """
        total_pnl = self._tracker.get_total_realized_pnl()
        drawdown = self._calculate_drawdown(total_pnl)

        # Emit metrics per observability.mdc §4
        self._metrics.set_gauge("pnl_realized", total_pnl)
        self._metrics.set_gauge("drawdown", drawdown)

    def _calculate_drawdown(self, current_equity: float) -> float:
        """Calculate current drawdown from peak equity.

        Drawdown = peak_equity - current_equity
        If current_equity > peak_equity, update peak and return 0.

        Args:
            current_equity: Current equity (starting equity + total P&L)

        Returns:
            Current drawdown (0 if at new peak)
        """
        if current_equity > self._peak_equity:
            self._peak_equity = current_equity
            return 0.0
        return self._peak_equity - current_equity

    def get_win_rate(self) -> float:
        """Calculate win rate (percentage of winning trades).

        Returns:
            Win rate as percentage (0-100), or 0.0 if no trades
        """
        total = self._tracker.get_total_trades()
        if total == 0:
            return 0.0
        wins = len(self._tracker.get_wins())
        return (wins / total) * 100.0

    def get_average_pnl(self) -> float:
        """Calculate average P&L per trade.

        Returns:
            Average P&L across all closed positions, or 0.0 if no trades
        """
        total = self._tracker.get_total_trades()
        if total == 0:
            return 0.0
        return self._tracker.get_total_realized_pnl() / total

    def get_average_win(self) -> float:
        """Calculate average P&L for winning trades.

        Returns:
            Average P&L for winning trades, or 0.0 if no wins
        """
        wins = self._tracker.get_wins()
        if not wins:
            return 0.0
        return sum(p.pnl for p in wins) / len(wins)

    def get_average_loss(self) -> float:
        """Calculate average P&L for losing trades.

        Returns:
            Average P&L for losing trades, or 0.0 if no losses
        """
        losses = self._tracker.get_losses()
        if not losses:
            return 0.0
        return sum(p.pnl for p in losses) / len(losses)

    def get_best_trade(self) -> ClosedPosition | None:
        """Get the best (highest P&L) trade.

        Returns:
            ClosedPosition with highest P&L, or None if no trades
        """
        positions = self._tracker.get_closed_positions()
        if not positions:
            return None
        return max(positions, key=lambda p: p.pnl)

    def get_worst_trade(self) -> ClosedPosition | None:
        """Get the worst (lowest P&L) trade.

        Returns:
            ClosedPosition with lowest P&L, or None if no trades
        """
        positions = self._tracker.get_closed_positions()
        if not positions:
            return None
        return min(positions, key=lambda p: p.pnl)

    def get_total_realized_pnl(self) -> float:
        """Get total realized P&L.

        Returns:
            Sum of all P&L from closed positions
        """
        return self._tracker.get_total_realized_pnl()

    def get_drawdown(self, current_equity: float) -> float:
        """Get current drawdown from peak equity.

        Args:
            current_equity: Current equity (starting equity + total P&L)

        Returns:
            Current drawdown
        """
        return self._calculate_drawdown(current_equity)

    def get_summary(self, starting_equity: float = 0.0) -> dict[str, float | int | None]:
        """Get performance summary statistics.

        Args:
            starting_equity: Starting equity for drawdown calculation

        Returns:
            Dictionary with performance summary metrics
        """
        total_trades = self._tracker.get_total_trades()
        current_equity = starting_equity + self.get_total_realized_pnl()

        best_trade = self.get_best_trade()
        worst_trade = self.get_worst_trade()

        return {
            "total_trades": total_trades,
            "win_rate_pct": self.get_win_rate(),
            "total_realized_pnl": self.get_total_realized_pnl(),
            "average_pnl": self.get_average_pnl(),
            "average_win": self.get_average_win(),
            "average_loss": self.get_average_loss(),
            "best_trade_pnl": best_trade.pnl if best_trade else None,
            "worst_trade_pnl": worst_trade.pnl if worst_trade else None,
            "drawdown": self.get_drawdown(current_equity),
            "peak_equity": self._peak_equity if self._peak_equity > 0 else current_equity,
            "current_equity": current_equity,
        }
