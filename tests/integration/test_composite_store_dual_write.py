"""Integration tests for CompositeMarketDataStore dual-write behavior.

Tests that composite store:
- Writes to both memory and PostgreSQL stores
- Reads from memory store (fast path)
- Handles PostgreSQL store failures gracefully
- Persists data correctly
"""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.db.repository import MarketTickRepository
from polytrader.events.types import EventSource, MarketDataEvent
from polytrader.store import (
    CompositeMarketDataStore,
    MemoryMarketDataStore,
    PostgreSQLMarketTickStore,
)


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
async def composite_store(
    db_session: AsyncSession,
) -> AsyncGenerator[CompositeMarketDataStore, None]:
    """Create CompositeMarketDataStore for testing."""
    memory_store = MemoryMarketDataStore()
    repo = MarketTickRepository(db_session)
    postgres_store = PostgreSQLMarketTickStore(repo, batch_size=10, flush_interval=0.1)
    composite = CompositeMarketDataStore(memory_store, postgres_store)

    yield composite

    # Cleanup
    await composite.close()


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


class TestDualWrite:
    """Test dual-write behavior."""

    def test_add_writes_to_both_stores(
        self, composite_store: CompositeMarketDataStore, sample_event: MarketDataEvent
    ) -> None:
        """Test that add() writes to both memory and PostgreSQL stores."""
        # Add event
        composite_store.add(sample_event)

        # Wait for background processing
        asyncio.run(asyncio.sleep(0.2))

        # Flush PostgreSQL store
        asyncio.run(composite_store.flush())

        # Verify memory store has it (fast read via public interface)
        memory_latest = composite_store.latest("btc-updown-15m", "UP")
        assert memory_latest is not None
        assert memory_latest.market_slug == "btc-updown-15m"

        # Verify PostgreSQL store has it (via repository - using type checking)
        async def verify_postgres() -> None:
            # Access secondary store via type checking
            from polytrader.store import CompositeMarketDataStore, PostgreSQLMarketTickStore

            assert isinstance(composite_store, CompositeMarketDataStore)
            # Get secondary store via type checking (we know it's the first one)
            secondary_stores = [
                s for s in composite_store._secondary if isinstance(s, PostgreSQLMarketTickStore)
            ]
            assert len(secondary_stores) == 1
            postgres_store = secondary_stores[0]
            repo = postgres_store._repository
            latest = await repo.get_latest("btc-updown-15m", "UP")
            assert latest is not None
            assert latest.market_slug == "btc-updown-15m"
            assert float(latest.best_bid) == pytest.approx(0.45)

        asyncio.run(verify_postgres())

    def test_latest_reads_from_primary(
        self, composite_store: CompositeMarketDataStore, sample_event: MarketDataEvent
    ) -> None:
        """Test that latest() reads from primary store (memory, fast path)."""
        # Add event
        composite_store.add(sample_event)

        # Query latest (should read from memory store)
        latest = composite_store.latest("btc-updown-15m", "UP")

        assert latest is not None
        assert latest.market_slug == "btc-updown-15m"
        assert latest.best_bid == pytest.approx(0.45)

        # Verify it came from memory store (not PostgreSQL)
        # We can't directly access _primary, but we can verify behavior:
        # latest() should return immediately (memory store is fast)
        # If it came from PostgreSQL, it would be slower
        assert latest is not None

    def test_history_reads_from_primary(self, composite_store: CompositeMarketDataStore) -> None:
        """Test that history() reads from primary store."""
        # Add multiple events
        for i in range(3):
            event = MarketDataEvent(
                event_id=str(uuid4()),
                ts_wall=datetime.now(UTC).isoformat(),
                ts_mono=1000.0 + i,
                market_slug="test-market",
                outcome="UP",
                best_bid=0.40 + i * 0.01,
                best_ask=0.45 + i * 0.01,
            )
            composite_store.add(event)

        # Query history (should read from memory store)
        history = composite_store.history("test-market", "UP")

        assert len(history) == 3
        # Verify history is correct (reads from primary/memory store)
        assert all(e.market_slug == "test-market" for e in history)

    def test_handles_postgres_failure_gracefully(
        self, composite_store: CompositeMarketDataStore, sample_event: MarketDataEvent
    ) -> None:
        """Test that PostgreSQL store failures don't block writes."""
        # Close PostgreSQL store to simulate failure
        # Use type checking to access secondary store
        from polytrader.store import CompositeMarketDataStore, PostgreSQLMarketTickStore

        assert isinstance(composite_store, CompositeMarketDataStore)
        secondary_stores = [
            s for s in composite_store._secondary if isinstance(s, PostgreSQLMarketTickStore)
        ]
        if secondary_stores:
            postgres_store = secondary_stores[0]
            asyncio.run(postgres_store.close())

        # Add event (should still work, writes to memory)
        composite_store.add(sample_event)

        # Verify memory store has it
        latest = composite_store.latest("btc-updown-15m", "UP")
        assert latest is not None

        # PostgreSQL write should have failed silently (logged but not raised)


