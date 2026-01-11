"""Portfolio construction data models."""

from dataclasses import dataclass
from typing import Any

from polytrader.types import Outcome


@dataclass(frozen=True)
class Target:
    """Target position/exposure for a market outcome.

    Represents the desired exposure before sizing calculation.
    This is an internal model (not an event) used within the portfolio layer.

    Attributes:
        market_slug: Polymarket market identifier
        outcome: Market outcome (UP or DOWN)
        target_exposure: Desired exposure (shares or notional in USD, >= 0)
        rationale: Human-readable explanation of the target
        constraint_binding: List of constraints that clipped the target
        sizing_metadata: Additional sizing computation details
    """

    market_slug: str
    outcome: Outcome
    target_exposure: float  # >= 0.0
    rationale: str
    constraint_binding: list[str]
    sizing_metadata: dict[str, Any]

    def __post_init__(self) -> None:
        """Validate target_exposure is non-negative."""
        if self.target_exposure < 0.0:
            raise ValueError(f"target_exposure must be >= 0.0, got {self.target_exposure}")


@dataclass(frozen=True)
class PortfolioConstraints:
    """Portfolio-level constraints (optional, for future use).

    This can be used to clip targets based on:
    - Max position per market
    - Max capital per market
    - Max total exposure
    - etc.

    For Commit 2, this is a placeholder structure.
    """

    max_position_per_market: float | None = None
    max_capital_per_market: float | None = None
    max_total_exposure: float | None = None

    def clip_target(self, target: Target, current_position: float) -> Target:
        """Clip target based on constraints (future implementation).

        Args:
            target: Original target
            current_position: Current position for this market/outcome

        Returns:
            Clipped target with constraint_binding updated
        """
        # Placeholder: return target unchanged for now
        # Will be implemented in future commits
        return target
