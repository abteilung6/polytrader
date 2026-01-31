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


def _closed_trade_event_data(
    strategy_id: str,
    ts_mono: float,
    execution_mode: str = "paper",
) -> dict:
    """Minimal event_data for StrategyClosedTradeEvent (JSONB payload)."""
    return {
        "strategy_id": strategy_id,
        "market_slug": "btc-updown-15m",
        "outcome": "UP",
        "entry_price": 0.45,
        "exit_price": 0.55,
        "size": 100.0,
        "pnl": 10.0,
        "pnl_pct": 22.2,
        "entry_time": ts_mono - 100.0,
        "exit_time": ts_mono,
        "result": "WIN",
        "execution_mode": execution_mode,
        "order_id": str(uuid.uuid4()),
        "fill_id": str(uuid.uuid4()),
    }


class TestReadClosedTradeEventsByStrategy:
    """Test read_closed_trade_events_by_strategy (Past Performance read path)."""

    @pytest.mark.asyncio
    async def test_returns_closed_trades_for_strategy(self, db_session: AsyncSession) -> None:
        """read_closed_trade_events_by_strategy returns StrategyClosedTradeEvent for strategy_id."""
        repo = EventRepository(db_session)
        strategy_id = "strat-closed-trades-1"
        event_id = UUID(str(uuid.uuid4()))
        event_data = _closed_trade_event_data(strategy_id, ts_mono=2000.0)

        await repo.create_event(
            event_id=event_id,
            ts_wall=datetime.now(UTC),
            ts_mono=2000.0,
            correlation_id="corr-1",
            run_id="run-1",
            schema_version="1.0",
            source="posttrade",
            event_type="StrategyClosedTradeEvent",
            event_data=event_data,
        )

        records, next_cursor = await repo.read_closed_trade_events_by_strategy(
            strategy_id=strategy_id,
            limit=10,
        )
        assert len(records) == 1
        assert records[0].event_type == "StrategyClosedTradeEvent"
        assert records[0].event_data["strategy_id"] == strategy_id
        assert records[0].event_data["market_slug"] == "btc-updown-15m"
        assert records[0].event_data["pnl"] == 10.0
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_filters_by_execution_mode(self, db_session: AsyncSession) -> None:
        """read_closed_trade_events_by_strategy filters by execution_mode when provided."""
        repo = EventRepository(db_session)
        strategy_id = "strat-exec-mode"
        for i, mode in enumerate(["paper", "paper", "live"]):
            await repo.create_event(
                event_id=UUID(str(uuid.uuid4())),
                ts_wall=datetime.now(UTC),
                ts_mono=3000.0 + i,
                correlation_id=None,
                run_id="run-1",
                schema_version="1.0",
                source="posttrade",
                event_type="StrategyClosedTradeEvent",
                event_data=_closed_trade_event_data(strategy_id, 3000.0 + i, mode),
            )

        paper_only, _ = await repo.read_closed_trade_events_by_strategy(
            strategy_id=strategy_id,
            execution_mode="paper",
            limit=10,
        )
        assert len(paper_only) == 2
        assert all(r.event_data["execution_mode"] == "paper" for r in paper_only)

        live_only, _ = await repo.read_closed_trade_events_by_strategy(
            strategy_id=strategy_id,
            execution_mode="live",
            limit=10,
        )
        assert len(live_only) == 1
        assert live_only[0].event_data["execution_mode"] == "live"

    @pytest.mark.asyncio
    async def test_filters_by_time_range(self, db_session: AsyncSession) -> None:
        """read_closed_trade_events_by_strategy filters by from_ts and to_ts."""
        repo = EventRepository(db_session)
        strategy_id = "strat-ts-range"
        for i in range(5):
            ts = 4000.0 + i * 10
            await repo.create_event(
                event_id=UUID(str(uuid.uuid4())),
                ts_wall=datetime.now(UTC),
                ts_mono=ts,
                correlation_id=None,
                run_id="run-1",
                schema_version="1.0",
                source="posttrade",
                event_type="StrategyClosedTradeEvent",
                event_data=_closed_trade_event_data(strategy_id, ts),
            )

        records, _ = await repo.read_closed_trade_events_by_strategy(
            strategy_id=strategy_id,
            from_ts=4010.0,
            to_ts=4030.0,
            limit=10,
        )
        assert len(records) == 3  # ts 4010, 4020, 4030
        assert all(4010.0 <= r.ts_mono <= 4030.0 for r in records)

    @pytest.mark.asyncio
    async def test_returns_empty_for_other_strategy(self, db_session: AsyncSession) -> None:
        """read_closed_trade_events_by_strategy returns no rows for wrong strategy_id."""
        repo = EventRepository(db_session)
        await repo.create_event(
            event_id=UUID(str(uuid.uuid4())),
            ts_wall=datetime.now(UTC),
            ts_mono=5000.0,
            correlation_id=None,
            run_id="run-1",
            schema_version="1.0",
            source="posttrade",
            event_type="StrategyClosedTradeEvent",
            event_data=_closed_trade_event_data("strategy-A", 5000.0),
        )

        records, _ = await repo.read_closed_trade_events_by_strategy(
            strategy_id="strategy-B",
            limit=10,
        )
        assert len(records) == 0

    @pytest.mark.asyncio
    async def test_pagination_returns_next_cursor(self, db_session: AsyncSession) -> None:
        """read_closed_trade_events_by_strategy returns next_cursor when more rows exist."""
        repo = EventRepository(db_session)
        strategy_id = "strat-pagination"
        for i in range(5):
            ts = 6000.0 + i
            await repo.create_event(
                event_id=UUID(str(uuid.uuid4())),
                ts_wall=datetime.now(UTC),
                ts_mono=ts,
                correlation_id=None,
                run_id="run-1",
                schema_version="1.0",
                source="posttrade",
                event_type="StrategyClosedTradeEvent",
                event_data=_closed_trade_event_data(strategy_id, ts),
            )

        page1, cursor = await repo.read_closed_trade_events_by_strategy(
            strategy_id=strategy_id,
            limit=2,
        )
        assert len(page1) == 2
        assert cursor is not None

        page2, cursor2 = await repo.read_closed_trade_events_by_strategy(
            strategy_id=strategy_id,
            limit=2,
            cursor=cursor,
        )
        assert len(page2) == 2
        assert cursor2 is not None

        page3, cursor3 = await repo.read_closed_trade_events_by_strategy(
            strategy_id=strategy_id,
            limit=2,
            cursor=cursor2,
        )
        assert len(page3) == 1
        assert cursor3 is None