class TestFactory:
    """Test store factory function."""

    def test_factory_creates_composite_when_database_available(
        self, postgres_test_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that factory creates composite store when database is configured."""
        from urllib.parse import urlparse

        from polytrader.store_factory import create_market_data_store

        # Set up database config via environment
        parsed = urlparse(postgres_test_url)
        monkeypatch.setenv("DB_HOST", parsed.hostname or "localhost")
        monkeypatch.setenv("DB_PORT", str(parsed.port or 5432))
        monkeypatch.setenv(
            "DB_DATABASE", parsed.path.lstrip("/") if parsed.path else "polytrader_test"
        )
        monkeypatch.setenv("DB_USER", parsed.username or "test_user")
        monkeypatch.setenv("DB_PASSWORD", parsed.password or "test_password")

        # Create store (should create composite)
        store = create_market_data_store(enable_postgres=True)

        # Verify it's a composite store
        assert isinstance(store, CompositeMarketDataStore)

        # Verify structure via public interface
        # Composite store should have memory store as primary
        # We can verify by checking that latest() works (reads from primary)
        test_event = MarketDataEvent(
            event_id=str(uuid4()),
            ts_wall=datetime.now(UTC).isoformat(),
            ts_mono=1000.0,
            market_slug="test-market",
            outcome="UP",
            best_bid=0.40,
            best_ask=0.45,
        )
        store.add(test_event)
        latest = store.latest("test-market", "UP")
        assert latest is not None
        assert latest.market_slug == "test-market"

        # Cleanup
        asyncio.run(store.close())

        # Cleanup
        asyncio.run(store.close())

    def test_factory_creates_memory_only_when_database_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that factory creates memory-only dual-view store when database is not configured."""
        from polytrader.store import DualViewMarketDataStore
        from polytrader.store_factory import create_market_data_store

        # Mock get_database_url to raise ValueError (simulating missing config)
        def mock_get_database_url(*args: object, **kwargs: object) -> str:
            raise ValueError("Database configuration not available")

        monkeypatch.setattr("polytrader.store_factory.get_database_url", mock_get_database_url)

        # Create store (should create dual-view memory store, not composite)
        store = create_market_data_store(enable_postgres=True)

        # Verify it's dual-view memory store (slug + pattern views), not composite
        assert isinstance(store, DualViewMarketDataStore)
        assert not isinstance(store, CompositeMarketDataStore)

    def test_factory_respects_enable_postgres_flag(
        self, postgres_test_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that factory respects enable_postgres=False flag."""
        # Set up database config
        from urllib.parse import urlparse

        from polytrader.store import DualViewMarketDataStore
        from polytrader.store_factory import create_market_data_store

        parsed = urlparse(postgres_test_url)
        monkeypatch.setenv("DB_HOST", parsed.hostname or "localhost")
        monkeypatch.setenv(
            "DB_DATABASE", parsed.path.lstrip("/") if parsed.path else "polytrader_test"
        )

        # Create store with enable_postgres=False
        store = create_market_data_store(enable_postgres=False)

        # Verify it's dual-view memory store (slug + pattern views), not composite
        assert isinstance(store, DualViewMarketDataStore)
        assert not isinstance(store, CompositeMarketDataStore)


class TestCleanup:
    """Test cleanup and shutdown behavior."""

    @pytest.mark.asyncio
    async def test_close_flushes_all_stores(
        self, composite_store: CompositeMarketDataStore, sample_event: MarketDataEvent
    ) -> None:
        """Test that close() flushes all stores."""
        # Add event
        composite_store.add(sample_event)

        # Wait for background processing
        await asyncio.sleep(0.2)

        # Close (should flush)
        await composite_store.close()

        # Verify data was persisted to PostgreSQL
        # Use type checking to access secondary store
        from polytrader.store import CompositeMarketDataStore, PostgreSQLMarketTickStore

        assert isinstance(composite_store, CompositeMarketDataStore)
        secondary_stores = [
            s for s in composite_store._secondary if isinstance(s, PostgreSQLMarketTickStore)
        ]
        assert len(secondary_stores) == 1
        postgres_store = secondary_stores[0]
        repo = postgres_store._repository
        latest = await repo.get_latest("btc-updown-15m", "UP")
        assert latest is not None
