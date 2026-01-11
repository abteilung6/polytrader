"""Convert signals to target positions per flows.mdc §5."""

from polytrader.events.types import SignalEvent
from polytrader.portfolio.models import Target


def convert_signal_to_target(
    signal: SignalEvent,
    fixed_size_usd: float = 1.0,
) -> Target | None:
    """Convert SignalEvent to Target.

    Simple implementation: If signal has positive edge and confidence,
    create a target with fixed size.

    Per flows.mdc §5: Convert scores → target exposure or delta.

    Args:
        signal: SignalEvent from strategy layer
        fixed_size_usd: Fixed size in USD (default: 1.0)

    Returns:
        Target if signal should generate a target, None otherwise

    Note:
        This is a simple pass-through implementation.
        Will be enhanced in Commit 4 with WinnerThresholdProfitTargetStrategy logic.
    """
    # Simple rule: Only generate target if edge > 0 and confidence > 0
    if signal.edge <= 0.0 or signal.confidence <= 0.0:
        return None

    # Determine outcome based on signal
    # If p_up > p_down, target UP; otherwise target DOWN
    from polytrader.types import Outcome

    target_outcome: Outcome = "UP" if signal.p_up > signal.p_down else "DOWN"
    # Simple fixed sizing for now
    target_exposure = fixed_size_usd
    rationale = (
        f"Signal edge {signal.edge:.4f} > 0, confidence {signal.confidence:.4f}, "
        f"applying fixed size {fixed_size_usd:.2f} USD"
    )

    return Target(
        market_slug=signal.market_slug,
        outcome=target_outcome,
        target_exposure=target_exposure,
        rationale=rationale,
        constraint_binding=[],  # No constraints applied yet
        sizing_metadata={
            "signal_edge": signal.edge,
            "signal_confidence": signal.confidence,
            "signal_p_up": signal.p_up,
            "signal_p_down": signal.p_down,
            "size_method": "fixed",
            "fixed_size_usd": fixed_size_usd,
        },
    )
