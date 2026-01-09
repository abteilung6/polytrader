"""Tests for event store implementations."""

import asyncio
import time

import pytest

from polytrader.common.ids import generate_correlation_id, reset_run_id
from polytrader.events.store import MemoryEventStore
from polytrader.events.types import Event, EventSource


class TestMemoryEventStore:
    """Tests for MemoryEventStore implementation."""

    @pytest.fixture
    def store(self) -> MemoryEventStore:
        """Create a fresh event store for each test."""
        reset_run_id()
        return MemoryEventStore()

    async def test_append_stores_event(self, store: MemoryEventStore) -> None:
        """Test that append stores an event."""
        event = Event(source=EventSource.OPS)

        await store.append(event)

        assert store.count() == 1
        assert store.get_by_id(event.event_id) == event

    async def test_append_is_idempotent(self, store: MemoryEventStore) -> None:
        """Test that appending the same event twice is idempotent."""
        event = Event(source=EventSource.OPS)

        await store.append(event)
        await store.append(event)  # Duplicate

        assert store.count() == 1

    async def test_append_multiple_events(self, store: MemoryEventStore) -> None:
        """Test appending multiple different events."""
        event1 = Event(source=EventSource.OPS)
        event2 = Event(source=EventSource.MDP)
        event3 = Event(source=EventSource.STRATEGY)

        await store.append(event1)
        await store.append(event2)
        await store.append(event3)

        assert store.count() == 3

    async def test_read_stream_all_events(self, store: MemoryEventStore) -> None:
        """Test reading all events from stream."""
        event1 = Event(source=EventSource.OPS)
        event2 = Event(source=EventSource.MDP)
        event3 = Event(source=EventSource.STRATEGY)

        await store.append(event1)
        await store.append(event2)
        await store.append(event3)

        events = list(store.read_stream())
        assert len(events) == 3
        assert event1 in events
        assert event2 in events
        assert event3 in events

    async def test_read_stream_filters_by_type(self, store: MemoryEventStore) -> None:
        """Test filtering events by type."""

        # Create a custom event type
        class CustomEvent(Event):
            custom_field: str = "test"

        event1 = Event(source=EventSource.OPS)
        event2 = CustomEvent(source=EventSource.MDP, custom_field="value")
        event3 = Event(source=EventSource.STRATEGY)

        await store.append(event1)
        await store.append(event2)
        await store.append(event3)

        # Filter by CustomEvent
        custom_events = list(store.read_stream(event_type=CustomEvent))
        assert len(custom_events) == 1
        assert custom_events[0] == event2

        # Filter by base Event
        base_events = list(store.read_stream(event_type=Event))
        assert len(base_events) == 3  # All events are Event instances

    async def test_read_stream_filters_by_time_range(self, store: MemoryEventStore) -> None:
        """Test filtering events by time range."""
        base_time = time.monotonic()

        event1 = Event(source=EventSource.OPS, ts_mono=base_time)
        await asyncio.sleep(0.01)  # Small delay
        event2 = Event(source=EventSource.MDP, ts_mono=time.monotonic())
        await asyncio.sleep(0.01)
        event3 = Event(source=EventSource.STRATEGY, ts_mono=time.monotonic())

        await store.append(event1)
        await store.append(event2)
        await store.append(event3)

        # Filter by time range
        mid_time = event2.ts_mono
        events_in_range = list(store.read_stream(from_ts=mid_time, to_ts=event3.ts_mono))
        assert len(events_in_range) == 2
        assert event2 in events_in_range
        assert event3 in events_in_range
        assert event1 not in events_in_range

    async def test_read_stream_filters_by_correlation_id(self, store: MemoryEventStore) -> None:
        """Test filtering events by correlation_id."""
        correlation_id_1 = generate_correlation_id()
        correlation_id_2 = generate_correlation_id()

        event1 = Event(source=EventSource.OPS, correlation_id=correlation_id_1)
        event2 = Event(source=EventSource.MDP, correlation_id=correlation_id_1)
        event3 = Event(source=EventSource.STRATEGY, correlation_id=correlation_id_2)

        await store.append(event1)
        await store.append(event2)
        await store.append(event3)

        # Filter by correlation_id
        correlated_events = list(store.read_stream(correlation_id=correlation_id_1))
        assert len(correlated_events) == 2
        assert event1 in correlated_events
        assert event2 in correlated_events
        assert event3 not in correlated_events

    async def test_read_stream_combines_filters(self, store: MemoryEventStore) -> None:
        """Test that multiple filters are combined with AND logic."""
        correlation_id = generate_correlation_id()
        base_time = time.monotonic()

        # Event matching all filters
        event1 = Event(
            source=EventSource.OPS,
            correlation_id=correlation_id,
            ts_mono=base_time + 0.1,
        )
        # Event matching some filters
        event2 = Event(
            source=EventSource.MDP,
            correlation_id=correlation_id,
            ts_mono=base_time - 0.1,  # Before from_ts
        )
        # Event matching no filters
        event3 = Event(
            source=EventSource.STRATEGY,
            correlation_id=generate_correlation_id(),  # Different correlation_id
            ts_mono=base_time + 0.2,
        )

        await store.append(event1)
        await store.append(event2)
        await store.append(event3)

        # Combined filters
        filtered = list(
            store.read_stream(
                event_type=Event,
                from_ts=base_time,
                correlation_id=correlation_id,
            )
        )
        assert len(filtered) == 1
        assert filtered[0] == event1

    async def test_replay_sorts_by_ts_mono(self, store: MemoryEventStore) -> None:
        """Test that replay returns events sorted by ts_mono."""
        base_time = time.monotonic()

        # Append events out of order
        event3 = Event(source=EventSource.STRATEGY, ts_mono=base_time + 0.3)
        event1 = Event(source=EventSource.OPS, ts_mono=base_time + 0.1)
        event2 = Event(source=EventSource.MDP, ts_mono=base_time + 0.2)

        await store.append(event3)
        await store.append(event1)
        await store.append(event2)

        # Replay should be sorted
        replayed = list(store.replay())
        assert len(replayed) == 3
        assert replayed[0] == event1
        assert replayed[1] == event2
        assert replayed[2] == event3

    async def test_replay_respects_filters(self, store: MemoryEventStore) -> None:
        """Test that replay respects filters."""
        base_time = time.monotonic()

        event1 = Event(source=EventSource.OPS, ts_mono=base_time)
        await asyncio.sleep(0.01)
        event2 = Event(source=EventSource.MDP, ts_mono=time.monotonic())
        await asyncio.sleep(0.01)
        event3 = Event(source=EventSource.STRATEGY, ts_mono=time.monotonic())

        await store.append(event1)
        await store.append(event2)
        await store.append(event3)

        # Replay with time filter
        mid_time = event2.ts_mono
        replayed = list(store.replay(from_ts=mid_time))
        assert len(replayed) == 2
        assert replayed[0] == event2
        assert replayed[1] == event3

    async def test_clear_removes_all_events(self, store: MemoryEventStore) -> None:
        """Test that clear removes all events."""
        event1 = Event(source=EventSource.OPS)
        event2 = Event(source=EventSource.MDP)

        await store.append(event1)
        await store.append(event2)
        assert store.count() == 2

        store.clear()
        assert store.count() == 0
        assert store.get_by_id(event1.event_id) is None

    async def test_count_returns_correct_number(self, store: MemoryEventStore) -> None:
        """Test that count returns the correct number of events."""
        assert store.count() == 0

        for _ in range(5):
            await store.append(Event(source=EventSource.OPS))

        assert store.count() == 5

    async def test_get_by_id_finds_event(self, store: MemoryEventStore) -> None:
        """Test that get_by_id finds an event by ID."""
        event = Event(source=EventSource.OPS)

        await store.append(event)

        found = store.get_by_id(event.event_id)
        assert found == event

    async def test_get_by_id_returns_none_if_not_found(self, store: MemoryEventStore) -> None:
        """Test that get_by_id returns None for non-existent event."""
        assert store.get_by_id("non-existent-id") is None

    async def test_read_stream_empty_store(self, store: MemoryEventStore) -> None:
        """Test reading from empty store."""
        events = list(store.read_stream())
        assert len(events) == 0

    async def test_replay_empty_store(self, store: MemoryEventStore) -> None:
        """Test replaying from empty store."""
        events = list(store.replay())
        assert len(events) == 0
