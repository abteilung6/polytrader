"""Execution pricing: Limit price calculation.

Per flows.mdc §8: Execution applies pricing rules (bands, passive-first).
"""

from polytrader.types import OrderIntentEvent


def apply_limit_pricing(
    intent: OrderIntentEvent,
    mid_price: float,
    max_buy_slippage_bps: float = 50.0,  # 0.5% default
    max_sell_slippage_bps: float = 50.0,  # 0.5% default
) -> float:
    """Apply limit price rules with slippage bands.

    Per flows.mdc §8: Execution applies price bands:
    - BUY: limit_price <= mid * (1 + max_buy_slippage)
    - SELL: limit_price >= mid * (1 - max_sell_slippage)

    Args:
        intent: Order intent
        mid_price: Current mid price
        max_buy_slippage_bps: Max buy slippage in basis points (default 50 = 0.5%)
        max_sell_slippage_bps: Max sell slippage in basis points (default 50 = 0.5%)

    Returns:
        Adjusted limit price
    """
    if intent.side == "BUY":
        max_price = mid_price * (1.0 + max_buy_slippage_bps / 10000.0)
        return min(intent.limit_price, max_price)
    else:  # SELL
        min_price = mid_price * (1.0 - max_sell_slippage_bps / 10000.0)
        return max(intent.limit_price, min_price)


def should_use_post_only(
    intent: OrderIntentEvent,
    prefer_passive: bool = True,
) -> bool:
    """Determine if order should use post-only (passive) mode.

    Per flows.mdc §8: Execution applies post-only preference.

    Args:
        intent: Order intent
        prefer_passive: Whether to prefer passive orders (default True)

    Returns:
        True if should use post-only, False otherwise
    """
    # For now, always prefer passive if enabled
    # Future: Add logic based on urgency, market conditions, etc.
    return prefer_passive
