"""Outcome tracker for paper trading performance analysis.

Tracks closed positions and their outcomes (win/loss) for performance metrics.

Per Commit 4: Outcome Tracker and Performance Metrics
- Track each closed position with outcome (win/loss)
- Record P&L per position
- Provide data for performance metrics calculation

Per observability.mdc: Track realized P&L and position outcomes.
"""

from dataclasses import dataclass
from typing import Literal

from polytrader.types import Outcome


@dataclass
class ClosedPosition:
    """Record of a closed position with outcome and P&L.

    Attributes:
        market_slug: Market identifier
        outcome: Market outcome ("UP" or "DOWN")
        entry_price: Price when position was opened
        exit_price: Price when position was closed
        size: Position size in USD
        pnl: Realized profit/loss in USD
        pnl_pct: Realized profit/loss as percentage
        duration_seconds: Time position was held (seconds)
        entry_time: Timestamp when position was opened
        exit_time: Timestamp when position was closed
        result: "WIN" if pnl > 0, "LOSS" if pnl < 0, "BREAKEVEN" if pnl == 0
    """

    market_slug: str
    outcome: Outcome
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    duration_seconds: float
    entry_time: float
    exit_time: float
    result: Literal["WIN", "LOSS", "BREAKEVEN"]

    @classmethod
    def from_position_close(
        cls,
        market_slug: str,
        outcome: Outcome,
        entry_price: float,
        exit_price: float,
        size: float,
        entry_time: float,
        exit_time: float,
    ) -> "ClosedPosition":
        """Create ClosedPosition from position close data.

        Args:
            market_slug: Market identifier
            outcome: Market outcome
            entry_price: Entry price
            exit_price: Exit price
            size: Position size
            entry_time: Entry timestamp
            exit_time: Exit timestamp

        Returns:
            ClosedPosition instance with calculated P&L and result
        """
        pnl = (exit_price - entry_price) * size
        pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0
        duration_seconds = exit_time - entry_time

        if pnl > 0:
            result: Literal["WIN", "LOSS", "BREAKEVEN"] = "WIN"
        elif pnl < 0:
            result = "LOSS"
        else:
            result = "BREAKEVEN"

        return cls(
            market_slug=market_slug,
            outcome=outcome,
            entry_price=entry_price,
            exit_price=exit_price,
            size=size,
            pnl=pnl,
            pnl_pct=pnl_pct,
            duration_seconds=duration_seconds,
            entry_time=entry_time,
            exit_time=exit_time,
            result=result,
        )


class OutcomeTracker:
    """Tracks closed positions and their outcomes.

    Maintains a history of closed positions for performance analysis.
    Provides data for calculating win rate, average P&L, etc.

    Attributes:
        _closed_positions: List of closed positions in chronological order
    """

    def __init__(self) -> None:
        """Initialize the outcome tracker."""
        self._closed_positions: list[ClosedPosition] = []

    def record_closed_position(
        self,
        market_slug: str,
        outcome: Outcome,
        entry_price: float,
        exit_price: float,
        size: float,
        entry_time: float,
        exit_time: float,
    ) -> ClosedPosition:
        """Record a closed position.

        Args:
            market_slug: Market identifier
            outcome: Market outcome
            entry_price: Entry price
            exit_price: Exit price
            size: Position size
            entry_time: Entry timestamp
            exit_time: Exit timestamp

        Returns:
            ClosedPosition instance that was recorded
        """
        closed_position = ClosedPosition.from_position_close(
            market_slug=market_slug,
            outcome=outcome,
            entry_price=entry_price,
            exit_price=exit_price,
            size=size,
            entry_time=entry_time,
            exit_time=exit_time,
        )
        self._closed_positions.append(closed_position)
        return closed_position

    def get_closed_positions(self) -> list[ClosedPosition]:
        """Get all closed positions.

        Returns:
            List of closed positions in chronological order
        """
        return self._closed_positions.copy()

    def get_total_trades(self) -> int:
        """Get total number of closed positions.

        Returns:
            Total number of closed positions
        """
        return len(self._closed_positions)

    def get_wins(self) -> list[ClosedPosition]:
        """Get all winning positions.

        Returns:
            List of closed positions with pnl > 0
        """
        return [p for p in self._closed_positions if p.result == "WIN"]

    def get_losses(self) -> list[ClosedPosition]:
        """Get all losing positions.

        Returns:
            List of closed positions with pnl < 0
        """
        return [p for p in self._closed_positions if p.result == "LOSS"]

    def get_total_realized_pnl(self) -> float:
        """Get total realized P&L across all closed positions.

        Returns:
            Sum of all P&L from closed positions
        """
        return sum(p.pnl for p in self._closed_positions)
