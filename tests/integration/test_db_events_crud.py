"""Integration tests for database CRUD operations on events table.

Tests the pure database operations using SQLAlchemy ORM.
These tests verify the repository pattern works correctly.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.db.repository import EventRepository


@pytest.fixture
async def db_session(
    postgres_test_url: str, postgres_db: None
) -> AsyncGenerator[AsyncSession, None]:
    """Provide SQLAlchemy session for CRUD tests."""
    from sqlalchemy import text

    # Migrations are run by postgres_db fixture

    # Convert URL to SQLAlchemy async format (postgresql+psycopg://)
    sqlalchemy_url = postgres_test_url
    if sqlalchemy_url.startswith("postgresql://"):
        sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+psycopg://", 1)

    # Create engine and session
    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        # Truncate events table for clean state
        await session.execute(text("TRUNCATE TABLE events CASCADE"))
        await session.commit()

        yield session

        # Cleanup
        await session.execute(text("TRUNCATE TABLE events CASCADE"))
        await session.commit()

    await engine.dispose()


class TestCreateEvent:
    """Test create_event function."""

    @pytest.mark.asyncio
    async def test_create_event_inserts_successfully(self, db_session: AsyncSession) -> None:
        """Test that create_event inserts an event successfully."""
        repo = EventRepository(db_session)
        test_event_id = UUID(str(uuid.uuid4()))

        await repo.create_event(
            event_id=test_event_id,
            ts_wall=datetime.now(UTC),
            ts_mono=12345.678,
            correlation_id="test-correlation",
            run_id="test-run-123",
            schema_version="1.0",
            source="ops",
            event_type="SystemStartedEvent",
            event_data={},
        )

        # Verify event was inserted
        exists = await repo.event_exists(test_event_id)
        assert exists is True

    @pytest.mark.asyncio
    async def test_create_event_idempotent(self, db_session: AsyncSession) -> None:
        """Test that create_event is idempotent (duplicate event_id ignored)."""
        repo = EventRepository(db_session)
        test_event_id = UUID(str(uuid.uuid4()))

        # Insert twice with same event_id
        await repo.create_event(
            event_id=test_event_id,
            ts_wall=datetime.now(UTC),
            ts_mono=12345.678,
            correlation_id="test-correlation",
            run_id="test-run-123",
            schema_version="1.0",
            source="ops",
            event_type="SystemStartedEvent",
            event_data={},
        )
        await repo.create_event(
            event_id=test_event_id,
            ts_wall=datetime.now(UTC),
            ts_mono=12345.678,
            correlation_id="test-correlation",
            run_id="test-run-123",
            schema_version="1.0",
            source="ops",
            event_type="SystemStartedEvent",
            event_data={},
        )

        # Should only have one event (verify by reading)
        events = await repo.read_events()
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_create_event_with_jsonb_data(self, db_session: AsyncSession) -> None:
        """Test that create_event correctly stores JSONB event_data."""
        repo = EventRepository(db_session)
        test_event_id = UUID(str(uuid.uuid4()))

        event_data = {"order_id": "order-123", "size": 100.0, "limit_price": 0.45}
        await repo.create_event(
            event_id=test_event_id,
            ts_wall=datetime.now(UTC),
            ts_mono=12345.678,
            correlation_id=None,
            run_id="test-run-123",
            schema_version="1.0",
            source="oms",
            event_type="OrderCreatedEvent",
            event_data=event_data,
        )

        # Read back and verify JSONB data
        events = await repo.read_events(event_type="OrderCreatedEvent")
        assert len(events) == 1
        assert str(events[0].event_id) == str(test_event_id)
        # event_data should be a dict (SQLAlchemy automatically parses JSONB)
        assert isinstance(events[0].event_data, dict)
        assert events[0].event_data["order_id"] == "order-123"
        assert events[0].event_data["size"] == 100.0


class TestReadEvents:
    """Test read_events function."""

    @pytest.mark.asyncio
    async def test_read_events_returns_all_events(self, db_session: AsyncSession) -> None:
        """Test that read_events returns all events when no filters."""
        repo = EventRepository(db_session)
        # Insert multiple events
        for i in range(3):
            await repo.create_event(
                event_id=UUID(str(uuid.uuid4())),
                ts_wall=datetime.now(UTC),
                ts_mono=12345.0 + i,
                correlation_id=None,
                run_id="test-run-123",
                schema_version="1.0",
                source="ops",
                event_type="SystemStartedEvent",
                event_data={},
            )

        events = await repo.read_events()
        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_read_events_filter_by_event_type(self, db_session: AsyncSession) -> None:
        """Test filtering events by event_type."""
        repo = EventRepository(db_session)
        # Insert different event types
        event_id1 = UUID(str(uuid.uuid4()))
        event_id2 = UUID(str(uuid.uuid4()))
        await repo.create_event(
            event_id=event_id1,
            ts_wall=datetime.now(UTC),
            ts_mono=12345.0,
            correlation_id=None,
            run_id="test-run-123",
            schema_version="1.0",
            source="ops",
            event_type="SystemStartedEvent",
            event_data={},
        )
        await repo.create_event(
            event_id=event_id2,
            ts_wall=datetime.now(UTC),
            ts_mono=12346.0,
            correlation_id=None,
            run_id="test-run-123",
            schema_version="1.0",
            source="oms",
            event_type="OrderCreatedEvent",
            event_data={},
        )

        # Filter by event_type
        started_events = await repo.read_events(event_type="SystemStartedEvent")
        assert len(started_events) == 1
        assert started_events[0].event_id == event_id1

        order_events = await repo.read_events(event_type="OrderCreatedEvent")
        assert len(order_events) == 1
        assert order_events[0].event_id == event_id2

    @pytest.mark.asyncio
    async def test_read_events_filter_by_time_range(self, db_session: AsyncSession) -> None:
        """Test filtering events by time range."""
        repo = EventRepository(db_session)
        # Insert events with different timestamps
        for i in range(5):
            await repo.create_event(
                event_id=UUID(str(uuid.uuid4())),
                ts_wall=datetime.now(UTC),
                ts_mono=1000.0 + i * 10.0,
                correlation_id=None,
                run_id="test-run-123",
                schema_version="1.0",
                source="ops",
                event_type="SystemStartedEvent",
                event_data={},
            )

        # Filter by time range
        events = await repo.read_events(from_ts=1010.0, to_ts=1030.0)
        assert len(events) == 3  # events with ts_mono 1010, 1020, 1030

    @pytest.mark.asyncio
    async def test_read_events_filter_by_correlation_id(self, db_session: AsyncSession) -> None:
        """Test filtering events by correlation_id."""
        repo = EventRepository(db_session)
        # Insert events with different correlation_ids
        event_id1 = UUID(str(uuid.uuid4()))
        event_id2 = UUID(str(uuid.uuid4()))
        await repo.create_event(
            event_id=event_id1,
            ts_wall=datetime.now(UTC),
            ts_mono=12345.0,
            correlation_id="corr-123",
            run_id="test-run-123",
            schema_version="1.0",
            source="ops",
            event_type="SystemStartedEvent",
            event_data={},
        )
        await repo.create_event(
            event_id=event_id2,
            ts_wall=datetime.now(UTC),
            ts_mono=12346.0,
            correlation_id="corr-456",
            run_id="test-run-123",
            schema_version="1.0",
            source="ops",
            event_type="SystemStartedEvent",
            event_data={},
        )

        # Filter by correlation_id
        events = await repo.read_events(correlation_id="corr-123")
        assert len(events) == 1
        assert events[0].event_id == event_id1

    @pytest.mark.asyncio
    async def test_read_events_with_limit(self, db_session: AsyncSession) -> None:
        """Test that read_events respects limit parameter."""
        repo = EventRepository(db_session)
        # Insert multiple events
        for i in range(10):
            await repo.create_event(
                event_id=UUID(str(uuid.uuid4())),
                ts_wall=datetime.now(UTC),
                ts_mono=1000.0 + i,
                correlation_id=None,
                run_id="test-run-123",
                schema_version="1.0",
                source="ops",
                event_type="SystemStartedEvent",
                event_data={},
            )

        # Read with limit
        events = await repo.read_events(limit=5)
        assert len(events) == 5


class TestEventExists:
    """Test event_exists function."""

    @pytest.mark.asyncio
    async def test_event_exists_returns_true_when_exists(self, db_session: AsyncSession) -> None:
        """Test that event_exists returns True when event exists."""
        repo = EventRepository(db_session)
        test_event_id = UUID(str(uuid.uuid4()))
        await repo.create_event(
            event_id=test_event_id,
            ts_wall=datetime.now(UTC),
            ts_mono=12345.678,
            correlation_id=None,
            run_id="test-run-123",
            schema_version="1.0",
            source="ops",
            event_type="SystemStartedEvent",
            event_data={},
        )

        exists = await repo.event_exists(test_event_id)
        assert exists is True

    @pytest.mark.asyncio
    async def test_event_exists_returns_false_when_not_exists(
        self, db_session: AsyncSession
    ) -> None:
        """Test that event_exists returns False when event doesn't exist."""
        repo = EventRepository(db_session)
        non_existent_id = UUID(str(uuid.uuid4()))
        exists = await repo.event_exists(non_existent_id)
        assert exists is False
