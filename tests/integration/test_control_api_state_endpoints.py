"""Integration tests for control API state endpoints.

Tests GET endpoints for reading system state:
- GET /state/health
- GET /state/execution
- GET /state/live-strategies
- GET /state/strategies
- GET /state/strategies/{strategy_id}
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
