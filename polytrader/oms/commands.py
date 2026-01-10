"""OMS Commands: Requests from OMS to Execution layer.

Per flows.mdc §7, §8: OMS sends commands to Execution.
Commands are distinct from events - they represent requests, not facts.
Commands are mutable and can be retried, unlike events which are immutable facts.
"""

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from polytrader.types import OrderIntentEvent


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


# Rebuild models to resolve forward references
# This is needed because SubmitOrderCommand uses OrderIntentEvent
# which is defined in polytrader.types
def _rebuild_models() -> None:
    """Rebuild Pydantic models to resolve forward references."""
    try:
        from polytrader.types import OrderIntentEvent  # noqa: F401

        SubmitOrderCommand.model_rebuild()
    except ImportError:
        # Types module not available yet, will be rebuilt on first use
        pass


# Rebuild on module import
_rebuild_models()
