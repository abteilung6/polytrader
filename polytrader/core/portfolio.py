"""Portfolio representation and management."""

from dataclasses import dataclass, field

from polytrader.core.position import Position
from polytrader.types import Outcome


@dataclass
class Portfolio:
    """Represents a trading portfolio."""

    balance: float  # USDC balance
    positions: dict[tuple[str, Outcome], Position] = field(default_factory=dict)

    def get_position(self, market_id: str, outcome: Outcome) -> Position | None:
        """Get position for a specific market and outcome."""
        return self.positions.get((market_id, outcome))

    def add_position(self, market_id: str, outcome: Outcome, quantity: float, price: float) -> None:
        """Add or update a position."""
        key = (market_id, outcome)
        if key in self.positions:
            # Update existing position
            pos = self.positions[key]
            total_cost = (pos.quantity * pos.avg_price) + (quantity * price)
            total_quantity = pos.quantity + quantity
            pos.quantity = total_quantity
            pos.avg_price = total_cost / total_quantity if total_quantity > 0 else 0.0
        else:
            # Create new position
            self.positions[key] = Position(
                market_id=market_id,
                outcome=outcome,
                quantity=quantity,
                avg_price=price,
            )

    def get_total_value(self, prices: dict[tuple[str, Outcome], float]) -> float:
        """Calculate total portfolio value including positions."""
        total = self.balance
        for (market_id, outcome), position in self.positions.items():
            current_price = prices.get((market_id, outcome), position.avg_price)
            total += position.quantity * current_price
        return total

