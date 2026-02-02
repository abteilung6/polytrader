"""Pure indicator functions for strategy signal generation.

Per flow.mdc §4: Alpha/Signal layer uses deterministic, testable logic.
All functions in this package are pure: no I/O, no randomness, no system clock.
Indicators live below strategy code (top-level module).
"""

from polytrader.indicators.atr import atr
from polytrader.indicators.primitives import (
    deviation_z,
    fair_price_anchor,
    trend_strength_ema_gap,
)
from polytrader.indicators.rolling import ema, rolling_mean
from polytrader.indicators.typical_price import typical_price

__all__ = [
    "atr",
    "deviation_z",
    "ema",
    "fair_price_anchor",
    "rolling_mean",
    "trend_strength_ema_gap",
    "typical_price",
]
