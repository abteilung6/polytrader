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
