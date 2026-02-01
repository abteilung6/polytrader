"""Rolling mean and EMA (exponential moving average).

Per model_proposal.md §2.2: anchor = rolling_mean(typical_price, window=96);
ema_fast = EMA(close, 20), ema_slow = EMA(close, 80).
Pure functions; deterministic; no I/O.
"""

from __future__ import annotations


def rolling_mean(values: list[float], window: int) -> list[float]:
    """Compute rolling (simple) mean over a window.

    For each valid starting index k, result[k] = mean(values[k : k+window]).
    Returns only "valid" values: length = max(0, len(values) - window + 1).
    So the last element is the most recent rolling mean.

    Args:
        values: Input series (e.g. typical prices or closes)
        window: Window size (must be >= 1)

    Returns:
        List of rolling means; empty if len(values) < window

    Raises:
        ValueError: If window < 1

    Note:
        Pure function; deterministic.
    """
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    n = len(values)
    if n < window:
        return []
    result: list[float] = []
    for k in range(n - window + 1):
        segment = values[k : k + window]
        result.append(sum(segment) / window)
    return result


def ema(values: list[float], window: int) -> list[float]:
    """Compute exponential moving average.

    Uses alpha = 2 / (window + 1). First value seeds with values[0];
    then EMA[i] = alpha * values[i] + (1 - alpha) * EMA[i-1].
    Result has same length as values.

    Args:
        values: Input series (e.g. close prices)
        window: EMA period (span); must be >= 1

    Returns:
        List of EMA values; same length as values

    Raises:
        ValueError: If window < 1

    Note:
        Pure function; deterministic. First output equals first input.
    """
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    if not values:
        return []
    alpha = 2.0 / (window + 1)
    result: list[float] = [values[0]]
    for i in range(1, len(values)):
        result.append(alpha * values[i] + (1.0 - alpha) * result[i - 1])
    return result
