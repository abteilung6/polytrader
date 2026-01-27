"""Integration tests for market data API endpoints.

Per Commit 3: Integration tests for GET /api/v1/market/ticks/latest endpoint.
Per testing.mdc: Integration tests use real database and verify end-to-end behavior.
"""

import uuid
from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.api.app import create_app
from polytrader.api.dependencies import get_db_session
from polytrader.db.repository import MarketTickRepository


@pytest.fixture
def client(postgres_test_url: str, postgres_db: AsyncGenerator[None, None]) -> Iterator[TestClient]:
    """Create FastAPI test client with test database.

    Overrides get_db_session dependency to use test database instead of dev database.
    """
    # Convert URL to SQLAlchemy async format
    sqlalchemy_url = postgres_test_url
    if sqlalchemy_url.startswith("postgresql://"):
        sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+psycopg://", 1)

    # Create engine and session factory for test database
    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Clean up market_ticks table at test start
    async def cleanup_ticks() -> None:
        """Clean up market_ticks table."""
        from sqlalchemy import text

        async with Session() as session:
            try:
                await session.execute(text("TRUNCATE TABLE market_ticks CASCADE"))
                await session.commit()
            except Exception:
                await session.rollback()

    # Run cleanup synchronously using asyncio
    import asyncio

    asyncio.run(cleanup_ticks())

    app = create_app()

    # Override get_db_session to use test database session
    async def override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        """Override dependency to use test database session."""
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    yield TestClient(app)

    # Cleanup: remove dependency override and clean up ticks
    app.dependency_overrides.clear()
    asyncio.run(cleanup_ticks())


@pytest.fixture
def sample_tick(
    postgres_test_url: str,
) -> tuple[str, str]:  # Returns (market_slug, outcome)
    """Create a sample tick in the database and return market_slug and outcome."""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    # Convert URL to SQLAlchemy async format
    sqlalchemy_url = postgres_test_url
    if sqlalchemy_url.startswith("postgresql://"):
        sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+psycopg://", 1)

    # Create engine and session factory for test database
    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Create sample tick
    async def create_tick() -> tuple[str, str]:
        async with Session() as session:
            repo = MarketTickRepository(session)

            tick_id = uuid.uuid4()
            market_slug = "btc-updown-15m-1767900600"
            outcome = "UP"
            ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

            await repo.create_tick(
                tick_id=tick_id,
                ts_wall=ts_wall,
                ts_mono=1234567890.123456,
                market_slug=market_slug,
                outcome=outcome,
                best_bid=Decimal("0.45000000"),
                best_ask=Decimal("0.46000000"),
                mid=Decimal("0.45500000"),
                spread=Decimal("0.01000000"),
                spread_bps=Decimal("100.00"),
                event_id=None,
                run_id="test-run-123",
            )

            await session.commit()
            return (market_slug, outcome)

    # Run async function synchronously
    return asyncio.run(create_tick())


@pytest.mark.integration
def test_get_latest_tick_not_found(client: TestClient) -> None:
    """Test GET /api/v1/market/ticks/latest returns 404 when no data."""
    response = client.get(
        "/api/v1/market/ticks/latest",
        params={"market_slug": "nonexistent-market", "outcome": "UP"},
    )

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    detail = data["detail"]
    assert detail["error"] == "Market not found"
    assert detail["code"] == "MARKET_NOT_FOUND"


