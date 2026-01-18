"""Integration tests for PostgreSQLEventStore.

Tests PostgreSQL event store implementation with real database.
"""

import asyncio
from collections.abc import AsyncGenerator

import pytest

from polytrader.events.stores import PostgreSQLEventStore
from polytrader.events.types import (
    EventSource,
    OrderCreatedEvent,
    SystemStartedEvent,
    SystemStoppedEvent,
)


@pytest.fixture
async def postgres_store(
    postgres_test_url: str,
) -> AsyncGenerator[PostgreSQLEventStore, None]:
    """Create PostgreSQL event store for testing."""
    # Ensure migrations are run first
    from sqlalchemy import text

    from polytrader.db.migrations import run_migrations

    await run_migrations(postgres_test_url)

    store = PostgreSQLEventStore(connection_url=postgres_test_url, pool_size=5)
    await store.initialize()

    # Truncate table for clean state using SQLAlchemy
    if store._Session:
        async with store._Session() as session:
            await session.execute(text("TRUNCATE TABLE events CASCADE"))
            await session.commit()

    yield store

    await store.cleanup()


@pytest.mark.asyncio
async def test_postgres_store_append(postgres_store: PostgreSQLEventStore) -> None:
    """Test appending events to PostgreSQL store."""
    event = SystemStartedEvent()

    await postgres_store.append(event)

    # Verify event was stored
    events = list(postgres_store.read_stream())
    assert len(events) == 1
    assert events[0].event_id == event.event_id
    assert isinstance(events[0], SystemStartedEvent)


@pytest.mark.asyncio
async def test_postgres_store_idempotency(postgres_store: PostgreSQLEventStore) -> None:
    """Test that duplicate events are not stored (idempotency)."""
    event = SystemStartedEvent()

    # Append same event twice
    await postgres_store.append(event)
    await postgres_store.append(event)

    # Should only have one event
    events = list(postgres_store.read_stream())
    assert len(events) == 1
    assert events[0].event_id == event.event_id


@pytest.mark.asyncio
async def test_postgres_store_read_stream_filter_by_type(
    postgres_store: PostgreSQLEventStore,
) -> None:
    """Test filtering events by type."""
    # Create different event types
    event1 = SystemStartedEvent()
    event2 = SystemStoppedEvent(reason="test")
    # Create OrderIntentEvent first, then OrderCreatedEvent
    from polytrader.events.types import OrderIntentEvent

    intent = OrderIntentEvent(
        market_slug="btc-updown-15m",
        outcome="UP",
        side="BUY",
        target_price=0.5,
        limit_price=0.45,
        size=100.0,
        reason="Test order",
    )
    event3 = OrderCreatedEvent(
        order_id="order-123",
        client_order_id="client-456",
        intent=intent,
    )

    await postgres_store.append(event1)
    await postgres_store.append(event2)
    await postgres_store.append(event3)

    # Filter by SystemStartedEvent
    started_events = list(postgres_store.read_stream(event_type=SystemStartedEvent))
    assert len(started_events) == 1
    assert isinstance(started_events[0], SystemStartedEvent)

    # Filter by OrderCreatedEvent
    order_events = list(postgres_store.read_stream(event_type=OrderCreatedEvent))
    assert len(order_events) == 1
    assert isinstance(order_events[0], OrderCreatedEvent)
    assert order_events[0].order_id == "order-123"


@pytest.mark.asyncio
async def test_postgres_store_read_stream_filter_by_time(
    postgres_store: PostgreSQLEventStore,
) -> None:
    """Test filtering events by time range."""
    import time

    # Create events with different timestamps
    from polytrader.events.types import OrderIntentEvent

    ts1 = time.monotonic()
    event1 = SystemStartedEvent.model_construct(ts_mono=ts1)

    await asyncio.sleep(0.01)  # Small delay

    ts2 = time.monotonic()
    event2 = SystemStoppedEvent.model_construct(reason="test", ts_mono=ts2)

    await asyncio.sleep(0.01)

    ts3 = time.monotonic()
    intent = OrderIntentEvent(
        market_slug="btc-updown-15m",
        outcome="UP",
        side="BUY",
        target_price=0.5,
        limit_price=0.45,
        size=100.0,
        reason="Test order",
    )
    event3 = OrderCreatedEvent.model_construct(
        order_id="order-123",
        client_order_id="client-456",
        intent=intent,
        ts_mono=ts3,
    )

    await postgres_store.append(event1)
    await postgres_store.append(event2)
    await postgres_store.append(event3)

    # Filter by time range (from_ts to to_ts)
    events = list(postgres_store.read_stream(from_ts=ts1, to_ts=ts2))
    assert len(events) == 2  # event1 and event2
    assert all(e.ts_mono >= ts1 and e.ts_mono <= ts2 for e in events)

    # Filter by from_ts only
    events = list(postgres_store.read_stream(from_ts=ts2))
    assert len(events) == 2  # event2 and event3
    assert all(e.ts_mono >= ts2 for e in events)

    # Filter by to_ts only
    events = list(postgres_store.read_stream(to_ts=ts2))
    assert len(events) == 2  # event1 and event2
    assert all(e.ts_mono <= ts2 for e in events)


