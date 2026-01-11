"""Tests for OutcomeTracker."""

from polytrader.position_manager.outcome_tracker import ClosedPosition, OutcomeTracker


class TestClosedPosition:
    """Tests for ClosedPosition dataclass."""

    def test_from_position_close_win(self) -> None:
        """Test creating ClosedPosition for a winning trade."""
        closed = ClosedPosition.from_position_close(
            market_slug="test-market",
            outcome="UP",
            entry_price=0.50,
            exit_price=0.60,
            size=100.0,
            entry_time=1000.0,
            exit_time=2000.0,
        )

        assert closed.market_slug == "test-market"
        assert closed.outcome == "UP"
        assert closed.entry_price == 0.50
        assert closed.exit_price == 0.60
        assert closed.size == 100.0
        assert abs(closed.pnl - 10.0) < 0.01  # (0.60 - 0.50) * 100
        assert abs(closed.pnl_pct - 20.0) < 0.01  # ((0.60 - 0.50) / 0.50) * 100
        assert closed.duration_seconds == 1000.0
        assert closed.result == "WIN"

    def test_from_position_close_loss(self) -> None:
        """Test creating ClosedPosition for a losing trade."""
        closed = ClosedPosition.from_position_close(
            market_slug="test-market",
            outcome="DOWN",
            entry_price=0.50,
            exit_price=0.40,
            size=100.0,
            entry_time=1000.0,
            exit_time=2000.0,
        )

        assert abs(closed.pnl - (-10.0)) < 0.01  # (0.40 - 0.50) * 100
        assert abs(closed.pnl_pct - (-20.0)) < 0.01
        assert closed.result == "LOSS"

    def test_from_position_close_breakeven(self) -> None:
        """Test creating ClosedPosition for a breakeven trade."""
        closed = ClosedPosition.from_position_close(
            market_slug="test-market",
            outcome="UP",
            entry_price=0.50,
            exit_price=0.50,
            size=100.0,
            entry_time=1000.0,
            exit_time=2000.0,
        )

        assert closed.pnl == 0.0
        assert closed.pnl_pct == 0.0
        assert closed.result == "BREAKEVEN"


class TestOutcomeTracker:
    """Tests for OutcomeTracker."""

    def test_initial_state(self) -> None:
        """Test initial state of OutcomeTracker."""
        tracker = OutcomeTracker()
        assert tracker.get_total_trades() == 0
        assert tracker.get_closed_positions() == []
        assert tracker.get_total_realized_pnl() == 0.0

    def test_record_closed_position(self) -> None:
        """Test recording a closed position."""
        tracker = OutcomeTracker()
        closed = tracker.record_closed_position(
            market_slug="test-market",
            outcome="UP",
            entry_price=0.50,
            exit_price=0.60,
            size=100.0,
            entry_time=1000.0,
            exit_time=2000.0,
        )

        assert closed.result == "WIN"
        assert tracker.get_total_trades() == 1
        assert len(tracker.get_closed_positions()) == 1
        assert abs(tracker.get_total_realized_pnl() - 10.0) < 0.01

    def test_get_wins(self) -> None:
        """Test getting winning positions."""
        tracker = OutcomeTracker()
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

        wins = tracker.get_wins()
        assert len(wins) == 1
        assert wins[0].market_slug == "market1"

    def test_get_losses(self) -> None:
        """Test getting losing positions."""
        tracker = OutcomeTracker()
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

        losses = tracker.get_losses()
        assert len(losses) == 1
        assert losses[0].market_slug == "market2"

    def test_get_total_realized_pnl(self) -> None:
        """Test calculating total realized P&L."""
        tracker = OutcomeTracker()
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

        total_pnl = tracker.get_total_realized_pnl()
        assert total_pnl == 0.0  # 10.0 - 10.0
