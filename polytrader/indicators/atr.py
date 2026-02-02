"""Average True Range (ATR).

Per model_proposal.md §2.2: atr = ATR(high, low, close, window=14).
Uses Wilder's smoothing (RMA of True Range).
Pure function; deterministic; no I/O.
"""

from __future__ import annotations


def atr(
    high: list[float],
    low: list[float],
    close: list[float],
    window: int,
) -> list[float]:
    """Compute Average True Range (Wilder's ATR).

    True Range:
      TR[0] = high[0] - low[0]
      TR[i] = max(high[i]-low[i], |high[i]-close[i-1]|, |low[i]-close[i-1]|)

    Wilder's ATR (smoothed like RMA):
      First ATR value at index (window-1): ATR[window-1] = mean(TR[0:window])
      Then ATR[i] = (ATR[i-1] * (window-1) + TR[i]) / window

    Result has same length as inputs. Values at indices 0..window-2 are 0.0
    (not enough data); valid ATR starts at index window-1. Caller should use
    result[-1] for latest ATR or result[i] for i >= window-1.

    Args:
        high: High prices (same length as low, close)
        low: Low prices
        close: Close prices
        window: ATR period; must be >= 1

    Returns:
        List of ATR values; same length as high. First (window-1) values are 0.0.

    Raises:
        ValueError: If window < 1 or lengths of high, low, close differ
    """
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    n = len(high)
    if len(low) != n or len(close) != n:
        raise ValueError(
            f"high, low, close must have same length; got {n}, {len(low)}, {len(close)}"
        )
    if n == 0:
        return []

    # True Range
    tr: list[float] = [high[0] - low[0]]
    for i in range(1, n):
        a = high[i] - low[i]
        b = abs(high[i] - close[i - 1])
        c = abs(low[i] - close[i - 1])
        tr.append(max(a, b, c))

    # ATR: first (window-1) slots 0.0; then Wilder smoothing
    result: list[float] = [0.0] * n
    if n < window:
        return result

    # First ATR = simple mean of first `window` TR values
    result[window - 1] = sum(tr[:window]) / window
    for i in range(window, n):
        result[i] = (result[i - 1] * (window - 1) + tr[i]) / window

    return result
