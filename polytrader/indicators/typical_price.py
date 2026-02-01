"""Typical price: (high + low + close) / 3 for a single candle.

Per model_proposal.md §2.2: anchor uses rolling_mean(typical_price, window=96).
Pure function; deterministic; no I/O.
"""


def typical_price(high: float, low: float, close: float) -> float:
    """Compute typical price for one candle.

    Typical price = (high + low + close) / 3.
    Used as price proxy when OHLC is available (e.g. for anchor/VWAP approximation).

    Args:
        high: High price
        low: Low price
        close: Close price

    Returns:
        Typical price (float)

    Note:
        Pure function; no side effects. Caller must ensure high, low, close are valid.
    """
    return (high + low + close) / 3.0
