"""PostgreSQL event store implementation using SQLAlchemy ORM.

Per architecture.mdc §G: Event store is append-only.
Uses JSONB for event-specific fields.

This implementation uses SQLAlchemy ORM for type-safe database operations.
All type conversions (UUID, datetime, JSONB) are handled automatically.
"""

import asyncio
from collections.abc import Iterator
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from polytrader.db.models import EventRecord
from polytrader.db.repository import EventRepository
from polytrader.events.store import IEventStore
from polytrader.events.types import (
    # Import all event types for registry
    CancelRequestedEvent,
    CircuitBreakerEvent,
    ConfigLoadedEvent,
    Event,
    EventSource,
    ExecutionErrorEvent,
    ExecutionPermitEvent,
    ExecutionRequestEvent,
    ExecutionResponseEvent,
    FillEvent,
    KillSwitchEvent,
    MarketChangeEvent,
    MarketDataEvent,
    MarketDiscoveryEvent,
    OrderAckEvent,
    OrderCanceledEvent,
    OrderCreatedEvent,
    OrderExecutedEvent,
    OrderIntentEvent,
    OrderRejectedEvent,
    OrderSubmittedEvent,
    PnLEvent,
    PositionUpdatedEvent,
    ReconcileEvent,
    RiskCheckEvent,
    ServiceErrorEvent,
    ServiceStartedEvent,
    ServiceStoppedEvent,
    SignalEvent,
    SystemStartedEvent,
    SystemStoppedEvent,
    TargetEvent,
    VenueConnectedEvent,
    VenueDisconnectedEvent,
)

if TYPE_CHECKING:
    pass  # Type checking only imports


