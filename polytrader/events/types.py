"""Event type definitions and base classes."""

import time
import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field

from polytrader.common.ids import generate_correlation_id, get_run_id


class EventSource(str, Enum):
    """Event source component identifier.

    Identifies which component in the trading pipeline emitted the event.
    """

    MDP = "mdp"  # Market Data Plant
    STRATEGY = "strategy"  # Strategy/Alpha
    PORTFOLIO = "portfolio"  # Portfolio Construction
    RISK = "risk"  # Risk Engine
    OMS = "oms"  # Order Management System
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
