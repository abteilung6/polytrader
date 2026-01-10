"""Event type definitions and base classes."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from polytrader.common.ids import generate_correlation_id, get_run_id

if TYPE_CHECKING:
    from polytrader.risk.models import RiskReasonCode, RiskResult
    from polytrader.types import OrderIntentEvent


class EventSource(str, Enum):
    """Event source component identifier.

    Identifies which component in the trading pipeline emitted the event.
    """

    MDP = "mdp"  # Market Data Plant
    STRATEGY = "strategy"  # Strategy/Alpha
    PORTFOLIO = "portfolio"  # Portfolio Construction
    RISK = "risk"  # Risk Engine
    OMS = "oms"  # Order Management System
    EXECUTION = "execution"  # Execution / Routing
    EXEC = "exec"  # Execution
    POSTTRADE = "posttrade"  # Post-Trade
    OPS = "ops"  # Operations/Control


class Event(BaseModel):
    """Base class for all events in the system.

    All events must include these required fields per observability.md:
    - event_id: Unique identifier for this event instance
    - ts_wall: Wall-clock time in ISO format (UTC)
    - ts_mono: Monotonic timestamp for ordering
    - correlation_id: ID for tracing decision → actions
    - run_id: Process run ID (singleton per process)
    - schema_version: Event schema version
    - source: Component that emitted the event

    Events are immutable (frozen model) and should never be modified
    after creation. This ensures event sourcing integrity.
    """

    # Required fields
    event_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this event instance",
    )
    ts_wall: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="Wall-clock time in ISO format (UTC)",
    )
    ts_mono: float = Field(
        default_factory=time.monotonic,
        description="Monotonic timestamp for ordering",
    )
    correlation_id: str = Field(
        default_factory=generate_correlation_id,
        description="ID for tracing decision → actions",
    )
    run_id: str = Field(
        default_factory=get_run_id,
        description="Process run ID (singleton per process)",
    )
    schema_version: str = Field(
        default="1.0",
        description="Event schema version",
    )
    source: EventSource = Field(
        default=EventSource.OPS,
        description="Component that emitted the event",
    )

    model_config = {
        "frozen": True,  # Immutability for event sourcing
        "validate_assignment": True,  # Validate on assignment
    }


class SystemStartedEvent(Event):
    """Emitted when the system starts.

    This event marks the beginning of a system run and is emitted
    once at process startup. It allows correlating all events from
    a single process execution.
    """

    source: EventSource = Field(default=EventSource.OPS)


class ConfigLoadedEvent(Event):
    """Emitted when configuration is loaded.

    This event records when and what configuration was loaded,
    enabling audit trails and debugging of configuration issues.

    Attributes:
        config_hash: Hash of loaded configuration (for verification)
        config_version: Optional version identifier for the config
    """

    source: EventSource = Field(default=EventSource.OPS)
    config_hash: str = Field(description="Hash of loaded configuration")
    config_version: str | None = Field(default=None, description="Optional version identifier")


class SystemStoppedEvent(Event):
    """Emitted when the system stops.

    This event marks the end of a system run and is emitted
    during graceful shutdown. It allows tracking why and when
    the system stopped.

    Attributes:
        reason: Optional reason for shutdown (e.g., "KeyboardInterrupt", "Error")
    """

    source: EventSource = Field(default=EventSource.OPS)
    reason: str | None = Field(default=None, description="Optional reason for shutdown")


class RiskCheckEvent(Event):
    """Event emitted for every risk check per flows.mdc §6 and observability.mdc §1.

    This event is always emitted (for both allowed and denied orders)
    to provide a complete audit trail of all risk decisions.

    Per flows.mdc §6: Emit RiskCheckEvent ALWAYS.
    Per observability.mdc §1: RiskCheckEvent is a core event type.

    Attributes:
        intent: The order intent that was checked
        result: The risk check result (allowed, reason_codes, projections, metadata)
    """

    source: EventSource = Field(default=EventSource.RISK)

    intent: OrderIntentEvent = Field(description="Order intent that was checked")
    result: RiskResult = Field(description="Risk check result")

    @property
    def allowed(self) -> bool:
        """Convenience property to check if order was allowed."""
        return self.result.allowed

    @property
    def reason_codes(self) -> list[RiskReasonCode]:
        """Convenience property to get reason codes."""
        return self.result.reason_codes


class OrderCreatedEvent(Event):
    """Event emitted when an order is created in the OMS.

    Per flows.mdc §7: OMS creates order and emits OrderCreatedEvent.
    This event marks the beginning of an order's lifecycle.

    Attributes:
        order_id: Internal UUID for the order
        client_order_id: Idempotency key (deterministic from intent)
        intent: Original approved order intent
    """

    source: EventSource = Field(default=EventSource.OMS)

    order_id: str = Field(description="Internal UUID for the order")
    client_order_id: str = Field(description="Idempotency key (deterministic from intent)")
    intent: OrderIntentEvent = Field(description="Original approved order intent")


class OrderSubmittedEvent(Event):
    """Event emitted when an order is submitted to the execution layer.

    Per flows.mdc §7: OMS transitions order to SUBMITTED and emits OrderSubmittedEvent
    when sending SubmitOrderCommand to Execution.

    Attributes:
        order_id: Internal UUID for the order
        client_order_id: Idempotency key
    """

    source: EventSource = Field(default=EventSource.OMS)

    order_id: str = Field(description="Internal UUID for the order")
    client_order_id: str = Field(description="Idempotency key")


class OrderAckEvent(Event):
    """Event emitted when venue acknowledges an order.

    Per flows.mdc §10: OMS receives venue ack and emits OrderAckEvent.
    This event includes the venue_order_id assigned by the venue.

    Attributes:
        order_id: Internal UUID for the order
        venue_order_id: Venue-assigned order ID
    """

    source: EventSource = Field(default=EventSource.OMS)

    order_id: str = Field(description="Internal UUID for the order")
    venue_order_id: str = Field(description="Venue-assigned order ID")


class OrderRejectedEvent(Event):
    """Event emitted when venue rejects an order.

    Per flows.mdc §10: OMS receives venue reject and emits OrderRejectedEvent.
    This event marks the order as REJECTED (terminal state).

    Attributes:
        order_id: Internal UUID for the order
        reason: Rejection reason from venue
    """

    source: EventSource = Field(default=EventSource.OMS)

    order_id: str = Field(description="Internal UUID for the order")
    reason: str = Field(description="Rejection reason from venue")


class FillEvent(Event):
    """Event emitted when an order is filled (partially or fully).

    Per flows.mdc §10: OMS receives fill from venue and emits FillEvent.
    This event represents a single fill (partial or full).

    Attributes:
        order_id: Internal UUID for the parent order
        fill_id: Internal UUID for this fill
        size: Fill size in USD
        price: Fill price
        fee: Fee amount for this fill
        venue_fill_id: Venue-assigned fill ID (if available)
    """

    source: EventSource = Field(default=EventSource.OMS)

    order_id: str = Field(description="Internal UUID for the parent order")
    fill_id: str = Field(description="Internal UUID for this fill")
    size: float = Field(gt=0, description="Fill size in USD")
    price: float = Field(gt=0, le=1, description="Fill price")
    fee: float = Field(ge=0, description="Fee amount for this fill")
    venue_fill_id: str | None = Field(
        default=None, description="Venue-assigned fill ID (if available)"
    )


class OrderCanceledEvent(Event):
    """Event emitted when an order is cancelled.

    Per flows.mdc §7, §10: OMS cancels order and emits OrderCanceledEvent.
    This event marks the order as CANCELLED (terminal state).

    Attributes:
        order_id: Internal UUID for the order
        reason: Optional cancellation reason
    """

    source: EventSource = Field(default=EventSource.OMS)

    order_id: str = Field(description="Internal UUID for the order")
    reason: str | None = Field(default=None, description="Optional cancellation reason")


class ExecutionRequestEvent(Event):
    """Event emitted when execution sends request to venue.

    Per flows.mdc §8: Execution emits structured logs for request/response/latency.

    Attributes:
        order_id: Internal UUID for the order
        client_order_id: Idempotency key
        venue: Venue name (e.g., "polymarket")
        request_type: Type of request (submit, cancel)
    """

    source: EventSource = Field(default=EventSource.EXECUTION)

    order_id: str = Field(description="Internal UUID for the order")
    client_order_id: str = Field(description="Idempotency key")
    venue: str = Field(description="Venue name")
    request_type: str = Field(description="Type of request (submit, cancel)")


class ExecutionResponseEvent(Event):
    """Event emitted when execution receives response from venue.

    Per flows.mdc §8: Execution emits structured logs for request/response/latency.

    Attributes:
        order_id: Internal UUID for the order
        client_order_id: Idempotency key
        venue_order_id: Venue-assigned order ID
        latency_ms: Request latency in milliseconds
        success: Whether request succeeded
    """

    source: EventSource = Field(default=EventSource.EXECUTION)

    order_id: str = Field(description="Internal UUID for the order")
    client_order_id: str = Field(description="Idempotency key")
    venue_order_id: str | None = Field(default=None, description="Venue-assigned order ID")
    latency_ms: float = Field(description="Request latency in milliseconds")
    success: bool = Field(description="Whether request succeeded")


class ExecutionErrorEvent(Event):
    """Event emitted when execution encounters an error.

    Per flows.mdc §8: Execution emits structured logs with error classification.

    Attributes:
        order_id: Internal UUID for the order
        client_order_id: Idempotency key
        error_type: Error classification (retryable, fatal)
        error_message: Error message
        venue: Venue name
    """

    source: EventSource = Field(default=EventSource.EXECUTION)

    order_id: str = Field(description="Internal UUID for the order")
    client_order_id: str = Field(description="Idempotency key")
    error_type: str = Field(description="Error classification (retryable, fatal)")
    error_message: str = Field(description="Error message")
    venue: str = Field(description="Venue name")


# Rebuild models to resolve forward references
# This is needed because OrderCreatedEvent uses OrderIntentEvent
# which is defined in polytrader.types
def _rebuild_models() -> None:
    """Rebuild Pydantic models to resolve forward references."""
    try:
        from polytrader.types import OrderIntentEvent  # noqa: F401

        OrderCreatedEvent.model_rebuild()
    except ImportError:
        # Types module not available yet, will be rebuilt on first use
        pass


# Rebuild on module import
_rebuild_models()