class EventDbFields(BaseModel):
    """Pydantic model for serialized event fields ready for database insertion.

    This model provides:
    - Type-safe field definitions matching EventRepository.create_event()
    - Automatic validation of field types
    - Clean serialization via model_dump() for **kwargs unpacking
    - Immutability (frozen) for event sourcing safety

    Per architecture.mdc: Events are immutable facts.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    event_id: UUID = Field(description="Unique event identifier")
    ts_wall: datetime = Field(description="Wall-clock time (UTC)")
    ts_mono: float = Field(ge=0, description="Monotonic timestamp for ordering")
    correlation_id: str | None = Field(default=None, description="Correlation ID for tracing")
    run_id: str = Field(description="Process run ID")
    schema_version: str = Field(default="1.0", description="Event schema version")
    source: str = Field(description="Event source component")
    event_type: str = Field(description="Event class name")
    event_data: dict[str, Any] = Field(default_factory=dict, description="Event-specific fields")


# Event class registry for deserialization
_EVENT_CLASS_REGISTRY: dict[str, type[Event]] = {}


def register_event_class(event_class: type[Event]) -> None:
    """Register event class for deserialization.

    Args:
        event_class: Event class to register
    """
    _EVENT_CLASS_REGISTRY[event_class.__name__] = event_class


def get_event_class_by_name(name: str) -> type[Event]:
    """Get event class by name.

    Args:
        name: Event class name (e.g., 'OrderCreatedEvent')

    Returns:
        Event class

    Raises:
        ValueError: If event class not found in registry
    """
    if name not in _EVENT_CLASS_REGISTRY:
        raise ValueError(
            f"Event class '{name}' not found in registry. "
            f"Available classes: {list(_EVENT_CLASS_REGISTRY.keys())}"
        )
    return _EVENT_CLASS_REGISTRY[name]


def _register_all_event_classes() -> None:
    """Register all event classes in the registry.

    This function is called at module import time to populate the registry.
    """
    event_classes: list[type[Event]] = [
        CancelRequestedEvent,
        CircuitBreakerEvent,
        ConfigLoadedEvent,
        ExecutionErrorEvent,
        ExecutionPermitEvent,
        ExecutionRequestEvent,
        ExecutionResponseEvent,
        FillEvent,
        KillSwitchEvent,
        MarketChangeEvent,
        MarketDataEvent,
        MarketDiscoveryEvent,
        OrderAckEvent,
        OrderCanceledEvent,
        OrderCreatedEvent,
        OrderExecutedEvent,
        OrderIntentEvent,
        OrderRejectedEvent,
        OrderSubmittedEvent,
        PnLEvent,
        PositionUpdatedEvent,
        ReconcileEvent,
        RiskCheckEvent,
        ServiceErrorEvent,
        ServiceStartedEvent,
        ServiceStoppedEvent,
        SignalEvent,
        SystemStartedEvent,
        SystemStoppedEvent,
        TargetEvent,
        VenueConnectedEvent,
        VenueDisconnectedEvent,
    ]

    for event_class in event_classes:
        register_event_class(event_class)


# Register all event classes at module import
_register_all_event_classes()


def serialize_event_for_db(event: Event) -> EventDbFields:
    """Serialize an Event to database fields for SQLAlchemy.

    Extracts base Event fields as columns and stores event-specific
    fields in JSONB. Returns a Pydantic model with SQLAlchemy-compatible types:
    - UUID instead of string
    - datetime instead of ISO string
    - dict instead of JSON string

    Args:
        event: The event to serialize

    Returns:
        EventDbFields model ready for database insertion.
        Use .model_dump() to unpack as **kwargs.

    Example:
        >>> event = SystemStartedEvent()
        >>> fields = serialize_event_for_db(event)
        >>> assert isinstance(fields.event_id, UUID)
        >>> assert isinstance(fields.ts_wall, datetime)
        >>> await repo.create_event(**fields.model_dump())
    """
    # Serialize event to dict (JSON mode for consistent string representation)
    event_dict: dict[str, Any] = event.model_dump(mode="json")

    # Extract base fields (these become database columns)
    event_id_str: str = event_dict.pop("event_id")
    ts_wall_str: str = event_dict.pop("ts_wall")
    ts_mono: float = event_dict.pop("ts_mono")
    correlation_id: str | None = event_dict.pop("correlation_id", None)
    run_id: str = event_dict.pop("run_id")
    schema_version: str = event_dict.pop("schema_version", "1.0")
    source: str | EventSource = event_dict.pop("source")

    # Convert EventSource enum to string value
    source_str = source.value if isinstance(source, EventSource) else str(source)

    # Convert to SQLAlchemy-compatible types
    event_id = UUID(event_id_str)
    ts_wall = datetime.fromisoformat(ts_wall_str.replace("Z", "+00:00"))

    # Remaining fields go into event_data JSONB
    return EventDbFields(
        event_id=event_id,
        ts_wall=ts_wall,
        ts_mono=ts_mono,
        correlation_id=correlation_id,
        run_id=run_id,
        schema_version=schema_version,
        source=source_str,
        event_type=type(event).__name__,
        event_data=event_dict,
    )


class PostgreSQLEventStore(IEventStore):
    """PostgreSQL event store using SQLAlchemy ORM.

    Per architecture.mdc §G: Event store is append-only.
    Uses JSONB for event-specific fields.

    Base Event fields are stored as columns for efficient querying.
    Event-specific fields are stored in JSONB column.

    This implementation:
    - Uses SQLAlchemy async engine for connection pooling
    - Implements idempotent append() using ON CONFLICT DO NOTHING
    - Supports filtering by event_type, time range, correlation_id
    - Automatic type conversions (UUID, datetime, JSONB)
    - Requires initialize() to be called before use
    - Requires cleanup() to be called when done (for testing)
    """

    def __init__(self, connection_url: str, pool_size: int = 10) -> None:
        """Initialize PostgreSQL event store.

        Args:
            connection_url: PostgreSQL connection URL (postgresql://... or postgresql+psycopg://...)
            pool_size: Connection pool max size (default: 10)
        """
        # SQLAlchemy handles connection URL normalization
        # Convert postgresql:// to postgresql+psycopg:// for async
        if connection_url.startswith("postgresql://"):
            # SQLAlchemy async needs postgresql+psycopg://
            self._connection_url = connection_url.replace(
                "postgresql://", "postgresql+psycopg://", 1
            )
        else:
            self._connection_url = connection_url

        self._engine: AsyncEngine | None = None
        self._Session: async_sessionmaker[AsyncSession] | None = None
        self._pool_size = pool_size

    async def initialize(self) -> None:
        """Initialize SQLAlchemy engine and verify schema exists."""
        # Create async engine
        self._engine = create_async_engine(
            self._connection_url,
            pool_size=self._pool_size,
            echo=False,  # Set to True for SQL debugging
        )

        # Create session factory
        self._Session = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Verify table exists (or raise error - migrations should be run first)
        # Use run_sync to safely run synchronous inspection in async context
        async with self._engine.connect() as conn:
            table_names = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names()
            )
            if "events" not in table_names:
                raise RuntimeError("Events table not found. Run migrations first: make db-migrate")

    async def append(self, event: Event) -> None:
        """Append event to PostgreSQL (idempotent).

        Args:
            event: The event to append

        Raises:
            RuntimeError: If store not initialized
        """
        if self._Session is None:
            raise RuntimeError("Store not initialized. Call initialize() first.")

        # Serialize event to database fields (returns Pydantic model)
        event_fields = serialize_event_for_db(event)

        # Insert into database using repository (model_dump() for **kwargs unpacking)
        async with self._Session() as session:
            repo = EventRepository(session)
            await repo.create_event(**event_fields.model_dump())

    def read_stream(
        self,
        event_type: type[Event] | None = None,
        from_ts: float | None = None,
        to_ts: float | None = None,
        correlation_id: str | None = None,
    ) -> Iterator[Event]:
        """Read events from PostgreSQL (sync iterator).

        Note: This is a sync method that returns a sync iterator.
        Internally, it uses async queries but fetches all results
        synchronously using asyncio.run().

        Args:
            event_type: Filter by event type (subclass of Event)
            from_ts: Filter by ts_mono >= from_ts
            to_ts: Filter by ts_mono <= to_ts
            correlation_id: Filter by correlation_id

        Yields:
            Events matching all specified filters (in append order)

        Raises:
            RuntimeError: If store not initialized
        """
        if self._Session is None:
            raise RuntimeError("Store not initialized. Call initialize() first.")

        # Fetch all matching events using repository
        async def _fetch_events() -> list[EventRecord]:
            if self._Session is None:
                raise RuntimeError("Store not initialized. Call initialize() first.")

            async with self._Session() as session:
                repo = EventRepository(session)
                return await repo.read_events(
                    event_type=event_type.__name__ if event_type else None,
                    from_ts=from_ts,
                    to_ts=to_ts,
                    correlation_id=correlation_id,
                )

        # Run async query and yield results synchronously
        # Handle both sync and async contexts
        try:
            # Check if we're in an async context (event loop running)
            asyncio.get_running_loop()
            # If we're in an async context, run in a thread with new event loop
            import concurrent.futures

            def run_in_thread() -> list[EventRecord]:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(_fetch_events())
                finally:
                    new_loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                rows = future.result()
        except RuntimeError:
            # No running loop, safe to use asyncio.run()
            rows = asyncio.run(_fetch_events())

        for record in rows:
            # Convert ORM record to Event
            event = self._record_to_event(record)
            yield event

    def replay(
        self,
        event_type: type[Event] | None = None,
        from_ts: float | None = None,
        to_ts: float | None = None,
    ) -> Iterator[Event]:
        """Replay events in chronological order (sorted by ts_mono).

        Args:
            event_type: Filter by event type (subclass of Event)
            from_ts: Filter by ts_mono >= from_ts
            to_ts: Filter by ts_mono <= to_ts

        Yields:
            Events matching filters, sorted by ts_mono (ascending)

        Note:
            This method sorts events by ts_mono to ensure chronological
            replay, which is critical for event sourcing correctness.
        """
        # read_stream already sorts by ts_mono, so we can just use it
        yield from self.read_stream(event_type, from_ts, to_ts)

    def _record_to_event(self, record: EventRecord) -> Event:
        """Convert SQLAlchemy ORM record to Event instance.

        Args:
            record: EventRecord ORM model instance

        Returns:
            Event instance

        Raises:
            ValueError: If event class not found in registry or validation fails
        """
        # Get event class
        event_class = get_event_class_by_name(record.event_type)

        # Convert source string back to EventSource enum
        source_value: EventSource | str
        try:
            source_value = EventSource(record.source)
        except (ValueError, KeyError):
            # If conversion fails, keep as string (will be validated by Pydantic)
            source_value = record.source

        # Build event dict (automatic type conversions from ORM)
        base_fields: dict[str, object] = {
            "event_id": str(record.event_id),  # UUID -> str
            "ts_wall": record.ts_wall.isoformat(),  # datetime -> ISO string
            "ts_mono": float(record.ts_mono),
            "run_id": record.run_id,
            "schema_version": record.schema_version,
            "source": source_value,
        }

        # Only include correlation_id if it's not None (Event model has default_factory)
        if record.correlation_id is not None:
            base_fields["correlation_id"] = record.correlation_id

        # Merge with event_data (already a dict, no JSON parsing needed)
        # SQLAlchemy automatically converts JSONB to dict
        event_dict = {**base_fields, **record.event_data}

        # Special handling for OrderCreatedEvent: convert intent dict to OrderIntentEvent
        if event_class.__name__ == "OrderCreatedEvent":
            if "intent" in event_dict:
                intent_value = event_dict["intent"]
                # If intent is a dict (from JSONB), convert to OrderIntentEvent
                if isinstance(intent_value, dict):
                    event_dict["intent"] = OrderIntentEvent.model_validate(intent_value)
            elif "intent" not in event_dict:
                # Legacy: if intent is missing but we have individual fields, reconstruct
                intent_fields = ["market_slug", "outcome", "side", "limit_price", "size"]
                if all(field in record.event_data for field in intent_fields):
                    intent_dict = {
                        "market_slug": record.event_data.pop("market_slug"),
                        "outcome": record.event_data.pop("outcome"),
                        "side": record.event_data.pop("side"),
                        "limit_price": record.event_data.pop("limit_price"),
                        "size": record.event_data.pop("size"),
                    }
                    # Add optional fields if present
                    for field in ["target_price", "reason", "ttl_s"]:
                        if field in record.event_data:
                            intent_dict[field] = record.event_data.pop(field)

                    event_dict["intent"] = OrderIntentEvent(**intent_dict)

        # Deserialize to Event subclass
        try:
            return event_class.model_validate(event_dict)
        except Exception as e:
            raise ValueError(
                f"Failed to deserialize {event_class.__name__}: {e}. "
                f"Event dict keys: {list(event_dict.keys())}"
            ) from e

    async def cleanup(self) -> None:
        """Clean up connections (for testing).

        Closes the SQLAlchemy engine. Should be called when done with the store.
        """
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._Session = None
