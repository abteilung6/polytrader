"""Candle (OHLC) model for aggregated tick data.

Per model_proposal.md §2.2: VFMR uses 15m candles with open, high, low, close.
ts_start is the interval start (UTC) for bucketing and ordering.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Candle:
    """Single OHLC candle from aggregated ticks.

    Attributes:
        open: First mid price in the interval
        high: Maximum mid price in the interval
        low: Minimum mid price in the interval
        close: Last mid price in the interval
        ts_start: Start of the interval (UTC); used for bucketing
    """

    open: float
    high: float
    low: float
    close: float
    ts_start: datetime
