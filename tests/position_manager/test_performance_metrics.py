"""Tests for PerformanceMetrics."""

from polytrader.position_manager.outcome_tracker import OutcomeTracker
from polytrader.position_manager.performance_metrics import PerformanceMetrics


class TestPerformanceMetrics:
    """Tests for PerformanceMetrics."""

    def test_initial_state(self) -> None:
        """Test initial state of PerformanceMetrics."""
        tracker = OutcomeTracker()
        metrics = PerformanceMetrics(tracker)

        assert metrics.get_win_rate() == 0.0
        assert metrics.get_average_pnl() == 0.0
        assert metrics.get_total_realized_pnl() == 0.0
        assert metrics.get_best_trade() is None
        assert metrics.get_worst_trade() is None

    def test_win_rate(self) -> None:
        """Test win rate calculation."""
        tracker = OutcomeTracker()
        metrics = PerformanceMetrics(tracker)

        # 3 wins, 1 loss
        tracker.record_closed_position(
            market_slug="market1",
            outcome="UP",
            entry_price=0.50,
            exit_price=0.60,
            size=100.0,
            entry_time=1000.0,
            exit_time=2000.0,
        )
        tracker.record_closed_position(
            market_slug="market2",
            outcome="UP",
            entry_price=0.50,
            exit_price=0.55,
            size=100.0,
            entry_time=2000.0,
            exit_time=3000.0,
        )
        tracker.record_closed_position(
            market_slug="market3",
            outcome="UP",
            entry_price=0.50,
            exit_price=0.65,
            size=100.0,
            entry_time=3000.0,
            exit_time=4000.0,
        )
        tracker.record_closed_position(
            market_slug="market4",
            outcome="DOWN",
            entry_price=0.50,
            exit_price=0.40,
            size=100.0,
            entry_time=4000.0,
            exit_time=5000.0,
        )

        win_rate = metrics.get_win_rate()
        assert win_rate == 75.0  # 3 wins out of 4 trades

    def test_average_pnl(self) -> None:
        """Test average P&L calculation."""
        tracker = OutcomeTracker()
        metrics = PerformanceMetrics(tracker)

        tracker.record_closed_position(
            market_slug="market1",
            outcome="UP",
            entry_price=0.50,
            exit_price=0.60,
            size=100.0,
            entry_time=1000.0,
            exit_time=2000.0,
        )
        tracker.record_closed_position(
            market_slug="market2",
            outcome="DOWN",
            entry_price=0.50,
            exit_price=0.40,
            size=100.0,
            entry_time=2000.0,
            exit_time=3000.0,
        )

        avg_pnl = metrics.get_average_pnl()
        assert avg_pnl == 0.0  # (10.0 - 10.0) / 2

    def test_average_win(self) -> None:
        """Test average win calculation."""
        tracker = OutcomeTracker()
        metrics = PerformanceMetrics(tracker)

        tracker.record_closed_position(
            market_slug="market1",
            outcome="UP",
            entry_price=0.50,
            exit_price=0.60,
            size=100.0,
            entry_time=1000.0,
            exit_time=2000.0,
        )
        tracker.record_closed_position(
            market_slug="market2",
            outcome="UP",
            entry_price=0.50,
            exit_price=0.70,
            size=100.0,
            entry_time=2000.0,
            exit_time=3000.0,
        )

        avg_win = metrics.get_average_win()
        assert abs(avg_win - 15.0) < 0.01  # (10.0 + 20.0) / 2

    def test_average_loss(self) -> None:
        """Test average loss calculation."""
        tracker = OutcomeTracker()
        metrics = PerformanceMetrics(tracker)

        tracker.record_closed_position(
            market_slug="market1",
            outcome="DOWN",
            entry_price=0.50,
            exit_price=0.40,
            size=100.0,
            entry_time=1000.0,
            exit_time=2000.0,
        )
        tracker.record_closed_position(
            market_slug="market2",
            outcome="DOWN",
            entry_price=0.50,
            exit_price=0.30,
            size=100.0,
            entry_time=2000.0,
            exit_time=3000.0,
        )

        avg_loss = metrics.get_average_loss()
        assert avg_loss == -15.0  # (-10.0 - 20.0) / 2

    def test_best_and_worst_trade(self) -> None:
        """Test getting best and worst trades."""
        tracker = OutcomeTracker()
        metrics = PerformanceMetrics(tracker)

        tracker.record_closed_position(
            market_slug="market1",
            outcome="UP",
            entry_price=0.50,
            exit_price=0.60,
            size=100.0,
            entry_time=1000.0,
            exit_time=2000.0,
        )
        tracker.record_closed_position(
            market_slug="market2",
            outcome="UP",
            entry_price=0.50,
            exit_price=0.80,
            size=100.0,
            entry_time=2000.0,
            exit_time=3000.0,
        )
        tracker.record_closed_position(
            market_slug="market3",
            outcome="DOWN",
            entry_price=0.50,
            exit_price=0.30,
            size=100.0,
            entry_time=3000.0,
            exit_time=4000.0,
        )

        best = metrics.get_best_trade()
        worst = metrics.get_worst_trade()

        assert best is not None
        assert abs(best.pnl - 30.0) < 0.01  # (0.80 - 0.50) * 100
        assert worst is not None
        assert abs(worst.pnl - (-20.0)) < 0.01  # (0.30 - 0.50) * 100

    def test_drawdown(self) -> None:
        """Test drawdown calculation."""
        tracker = OutcomeTracker()
        metrics = PerformanceMetrics(tracker)

        # Start at 1000
        starting_equity = 1000.0

        # Win: +100
        tracker.record_closed_position(
            market_slug="market1",
            outcome="UP",
            entry_price=0.50,
            exit_price=0.60,
            size=1000.0,
            entry_time=1000.0,
            exit_time=2000.0,
        )
        metrics.update_metrics()

        # Peak should be 1100, drawdown should be 0
        current_equity = starting_equity + metrics.get_total_realized_pnl()
        drawdown = metrics.get_drawdown(current_equity)
        assert drawdown == 0.0

        # Loss: -50 (equity now 1050, peak still 1100)
        tracker.record_closed_position(
            market_slug="market2",
            outcome="DOWN",
            entry_price=0.50,
            exit_price=0.45,
            size=1000.0,
            entry_time=2000.0,
            exit_time=3000.0,
        )
        metrics.update_metrics()

        current_equity = starting_equity + metrics.get_total_realized_pnl()
        drawdown = metrics.get_drawdown(current_equity)
        assert drawdown == 50.0  # 1100 - 1050

    def test_get_summary(self) -> None:
        """Test getting performance summary."""
        tracker = OutcomeTracker()
        metrics = PerformanceMetrics(tracker)

        tracker.record_closed_position(
            market_slug="market1",
            outcome="UP",
            entry_price=0.50,
            exit_price=0.60,
            size=100.0,
            entry_time=1000.0,
            exit_time=2000.0,
        )
        tracker.record_closed_position(
            market_slug="market2",
            outcome="DOWN",
            entry_price=0.50,
            exit_price=0.40,
            size=100.0,
            entry_time=2000.0,
            exit_time=3000.0,
        )

        summary = metrics.get_summary(starting_equity=1000.0)
        assert summary["total_trades"] == 2
        assert summary["win_rate_pct"] == 50.0
        assert summary["total_realized_pnl"] == 0.0
        assert summary["average_pnl"] == 0.0
        assert summary["best_trade_pnl"] is not None
        assert abs(summary["best_trade_pnl"] - 10.0) < 0.01
        assert summary["worst_trade_pnl"] is not None
        assert abs(summary["worst_trade_pnl"] - (-10.0)) < 0.01
        assert summary["current_equity"] == 1000.0
