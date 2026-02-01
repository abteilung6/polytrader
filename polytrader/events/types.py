"""Event type definitions and base classes."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from polytrader.common.ids import generate_correlation_id, get_run_id

# Import domain types (no circular dependency - types.py doesn't import from events)
from polytrader.types import Outcome, Side

if TYPE_CHECKING:
    from polytrader.risk.models import RiskReasonCode, RiskResult


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
    ADAPTER = "adapter"  # Adapters (venue connectivity)


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

    Per flows.mdc §2: SystemStartedEvent includes run_id for correlation.
    The run_id should be explicitly set during boot to ensure all events
    in the same run share the same run_id. If not explicitly set, it uses
    the default from Event base class (get_run_id()).

    Attributes:
        run_id: Process run ID (inherited from Event, can be explicitly set)
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


class VenueConnectedEvent(Event):
    """Emitted when a venue connection is established.

    Per observability.mdc §6: VenueConnectedEvent enables replayability checks.
    This event is emitted when a WebSocket connection to a venue is successfully
    established, allowing the system to track connection state for replay.

    Attributes:
        venue: Venue identifier (e.g., "polymarket")
        connection_type: Type of connection (e.g., "websocket", "rest")
        url: Connection URL (if applicable)
    """

    source: EventSource = Field(default=EventSource.ADAPTER)

    venue: str = Field(description="Venue identifier (e.g., 'polymarket')")
    connection_type: str = Field(description="Type of connection (e.g., 'websocket', 'rest')")
    url: str | None = Field(default=None, description="Connection URL (if applicable)")


class VenueDisconnectedEvent(Event):
    """Emitted when a venue connection is lost.

    Per observability.mdc §6: VenueDisconnectedEvent enables replayability checks.
    This event is emitted when a WebSocket connection to a venue is lost or closed,
    allowing the system to track connection state for replay.

    Attributes:
        venue: Venue identifier (e.g., "polymarket")
        connection_type: Type of connection (e.g., "websocket", "rest")
        reason: Optional reason for disconnection
    """

    source: EventSource = Field(default=EventSource.ADAPTER)

    venue: str = Field(description="Venue identifier (e.g., 'polymarket')")
    connection_type: str = Field(description="Type of connection (e.g., 'websocket', 'rest')")
    reason: str | None = Field(default=None, description="Optional reason for disconnection")


class ServiceStartedEvent(Event):
    """Emitted when a service starts successfully.

    Per observability.mdc §1: All important actions emit events.
    This event tracks service lifecycle for debugging and monitoring.

    Attributes:
        service_name: Name of the service (e.g., "PortfolioService", "RiskChecker")
        supervisor_type: Type of supervisor ("SystemSupervisor" or "MarketSupervisor")
        startup_time_ms: Time taken to start the service in milliseconds
    """

    source: EventSource = Field(default=EventSource.OPS)
    service_name: str = Field(description="Name of the service")
    supervisor_type: str = Field(description="Type of supervisor")
    startup_time_ms: float | None = Field(
        default=None, description="Time taken to start the service (ms)"
    )


class ServiceStoppedEvent(Event):
    """Emitted when a service stops.

    Per observability.mdc §1: All important actions emit events.
    This event tracks service lifecycle for debugging and monitoring.

    Attributes:
        service_name: Name of the service (e.g., "PortfolioService", "RiskChecker")
        supervisor_type: Type of supervisor ("SystemSupervisor" or "MarketSupervisor")
        reason: Optional reason for shutdown
    """

    source: EventSource = Field(default=EventSource.OPS)
    service_name: str = Field(description="Name of the service")
    supervisor_type: str = Field(description="Type of supervisor")
    reason: str | None = Field(default=None, description="Optional reason for shutdown")


class ServiceErrorEvent(Event):
    """Emitted when a service encounters an error.

    Per observability.mdc §1: All important actions emit events.
    This event tracks service errors for debugging and alerting.

    Attributes:
        service_name: Name of the service
        supervisor_type: Type of supervisor
        error_type: Type of error (e.g., "RuntimeError", "ConnectionError")
        error_message: Error message
        error_class: Error classification ("retryable" or "fatal")
    """

    source: EventSource = Field(default=EventSource.OPS)
    service_name: str = Field(description="Name of the service")
    supervisor_type: str = Field(description="Type of supervisor")
    error_type: str = Field(description="Type of error")
    error_message: str = Field(description="Error message")
    error_class: str = Field(description="Error classification (retryable/fatal)")


class SignalEvent(Event):
    """Event emitted by strategy/alpha layer with probabilistic scores.

    Per flows.mdc §4: Alpha/Signal Layer produces probabilistic scores
    (p_up, p_down, edge, confidence).
    This event represents a signal from a trading strategy, NOT an order intent.

    Key properties:
    - Output is NOT an order and contains NO venue details (per flows.mdc §4)
    - Contains probabilistic scores only
    - Model/version identification for auditability
    - Input snapshot reference for replay/debugging

    Attributes:
        market_slug: Polymarket market identifier
        outcome: Market outcome ("UP" or "DOWN")
        p_up: Probability that UP outcome wins (0-1)
        p_down: Probability that DOWN outcome wins (0-1)
        edge: Edge/confidence score (can be negative, no bounds)
        confidence: Confidence level (0-1)
        model_id: Strategy/model identifier (e.g., "simple_threshold")
        model_version: Model version (e.g., "1.0.0")
        snapshot_hash: Hash of input snapshot/features (optional, for replay)
        snapshot_version: Version of input snapshot (optional)
        rationale: Human-readable explanation of the signal
    """

    source: EventSource = Field(default=EventSource.STRATEGY)

    market_slug: str = Field(description="Polymarket market identifier")
    outcome: Outcome = Field(description="Market outcome: UP or DOWN")

    # Probabilistic scores (per flows.mdc §4)
    p_up: float = Field(ge=0.0, le=1.0, description="Probability that UP outcome wins (0-1)")
    p_down: float = Field(
        ge=0.0,
        le=1.0,
        description="Probability that DOWN outcome wins (0-1)",
    )
    edge: float = Field(description="Edge/confidence score (can be negative, no bounds)")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence level (0-1)")

    # Model identification (per observability.mdc §1: strategy_id)
    model_id: str = Field(description="Strategy/model identifier (e.g., 'simple_threshold')")
    model_version: str = Field(description="Model version (e.g., '1.0.0')")

    # Input snapshot reference (optional, per flows.mdc §4)
    snapshot_hash: str | None = Field(
        default=None,
        description="Hash of input snapshot/features (for replay/debugging)",
    )
    snapshot_version: str | None = Field(
        default=None, description="Version of input snapshot (optional)"
    )

    # Rationale (for observability)
    rationale: str = Field(
        description="Human-readable explanation of the signal (e.g., 'Price below threshold')"
    )


class TargetEvent(Event):
    """Event emitted by portfolio construction layer with target exposure.

    Per flows.mdc §5: Portfolio Construction converts signals to target positions/exposures.
    This event represents a target exposure before sizing calculation.

    Key properties:
    - Target exposure (shares or notional in USD)
    - Target rationale (why this target)
    - Constraint binding (which constraints clipped the target)
    - Sizing metadata (computation details)

    Attributes:
        market_slug: Polymarket market identifier
        outcome: Market outcome ("UP" or "DOWN")
        target_exposure: Desired exposure (shares or notional in USD, >= 0)
        target_rationale: Human-readable explanation of the target
        constraint_binding: List of constraints that clipped the target
        sizing_metadata: Additional sizing computation details (flexible dict)
    """

    source: EventSource = Field(default=EventSource.PORTFOLIO)

    market_slug: str = Field(description="Polymarket market identifier")
    outcome: Outcome = Field(description="Market outcome: UP or DOWN")

    # Target exposure (per flows.mdc §5)
    target_exposure: float = Field(
        ge=0.0, description="Desired exposure (shares or notional in USD)"
    )

    # Rationale (per flows.mdc §5)
    target_rationale: str = Field(
        description="Human-readable explanation of the target (e.g., 'Signal edge > 0.1')"
    )

    # Constraint binding (per flows.mdc §5)
    constraint_binding: list[str] = Field(
        default_factory=list,
        description=(
            "List of constraints that clipped the target (e.g., ['max_position', 'capital_limit'])"
        ),
    )

    # Computed sizing terms (per flows.mdc §5)
    sizing_metadata: dict[str, float | str] = Field(
        default_factory=dict,
        description=(
            "Additional sizing computation details "
            "(e.g., {'current_position': 0.0, 'sizing_method': 'fixed'})"
        ),
    )


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

    intent: "OrderIntentEvent" = Field(description="Order intent that was checked")  # noqa: UP037
    result: "RiskResult" = Field(description="Risk check result")  # noqa: UP037

    @property
    def allowed(self) -> bool:
        """Convenience property to check if order was allowed."""
        return self.result.allowed

    @property
    def reason_codes(self) -> "list[RiskReasonCode]":  # noqa: UP037
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


class MarketDiscoveryEvent(Event):
    """Event emitted during market discovery operations.

    Per observability.mdc §1: All important actions emit immutable events.
    This event provides observability for market discovery operations.

    Attributes:
        pattern: Market pattern being searched (e.g., "btc-updown-15m")
        discovered_market: Market slug if found, None otherwise
        search_strategy: Search strategy used (e.g., "current_first")
        windows_checked: Number of windows checked during search
        latency_ms: Discovery latency in milliseconds
        success: Whether discovery was successful
        error: Error message if discovery failed
        error_class: Error classification ("retryable", "fatal", or None)
    """

    source: EventSource = Field(default=EventSource.OPS)

    pattern: str = Field(description="Market pattern being searched")
    discovered_market: str | None = Field(
        default=None, description="Market slug if found, None otherwise"
    )
    search_strategy: str = Field(default="current_first", description="Search strategy used")
    windows_checked: int = Field(ge=0, description="Number of windows checked")
    latency_ms: float = Field(ge=0, description="Discovery latency in milliseconds")
    success: bool = Field(description="Whether discovery was successful")
    error: str | None = Field(default=None, description="Error message if failed")
    error_class: str | None = Field(
        default=None, description="Error classification: 'retryable', 'fatal', or None"
    )


# Market Data Event (moved from types.py to break circular dependency)
class MarketDataEvent(Event):
    """Market data event from the Market Data Plant (MDP).

    Represents a snapshot of the order book for a specific market outcome.
    This is the canonical representation of market data in the system.

    Attributes:
        market_slug: Polymarket market identifier (e.g., "btc-updown-15m-1767900600")
        outcome: Market outcome ("UP" or "DOWN")
        best_bid: Best bid price (highest price buyers are willing to pay)
        best_ask: Best ask price (lowest price sellers are willing to accept)

    Note:
        - Timestamps come from Event base class (ts_wall, ts_mono)
        - Source is automatically set to EventSource.MDP
        - All Event base class fields are inherited (event_id, correlation_id, run_id, etc.)
    """

    source: EventSource = Field(default=EventSource.MDP)

    market_slug: str = Field(description="Polymarket market identifier")
    outcome: Outcome = Field(description="Market outcome: UP or DOWN")
    best_bid: float = Field(
        ge=0, le=1, description="Best bid price (0-1 range, can be 0 if no bid)"
    )
    best_ask: float = Field(
        ge=0, le=1, description="Best ask price (0-1 range, can be 0 if no ask)"
    )

    @property
    def mid(self) -> float:
        """Mid-market price (average of bid and ask).

        This is the fair value estimate between bid and ask.
        """
        return (self.best_bid + self.best_ask) / 2.0

    @property
    def spread(self) -> float:
        """Bid-ask spread (ask - bid).

        Represents the cost of immediate execution (liquidity cost).
        """
        return self.best_ask - self.best_bid

    @property
    def spread_bps(self) -> float:
        """Bid-ask spread in basis points (10000 * spread).

        Useful for comparing liquidity across different price levels.
        """
        return self.spread * 10000


# Order Intent Event (moved from types.py to break circular dependency)
class OrderIntentEvent(Event):
    """Order intent event generated by portfolio construction.

    Represents an intent to place an order, generated by the portfolio
    construction layer (e.g., SimpleThresholdStrategy). This is the canonical
    representation of trading intents in the system.

    Attributes:
        market_slug: Polymarket market identifier
        outcome: Market outcome ("UP" or "DOWN")
        side: Trade side ("BUY" or "SELL")
        target_price: Target price for the trade (e.g., expected exit price)
        limit_price: Limit price for order execution (best_ask for BUY, best_bid for SELL)
        size: Trade size in USD
        reason: Human-readable reason for the intent
        ttl_s: Time-to-live in seconds before intent expires (default: 2.0)
        strategy_id: Strategy identifier (propagated from SignalEvent.model_id)

    Note:
        - Timestamps come from Event base class (ts_wall, ts_mono)
        - Source is automatically set to EventSource.PORTFOLIO
        - All Event base class fields are inherited (event_id, correlation_id, run_id, etc.)
        - strategy_id is propagated from SignalEvent.model_id in portfolio layer
    """

    source: EventSource = Field(default=EventSource.PORTFOLIO)

    market_slug: str = Field(description="Polymarket market identifier")
    outcome: Outcome = Field(description="Market outcome: UP or DOWN")
    side: Side = Field(description="Trade side: BUY or SELL")
    target_price: float = Field(gt=0, le=1, description="Target price for the trade (0-1 range)")
    limit_price: float = Field(
        gt=0, le=1, description="Limit price for order execution (0-1 range)"
    )
    size: float = Field(gt=0, description="Trade size in USD")
    reason: str = Field(description="Human-readable reason for the intent")
    strategy_id: str = Field(description="Strategy identifier (from SignalEvent.model_id)")
    ttl_s: float = Field(
        default=2.0, gt=0, description="Time-to-live in seconds before intent expires"
    )


# Order Executed Event (moved from types.py to break circular dependency)
class OrderExecutedEvent(Event):
    """Order executed event from execution layer.

    Represents an order that has been executed by the ExecutionRouter.
    This is the canonical representation of executed orders in the system.
    Note: This event type may be deprecated in favor of OMS events (OrderAckEvent, FillEvent).

    Attributes:
        market_slug: Polymarket market identifier
        outcome: Market outcome ("UP" or "DOWN")
        side: Trade side ("BUY" or "SELL")
        size: Trade size in USD
        target_price: Target price for position (from intent, None for SELL orders)
        proposal_reason: Original reason from the order intent
        response: Order response from the CLOB API (dict with order_id, status, etc.)

    Note:
        - Timestamps come from Event base class (ts_wall, ts_mono)
        - Source is automatically set to EventSource.EXEC
        - All Event base class fields are inherited (event_id, correlation_id, run_id, etc.)
    """

    source: EventSource = Field(default=EventSource.EXEC)

    market_slug: str = Field(description="Polymarket market identifier")
    outcome: Outcome = Field(description="Market outcome: UP or DOWN")
    side: Side = Field(description="Trade side: BUY or SELL")
    size: float = Field(gt=0, description="Trade size in USD")
    target_price: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Target price for position (from intent, None for SELL orders)",
    )
    proposal_reason: str = Field(description="Original reason from the order intent")
    response: dict = Field(description="Order response from the CLOB API")


# Market Change Event (moved from types.py to break circular dependency)
class MarketChangeEvent(Event):
    """Event published when market transitions.

    Represents a transition from one market to another, typically when
    a market expires and a new one becomes active. This is an operational
    event that triggers component lifecycle changes.

    Attributes:
        old_market: Previous market slug (None if initial market)
        new_market: New market slug (required)

    Note:
        - Timestamps come from Event base class (ts_wall, ts_mono)
        - Source is automatically set to EventSource.OPS
        - All Event base class fields are inherited (event_id, correlation_id, run_id, etc.)
    """

    source: EventSource = Field(default=EventSource.OPS)

    old_market: str | None = Field(
        default=None, description="Previous market slug (None if initial)"
    )
    new_market: str = Field(description="New market slug")


class ReconcileEvent(Event):
    """Event emitted when reconciliation detects divergence between OMS and venue.

    Per flows.mdc §12: Reconciliation compares venue truth vs OMS projection
    and emits ReconcileEvent for any divergences detected.

    Attributes:
        divergence_type: Type of divergence detected
        order_id: Internal order ID (if applicable)
        venue_order_id: Venue order ID (if applicable)
        severity: Severity level (INFO, WARNING, ERROR)
        details: Dictionary with divergence details (diff, expected, actual, etc.)

    Note:
        - Timestamps come from Event base class (ts_wall, ts_mono)
        - Source is automatically set to EventSource.OPS
        - All Event base class fields are inherited (event_id, correlation_id, run_id, etc.)
    """

    source: EventSource = Field(default=EventSource.OPS)

    divergence_type: Literal["phantom_order", "orphan_order", "fill_mismatch", "none"] = Field(
        description="Type of divergence detected"
    )
    order_id: str | None = Field(default=None, description="Internal order ID (if applicable)")
    venue_order_id: str | None = Field(default=None, description="Venue order ID (if applicable)")
    severity: Literal["INFO", "WARNING", "ERROR"] = Field(
        description="Severity level of the divergence"
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary with divergence details (diff, expected, actual, etc.)",
    )


class StrategyStateTransitionEvent(Event):
    """Event emitted when a strategy instance transitions between lifecycle states.

    Per observability.mdc §1: All state transitions must emit events.
    This event provides an audit trail for strategy lifecycle changes, enabling
    replay, debugging, and correlation of logs/metrics/events.

    Per Commit 12: StrategyStateTransitionEvent includes all necessary fields
    for deterministic replay and incident debugging.

    Attributes:
        strategy_id: Unique strategy instance identifier
        from_state: Previous lifecycle state
        to_state: New lifecycle state
        reason: Optional human-readable reason for the transition
        deployment_id: UUID for each activation (correlates logs/metrics/events)

    Note:
        - Timestamps come from Event base class (ts_wall, ts_mono)
        - Source is automatically set to EventSource.OPS
        - run_id comes from Event base class (process run_id when strategy is active)
        - All Event base class fields are inherited (event_id, correlation_id, etc.)
    """

    source: EventSource = Field(default=EventSource.OPS)

    strategy_id: str = Field(min_length=1, description="Unique strategy instance identifier")
    from_state: str = Field(
        min_length=1, description="Previous lifecycle state (STOPPED, STARTING, RUNNING, etc.)"
    )
    to_state: str = Field(
        min_length=1, description="New lifecycle state (STOPPED, STARTING, RUNNING, etc.)"
    )
    reason: str | None = Field(default=None, description="Optional reason for the transition")
    deployment_id: str | None = Field(
        default=None, description="UUID for each activation (correlates logs/metrics/events)"
    )


class CircuitBreakerEvent(Event):
    """Event emitted when circuit breaker triggers or resets.

    Per flows.mdc §13: Circuit breakers trigger on severe divergence or system issues
    and emit CircuitBreakerEvent to disable execution.

    Attributes:
        breaker_type: Type of circuit breaker (reconcile_divergence, data_stale, error_rate)
        triggered: True if circuit breaker triggered, False if reset
        reason: Human-readable reason for trigger/reset
        details: Dictionary with additional context (thresholds, counts, etc.)

    Note:
        - Timestamps come from Event base class (ts_wall, ts_mono)
        - Source is automatically set to EventSource.OPS
        - All Event base class fields are inherited (event_id, correlation_id, run_id, etc.)
    """

    source: EventSource = Field(default=EventSource.OPS)

    breaker_type: Literal["reconcile_divergence", "data_stale", "error_rate"] = Field(
        description="Type of circuit breaker"
    )
    triggered: bool = Field(description="True if triggered, False if reset")
    reason: str = Field(description="Human-readable reason for trigger/reset")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary with additional context (thresholds, counts, etc.)",
    )


class ExecutionPermitEvent(Event):
    """Event emitted when execution is enabled.

    Per flows.mdc §2: Execution is only enabled after all health gates pass.
    This event records when and why execution was enabled, providing an audit trail.

    Attributes:
        permit_type: Type of permit ("boot", "manual", "health_reset")
        reason: Human-readable reason for enabling execution
        health_status: Snapshot of health status at permit time (dict with health metrics)
        issued_by: Who issued the permit ("system" | "operator")

    Note:
        - Timestamps come from Event base class (ts_wall, ts_mono)
        - Source is automatically set to EventSource.OPS
        - All Event base class fields are inherited (event_id, correlation_id, run_id, etc.)
    """

    source: EventSource = Field(default=EventSource.OPS)

    permit_type: Literal["boot", "manual", "health_reset"] = Field(
        description="Type of execution permit"
    )
    reason: str = Field(description="Human-readable reason for enabling execution")
    health_status: dict[str, Any] = Field(
        default_factory=dict,
        description="Snapshot of health status at permit time (health metrics)",
    )
    issued_by: Literal["system", "operator"] = Field(
        default="system", description="Who issued the permit"
    )


class KillSwitchEvent(Event):
    """Event emitted when kill switch is triggered or reset.

    Per flows.mdc §13: Kill switch provides immediate stop-trading + cancel-open-orders policy.
    This event records when and why the kill switch was triggered.

    Attributes:
        triggered: True if kill switch triggered, False if reset
        reason: Human-readable reason for trigger/reset
        cancel_open_orders: Whether to cancel open orders when triggered
        triggered_by: Who triggered the kill switch ("system" | "operator" | "circuit_breaker")
        details: Dictionary with additional context (order counts, etc.)

    Note:
        - Timestamps come from Event base class (ts_wall, ts_mono)
        - Source is automatically set to EventSource.OPS
        - All Event base class fields are inherited (event_id, correlation_id, run_id, etc.)
    """

    source: EventSource = Field(default=EventSource.OPS)

    triggered: bool = Field(description="True if triggered, False if reset")
    reason: str = Field(description="Human-readable reason for trigger/reset")
    cancel_open_orders: bool = Field(
        default=True, description="Whether to cancel open orders when triggered"
    )
    triggered_by: Literal["system", "operator", "circuit_breaker"] = Field(
        description="Who triggered the kill switch"
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary with additional context (order counts, etc.)",
    )


class ControlCommandEvent(Event):
    """Event emitted when control command is applied.

    Per Platform_Proposal.md §2.4.2: ControlCommandEvent records when control commands
    are processed by the control plane service. This provides an audit trail for
    execution control and strategy activation changes.

    Attributes:
        command_id: Command identifier (UUID as string)
        command_type: Type of command (enable_execution, disable_execution, etc.)
        strategy_id: Strategy identifier (None for enable/disable commands)
        reason: Reason for the command
        issued_by: User/system that issued the command
        client_request_id: Client request ID for idempotency tracking (optional)
        status: Command status (pending, applied, failed)
        error_message: Error message if command failed (optional)
        expected_version: Version that was expected (for optimistic concurrency)
        actual_version: Version after application (for optimistic concurrency)

    Note:
        - Timestamps come from Event base class (ts_wall, ts_mono)
        - Source is automatically set to EventSource.OPS
        - All Event base class fields are inherited (event_id, correlation_id, run_id, etc.)
    """

    source: EventSource = Field(default=EventSource.OPS)

    command_id: str = Field(description="Command identifier (UUID as string)")
    command_type: Literal[
        "enable_execution",
        "disable_execution",
        "add_active_strategy",
        "remove_active_strategy",
    ] = Field(description="Type of command")
    strategy_id: str | None = Field(
        default=None, description="Strategy identifier (None for enable/disable commands)"
    )
    reason: str = Field(description="Reason for the command")
    issued_by: str = Field(description="User/system that issued the command")
    client_request_id: str | None = Field(
        default=None, description="Client request ID for idempotency tracking"
    )
    status: Literal["pending", "applied", "failed"] = Field(description="Command status")
    error_message: str | None = Field(default=None, description="Error message if command failed")
    expected_version: int | None = Field(
        default=None, description="Version that was expected (for optimistic concurrency)"
    )
    actual_version: int | None = Field(
        default=None, description="Version after application (for optimistic concurrency)"
    )


class PositionUpdatedEvent(Event):
    """Event emitted when a position is updated.

    Per flows.mdc §11: Post-Trade updates positions from FillEvents and emits PositionUpdatedEvent.
    Per observability.mdc §1: PositionUpdatedEvent is a core event type.

    This event is emitted whenever a position changes:
    - New position created (from BUY fill)
    - Position updated (from additional BUY fills)
    - Position reduced (from SELL fill)
    - Position closed (from SELL fill that closes position)

    Attributes:
        market_slug: Polymarket market identifier
        outcome: Market outcome ("UP" or "DOWN")
        net_position: Net position size (positive for long, negative for short, 0 for closed)
        size: Current position size in USD (absolute value of net_position)
        entry_price: Average entry price for the position
        target_price: Target price to sell at (if applicable)
        entry_time: Timestamp when position was first opened
        order_id: ID of the order that caused this update
        update_type: Type of update ("created", "updated", "reduced", "closed")
    """

    source: EventSource = Field(default=EventSource.POSTTRADE)

    market_slug: str = Field(description="Polymarket market identifier")
    outcome: Outcome = Field(description="Market outcome: UP or DOWN")
    net_position: float = Field(
        description="Net position size (positive for long, negative for short, 0 for closed)"
    )
    size: float = Field(ge=0, description="Current position size in USD (absolute value)")
    entry_price: float = Field(gt=0, le=1, description="Average entry price for the position")
    target_price: float | None = Field(
        default=None, ge=0, le=1, description="Target price to sell at (if applicable)"
    )
    entry_time: float = Field(description="Timestamp when position was first opened")
    order_id: str | None = Field(
        default=None, description="ID of the order that caused this update"
    )
    update_type: Literal["created", "updated", "reduced", "closed"] = Field(
        description="Type of position update"
    )


class PnLEvent(Event):
    """Event emitted when PnL is calculated or updated.

    Per flows.mdc §11: Post-Trade updates realized/unrealized PnL and emits PnLEvent.
    Per observability.mdc §1: PnLEvent is a core event type.

    This event is emitted periodically or when PnL changes significantly:
    - After position updates
    - After market price updates (for unrealized PnL)
    - After position closes (for realized PnL)

    Attributes:
        realized_pnl: Realized P&L from closed positions (USD)
        unrealized_pnl: Unrealized P&L from open positions (USD)
        total_pnl: Total P&L (realized + unrealized)
        position_count: Number of open positions
        update_reason: Reason for this PnL update ("position_update", "price_update", "periodic")
    """

    source: EventSource = Field(default=EventSource.POSTTRADE)

    realized_pnl: float = Field(default=0.0, description="Realized P&L from closed positions (USD)")
    unrealized_pnl: float = Field(
        default=0.0, description="Unrealized P&L from open positions (USD)"
    )
    total_pnl: float = Field(description="Total P&L (realized + unrealized)")
    position_count: int = Field(ge=0, description="Number of open positions")
    update_reason: Literal["position_update", "price_update", "periodic"] = Field(
        description="Reason for this PnL update"
    )


class StrategyClosedTradeEvent(Event):
    """Event emitted when a strategy closes a position (realized trade).

    Per proposal-past-performance-tab.md: Emitted by post-trade layer when a
    position is closed so past-performance API can read closed trades by strategy_id.
    Enables audit trail and equity curve derivation without replaying all fills.

    Attributes:
        strategy_id: Strategy instance identifier
        market_slug: Polymarket market identifier
        outcome: Market outcome ("UP" or "DOWN")
        entry_price: Average entry price for the position
        exit_price: Fill price when position was closed
        size: Position size in USD
        pnl: Realized P&L in USD
        pnl_pct: Realized P&L as percentage
        entry_time: Monotonic timestamp when position was opened
        exit_time: Monotonic timestamp when position was closed
        result: "WIN" if pnl > 0, "LOSS" if pnl < 0, "BREAKEVEN" if pnl == 0
        execution_mode: "paper" or "live"
        order_id: Internal order UUID that caused the close (empty for market-expiry)
        fill_id: Internal fill UUID for the closing fill (empty for market-expiry)
    """

    source: EventSource = Field(default=EventSource.POSTTRADE)

    strategy_id: str = Field(min_length=1, description="Strategy instance identifier")
    market_slug: str = Field(description="Polymarket market identifier")
    outcome: Outcome = Field(description="Market outcome: UP or DOWN")
    entry_price: float = Field(gt=0, le=1, description="Average entry price for the position")
    exit_price: float = Field(
        ge=0,
        le=1,
        description="Fill/settlement price when position was closed (0 allowed for settlement)",
    )
    size: float = Field(gt=0, description="Position size in USD")
    pnl: float = Field(description="Realized P&L in USD")
    pnl_pct: float = Field(description="Realized P&L as percentage")
    entry_time: float = Field(description="Monotonic timestamp when position was opened")
    exit_time: float = Field(description="Monotonic timestamp when position was closed")
    result: Literal["WIN", "LOSS", "BREAKEVEN"] = Field(
        description="WIN if pnl > 0, LOSS if pnl < 0, BREAKEVEN if pnl == 0"
    )
    execution_mode: Literal["paper", "live"] = Field(description="Execution mode: paper or live")
    order_id: str = Field(
        description="Internal order UUID that caused the close (empty for market-expiry)"
    )
    fill_id: str = Field(
        description="Internal fill UUID for the closing fill (empty for market-expiry)"
    )


class CancelRequestedEvent(Event):
    """Event emitted when a cancel request is made.

    Per observability.mdc §1: CancelRequestedEvent is a core event type.
    This event is emitted when a cancel command is received, before the actual cancellation.

    Attributes:
        order_id: Internal UUID for the order
        client_order_id: Idempotency key
        reason: Optional cancellation reason
        requested_by: Who requested the cancel ("system", "operator", "strategy")
    """

    source: EventSource = Field(default=EventSource.OMS)

    order_id: str = Field(description="Internal UUID for the order")
    client_order_id: str = Field(description="Idempotency key")
    reason: str | None = Field(default=None, description="Optional cancellation reason")
    requested_by: Literal["system", "operator", "strategy"] = Field(
        default="system", description="Who requested the cancel"
    )
