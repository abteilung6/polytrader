"""Factories for creating Order objects in tests.

Per unit_testing_techinical.mdc §5: All domain objects MUST be created via factories.
"""

import uuid

from polytrader.events.types import OrderIntentEvent
from polytrader.oms.models import Order, OrderState
from polytrader.types import Outcome, Side
from tests.factories.events import create_order_intent_event


def create_order(
    state: OrderState = OrderState.NEW,
    market_slug: str = "test-market",
    outcome: Outcome = "UP",
    side: Side = "BUY",
    size: float = 10.0,
    intent: OrderIntentEvent | None = None,
    **kwargs: object,
) -> Order:
    """Create a test Order with deterministic defaults.

    Args:
        state: Order state (default: NEW)
        market_slug: Market identifier
        outcome: Market outcome
        side: Trade side
        size: Order size in USD
        intent: Order intent (defaults to created from params)
        **kwargs: Additional order fields (order_id, client_order_id, correlation_id, etc.)

    Returns:
        Order with specified parameters
    """
    if intent is None:
        correlation_id = kwargs.get("correlation_id")
        intent = create_order_intent_event(
            market_slug=market_slug,
            outcome=outcome,
            side=side,
            size=size,
            correlation_id=correlation_id if isinstance(correlation_id, str) else None,
        )

    return Order(
        order_id=kwargs.get("order_id") or str(uuid.uuid4()),
        client_order_id=kwargs.get("client_order_id") or str(uuid.uuid4()),
        intent=intent,
        market_slug=market_slug,
        outcome=outcome,
        side=side,
        size=size,
        limit_price=intent.limit_price,
        state=state,
        correlation_id=kwargs.get("correlation_id") or intent.correlation_id,
    )
