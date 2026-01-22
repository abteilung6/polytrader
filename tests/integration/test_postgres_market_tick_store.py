"""Integration tests for PostgreSQLMarketTickStore."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.db.repository import MarketTickRepository
from polytrader.events.types import EventSource, MarketDataEvent
from polytrader.store import PostgreSQLMarketTickStore


@pytest.fixture
async def db_session(
    postgres_test_url: str, postgres_db: None
) -> AsyncGenerator[AsyncSession, None]:
    """Provide SQLAlchemy session for tests."""
    from sqlalchemy import text

    # Migrations are run by postgres_db fixture

    # Convert URL to SQLAlchemy async format
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


@pytest.fixture
async def store(
    db_session: AsyncSession,
) -> AsyncGenerator[PostgreSQLMarketTickStore, None]:
    """Create PostgreSQLMarketTickStore for testing."""
    repo = MarketTickRepository(db_session)
    store = PostgreSQLMarketTickStore(repo, batch_size=10, flush_interval=0.1)

    yield store

    # Cleanup
    await store.close()


@pytest.fixture
def sample_event() -> MarketDataEvent:
    """Create sample MarketDataEvent."""
    return MarketDataEvent(
        event_id=str(uuid4()),
        ts_wall=datetime.now(UTC).isoformat(),
        ts_mono=12345.678,
        correlation_id="test-correlation",
        run_id="test-run",
        schema_version="1.0",
        source=EventSource.MDP,
        market_slug="btc-updown-15m",
        outcome="UP",
        best_bid=0.45,
        best_ask=0.50,
    )


class TestAdd:
    """Test add() method."""

    @pytest.mark.asyncio
    async def test_add_writes_to_database(
        self, store: PostgreSQLMarketTickStore, sample_event: MarketDataEvent
    ) -> None:
        """Test that add() writes event to database."""
        # Add event (sync, non-blocking)
        store.add(sample_event)

        # Wait a bit for background thread to process
        await asyncio.sleep(0.1)

        # Flush to ensure write completes
        await store.flush()

        # Verify via repository
        repo = store._repository
        latest = await repo.get_latest("btc-updown-15m", "UP")
        assert latest is not None
        assert latest.market_slug == "btc-updown-15m"
        assert latest.outcome == "UP"
        assert float(latest.best_bid) == pytest.approx(0.45)
        assert float(latest.best_ask) == pytest.approx(0.50)

    def test_add_is_non_blocking(
        self, store: PostgreSQLMarketTickStore, sample_event: MarketDataEvent
    ) -> None:
        """Test that add() is non-blocking."""
        import time

        start = time.time()
        store.add(sample_event)
        elapsed = time.time() - start

        # Should return quickly (< 10ms)
        assert elapsed < 0.01


class TestLatest:
    """Test latest() method."""

    @pytest.mark.asyncio
    async def test_latest_returns_correct_tick(
        self, store: PostgreSQLMarketTickStore, sample_event: MarketDataEvent
    ) -> None:
        """Test that latest() returns the most recent tick."""
        # Add event
        store.add(sample_event)

        # Wait for background thread to process
        await asyncio.sleep(0.1)
        await store.flush()

        # Query latest
        latest = store.latest("btc-updown-15m", "UP")

        assert latest is not None
        assert latest.market_slug == "btc-updown-15m"
        assert latest.outcome == "UP"
        assert latest.best_bid == pytest.approx(0.45)
        assert latest.best_ask == pytest.approx(0.50)

    @pytest.mark.asyncio
    async def test_latest_returns_none_if_no_ticks(self, store: PostgreSQLMarketTickStore) -> None:
        """Test that latest() returns None if no ticks exist."""
        latest = store.latest("nonexistent-market", "UP")
        assert latest is None

    @pytest.mark.asyncio
    async def test_latest_returns_most_recent(self, store: PostgreSQLMarketTickStore) -> None:
        """Test that latest() returns the most recent tick."""
        # Add multiple events
        event1 = MarketDataEvent(
            event_id=str(uuid4()),
            ts_wall=datetime.now(UTC).isoformat(),
            ts_mono=1000.0,
            market_slug="test-market",
            outcome="UP",
            best_bid=0.40,
            best_ask=0.45,
        )
        event2 = MarketDataEvent(
            event_id=str(uuid4()),
            ts_wall=datetime.now(UTC).isoformat(),
            ts_mono=2000.0,
            market_slug="test-market",
            outcome="UP",
            best_bid=0.50,
            best_ask=0.55,
        )

        store.add(event1)
        store.add(event2)

        # Wait for background thread to process
        await asyncio.sleep(0.1)
        await store.flush()

        # Latest should be event2
        latest = store.latest("test-market", "UP")
        assert latest is not None
        assert latest.best_bid == pytest.approx(0.50)


class TestHistory:
    """Test history() method."""

    @pytest.mark.asyncio
    async def test_history_returns_all_ticks(self, store: PostgreSQLMarketTickStore) -> None:
        """Test that history() returns all ticks for market/outcome."""
        # Add multiple events
        for i in range(5):
            event = MarketDataEvent(
                event_id=str(uuid4()),
                ts_wall=datetime.now(UTC).isoformat(),
                ts_mono=1000.0 + i,
                market_slug="test-market",
                outcome="UP",
                best_bid=0.40 + i * 0.01,
                best_ask=0.45 + i * 0.01,
            )
            store.add(event)

        # Wait for background thread to process
        await asyncio.sleep(0.1)
        await store.flush()

        # Query history
        history = store.history("test-market", "UP")

        assert len(history) == 5
        # Should be sorted by time (oldest first)
        assert history[0].best_bid == pytest.approx(0.40)
        assert history[-1].best_bid == pytest.approx(0.44)

    @pytest.mark.asyncio
    async def test_history_returns_empty_list_if_no_ticks(
        self, store: PostgreSQLMarketTickStore
    ) -> None:
        """Test that history() returns empty list if no ticks exist."""
        history = store.history("nonexistent-market", "UP")
        assert history == []


class TestGetAllMarkets:
    """Test get_all_markets() method."""

    @pytest.mark.asyncio
    async def test_get_all_markets_returns_all_pairs(
        self, store: PostgreSQLMarketTickStore
    ) -> None:
        """Test that get_all_markets() returns all market/outcome pairs."""
        # Add events for different markets/outcomes
        events = [
            MarketDataEvent(
                event_id=str(uuid4()),
                ts_wall=datetime.now(UTC).isoformat(),
                ts_mono=1000.0,
                market_slug="market1",
                outcome="UP",
                best_bid=0.40,
                best_ask=0.45,
            ),
            MarketDataEvent(
                event_id=str(uuid4()),
                ts_wall=datetime.now(UTC).isoformat(),
                ts_mono=1001.0,
                market_slug="market1",
                outcome="DOWN",
                best_bid=0.50,
                best_ask=0.55,
            ),
            MarketDataEvent(
                event_id=str(uuid4()),
                ts_wall=datetime.now(UTC).isoformat(),
                ts_mono=1002.0,
                market_slug="market2",
                outcome="UP",
                best_bid=0.60,
                best_ask=0.65,
            ),
        ]

        for event in events:
            store.add(event)

        # Wait for background thread to process
        await asyncio.sleep(0.1)
        await store.flush()

        # Query all markets
        markets = store.get_all_markets()

        assert len(markets) == 3
        assert ("market1", "UP") in markets
        assert ("market1", "DOWN") in markets
        assert ("market2", "UP") in markets

    @pytest.mark.asyncio
    async def test_get_all_markets_returns_empty_list_if_no_ticks(
        self, store: PostgreSQLMarketTickStore
    ) -> None:
        """Test that get_all_markets() returns empty list if no ticks exist."""
        markets = store.get_all_markets()
        assert markets == []


class TestFlushAndClose:
    """Test flush() and close() methods."""

    @pytest.mark.asyncio
    async def test_flush_writes_buffered_ticks(
        self, store: PostgreSQLMarketTickStore, sample_event: MarketDataEvent
    ) -> None:
        """Test that flush() writes all buffered ticks."""
        # Add event (not yet flushed)
        store.add(sample_event)

        # Wait for background thread to process
        await asyncio.sleep(0.1)

        # Flush manually
        await store.flush()

        # Verify tick was written
        latest = store.latest("btc-updown-15m", "UP")
        assert latest is not None

    @pytest.mark.asyncio
    async def test_close_flushes_remaining_ticks(
        self, store: PostgreSQLMarketTickStore, sample_event: MarketDataEvent
    ) -> None:
        """Test that close() flushes remaining ticks."""
        # Add event
        store.add(sample_event)

        # Wait for background thread to process
        await asyncio.sleep(0.1)

        # Close (should flush)
        await store.close()

        # Verify tick was written
        latest = store.latest("btc-updown-15m", "UP")
        assert latest is not None

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self, store: PostgreSQLMarketTickStore) -> None:
        """Test that close() can be called multiple times safely."""
        await store.close()
        await store.close()  # Should not raise
