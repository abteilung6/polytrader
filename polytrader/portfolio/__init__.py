"""Portfolio construction layer per flows.mdc §5.

Converts signals to targets, computes sizing, and generates order intents.
"""

from polytrader.portfolio.intents import convert_target_to_intent
from polytrader.portfolio.models import PortfolioConstraints, Target
from polytrader.portfolio.sizing import calculate_size
from polytrader.portfolio.targets import convert_signal_to_target

__all__ = [
    "Target",
    "PortfolioConstraints",
    "convert_signal_to_target",
    "calculate_size",
    "convert_target_to_intent",
]
