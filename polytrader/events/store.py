"""Event store for append-only event persistence and replay."""

from abc import ABC, abstractmethod
from collections.abc import Iterator

from polytrader.events.types import Event


class IEventStore(ABC):
    """Abstract base class for event store implementations.

    Event stores provide append-only persistence of events with support
    for filtering and replay. All implementations must be idempotent.
    """

    @abstractmethod
    async def append(self, event: Event) -> None:
        """Append an event to the store (idempotent).

        Args:
            event: The event to append

        Raises:
            ValueError: If event validation fails (implementation-specific)
        """
        ...

    @abstractmethod
    def read_stream(
        self,
        event_type: type[Event] | None = None,
        from_ts: float | None = None,
        to_ts: float | None = None,
        correlation_id: str | None = None,
    ) -> Iterator[Event]:
        """Read events matching filters (lazy iterator).

        Args:
            event_type: Filter by event type (subclass of Event)
            from_ts: Filter by ts_mono >= from_ts
            to_ts: Filter by ts_mono <= to_ts
            correlation_id: Filter by correlation_id

        Yields:
            Events matching all specified filters
        """
        ...

    @abstractmethod
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
        """
        ...


class MemoryEventStore(IEventStore):
    """In-memory event store (Phase 1 implementation).

    Events are stored in a list. For production, use a file-based or
    database-backed implementation.

    This implementation is:
    - Append-only (events never modified)
    - Idempotent (duplicate event_ids are skipped)
    - Thread-safe for single-threaded async (no locks needed)
    - Suitable for testing and small-scale use

    For production scale, consider:
    - FileEventStore (JSONL files)
    - DatabaseEventStore (PostgreSQL, etc.)
    """

    def __init__(self) -> None:
        """Initialize the in-memory event store."""
        self._events: list[Event] = []
        self._event_ids: set[str] = set()  # For O(1) idempotency check

    async def append(self, event: Event) -> None:
        """Append event (idempotent - skip if event_id already exists).

        Args:
            event: The event to append

        Note:
            Duplicate events (same event_id) are silently skipped.
            This ensures idempotency for replay and retry scenarios.
        """
        if event.event_id in self._event_ids:
            return  # Already stored, skip (idempotent)
        self._events.append(event)
        self._event_ids.add(event.event_id)

    def read_stream(
        self,
        event_type: type[Event] | None = None,
        from_ts: float | None = None,
        to_ts: float | None = None,
        correlation_id: str | None = None,
    ) -> Iterator[Event]:
        """Read events matching filters (lazy iterator, unsorted).

        Args:
            event_type: Filter by event type (subclass of Event)
            from_ts: Filter by ts_mono >= from_ts
            to_ts: Filter by ts_mono <= to_ts
            correlation_id: Filter by correlation_id

        Yields:
            Events matching all specified filters (in append order)
        """
        for event in self._events:
            # Type filter
            if event_type and not isinstance(event, event_type):
                continue
            # Time range filter
            if from_ts and event.ts_mono < from_ts:
                continue
            if to_ts and event.ts_mono > to_ts:
                continue
            # Correlation ID filter
            if correlation_id and event.correlation_id != correlation_id:
                continue
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
        events = list(self.read_stream(event_type, from_ts, to_ts))
        yield from sorted(events, key=lambda e: e.ts_mono)

    def clear(self) -> None:
        """Clear all events (for testing only).

        Warning:
            This method should only be used in tests. In production,
            events should never be deleted (append-only principle).
        """
        self._events.clear()
        self._event_ids.clear()

    def count(self) -> int:
        """Get the total number of events in the store.

        Returns:
            Number of events stored
        """
        return len(self._events)

    def get_by_id(self, event_id: str) -> Event | None:
        """Get an event by its event_id.

        Args:
            event_id: The event ID to lookup

        Returns:
            The event if found, None otherwise
        """
        if event_id not in self._event_ids:
            return None
        # Linear search - for large stores, consider indexing
        for event in self._events:
            if event.event_id == event_id:
                return event
        return None
