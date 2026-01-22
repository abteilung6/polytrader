"""Integration tests for database CRUD operations on market_ticks table.

Tests the pure database operations using SQLAlchemy ORM.
These tests verify the MarketTickRepository pattern works correctly.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.db.migrations import run_migrations
from polytrader.db.repository import MarketTickRepository


@pytest.fixture
async def db_session(postgres_test_url: str) -> AsyncGenerator[AsyncSession, None]:
    """Provide SQLAlchemy session for CRUD tests."""
    from sqlalchemy import text

    # Ensure migrations are run
    await run_migrations(postgres_test_url)

    # Convert URL to SQLAlchemy async format (postgresql+psycopg://)
    sqlalchemy_url = postgres_test_url
    if sqlalchemy_url.startswith("postgresql://"):
        sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+psycopg://", 1)

    # Create engine and session
    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        # Truncate market_ticks table for clean state
        await session.execute(text("TRUNCATE TABLE market_ticks CASCADE"))
        await session.commit()

        yield session

        # Cleanup
        await session.execute(text("TRUNCATE TABLE market_ticks CASCADE"))
        await session.commit()

    await engine.dispose()


class TestCreateTick:
    """Test create_tick function."""

    @pytest.mark.asyncio
    async def test_create_tick_inserts_successfully(self, db_session: AsyncSession) -> None:
        """Test that create_tick inserts a tick successfully."""
        repo = MarketTickRepository(db_session)
        test_tick_id = UUID(str(uuid.uuid4()))
        test_ts_wall = datetime.now(UTC)

        await repo.create_tick(
            tick_id=test_tick_id,
            ts_wall=test_ts_wall,
            ts_mono=12345.678,
            market_slug="btc-updown-15m",
            outcome="UP",
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.50"),
            mid=Decimal("0.475"),
            spread=Decimal("0.05"),
            spread_bps=Decimal("500.00"),
            event_id=None,
            run_id="test-run-123",
        )

        # Verify tick was inserted
        exists = await repo.tick_exists(test_tick_id, test_ts_wall)
        assert exists is True

    @pytest.mark.asyncio
    async def test_create_tick_idempotent(self, db_session: AsyncSession) -> None:
        """Test that create_tick is idempotent (duplicate tick_id+ts_wall ignored)."""
        repo = MarketTickRepository(db_session)
        test_tick_id = UUID(str(uuid.uuid4()))
        test_ts_wall = datetime.now(UTC)

        # Insert twice with same tick_id and ts_wall
        await repo.create_tick(
            tick_id=test_tick_id,
            ts_wall=test_ts_wall,
            ts_mono=12345.678,
            market_slug="btc-updown-15m",
            outcome="UP",
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.50"),
            mid=Decimal("0.475"),
            spread=Decimal("0.05"),
            spread_bps=Decimal("500.00"),
            event_id=None,
            run_id="test-run-123",
        )
        await repo.create_tick(
            tick_id=test_tick_id,
            ts_wall=test_ts_wall,
            ts_mono=12346.789,  # Different ts_mono, but same tick_id+ts_wall
            market_slug="btc-updown-15m",
            outcome="UP",
            best_bid=Decimal("0.46"),  # Different price
            best_ask=Decimal("0.51"),
            mid=Decimal("0.485"),
            spread=Decimal("0.05"),
            spread_bps=Decimal("500.00"),
            event_id=None,
            run_id="test-run-123",
        )

        # Should only have one tick (verify by reading)
        ticks = await repo.get_history(market_slug="btc-updown-15m", outcome="UP")
        assert len(ticks) == 1
        # First insert should be kept (idempotent = ignore second)
        assert ticks[0].ts_mono == 12345.678

    @pytest.mark.asyncio
    async def test_create_tick_with_event_id(self, db_session: AsyncSession) -> None:
        """Test that create_tick correctly stores event_id reference."""
        repo = MarketTickRepository(db_session)
        test_tick_id = UUID(str(uuid.uuid4()))
        test_event_id = UUID(str(uuid.uuid4()))
        test_ts_wall = datetime.now(UTC)

        await repo.create_tick(
            tick_id=test_tick_id,
            ts_wall=test_ts_wall,
            ts_mono=12345.678,
            market_slug="btc-updown-15m",
            outcome="UP",
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.50"),
            mid=Decimal("0.475"),
            spread=Decimal("0.05"),
            spread_bps=Decimal("500.00"),
            event_id=test_event_id,
            run_id="test-run-123",
        )

        # Read back and verify event_id
        latest = await repo.get_latest("btc-updown-15m", "UP")
        assert latest is not None
        assert latest.event_id == test_event_id


class TestBulkCreateTicks:
    """Test bulk_create_ticks function."""

    @pytest.mark.asyncio
    async def test_bulk_create_ticks_inserts_multiple(self, db_session: AsyncSession) -> None:
        """Test that bulk_create_ticks inserts multiple ticks."""
        repo = MarketTickRepository(db_session)
        base_time = datetime.now(UTC)

        ticks = []
        for i in range(5):
            ticks.append(
                {
                    "tick_id": UUID(str(uuid.uuid4())),
                    "ts_wall": base_time + timedelta(seconds=i),
                    "ts_mono": 12345.0 + i,
                    "market_slug": "btc-updown-15m",
                    "outcome": "UP",
                    "best_bid": Decimal("0.45"),
                    "best_ask": Decimal("0.50"),
                    "mid": Decimal("0.475"),
                    "spread": Decimal("0.05"),
                    "spread_bps": Decimal("500.00"),
                    "event_id": None,
                    "run_id": "test-run-123",
                }
            )

        count = await repo.bulk_create_ticks(ticks)
        assert count == 5

        # Verify all ticks were inserted
        all_ticks = await repo.get_history(market_slug="btc-updown-15m", outcome="UP")
        assert len(all_ticks) == 5

    @pytest.mark.asyncio
    async def test_bulk_create_ticks_idempotent(self, db_session: AsyncSession) -> None:
        """Test that bulk_create_ticks is idempotent (duplicates ignored)."""
        repo = MarketTickRepository(db_session)
        test_tick_id = UUID(str(uuid.uuid4()))
        test_ts_wall = datetime.now(UTC)

        ticks = [
            {
                "tick_id": test_tick_id,
                "ts_wall": test_ts_wall,
                "ts_mono": 12345.678,
                "market_slug": "btc-updown-15m",
                "outcome": "UP",
                "best_bid": Decimal("0.45"),
                "best_ask": Decimal("0.50"),
                "mid": Decimal("0.475"),
                "spread": Decimal("0.05"),
                "spread_bps": Decimal("500.00"),
                "event_id": None,
                "run_id": "test-run-123",
            },
        ]

        # Insert first time
        count1 = await repo.bulk_create_ticks(ticks)
        assert count1 == 1

        # Insert again (duplicate)
        count2 = await repo.bulk_create_ticks(ticks)
        assert count2 == 0  # Duplicate ignored

        # Should still only have one tick
        all_ticks = await repo.get_history(market_slug="btc-updown-15m", outcome="UP")
        assert len(all_ticks) == 1

    @pytest.mark.asyncio
    async def test_bulk_create_ticks_empty_list(self, db_session: AsyncSession) -> None:
        """Test that bulk_create_ticks handles empty list."""
        repo = MarketTickRepository(db_session)
        count = await repo.bulk_create_ticks([])
        assert count == 0


class TestGetLatest:
    """Test get_latest function."""

    @pytest.mark.asyncio
    async def test_get_latest_returns_most_recent(self, db_session: AsyncSession) -> None:
        """Test that get_latest returns the most recent tick."""
        repo = MarketTickRepository(db_session)
        base_time = datetime.now(UTC)

        # Insert ticks with different timestamps
        for i in range(3):
            await repo.create_tick(
                tick_id=UUID(str(uuid.uuid4())),
                ts_wall=base_time + timedelta(seconds=i),
                ts_mono=12345.0 + i,
                market_slug="btc-updown-15m",
                outcome="UP",
                best_bid=Decimal("0.45") + Decimal(str(i * 0.01)),
                best_ask=Decimal("0.50") + Decimal(str(i * 0.01)),
                mid=Decimal("0.475") + Decimal(str(i * 0.01)),
                spread=Decimal("0.05"),
                spread_bps=Decimal("500.00"),
                event_id=None,
                run_id="test-run-123",
            )

        latest = await repo.get_latest("btc-updown-15m", "UP")
        assert latest is not None
        # Latest should have highest ts_wall
        assert latest.ts_wall == base_time + timedelta(seconds=2)
        assert latest.ts_mono == 12347.0

    @pytest.mark.asyncio
    async def test_get_latest_returns_none_when_no_ticks(self, db_session: AsyncSession) -> None:
        """Test that get_latest returns None when no ticks exist."""
        repo = MarketTickRepository(db_session)
        latest = await repo.get_latest("btc-updown-15m", "UP")
        assert latest is None

    @pytest.mark.asyncio
    async def test_get_latest_filters_by_market_and_outcome(self, db_session: AsyncSession) -> None:
        """Test that get_latest correctly filters by market and outcome."""
        repo = MarketTickRepository(db_session)
        base_time = datetime.now(UTC)

        # Insert ticks for different markets/outcomes
        await repo.create_tick(
            tick_id=UUID(str(uuid.uuid4())),
            ts_wall=base_time,
            ts_mono=12345.0,
            market_slug="btc-updown-15m",
            outcome="UP",
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.50"),
            mid=Decimal("0.475"),
            spread=Decimal("0.05"),
            spread_bps=Decimal("500.00"),
            event_id=None,
            run_id="test-run-123",
        )
        await repo.create_tick(
            tick_id=UUID(str(uuid.uuid4())),
            ts_wall=base_time + timedelta(seconds=1),
            ts_mono=12346.0,
            market_slug="btc-updown-15m",
            outcome="DOWN",
            best_bid=Decimal("0.40"),
            best_ask=Decimal("0.45"),
            mid=Decimal("0.425"),
            spread=Decimal("0.05"),
            spread_bps=Decimal("500.00"),
            event_id=None,
            run_id="test-run-123",
        )

        # Get latest for UP
        latest_up = await repo.get_latest("btc-updown-15m", "UP")
        assert latest_up is not None
        assert latest_up.outcome == "UP"

        # Get latest for DOWN
        latest_down = await repo.get_latest("btc-updown-15m", "DOWN")
        assert latest_down is not None
        assert latest_down.outcome == "DOWN"


class TestGetHistory:
    """Test get_history function."""

    @pytest.mark.asyncio
    async def test_get_history_returns_all_ticks(self, db_session: AsyncSession) -> None:
        """Test that get_history returns all ticks when no filters."""
        repo = MarketTickRepository(db_session)
        base_time = datetime.now(UTC)

        # Insert multiple ticks
        for i in range(5):
            await repo.create_tick(
                tick_id=UUID(str(uuid.uuid4())),
                ts_wall=base_time + timedelta(seconds=i),
                ts_mono=12345.0 + i,
                market_slug="btc-updown-15m",
                outcome="UP",
                best_bid=Decimal("0.45"),
                best_ask=Decimal("0.50"),
                mid=Decimal("0.475"),
                spread=Decimal("0.05"),
                spread_bps=Decimal("500.00"),
                event_id=None,
                run_id="test-run-123",
            )

        ticks = await repo.get_history()
        assert len(ticks) == 5

    @pytest.mark.asyncio
    async def test_get_history_filter_by_market_slug(self, db_session: AsyncSession) -> None:
        """Test filtering ticks by market_slug."""
        repo = MarketTickRepository(db_session)
        base_time = datetime.now(UTC)

        # Insert ticks for different markets
        await repo.create_tick(
            tick_id=UUID(str(uuid.uuid4())),
            ts_wall=base_time,
            ts_mono=12345.0,
            market_slug="btc-updown-15m",
            outcome="UP",
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.50"),
            mid=Decimal("0.475"),
            spread=Decimal("0.05"),
            spread_bps=Decimal("500.00"),
            event_id=None,
            run_id="test-run-123",
        )
        await repo.create_tick(
            tick_id=UUID(str(uuid.uuid4())),
            ts_wall=base_time + timedelta(seconds=1),
            ts_mono=12346.0,
            market_slug="eth-updown-15m",
            outcome="UP",
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.50"),
            mid=Decimal("0.475"),
            spread=Decimal("0.05"),
            spread_bps=Decimal("500.00"),
            event_id=None,
            run_id="test-run-123",
        )

        # Filter by market_slug
        btc_ticks = await repo.get_history(market_slug="btc-updown-15m")
        assert len(btc_ticks) == 1
        assert btc_ticks[0].market_slug == "btc-updown-15m"

    @pytest.mark.asyncio
    async def test_get_history_filter_by_outcome(self, db_session: AsyncSession) -> None:
        """Test filtering ticks by outcome."""
        repo = MarketTickRepository(db_session)
        base_time = datetime.now(UTC)

        # Insert ticks for different outcomes
        await repo.create_tick(
            tick_id=UUID(str(uuid.uuid4())),
            ts_wall=base_time,
            ts_mono=12345.0,
            market_slug="btc-updown-15m",
            outcome="UP",
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.50"),
            mid=Decimal("0.475"),
            spread=Decimal("0.05"),
            spread_bps=Decimal("500.00"),
            event_id=None,
            run_id="test-run-123",
        )
        await repo.create_tick(
            tick_id=UUID(str(uuid.uuid4())),
            ts_wall=base_time + timedelta(seconds=1),
            ts_mono=12346.0,
            market_slug="btc-updown-15m",
            outcome="DOWN",
            best_bid=Decimal("0.40"),
            best_ask=Decimal("0.45"),
            mid=Decimal("0.425"),
            spread=Decimal("0.05"),
            spread_bps=Decimal("500.00"),
            event_id=None,
            run_id="test-run-123",
        )

        # Filter by outcome
        up_ticks = await repo.get_history(market_slug="btc-updown-15m", outcome="UP")
        assert len(up_ticks) == 1
        assert up_ticks[0].outcome == "UP"

    @pytest.mark.asyncio
    async def test_get_history_filter_by_time_range(self, db_session: AsyncSession) -> None:
        """Test filtering ticks by time range."""
        repo = MarketTickRepository(db_session)
        base_time = datetime.now(UTC)

        # Insert ticks with different timestamps
        for i in range(10):
            await repo.create_tick(
                tick_id=UUID(str(uuid.uuid4())),
                ts_wall=base_time + timedelta(seconds=i),
                ts_mono=12345.0 + i,
                market_slug="btc-updown-15m",
                outcome="UP",
                best_bid=Decimal("0.45"),
                best_ask=Decimal("0.50"),
                mid=Decimal("0.475"),
                spread=Decimal("0.05"),
                spread_bps=Decimal("500.00"),
                event_id=None,
                run_id="test-run-123",
            )

        # Filter by time range
        ticks = await repo.get_history(
            market_slug="btc-updown-15m",
            from_ts=base_time + timedelta(seconds=2),
            to_ts=base_time + timedelta(seconds=7),
        )
        assert len(ticks) == 6  # ticks at seconds 2, 3, 4, 5, 6, 7

    @pytest.mark.asyncio
    async def test_get_history_with_limit(self, db_session: AsyncSession) -> None:
        """Test that get_history respects limit parameter."""
        repo = MarketTickRepository(db_session)
        base_time = datetime.now(UTC)

        # Insert multiple ticks
        for i in range(10):
            await repo.create_tick(
                tick_id=UUID(str(uuid.uuid4())),
                ts_wall=base_time + timedelta(seconds=i),
                ts_mono=12345.0 + i,
                market_slug="btc-updown-15m",
                outcome="UP",
                best_bid=Decimal("0.45"),
                best_ask=Decimal("0.50"),
                mid=Decimal("0.475"),
                spread=Decimal("0.05"),
                spread_bps=Decimal("500.00"),
                event_id=None,
                run_id="test-run-123",
            )

        # Read with limit
        ticks = await repo.get_history(market_slug="btc-updown-15m", limit=5)
        assert len(ticks) == 5
        # Should be ordered by ts_wall ASC
        assert ticks[0].ts_wall == base_time
        assert ticks[4].ts_wall == base_time + timedelta(seconds=4)


class TestGetMarkets:
    """Test get_markets function."""

    @pytest.mark.asyncio
    async def test_get_markets_returns_all_pairs(self, db_session: AsyncSession) -> None:
        """Test that get_markets returns all market/outcome pairs."""
        repo = MarketTickRepository(db_session)
        base_time = datetime.now(UTC)

        # Insert ticks for different markets/outcomes
        await repo.create_tick(
            tick_id=UUID(str(uuid.uuid4())),
            ts_wall=base_time,
            ts_mono=12345.0,
            market_slug="btc-updown-15m",
            outcome="UP",
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.50"),
            mid=Decimal("0.475"),
            spread=Decimal("0.05"),
            spread_bps=Decimal("500.00"),
            event_id=None,
            run_id="test-run-123",
        )
        await repo.create_tick(
            tick_id=UUID(str(uuid.uuid4())),
            ts_wall=base_time + timedelta(seconds=1),
            ts_mono=12346.0,
            market_slug="btc-updown-15m",
            outcome="DOWN",
            best_bid=Decimal("0.40"),
            best_ask=Decimal("0.45"),
            mid=Decimal("0.425"),
            spread=Decimal("0.05"),
            spread_bps=Decimal("500.00"),
            event_id=None,
            run_id="test-run-123",
        )
        await repo.create_tick(
            tick_id=UUID(str(uuid.uuid4())),
            ts_wall=base_time + timedelta(seconds=2),
            ts_mono=12347.0,
            market_slug="eth-updown-15m",
            outcome="UP",
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.50"),
            mid=Decimal("0.475"),
            spread=Decimal("0.05"),
            spread_bps=Decimal("500.00"),
            event_id=None,
            run_id="test-run-123",
        )

        markets = await repo.get_markets()
        assert len(markets) == 3
        # Should contain all pairs
        assert ("btc-updown-15m", "UP") in markets
        assert ("btc-updown-15m", "DOWN") in markets
        assert ("eth-updown-15m", "UP") in markets

    @pytest.mark.asyncio
    async def test_get_markets_returns_empty_when_no_ticks(self, db_session: AsyncSession) -> None:
        """Test that get_markets returns empty list when no ticks exist."""
        repo = MarketTickRepository(db_session)
        markets = await repo.get_markets()
        assert markets == []


class TestTickExists:
    """Test tick_exists function."""

    @pytest.mark.asyncio
    async def test_tick_exists_returns_true_when_exists(self, db_session: AsyncSession) -> None:
        """Test that tick_exists returns True when tick exists."""
        repo = MarketTickRepository(db_session)
        test_tick_id = UUID(str(uuid.uuid4()))
        test_ts_wall = datetime.now(UTC)

        await repo.create_tick(
            tick_id=test_tick_id,
            ts_wall=test_ts_wall,
            ts_mono=12345.678,
            market_slug="btc-updown-15m",
            outcome="UP",
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.50"),
            mid=Decimal("0.475"),
            spread=Decimal("0.05"),
            spread_bps=Decimal("500.00"),
            event_id=None,
            run_id="test-run-123",
        )

        exists = await repo.tick_exists(test_tick_id, test_ts_wall)
        assert exists is True

    @pytest.mark.asyncio
    async def test_tick_exists_returns_false_when_not_exists(
        self, db_session: AsyncSession
    ) -> None:
        """Test that tick_exists returns False when tick doesn't exist."""
        repo = MarketTickRepository(db_session)
        non_existent_id = UUID(str(uuid.uuid4()))
        non_existent_time = datetime.now(UTC)
        exists = await repo.tick_exists(non_existent_id, non_existent_time)
        assert exists is False
