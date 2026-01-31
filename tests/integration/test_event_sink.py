"""Integration tests for EventSink.

Tests EventSink functionality with real PostgreSQL database.
"""

import asyncio
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.db.repository import EventRepository
from polytrader.events.bus import EventBus
from polytrader.events.sink import EventSink
from polytrader.events.stores import PostgreSQLEventStore
from polytrader.events.types import (
    OrderCreatedEvent,
    OrderIntentEvent,
    SystemStartedEvent,
)


@pytest.fixture
async def event_sink(postgres_test_url: str, postgres_db: None) -> AsyncGenerator[EventSink, None]:
    """Create EventSink for testing."""
    from sqlalchemy import text

    # Migrations are run by postgres_db fixture

    # Create event bus and store
    store = PostgreSQLEventStore(connection_url=postgres_test_url, pool_size=5)
    await store.initialize()

    # Truncate table for clean state
    if store._Session:
        async with store._Session() as session:
            await session.execute(text("TRUNCATE TABLE events CASCADE"))
            await session.commit()

    bus = EventBus()
    sink = EventSink(bus=bus, store=store, batch_size=10, flush_interval_s=0.1)

    # Start sink in background
    sink_task = asyncio.create_task(sink.run())

    yield sink

    # Stop sink
    await sink.stop()
    sink_task.cancel()
    try:
        await sink_task
    except asyncio.CancelledError:
        pass

    await store.cleanup()


@pytest.mark.asyncio
async def test_event_sink_persists_events(event_sink: EventSink) -> None:
    """Test that EventSink persists events to database."""
    from polytrader.events import SYSTEM_LIFECYCLE

    # Publish events
    event1 = SystemStartedEvent()
    await event_sink._bus.publish(SYSTEM_LIFECYCLE, event1)

    # Wait for flush (flush_interval is 0.1s in test)
    await asyncio.sleep(0.2)

    # Verify events were persisted
    events = list(event_sink._store.read_stream())
    assert len(events) >= 1
    assert any(e.event_id == event1.event_id for e in events)


@pytest.mark.asyncio
async def test_event_sink_batch_writing(event_sink: EventSink) -> None:
    """Test that EventSink batches events before writing."""
    from polytrader.events import SYSTEM_LIFECYCLE

    # Publish multiple events
    events_published = []
    for _ in range(5):
        event = SystemStartedEvent()
        events_published.append(event)
        await event_sink._bus.publish(SYSTEM_LIFECYCLE, event)

    # Wait for flush (flush_interval is 0.1s, wait longer to ensure completion)
    await asyncio.sleep(0.5)

    # Verify all events were persisted
    events = list(event_sink._store.read_stream())
    # Filter to only SystemStartedEvent to avoid counting other events
    system_events = [e for e in events if isinstance(e, SystemStartedEvent)]
    assert len(system_events) >= 5

    # Verify all published events are in database
    published_ids = {e.event_id for e in events_published}
    stored_ids = {e.event_id for e in events}
    assert published_ids.issubset(stored_ids)


@pytest.mark.asyncio
async def test_event_sink_subscribes_to_all_topics(event_sink: EventSink) -> None:
    """Test that EventSink subscribes to all event topics."""
    from polytrader.events import (
        ORDER_CREATED,
        SYSTEM_LIFECYCLE,
    )

    # Publish events to different topics
    event1 = SystemStartedEvent()
    await event_sink._bus.publish(SYSTEM_LIFECYCLE, event1)

    intent = OrderIntentEvent(
        market_slug="btc-updown-15m",
        outcome="UP",
        side="BUY",
        target_price=0.5,
        limit_price=0.45,
        size=100.0,
        reason="Test",
        strategy_id="simple_threshold",
    )
    event2 = OrderCreatedEvent(
        order_id="order-123",
        client_order_id="client-456",
        intent=intent,
    )
    await event_sink._bus.publish(ORDER_CREATED, event2)

    # Wait for flush
    await asyncio.sleep(0.2)

    # Verify both events were persisted
    events = list(event_sink._store.read_stream())
    assert len(events) >= 2

    event_ids = {e.event_id for e in events}
    assert event1.event_id in event_ids
    assert event2.event_id in event_ids


@pytest.mark.asyncio
async def test_event_sink_handles_database_errors_gracefully(
    postgres_test_url: str, postgres_db: None
) -> None:
    """Test that EventSink handles database errors gracefully."""

    # Create store
    store = PostgreSQLEventStore(connection_url=postgres_test_url, pool_size=5)
    await store.initialize()

    # Truncate table
    from sqlalchemy import text

    if store._Session:
        async with store._Session() as session:
            await session.execute(text("TRUNCATE TABLE events CASCADE"))
            await session.commit()

    bus = EventBus()
    sink = EventSink(bus=bus, store=store, batch_size=10, flush_interval_s=0.1)

    # Start sink
    sink_task = asyncio.create_task(sink.run())

    try:
        # Publish an event
        from polytrader.events import SYSTEM_LIFECYCLE

        event = SystemStartedEvent()
        await bus.publish(SYSTEM_LIFECYCLE, event)

        # Wait a bit
        await asyncio.sleep(0.2)

        # Close store connection to simulate database error
        await store.cleanup()

        # Publish another event (should fail gracefully)
        event2 = SystemStartedEvent()
        await bus.publish(SYSTEM_LIFECYCLE, event2)

        # Wait for flush attempt
        await asyncio.sleep(0.2)

        # Sink should still be running (errors are logged, not thrown)
        assert sink._running is True

    finally:
        await sink.stop()
        sink_task.cancel()
        try:
            await sink_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_event_sink_circuit_breaker(postgres_test_url: str, postgres_db: None) -> None:
    """Test that EventSink circuit breaker opens after failures."""

    # Create a store that will fail (invalid connection)
    invalid_store = PostgreSQLEventStore(
        connection_url="postgresql://invalid:invalid@localhost:9999/invalid", pool_size=1
    )
    # Don't initialize - this will cause failures

    bus = EventBus()
    sink = EventSink(
        bus=bus,
        store=invalid_store,
        batch_size=1,
        flush_interval_s=0.1,
    )

    # Test circuit breaker directly
    breaker = sink._circuit_breaker

    # Record failures until circuit opens
    for _ in range(10):
        breaker.record_failure()

    # Circuit should be open
    assert breaker.state.value == "open"
    assert not breaker.allow_request()

    # Record success in OPEN state doesn't close it (need to wait for cooldown)
    # But if we're in HALF_OPEN, success will close it
    # For this test, verify that success in HALF_OPEN closes the circuit
    # First, manually set to HALF_OPEN (simulating cooldown passed)
    from polytrader.events.sink import CircuitState

    breaker._state = CircuitState.HALF_OPEN
    breaker.record_success()
    assert breaker.state.value == "closed"
    assert breaker.allow_request()


