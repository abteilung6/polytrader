"""Candle aggregation from tick-level market data.

Per VFMR roadmap: Pure, deterministic conversion of MarketDataEvent list
into OHLC candles for strategy indicators. No I/O, no system clock.
"""

from polytrader.indicators.candles.aggregate import aggregate_ticks_to_candles
from polytrader.indicators.candles.models import Candle

__all__ = [
    "Candle",
    "aggregate_ticks_to_candles",
]
