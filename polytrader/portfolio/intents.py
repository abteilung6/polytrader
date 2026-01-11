"""Convert targets to order intents per flows.mdc §5."""

from polytrader.events.types import SignalEvent
from polytrader.portfolio.models import Target
from polytrader.types import MarketDataEvent, OrderIntentEvent


def convert_target_to_intent(
    target: Target,
    market_data: MarketDataEvent,
    signal: SignalEvent,
    size: float,
) -> OrderIntentEvent | None:
    """Convert Target to OrderIntentEvent.

    Per flows.mdc §5: Produce OrderIntent objects with side, qty, limit price, etc.

    Args:
        target: Target position/exposure
        market_data: Current market data (for limit_price)
        signal: Original signal (for correlation_id propagation)
        size: Calculated order size (from calculate_size)

    Returns:
        OrderIntentEvent if size > 0, None otherwise

    Note:
        - Always generates BUY orders (no SELL orders yet)
        - Limit price = best_ask for BUY orders
        - Target price = signal-based or mid price
    """
    # No order if size is zero or negative
    if size <= 0.0:
        return None

    # Always BUY for now (no SELL orders)
    side = "BUY"

    # Limit price = best_ask for BUY orders
    limit_price = market_data.best_ask

    # Target price = mid price (simple default)
    # Can be enhanced later with signal-based target pricing
    target_price = market_data.mid

    reason = f"{target.rationale}. Order size: {size:.2f} USD, limit_price: {limit_price:.4f}"

    return OrderIntentEvent(
        market_slug=target.market_slug,
        outcome=target.outcome,
        side=side,
        target_price=target_price,
        limit_price=limit_price,
        size=size,
        reason=reason,
        correlation_id=signal.correlation_id,  # Propagate from signal
        ttl_s=60.0,  # Default TTL
    )
