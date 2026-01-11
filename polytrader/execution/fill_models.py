"""Fill price calculation models for paper trading.

Per Commit 2: Pure functions for calculating fill prices based on different models.
"""

import random
from enum import Enum

from polytrader.events.types import OrderIntentEvent
from polytrader.store import IMarketDataStore
from polytrader.types import Outcome


class FillModel(str, Enum):
    """Fill simulation models for paper trading.

    Defines how fill prices are calculated:
    - IMMEDIATE: Fill at limit price (optimistic)
    - MID_PRICE: Fill at current mid price (realistic)
    - SLIPPAGE: Fill at mid price with slippage (pessimistic)
    """

    IMMEDIATE = "immediate"  # Fill immediately at limit price
    MID_PRICE = "mid_price"  # Fill at mid price (realistic)
    SLIPPAGE = "slippage"  # Fill with slippage (pessimistic)


def calculate_fill_price(
    model: FillModel,
    intent: OrderIntentEvent,
    store: IMarketDataStore,
    slippage_bps: float = 10.0,
) -> float:
    """Calculate fill price based on fill model.

    Per Commit 2: Pure function for fill price calculation.

    Args:
        model: Fill model to use
        intent: Order intent (contains limit_price, market_slug, outcome)
        store: Market data store (for MID_PRICE and SLIPPAGE models)
        slippage_bps: Slippage in basis points (for SLIPPAGE model, default: 10 bps)

    Returns:
        Fill price (0-1 range)

    Raises:
        ValueError: If MID_PRICE or SLIPPAGE model used but no market data available
    """
    if model == FillModel.IMMEDIATE:
        return intent.limit_price

    if model in (FillModel.MID_PRICE, FillModel.SLIPPAGE):
        # Get latest market data
        outcome: Outcome = intent.outcome
        market_data = store.latest(intent.market_slug, outcome)

        if market_data is None:
            # Fallback to limit price if no market data
            return intent.limit_price

        mid_price = market_data.mid

        if model == FillModel.MID_PRICE:
            return mid_price

        # SLIPPAGE model: add slippage based on side
        slippage = slippage_bps / 10000.0  # Convert bps to decimal

        if intent.side == "BUY":
            # Buy at ask (mid + half spread) + slippage
            fill_price = mid_price + (market_data.spread / 2.0) + slippage
        else:  # SELL
            # Sell at bid (mid - half spread) - slippage
            fill_price = mid_price - (market_data.spread / 2.0) - slippage

        # Clamp to valid range [0, 1]
        return max(0.0, min(1.0, fill_price))

    raise ValueError(f"Unknown fill model: {model}")


def should_fill(fill_probability: float, rng: random.Random | None = None) -> bool:
    """Determine if an order should fill based on probability.

    Per Commit 2: Stochastic fill probability.

    Args:
        fill_probability: Probability of fill (0-1)
        rng: Random number generator (defaults to global random module)

    Returns:
        True if order should fill, False otherwise
    """
    if rng is None:
        return random.random() < fill_probability
    return rng.random() < fill_probability


def should_reject(rejection_probability: float, rng: random.Random | None = None) -> bool:
    """Determine if an order should be rejected based on probability.

    Per Commit 2: Stochastic rejection probability.

    Args:
        rejection_probability: Probability of rejection (0-1)
        rng: Random number generator (defaults to global random module)

    Returns:
        True if order should be rejected, False otherwise
    """
    if rng is None:
        return random.random() < rejection_probability
    return rng.random() < rejection_probability