@pytest.mark.integration
async def test_get_latest_tick_success(client: TestClient, sample_tick: tuple[str, str]) -> None:
    """Test GET /api/v1/market/ticks/latest returns 200 with actual tick data."""
    market_slug, outcome = sample_tick

    response = client.get(
        "/api/v1/market/ticks/latest",
        params={"market_slug": market_slug, "outcome": outcome},
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "tick_id" in data
    assert "ts_wall" in data
    assert "ts_mono" in data
    assert data["market_slug"] == market_slug
    assert data["outcome"] == outcome
    assert "best_bid" in data
    assert "best_ask" in data
    assert "mid" in data
    assert "spread" in data
    assert "spread_bps" in data

    # Verify Pydantic model structure
    from polytrader.api.models import MarketTickResponse

    MarketTickResponse(**data)  # Should not raise

    # Verify price values
    assert Decimal(data["best_bid"]) == Decimal("0.45000000")
    assert Decimal(data["best_ask"]) == Decimal("0.46000000")
    assert Decimal(data["mid"]) == Decimal("0.45500000")


@pytest.mark.integration
def test_get_latest_tick_returns_most_recent(
    client: TestClient, sample_tick: tuple[str, str], postgres_test_url: str
) -> None:
    """Test that GET /api/v1/market/ticks/latest returns the most recent tick."""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    market_slug, outcome = sample_tick

    # Use the same database URL as the client fixture
    async def add_newer_tick() -> None:
        # Create session using test database (same as client fixture)
        sqlalchemy_url = postgres_test_url
        if sqlalchemy_url.startswith("postgresql://"):
            sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+psycopg://", 1)

        engine = create_async_engine(sqlalchemy_url, echo=False)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with Session() as session:
            repo = MarketTickRepository(session)
            # Create a newer tick (later timestamp)
            newer_tick_id = uuid.uuid4()
            newer_ts_wall = datetime(2025, 1, 27, 12, 5, 0, tzinfo=UTC)

            await repo.create_tick(
                tick_id=newer_tick_id,
                ts_wall=newer_ts_wall,
                ts_mono=1234567920.123456,  # Later monotonic time
                market_slug=market_slug,
                outcome=outcome,
                best_bid=Decimal("0.46000000"),  # Different price
                best_ask=Decimal("0.47000000"),
                mid=Decimal("0.46500000"),
                spread=Decimal("0.01000000"),
                spread_bps=Decimal("100.00"),
                event_id=None,
                run_id="test-run-123",
            )

            await session.commit()

    # Run async function synchronously
    asyncio.run(add_newer_tick())

    # Request latest tick
    response = client.get(
        "/api/v1/market/ticks/latest",
        params={"market_slug": market_slug, "outcome": outcome},
    )

    assert response.status_code == 200
    data = response.json()

    # Verify it returns the newer tick (by checking price)
    assert Decimal(data["best_bid"]) == Decimal("0.46000000")
    assert Decimal(data["mid"]) == Decimal("0.46500000")


@pytest.mark.integration
def test_get_latest_tick_invalid_outcome(client: TestClient) -> None:
    """Test that invalid outcome returns 400."""
    response = client.get(
        "/api/v1/market/ticks/latest",
        params={"market_slug": "btc-updown-15m-1767900600", "outcome": "INVALID"},
    )

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    detail = data["detail"]
    assert detail["error"] == "Invalid outcome"
    assert detail["code"] == "INVALID_OUTCOME"


@pytest.mark.integration
def test_get_historical_ticks_empty(client: TestClient) -> None:
    """Test GET /api/v1/market/ticks/history returns empty list when no data."""
    response = client.get(
        "/api/v1/market/ticks/history",
        params={"market_slug": "nonexistent-market", "outcome": "UP"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "ticks" in data
    assert "count" in data
    assert data["ticks"] == []
    assert data["count"] == 0


@pytest.mark.integration
def test_get_historical_ticks_success(client: TestClient, sample_tick: tuple[str, str]) -> None:
    """Test GET /api/v1/market/ticks/history returns 200 with actual tick data."""
    market_slug, outcome = sample_tick

    response = client.get(
        "/api/v1/market/ticks/history",
        params={"market_slug": market_slug, "outcome": outcome},
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "ticks" in data
    assert "count" in data
    assert len(data["ticks"]) == 1
    assert data["count"] == 1

    # Verify tick structure
    tick = data["ticks"][0]
    assert "tick_id" in tick
    assert "ts_wall" in tick
    assert tick["market_slug"] == market_slug
    assert tick["outcome"] == outcome

    # Verify Pydantic model structure
    from polytrader.api.models import HistoricalTicksResponse

    HistoricalTicksResponse(**data)  # Should not raise


@pytest.mark.integration
def test_get_historical_ticks_with_time_range(
    client: TestClient, sample_tick: tuple[str, str], postgres_test_url: str
) -> None:
    """Test GET /api/v1/market/ticks/history with time range filters."""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    market_slug, outcome = sample_tick

    # Add another tick outside the time range
    async def add_tick_outside_range() -> None:
        from datetime import UTC, datetime

        sqlalchemy_url = postgres_test_url
        if sqlalchemy_url.startswith("postgresql://"):
            sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+psycopg://", 1)

        engine = create_async_engine(sqlalchemy_url, echo=False)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with Session() as session:
            repo = MarketTickRepository(session)
            # Create a tick outside the time range (earlier)
            earlier_tick_id = uuid.uuid4()
            earlier_ts_wall = datetime(2025, 1, 27, 11, 0, 0, tzinfo=UTC)

            await repo.create_tick(
                tick_id=earlier_tick_id,
                ts_wall=earlier_ts_wall,
                ts_mono=1234567800.123456,
                market_slug=market_slug,
                outcome=outcome,
                best_bid=Decimal("0.44000000"),
                best_ask=Decimal("0.45000000"),
                mid=Decimal("0.44500000"),
                spread=Decimal("0.01000000"),
                spread_bps=Decimal("100.00"),
                event_id=None,
                run_id="test-run-123",
            )

            await session.commit()

    # Run async function synchronously
    asyncio.run(add_tick_outside_range())

    # Query with time range that excludes the earlier tick
    from datetime import UTC, datetime

    from_ts = datetime(2025, 1, 27, 11, 30, 0, tzinfo=UTC)
    to_ts = datetime(2025, 1, 27, 13, 0, 0, tzinfo=UTC)

    response = client.get(
        "/api/v1/market/ticks/history",
        params={
            "market_slug": market_slug,
            "outcome": outcome,
            "from_ts": from_ts.isoformat(),
            "to_ts": to_ts.isoformat(),
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Should only return the tick within the time range
    assert len(data["ticks"]) == 1
    assert data["count"] == 1
    assert Decimal(data["ticks"][0]["best_bid"]) == Decimal("0.45000000")


@pytest.mark.integration
def test_get_historical_ticks_invalid_time_range(client: TestClient) -> None:
    """Test that from_ts > to_ts returns 400."""
    from datetime import UTC, datetime

    from_ts = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)
    to_ts = datetime(2025, 1, 27, 11, 0, 0, tzinfo=UTC)  # Before from_ts

    response = client.get(
        "/api/v1/market/ticks/history",
        params={
            "market_slug": "btc-updown-15m-1767900600",
            "outcome": "UP",
            "from_ts": from_ts.isoformat(),
            "to_ts": to_ts.isoformat(),
        },
    )

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    detail = data["detail"]
    assert detail["error"] == "Invalid time range"
    assert detail["code"] == "INVALID_TIME_RANGE"


@pytest.mark.integration
def test_get_markets_empty(client: TestClient) -> None:
    """Test GET /api/v1/market/markets returns empty list when no data."""
    response = client.get("/api/v1/market/markets")

    assert response.status_code == 200
    data = response.json()
    assert "markets" in data
    assert "count" in data
    assert data["markets"] == []
    assert data["count"] == 0


@pytest.mark.integration
def test_get_markets_success(client: TestClient, sample_tick: tuple[str, str]) -> None:
    """Test GET /api/v1/market/markets returns 200 with actual market data."""
    market_slug, outcome = sample_tick

    response = client.get("/api/v1/market/markets")

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "markets" in data
    assert "count" in data
    assert len(data["markets"]) >= 1
    assert data["count"] >= 1

    # Find our market in the list
    market = next(
        (m for m in data["markets"] if m["market_slug"] == market_slug and m["outcome"] == outcome),
        None,
    )
    assert market is not None
    assert market["market_slug"] == market_slug
    assert market["outcome"] == outcome
    assert market["latest_tick_ts"] is not None
    assert "active" in market

    # Verify Pydantic model structure
    from polytrader.api.models import MarketsResponse

    MarketsResponse(**data)  # Should not raise


@pytest.mark.integration
def test_get_markets_pattern_filter(client: TestClient, sample_tick: tuple[str, str]) -> None:
    """Test GET /api/v1/market/markets with pattern filter."""
    market_slug, outcome = sample_tick

    # Extract pattern from market slug
    pattern = "-".join(market_slug.split("-")[:-1])  # Everything except timestamp

    response = client.get("/api/v1/market/markets", params={"pattern": pattern})

    assert response.status_code == 200
    data = response.json()

    # All returned markets should match the pattern
    for market in data["markets"]:
        assert market["market_slug"].startswith(pattern + "-")


@pytest.mark.integration
def test_get_markets_ordering(
    client: TestClient, sample_tick: tuple[str, str], postgres_test_url: str
) -> None:
    """Test that GET /api/v1/market/markets orders markets by latest_tick_ts descending."""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    market_slug, outcome = sample_tick

    # Add another market with earlier timestamp
    async def add_earlier_market() -> None:
        sqlalchemy_url = postgres_test_url
        if sqlalchemy_url.startswith("postgresql://"):
            sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+psycopg://", 1)

        engine = create_async_engine(sqlalchemy_url, echo=False)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with Session() as session:
            repo = MarketTickRepository(session)
            # Create a market with earlier timestamp
            earlier_market_slug = "btc-updown-15m-1767899700"
            earlier_tick_id = uuid.uuid4()
            earlier_ts_wall = datetime(2025, 1, 27, 11, 45, 0, tzinfo=UTC)

            await repo.create_tick(
                tick_id=earlier_tick_id,
                ts_wall=earlier_ts_wall,
                ts_mono=1234567800.123456,
                market_slug=earlier_market_slug,
                outcome=outcome,
                best_bid=Decimal("0.44000000"),
                best_ask=Decimal("0.45000000"),
                mid=Decimal("0.44500000"),
                spread=Decimal("0.01000000"),
                spread_bps=Decimal("100.00"),
                event_id=None,
                run_id="test-run-123",
            )

            await session.commit()

    # Run async function synchronously
    asyncio.run(add_earlier_market())

    response = client.get("/api/v1/market/markets")

    assert response.status_code == 200
    data = response.json()

    # Markets should be ordered by latest_tick_ts descending
    # Find our markets in the list
    markets_with_ts = [m for m in data["markets"] if m["latest_tick_ts"] is not None]
    if len(markets_with_ts) >= 2:
        # Verify ordering (newest first)
        for i in range(len(markets_with_ts) - 1):
            current_ts = datetime.fromisoformat(
                markets_with_ts[i]["latest_tick_ts"].replace("Z", "+00:00")
            )
            next_ts = datetime.fromisoformat(
                markets_with_ts[i + 1]["latest_tick_ts"].replace("Z", "+00:00")
            )
            assert current_ts >= next_ts