@pytest.mark.asyncio
async def test_postgres_store_read_stream_filter_by_correlation_id(
    postgres_store: PostgreSQLEventStore,
) -> None:
    """Test filtering events by correlation_id."""
    correlation_id = "test-correlation-123"
    from polytrader.events.types import OrderIntentEvent

    event1 = SystemStartedEvent.model_construct(correlation_id=correlation_id)

    event2 = SystemStoppedEvent.model_construct(reason="test", correlation_id=correlation_id)

    intent = OrderIntentEvent(
        market_slug="btc-updown-15m",
        outcome="UP",
        side="BUY",
        target_price=0.5,
        limit_price=0.45,
        size=100.0,
        reason="Test order",
    )
    event3 = OrderCreatedEvent(
        order_id="order-123",
        client_order_id="client-456",
        intent=intent,
    )
    # event3 has different correlation_id (default)

    await postgres_store.append(event1)
    await postgres_store.append(event2)
    await postgres_store.append(event3)

    # Filter by correlation_id
    events = list(postgres_store.read_stream(correlation_id=correlation_id))
    assert len(events) == 2
    assert all(e.correlation_id == correlation_id for e in events)


@pytest.mark.asyncio
async def test_postgres_store_replay_chronological(
    postgres_store: PostgreSQLEventStore,
) -> None:
    """Test that replay() returns events in chronological order."""
    import time

    # Create events with different timestamps (out of order)
    from polytrader.events.types import OrderIntentEvent

    ts1 = time.monotonic()
    event1 = SystemStartedEvent.model_construct(ts_mono=ts1)

    await asyncio.sleep(0.01)

    ts2 = time.monotonic()
    event2 = SystemStoppedEvent.model_construct(reason="test", ts_mono=ts2)

    await asyncio.sleep(0.01)

    ts3 = time.monotonic()
    intent = OrderIntentEvent(
        market_slug="btc-updown-15m",
        outcome="UP",
        side="BUY",
        target_price=0.5,
        limit_price=0.45,
        size=100.0,
        reason="Test order",
    )
    event3 = OrderCreatedEvent.model_construct(
        order_id="order-123",
        client_order_id="client-456",
        intent=intent,
        ts_mono=ts3,
    )

    # Append out of order
    await postgres_store.append(event3)
    await postgres_store.append(event1)
    await postgres_store.append(event2)

    # Replay should return in chronological order
    events = list(postgres_store.replay())
    assert len(events) == 3
    assert events[0].ts_mono <= events[1].ts_mono <= events[2].ts_mono


@pytest.mark.asyncio
async def test_postgres_store_event_data_jsonb(
    postgres_store: PostgreSQLEventStore,
) -> None:
    """Test that event-specific fields are stored in JSONB and deserialized correctly."""
    from polytrader.events.types import OrderIntentEvent

    intent = OrderIntentEvent(
        market_slug="btc-updown-15m",
        outcome="UP",
        side="BUY",
        target_price=0.5,
        limit_price=0.45,
        size=100.0,
        reason="Test order",
    )
    event = OrderCreatedEvent(
        order_id="order-123",
        client_order_id="client-456",
        intent=intent,
    )

    await postgres_store.append(event)

    # Read back and verify all fields
    events = list(postgres_store.read_stream(event_type=OrderCreatedEvent))
    assert len(events) == 1

    read_event = events[0]
    assert isinstance(read_event, OrderCreatedEvent)
    assert read_event.order_id == "order-123"
    assert read_event.client_order_id == "client-456"
    assert read_event.intent.market_slug == "btc-updown-15m"
    assert read_event.intent.outcome == "UP"
    assert read_event.intent.side == "BUY"
    assert read_event.intent.size == 100.0
    assert read_event.intent.limit_price == 0.45


@pytest.mark.asyncio
async def test_postgres_store_event_source_enum(
    postgres_store: PostgreSQLEventStore,
) -> None:
    """Test that EventSource enum is correctly serialized/deserialized."""
    event = SystemStartedEvent.model_construct(source=EventSource.OPS)

    await postgres_store.append(event)

    # Read back and verify source
    events = list(postgres_store.read_stream())
    assert len(events) == 1
    assert events[0].source == EventSource.OPS


@pytest.mark.asyncio
async def test_postgres_store_initialize_raises_if_table_missing(
    postgres_test_url: str,
) -> None:
    """Test that initialize() raises if events table doesn't exist."""
    from psycopg import AsyncConnection

    from polytrader.db.migrations import run_migrations

    # Ensure migrations are run first (so table exists initially)
    await run_migrations(postgres_test_url)

    # Drop the events table temporarily
    async with await AsyncConnection.connect(postgres_test_url) as conn:
        async with conn.cursor() as cur:
            await cur.execute("DROP TABLE IF EXISTS events CASCADE")
            await conn.commit()

    # Now try to initialize a store - it should fail because table doesn't exist
    store = PostgreSQLEventStore(connection_url=postgres_test_url)

    try:
        with pytest.raises(RuntimeError, match="Events table not found"):
            await store.initialize()
    finally:
        # Clean up: close the pool if it was created (even if initialize() failed)
        await store.cleanup()
        # Restore the table by running migrations
        # This ensures other tests aren't affected
        await run_migrations(postgres_test_url)


@pytest.mark.asyncio
async def test_postgres_store_append_raises_if_not_initialized() -> None:
    """Test that append() raises if store not initialized."""
    from polytrader.config import get_database_url

    store = PostgreSQLEventStore(connection_url=get_database_url())
    event = SystemStartedEvent()

    with pytest.raises(RuntimeError, match="Store not initialized"):
        await store.append(event)


@pytest.mark.asyncio
async def test_postgres_store_read_stream_raises_if_not_initialized() -> None:
    """Test that read_stream() raises if store not initialized."""
    from polytrader.config import get_database_url

    store = PostgreSQLEventStore(connection_url=get_database_url())

    with pytest.raises(RuntimeError, match="Store not initialized"):
        list(store.read_stream())
