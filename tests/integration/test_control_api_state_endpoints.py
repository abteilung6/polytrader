"""Integration tests for control API state endpoints.

Tests GET endpoints for reading system state:
- GET /state/health
- GET /state/execution
- GET /state/live-strategies
- GET /state/strategies
- GET /state/strategies/{strategy_id}
- GET /state/strategies/{strategy_id}/signals
- GET /state/strategies/{strategy_id}/orders
- GET /state/strategies/{strategy_id}/performance
- GET /state/commands/{command_id}
"""

import asyncio
from collections.abc import AsyncGenerator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.api.app import create_app
from polytrader.api.dependencies import get_db_session


@pytest.fixture
def client(postgres_test_url: str, postgres_db: AsyncGenerator[None, None]) -> Iterator[TestClient]:
    """Create FastAPI test client with test database.

    Overrides get_db_session so GET /state/strategies and GET /state/strategies/{id}
    use the same test database as command endpoints.
    """
    if postgres_test_url.startswith("postgresql://"):
        sqlalchemy_url = postgres_test_url.replace("postgresql://", "postgresql+psycopg://", 1)
    else:
        sqlalchemy_url = postgres_test_url

    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def cleanup_strategies() -> None:
        from sqlalchemy import text

        async with Session() as session:
            try:
                await session.execute(text("TRUNCATE TABLE strategy_instances CASCADE"))
                await session.commit()
            except Exception:
                await session.rollback()

    asyncio.run(cleanup_strategies())

    app = create_app()

    async def override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    yield TestClient(app)

    app.dependency_overrides.clear()
    asyncio.run(cleanup_strategies())


@pytest.fixture
def test_strategy(client: TestClient) -> str:
    """Create a strategy via POST and return strategy_id for GET-by-id tests."""
    import uuid

    strategy_id = f"test-strategy-{uuid.uuid4().hex[:8]}"
    request = {
        "strategy_id": strategy_id,
        "name": "Test Strategy",
        "description": "Strategy for GET-by-id tests",
        "config": {"buy_threshold": 0.3, "min_history": 30},
        "template_type_id": "simple_threshold",
        "version_selector": {"exact": "1.0.0"},
        "desired_state": "RUNNING",
    }
    response = client.post("/api/v1/commands/strategies", json=request)
    assert response.status_code == 201
    return strategy_id


def test_get_health(client: TestClient) -> None:
    """Test GET /state/health returns health with gates."""
    response = client.get("/api/v1/state/health")
    assert response.status_code == 200
    data = response.json()
    assert "overall" in data
    assert "gates" in data
    assert data["overall"] in ["ok", "degraded", "down"]
    assert "db" in data["gates"]
    assert "market_data_freshness" in data["gates"]
    assert "event_bus_lag" in data["gates"]
    assert "venue_connectivity" in data["gates"]
    assert "risk_engine" in data["gates"]
    assert "clock_skew_ms" in data["gates"]

    # Verify Pydantic model structure
    from polytrader.api.models import HealthResponse

    HealthResponse(**data)  # Should not raise


def test_get_execution_state(client: TestClient) -> None:
    """Test GET /state/execution returns execution state with version."""
    response = client.get("/api/v1/state/execution")
    assert response.status_code == 200
    data = response.json()
    assert "execution_enabled" in data
    assert "version" in data
    assert isinstance(data["version"], int)
    assert "updated_at" in data
    assert "updated_by" in data
    assert "reason" in data

    # Verify Pydantic model structure
    from polytrader.api.models import ExecutionStateResponse

    ExecutionStateResponse(**data)  # Should not raise


def test_get_live_strategies(client: TestClient) -> None:
    """Test GET /state/live-strategies returns active strategy IDs."""
    response = client.get("/api/v1/state/live-strategies")
    assert response.status_code == 200
    data = response.json()
    assert "active_strategies" in data
    assert isinstance(data["active_strategies"], list)

    # Verify Pydantic model structure
    from polytrader.api.models import LiveStrategiesResponse

    LiveStrategiesResponse(**data)  # Should not raise


def test_get_strategies(client: TestClient) -> None:
    """Test GET /state/strategies returns all strategies."""
    response = client.get("/api/v1/state/strategies")
    assert response.status_code == 200
    data = response.json()
    assert "strategies" in data
    assert isinstance(data["strategies"], list)

    # Verify Pydantic model structure
    from polytrader.api.models import StrategiesResponse

    StrategiesResponse(**data)  # Should not raise