@pytest.mark.asyncio
async def test_event_sink_stop_flushes_remaining_events(event_sink: EventSink) -> None:
    """Test that stop() flushes remaining events in buffer."""
    from polytrader.events import SYSTEM_LIFECYCLE

    # Get initial event count to filter out events from other tests
    initial_events = list(event_sink._store.read_stream())
    initial_count = len(initial_events)
    initial_event_ids = {e.event_id for e in initial_events}

    # Publish events
    events_published = []
    for _ in range(3):
        event = SystemStartedEvent()
        events_published.append(event)
        await event_sink._bus.publish(SYSTEM_LIFECYCLE, event)

    # Wait a short time for events to be consumed into buffer (but less than flush_interval)
    # flush_interval is 0.1s, so wait 0.05s to ensure events are in buffer but not flushed yet
    await asyncio.sleep(0.05)

    # Stop sink (should flush remaining events in buffer)
    await event_sink.stop()

    # Verify events were flushed on stop
    all_events = list(event_sink._store.read_stream())

    # Filter to only new events (those we just published)
    published_ids = {e.event_id for e in events_published}
    stored_ids = {e.event_id for e in all_events}

    # All published events should be in store
    assert published_ids.issubset(stored_ids), (
        f"Expected all published events to be in store. "
        f"Published: {published_ids}, Stored: {stored_ids}"
    )

    # Verify we have at least 3 new events (our published ones)
    new_events = [e for e in all_events if e.event_id not in initial_event_ids]
    assert len(new_events) >= 3, (
        f"Expected at least 3 new events after stop(), got {len(new_events)}. "
        f"Total events: {len(all_events)}, Initial: {initial_count}"
    )


@pytest.mark.asyncio
async def test_event_sink_buffer_overflow_protection(event_sink: EventSink) -> None:
    """Test that EventSink handles buffer overflow by dropping oldest events."""
    from polytrader.events import SYSTEM_LIFECYCLE

    # Set small buffer size for test
    event_sink._max_buffer_size = 5

    # Publish more events than buffer size
    events_published = []
    for _ in range(10):
        event = SystemStartedEvent()
        events_published.append(event)
        await event_sink._bus.publish(SYSTEM_LIFECYCLE, event)

    # Wait a bit for events to be buffered
    await asyncio.sleep(0.05)

    # Buffer should not exceed max_buffer_size
    assert len(event_sink._buffer) <= event_sink._max_buffer_size

    # Wait for flush
    await asyncio.sleep(0.2)

    # Some events should have been persisted (those that weren't dropped)
    events = list(event_sink._store.read_stream())
    # At least some events should be persisted (buffer overflow drops oldest, not all)
    assert len(events) > 0


@pytest.mark.asyncio
async def test_event_sink_persists_signal_event_readable_by_repository(
    event_sink: EventSink,
    postgres_test_url: str,
) -> None:
    """EventSink-persisted SignalEvents are readable via repository.

    Per docs/analysis-why-no-signals-in-api.md: Platform start now uses EventSink
    to persist events to PostgreSQL so the Control API can return signals. This test
    verifies the contract: events written by EventSink are queryable by
    EventRepository.read_signal_events_by_strategy (used by the signals API).
    """
    from polytrader.events import SIGNALS
    from tests.factories.events import create_signal_event

    strategy_id = "test-strategy-signals-api"
    signal = create_signal_event(
        market_slug="btc-updown",
        outcome="UP",
        p_up=0.6,
        p_down=0.4,
        edge=0.1,
        confidence=0.8,
        model_id=strategy_id,
        rationale="EventSink → repository contract test",
    )
    await event_sink._bus.publish(SIGNALS, signal)

    # Wait for flush (flush_interval is 0.1s in fixture)
    await asyncio.sleep(0.25)

    sqlalchemy_url = postgres_test_url
    if sqlalchemy_url.startswith("postgresql://"):
        sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        repo = EventRepository(session)
        records, next_cursor = await repo.read_signal_events_by_strategy(
            strategy_id=strategy_id,
            limit=10,
        )
        await session.commit()

    await engine.dispose()

    assert len(records) >= 1, (
        "EventRepository.read_signal_events_by_strategy should return "
        "SignalEvents persisted by EventSink"
    )
    first = records[0]
    assert first.event_type == "SignalEvent"
    assert first.event_data.get("model_id") == strategy_id
    assert first.event_data.get("market_slug") == "btc-updown"
    assert first.event_data.get("p_up") == 0.6
    assert next_cursor is None or isinstance(next_cursor, str)
