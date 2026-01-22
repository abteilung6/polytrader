"""Integration tests for query utilities.

Per testing.mdc: Integration tests verify query utilities with real database.
Tests verify that query utilities return correct results for common use cases.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from polytrader.db.models import MarketTickRecord
from polytrader.db.query_helpers import (
    get_latest_ticks_by_market,
    get_price_statistics,
    get_tick_count,
    get_ticks_in_range,
)
from polytrader.db.repository import MarketTickRepository


@pytest.fixture
async def db_session(postgres_test_url: str) -> AsyncGenerator[AsyncSession, None]:
    """Create database session for testing."""
    from sqlalchemy import text

    # Convert URL to SQLAlchemy async format if needed
    sqlalchemy_url = postgres_test_url
    if sqlalchemy_url.startswith("postgresql://"):
        sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+psycopg://", 1)

    engine: AsyncEngine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Ensure migrations are run before truncating
    from polytrader.db.migrations import run_migrations

    await run_migrations(postgres_test_url)

    async with Session() as session:
        # Truncate market_ticks table for clean state (if it exists)
        try:
            await session.execute(text("TRUNCATE TABLE market_ticks CASCADE"))
            await session.commit()
        except Exception:
            # Table might not exist yet, that's OK
            await session.rollback()

        yield session

        # Cleanup
        try:
            await session.execute(text("TRUNCATE TABLE market_ticks CASCADE"))
            await session.commit()
        except Exception:
            await session.rollback()

    await engine.dispose()


@pytest.fixture
async def repository(db_session: AsyncSession) -> MarketTickRepository:
    """Create repository for testing."""
    return MarketTickRepository(db_session)


@pytest.fixture
async def sample_ticks(repository: MarketTickRepository) -> list[MarketTickRecord]:
    """Create sample ticks for testing."""
    now = datetime.now(UTC)
    ticks: list[MarketTickRecord] = []

    # Create 10 ticks over the last hour
    for i in range(10):
        ts_wall = now - timedelta(minutes=60 - i * 6)  # Spread over 60 minutes
        tick = MarketTickRecord(
            tick_id=uuid4(),
            ts_wall=ts_wall,
            ts_mono=ts_wall.timestamp(),
            market_slug="btc-updown-15m",
            outcome="UP",
            best_bid=Decimal("0.50") + Decimal(str(i * 0.01)),
            best_ask=Decimal("0.51") + Decimal(str(i * 0.01)),
            mid=Decimal("0.505") + Decimal(str(i * 0.01)),
            spread=Decimal("0.01"),
            spread_bps=Decimal("100.0"),
            event_id=None,
            run_id="test_run",
        )
        ticks.append(tick)
        await repository.create_tick(
            tick_id=tick.tick_id,
            ts_wall=tick.ts_wall,
            ts_mono=tick.ts_mono,
            market_slug=tick.market_slug,
            outcome=tick.outcome,
            best_bid=tick.best_bid,
            best_ask=tick.best_ask,
            mid=tick.mid,
            spread=tick.spread,
            spread_bps=tick.spread_bps,
            event_id=tick.event_id,
            run_id=tick.run_id,
        )

    await repository.session.commit()
    return ticks


class TestGetTicksInRange:
    """Test get_ticks_in_range utility."""

    @pytest.mark.asyncio
    async def test_get_ticks_in_range_returns_ticks_in_range(
        self, repository: MarketTickRepository, sample_ticks: list[MarketTickRecord]
    ) -> None:
        """Test that get_ticks_in_range returns ticks within time range."""
        now = datetime.now(UTC)
        from_ts = now - timedelta(hours=2)  # 2 hours ago
        to_ts = now  # Now

        ticks = await get_ticks_in_range(repository, "btc-updown-15m", "UP", from_ts, to_ts)

        assert len(ticks) == 10
        assert all(tick.market_slug == "btc-updown-15m" for tick in ticks)
        assert all(tick.outcome == "UP" for tick in ticks)

    @pytest.mark.asyncio
    async def test_get_ticks_in_range_respects_time_bounds(
        self, repository: MarketTickRepository, sample_ticks: list[MarketTickRecord]
    ) -> None:
        """Test that get_ticks_in_range respects time bounds."""
        now = datetime.now(UTC)
        from_ts = now - timedelta(minutes=30)  # 30 minutes ago
        to_ts = now - timedelta(minutes=10)  # 10 minutes ago

        ticks = await get_ticks_in_range(repository, "btc-updown-15m", "UP", from_ts, to_ts)

        # Should only return ticks within the range
        assert all(from_ts <= tick.ts_wall <= to_ts for tick in ticks)

    @pytest.mark.asyncio
    async def test_get_ticks_in_range_respects_limit(
        self, repository: MarketTickRepository, sample_ticks: list[MarketTickRecord]
    ) -> None:
        """Test that get_ticks_in_range respects limit parameter."""
        now = datetime.now(UTC)
        from_ts = now - timedelta(hours=2)
        to_ts = now

        ticks = await get_ticks_in_range(
            repository, "btc-updown-15m", "UP", from_ts, to_ts, limit=5
        )

        assert len(ticks) == 5

    @pytest.mark.asyncio
    async def test_get_ticks_in_range_returns_empty_for_no_matches(
        self, repository: MarketTickRepository
    ) -> None:
        """Test that get_ticks_in_range returns empty list when no matches."""
        now = datetime.now(UTC)
        from_ts = now - timedelta(days=1)
        to_ts = now - timedelta(hours=23)

        ticks = await get_ticks_in_range(repository, "nonexistent-market", "UP", from_ts, to_ts)

        assert len(ticks) == 0


class TestGetTickCount:
    """Test get_tick_count utility."""

    @pytest.mark.asyncio
    async def test_get_tick_count_returns_correct_count(
        self, repository: MarketTickRepository, sample_ticks: list[MarketTickRecord]
    ) -> None:
        """Test that get_tick_count returns correct count."""
        now = datetime.now(UTC)
        from_ts = now - timedelta(hours=2)
        to_ts = now

        count = await get_tick_count(repository, "btc-updown-15m", "UP", from_ts, to_ts)

        assert count == 10

    @pytest.mark.asyncio
    async def test_get_tick_count_without_time_bounds(
        self, repository: MarketTickRepository, sample_ticks: list[MarketTickRecord]
    ) -> None:
        """Test that get_tick_count works without time bounds."""
        count = await get_tick_count(repository, "btc-updown-15m", "UP")

        assert count == 10

    @pytest.mark.asyncio
    async def test_get_tick_count_returns_zero_for_no_matches(
        self, repository: MarketTickRepository
    ) -> None:
        """Test that get_tick_count returns zero when no matches."""
        count = await get_tick_count(repository, "nonexistent-market", "UP")

        assert count == 0


class TestGetPriceStatistics:
    """Test get_price_statistics utility."""

    @pytest.mark.asyncio
    async def test_get_price_statistics_returns_correct_statistics(
        self, repository: MarketTickRepository, sample_ticks: list[MarketTickRecord]
    ) -> None:
        """Test that get_price_statistics returns correct statistics."""
        now = datetime.now(UTC)
        from_ts = now - timedelta(hours=2)
        to_ts = now

        stats = await get_price_statistics(repository, "btc-updown-15m", "UP", from_ts, to_ts)

        assert stats.tick_count == 10
        assert stats.min_price <= stats.max_price
        assert stats.first_price <= stats.last_price  # Prices increase over time
        assert stats.avg_price >= stats.min_price
        assert stats.avg_price <= stats.max_price

    @pytest.mark.asyncio
    async def test_get_price_statistics_handles_empty_range(
        self, repository: MarketTickRepository
    ) -> None:
        """Test that get_price_statistics handles empty range."""
        now = datetime.now(UTC)
        from_ts = now - timedelta(days=1)
        to_ts = now - timedelta(hours=23)

        stats = await get_price_statistics(repository, "nonexistent-market", "UP", from_ts, to_ts)

        assert stats.tick_count == 0
        assert stats.min_price == Decimal("0")
        assert stats.max_price == Decimal("0")
        assert stats.avg_price == Decimal("0")


class TestGetLatestTicksByMarket:
    """Test get_latest_ticks_by_market utility."""

    @pytest.mark.asyncio
    async def test_get_latest_ticks_by_market_returns_latest_ticks(
        self, repository: MarketTickRepository, sample_ticks: list[MarketTickRecord]
    ) -> None:
        """Test that get_latest_ticks_by_market returns latest ticks."""
        latest = await get_latest_ticks_by_market(repository, limit_per_market=1)

        assert ("btc-updown-15m", "UP") in latest
        tick = latest[("btc-updown-15m", "UP")]

        assert tick.market_slug == "btc-updown-15m"
        assert tick.outcome == "UP"
        # Should be the latest tick (highest ts_wall)
        assert tick.ts_wall == max(t.ts_wall for t in sample_ticks)

    @pytest.mark.asyncio
    async def test_get_latest_ticks_by_market_returns_empty_for_no_data(
        self, repository: MarketTickRepository
    ) -> None:
        """Test that get_latest_ticks_by_market returns empty dict when no data."""
        latest = await get_latest_ticks_by_market(repository, limit_per_market=1)

        assert len(latest) == 0

    @pytest.mark.asyncio
    async def test_get_latest_ticks_by_market_respects_limit(
        self, repository: MarketTickRepository, sample_ticks: list[MarketTickRecord]
    ) -> None:
        """Test that get_latest_ticks_by_market respects limit_per_market."""
        latest = await get_latest_ticks_by_market(repository, limit_per_market=1)

        # Should only return one tick per market/outcome
        assert len(latest) == 1