def test_get_command_status_not_found(client: TestClient) -> None:
    """Test GET /state/commands/{command_id} returns 404 for non-existent."""
    response = client.get("/api/v1/state/commands/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data or "detail" in data


def test_get_strategy_by_id_not_found(client: TestClient) -> None:
    """Test GET /state/strategies/{strategy_id} returns 404 for non-existent."""
    response = client.get("/api/v1/state/strategies/nonexistent-strategy-id")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert data["detail"] == "Strategy not found"


def test_get_strategy_by_id_success(client: TestClient, test_strategy: str) -> None:
    """Test GET /state/strategies/{strategy_id} returns 200 and StrategyResponse."""
    response = client.get(f"/api/v1/state/strategies/{test_strategy}")
    assert response.status_code == 200
    data = response.json()
    assert data["strategy_id"] == test_strategy
    assert data["name"] == "Test Strategy"
    assert data["template_type_id"] == "simple_threshold"
    assert data["template_version"] == "1.0.0"
    assert "desired_state" in data
    assert "actual_state" in data
    assert "created_at" in data
    assert "updated_at" in data

    from polytrader.api.models import StrategyResponse

    StrategyResponse(**data)


async def _insert_signal_events(
    postgres_test_url: str,
    strategy_id: str,
    count: int,
) -> None:
    """Insert SignalEvent records for strategy_id into events table (same DB as client)."""
    import uuid
    from datetime import UTC, datetime

    from polytrader.db.repository import EventRepository

    if postgres_test_url.startswith("postgresql://"):
        sqlalchemy_url = postgres_test_url.replace("postgresql://", "postgresql+psycopg://", 1)
    else:
        sqlalchemy_url = postgres_test_url

    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        repo = EventRepository(session)
        for i in range(count):
            await repo.create_event(
                event_id=uuid.uuid4(),
                ts_wall=datetime.now(UTC),
                ts_mono=1000.0 + i,
                correlation_id=f"corr-{i}",
                run_id="test-run",
                schema_version="1.0",
                source="strategy",
                event_type="SignalEvent",
                event_data={
                    "market_slug": "btc-updown",
                    "outcome": "UP",
                    "p_up": 0.6,
                    "p_down": 0.4,
                    "edge": 0.1,
                    "confidence": 0.8,
                    "model_id": strategy_id,
                    "model_version": "1.0.0",
                    "snapshot_hash": None,
                    "rationale": f"signal-{i}",
                },
            )
        await session.commit()
    await engine.dispose()


def test_get_strategy_signals_empty(client: TestClient, test_strategy: str) -> None:
    """Test GET /state/strategies/{strategy_id}/signals returns 200 and empty list."""
    response = client.get(f"/api/v1/state/strategies/{test_strategy}/signals")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["items"] == []
    assert data.get("next_cursor") is None

    from polytrader.api.models import StrategySignalsResponse

    StrategySignalsResponse(**data)


def test_get_strategy_signals_success(
    client: TestClient,
    test_strategy: str,
    postgres_test_url: str,
    postgres_db: AsyncGenerator[None, None],
) -> None:
    """Test GET /state/strategies/{strategy_id}/signals returns 200 and signal DTOs."""
    asyncio.run(_insert_signal_events(postgres_test_url, test_strategy, 2))

    response = client.get(f"/api/v1/state/strategies/{test_strategy}/signals")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 2
    assert data.get("next_cursor") is None

    for item in data["items"]:
        assert item["model_id"] == test_strategy
        assert "event_id" in item
        assert "ts_wall" in item
        assert item["market_slug"] == "btc-updown"
        assert item["p_up"] == 0.6
        assert item["p_down"] == 0.4

    from polytrader.api.models import StrategySignalsResponse

    StrategySignalsResponse(**data)


def test_get_strategy_signals_pagination(
    client: TestClient,
    test_strategy: str,
    postgres_test_url: str,
    postgres_db: AsyncGenerator[None, None],
) -> None:
    """Test GET signals with limit returns next_cursor when more rows exist."""
    asyncio.run(_insert_signal_events(postgres_test_url, test_strategy, 3))

    response = client.get(
        f"/api/v1/state/strategies/{test_strategy}/signals",
        params={"limit": 2},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["next_cursor"] is not None

    next_response = client.get(
        f"/api/v1/state/strategies/{test_strategy}/signals",
        params={"limit": 10, "cursor": data["next_cursor"]},
    )
    assert next_response.status_code == 200
    next_data = next_response.json()
    assert len(next_data["items"]) == 1
    assert next_data.get("next_cursor") is None


async def _insert_order_events(
    postgres_test_url: str,
    strategy_id: str,
    count: int,
    execution_mode: str = "paper",
) -> None:
    """Insert OrderCreatedEvent records for strategy_id into events table."""
    import uuid
    from datetime import UTC, datetime

    from polytrader.db.repository import EventRepository

    if postgres_test_url.startswith("postgresql://"):
        sqlalchemy_url = postgres_test_url.replace("postgresql://", "postgresql+psycopg://", 1)
    else:
        sqlalchemy_url = postgres_test_url

    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        repo = EventRepository(session)
        for i in range(count):
            order_id = str(uuid.uuid4())
            client_order_id = f"client-{strategy_id}-{i}"
            await repo.create_event(
                event_id=uuid.uuid4(),
                ts_wall=datetime.now(UTC),
                ts_mono=2000.0 + i,
                correlation_id=f"corr-order-{i}",
                run_id="test-run",
                schema_version="1.0",
                source="oms",
                event_type="OrderCreatedEvent",
                event_data={
                    "order_id": order_id,
                    "client_order_id": client_order_id,
                    "execution_mode": execution_mode,
                    "intent": {
                        "market_slug": "btc-updown",
                        "outcome": "UP",
                        "side": "BUY",
                        "limit_price": 0.5,
                        "size": 10.0,
                        "reason": f"order-{i}",
                        "strategy_id": strategy_id,
                        "ttl_s": 2.0,
                    },
                },
            )
        await session.commit()
    await engine.dispose()


def test_get_strategy_orders_empty(client: TestClient, test_strategy: str) -> None:
    """Test GET /state/strategies/{strategy_id}/orders returns 200 and empty list."""
    response = client.get(f"/api/v1/state/strategies/{test_strategy}/orders")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["items"] == []
    assert data.get("next_cursor") is None

    from polytrader.api.models import StrategyOrdersResponse

    StrategyOrdersResponse(**data)


def test_get_strategy_orders_success(
    client: TestClient,
    test_strategy: str,
    postgres_test_url: str,
    postgres_db: AsyncGenerator[None, None],
) -> None:
    """Test GET orders returns 200 and order DTOs with execution_mode."""
    asyncio.run(_insert_order_events(postgres_test_url, test_strategy, 2, "paper"))

    response = client.get(f"/api/v1/state/strategies/{test_strategy}/orders")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 2
    assert data.get("next_cursor") is None

    for item in data["items"]:
        assert "order_id" in item
        assert "client_order_id" in item
        assert "ts_wall" in item
        assert item["market_slug"] == "btc-updown"
        assert item["side"] == "BUY"
        assert item["size"] == 10.0
        assert item["limit_price"] == 0.5
        assert item["status"] == "PENDING_SUBMIT"
        assert item["execution_mode"] == "paper"

    from polytrader.api.models import StrategyOrdersResponse

    StrategyOrdersResponse(**data)


def test_get_strategy_orders_execution_mode_live(
    client: TestClient,
    test_strategy: str,
    postgres_test_url: str,
    postgres_db: AsyncGenerator[None, None],
) -> None:
    """Test GET orders returns execution_mode live when stored in event_data."""
    asyncio.run(_insert_order_events(postgres_test_url, test_strategy, 1, "live"))

    response = client.get(f"/api/v1/state/strategies/{test_strategy}/orders")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["execution_mode"] == "live"


def test_get_strategy_orders_pagination(
    client: TestClient,
    test_strategy: str,
    postgres_test_url: str,
    postgres_db: AsyncGenerator[None, None],
) -> None:
    """Test GET orders with limit returns next_cursor when more rows exist."""
    asyncio.run(_insert_order_events(postgres_test_url, test_strategy, 3))

    response = client.get(
        f"/api/v1/state/strategies/{test_strategy}/orders",
        params={"limit": 2},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["next_cursor"] is not None

    next_response = client.get(
        f"/api/v1/state/strategies/{test_strategy}/orders",
        params={"limit": 10, "cursor": data["next_cursor"]},
    )
    assert next_response.status_code == 200
    next_data = next_response.json()
    assert len(next_data["items"]) == 1
    assert next_data.get("next_cursor") is None


async def _insert_closed_trade_events(
    postgres_test_url: str,
    strategy_id: str,
    count: int,
    execution_mode: str = "paper",
) -> None:
    """Insert StrategyClosedTradeEvent records for performance API tests."""
    import uuid
    from datetime import UTC, datetime

    from polytrader.db.repository import EventRepository

    if postgres_test_url.startswith("postgresql://"):
        sqlalchemy_url = postgres_test_url.replace("postgresql://", "postgresql+psycopg://", 1)
    else:
        sqlalchemy_url = postgres_test_url

    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        repo = EventRepository(session)
        for i in range(count):
            ts_mono = 5000.0 + i
            event_data = {
                "strategy_id": strategy_id,
                "market_slug": "btc-updown-15m",
                "outcome": "UP",
                "entry_price": 0.45,
                "exit_price": 0.55,
                "size": 100.0,
                "pnl": 10.0 + i,
                "pnl_pct": 22.2,
                "entry_time": ts_mono - 100.0,
                "exit_time": ts_mono,
                "result": "WIN" if i % 2 == 0 else "LOSS",
                "execution_mode": execution_mode,
                "order_id": str(uuid.uuid4()),
                "fill_id": str(uuid.uuid4()),
            }
            await repo.create_event(
                event_id=uuid.uuid4(),
                ts_wall=datetime.now(UTC),
                ts_mono=ts_mono,
                correlation_id=f"corr-perf-{i}",
                run_id="test-run",
                schema_version="1.0",
                source="posttrade",
                event_type="StrategyClosedTradeEvent",
                event_data=event_data,
            )
        await session.commit()
    await engine.dispose()


def test_get_strategy_performance_empty(client: TestClient, test_strategy: str) -> None:
    """Test GET /state/strategies/{strategy_id}/performance returns 200 and empty items."""
    response = client.get(f"/api/v1/state/strategies/{test_strategy}/performance")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert data["summary"]["total_trades"] == 0
    assert data["summary"]["total_realized_pnl"] == 0.0
    assert data["summary"]["win_rate_pct"] is None
    assert "items" in data
    assert data["items"] == []
    assert data.get("next_cursor") is None

    from polytrader.api.models import PerformanceResponse

    PerformanceResponse(**data)


def test_get_strategy_performance_success(
    client: TestClient,
    test_strategy: str,
    postgres_test_url: str,
    postgres_db: AsyncGenerator[None, None],
) -> None:
    """Test GET performance returns 200, summary and closed-trade DTOs."""
    asyncio.run(_insert_closed_trade_events(postgres_test_url, test_strategy, 2))

    response = client.get(f"/api/v1/state/strategies/{test_strategy}/performance")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert data["summary"]["total_trades"] == 2
    assert data["summary"]["total_realized_pnl"] == 21.0  # 10 + 11
    assert data["summary"]["win_rate_pct"] == 50.0  # 1 WIN, 1 LOSS
    assert "items" in data
    assert len(data["items"]) == 2
    for item in data["items"]:
        assert item["market_slug"] == "btc-updown-15m"
        assert item["outcome"] == "UP"
        assert item["entry_price"] == 0.45
        assert item["exit_price"] == 0.55
        assert item["size"] == 100.0
        assert "pnl" in item
        assert item["result"] in ("WIN", "LOSS")
        assert item["execution_mode"] == "paper"
        assert "exit_ts_wall" in item
        assert item["duration_seconds"] >= 0
    assert data.get("next_cursor") is None

    from polytrader.api.models import PerformanceResponse

    PerformanceResponse(**data)


def test_get_strategy_performance_execution_mode_filter(
    client: TestClient,
    test_strategy: str,
    postgres_test_url: str,
    postgres_db: AsyncGenerator[None, None],
) -> None:
    """Test GET performance with execution_mode=paper returns only paper trades."""
    asyncio.run(_insert_closed_trade_events(postgres_test_url, test_strategy, 1, "paper"))
    asyncio.run(_insert_closed_trade_events(postgres_test_url, test_strategy, 1, "live"))

    response = client.get(
        f"/api/v1/state/strategies/{test_strategy}/performance",
        params={"execution_mode": "paper"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_trades"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["execution_mode"] == "paper"


def test_get_strategy_performance_pagination(
    client: TestClient,
    test_strategy: str,
    postgres_test_url: str,
    postgres_db: AsyncGenerator[None, None],
) -> None:
    """Test GET performance with limit returns next_cursor when more rows exist."""
    asyncio.run(_insert_closed_trade_events(postgres_test_url, test_strategy, 3))

    response = client.get(
        f"/api/v1/state/strategies/{test_strategy}/performance",
        params={"limit": 2},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["summary"]["total_trades"] == 2
    assert data["next_cursor"] is not None

    next_response = client.get(
        f"/api/v1/state/strategies/{test_strategy}/performance",
        params={"limit": 10, "cursor": data["next_cursor"]},
    )
    assert next_response.status_code == 200
    next_data = next_response.json()
    assert len(next_data["items"]) == 1
    assert next_data["summary"]["total_trades"] == 1
    assert next_data.get("next_cursor") is None
