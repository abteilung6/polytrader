"""Semantic signal primitives composing raw indicators.

Per VFMR_STRATEGY_ROADMAP §5: primitives describe what is (volatility, anchor, trend);
strategies define what to do. Pure functions; deterministic; no I/O.
"""

from __future__ import annotations

from polytrader.indicators.candles.models import Candle
from polytrader.indicators.rolling import ema, rolling_mean
from polytrader.indicators.typical_price import typical_price


def deviation_z(value: float, anchor: float, scale: float) -> float:
    """Z-score of value relative to anchor, scaled by volatility.

    deviation_z = (value - anchor) / scale when scale > 0; else 0.0.
    Used for mean-reversion entry/exit (e.g. z >= entry_z → signal).

    Args:
        value: Current price or level (e.g. close).
        anchor: Fair price / anchor (e.g. rolling mean of typical price).
        scale: Volatility scale (e.g. ATR); must be > 0 for non-zero result.

    Returns:
        Z-score; 0.0 if scale <= 0 (guarded).

    Note:
        Pure function; deterministic.
    """
    if scale <= 0:
        return 0.0
    return (value - anchor) / scale


def fair_price_anchor(candles: list[Candle], method: str, window: int) -> list[float]:
    """Compute fair-price anchor series from OHLC candles.

    Supported method: "rolling_mean" — rolling mean of typical price
    (high + low + close) / 3 over window. Result aligned to candle indices:
    first (window - 1) values are 0.0 (warmup); then one anchor per candle.

    Args:
        candles: OHLC candles (order preserved).
        method: Anchor method; only "rolling_mean" supported.
        window: Rolling window size; must be >= 1.

    Returns:
        List of length len(candles). Indices 0..window-2 are 0.0;
        indices window-1..n-1 are rolling mean of typical price.

    Raises:
        ValueError: If window < 1 or method not supported.

    Note:
        Pure function; deterministic. Reuses typical_price and rolling_mean.
    """
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    if method != "rolling_mean":
        raise ValueError(f"method must be 'rolling_mean', got {method!r}")
    if not candles:
        return []

    typical_prices = [typical_price(c.high, c.low, c.close) for c in candles]
    rm = rolling_mean(typical_prices, window)
    # Align: result[i] = 0.0 for i < window-1; result[window-1+k] = rm[k]
    result: list[float] = [0.0] * (window - 1) + rm
    return result


def trend_strength_ema_gap(
    close_series: list[float],
    fast: int,
    slow: int,
    volatility_series: list[float],
) -> list[float]:
    """Trend strength as |EMA_fast - EMA_slow| / volatility at each index.

    Used for regime gate: trend_ok = (trend_strength <= threshold).
    When volatility <= 0 at an index, returns 0.0 at that index (guarded).

    Args:
        close_series: Close prices (same length as volatility_series).
        fast: EMA fast period (e.g. 20).
        slow: EMA slow period (e.g. 80).
        volatility_series: Volatility scale per index (e.g. ATR); same length.

    Returns:
        List of length len(close_series). Each element is
        abs(ema_fast[i] - ema_slow[i]) / volatility_series[i], or 0.0 if vol <= 0.

    Raises:
        ValueError: If fast < 1, slow < 1, or lengths differ.

    Note:
        Pure function; deterministic. Reuses ema from indicators.
    """
    if fast < 1:
        raise ValueError(f"fast must be >= 1, got {fast}")
    if slow < 1:
        raise ValueError(f"slow must be >= 1, got {slow}")
    n = len(close_series)
    if len(volatility_series) != n:
        raise ValueError(
            f"close_series and volatility_series must have same length; "
            f"got {n}, {len(volatility_series)}"
        )
    if n == 0:
        return []

    ema_fast = ema(close_series, fast)
    ema_slow = ema(close_series, slow)
    result: list[float] = []
    for i in range(n):
        vol = volatility_series[i]
        if vol <= 0:
            result.append(0.0)
        else:
            gap = abs(ema_fast[i] - ema_slow[i])
            result.append(gap / vol)
    return result
