"""Calculate order size from target (portfolio-aware) per flows.mdc §5."""

from polytrader.portfolio.models import Target
from polytrader.types import Position


def calculate_size(
    target: Target,
    current_position: Position | None = None,
) -> float:
    """Calculate required order size from target.

    Portfolio-aware sizing: Accounts for existing positions.

    Per flows.mdc §5: Compute sizing from targets.

    Args:
        target: Target position/exposure
        current_position: Current position for this market/outcome (optional)

    Returns:
        Required order size in USD (>= 0)

    Note:
        - If no current position: size = target_exposure
        - If current position exists: size = target_exposure - current_position.quantity
        - Size is always >= 0 (no negative sizes for now, no SELL orders)
    """
    if current_position is None:
        # No existing position: size = target_exposure
        return target.target_exposure

    # Portfolio-aware: size = target - current
    # But we don't support SELL orders yet, so size >= 0
    required_size = target.target_exposure - current_position.size

    # Clamp to >= 0 (no negative sizes)
    return max(0.0, required_size)
