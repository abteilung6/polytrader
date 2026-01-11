"""OMS Commands: Requests from OMS to Execution layer.

Per flows.mdc §7, §8: OMS sends commands to Execution.
Commands are distinct from events - they represent requests, not facts.
Commands are mutable and can be retried, unlike events which are immutable facts.
"""

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from polytrader.events.types import OrderIntentEvent
else:
    # Import at runtime for Pydantic model validation
    from polytrader.events.types import OrderIntentEvent


class SubmitOrderCommand(BaseModel):
    """Command from OMS to Execution layer to submit an order.

    Per flows.mdc §7: OMS sends SubmitOrderCommand to Execution after creating order.

    Attributes:
        order_id: Internal UUID for the order
        client_order_id: Idempotency key (for venue)
        intent: Original approved order intent
        correlation_id: Correlation ID for tracing
    """

    order_id: str = Field(description="Internal UUID for the order")
    client_order_id: str = Field(description="Idempotency key (for venue)")
    intent: "OrderIntentEvent" = Field(description="Original approved order intent")
    correlation_id: str = Field(description="Correlation ID for tracing")


class CancelOrderCommand(BaseModel):
    """Command from OMS to Execution layer to cancel an order.

    Per flows.mdc §7: OMS sends CancelOrderCommand to Execution.

    Attributes:
        order_id: Internal UUID for the order
        client_order_id: Idempotency key
        venue_order_id: Venue-assigned order ID (if known)
        reason: Optional cancellation reason
        correlation_id: Correlation ID for tracing
    """

    order_id: str = Field(description="Internal UUID for the order")
    client_order_id: str = Field(description="Idempotency key")
    venue_order_id: str | None = Field(
        default=None, description="Venue-assigned order ID (if known)"
    )
    reason: str | None = Field(default=None, description="Optional cancellation reason")
    correlation_id: str = Field(description="Correlation ID for tracing")


# Rebuild models after imports to resolve forward references
# This is safe because events/types.py doesn't import from oms/commands
SubmitOrderCommand.model_rebuild()
