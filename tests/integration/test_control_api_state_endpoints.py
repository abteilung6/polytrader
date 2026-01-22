"""Integration tests for control API state endpoints.

Tests GET endpoints for reading system state:
- GET /state/health
- GET /state/execution
- GET /state/live-strategies
- GET /state/strategies
- GET /state/commands/{command_id}
"""

import pytest
from fastapi.testclient import TestClient

from polytrader.api.app import create_app


@pytest.fixture
def client(postgres_db: None) -> TestClient:
    """Create FastAPI test client with real database."""
    app = create_app()
    return TestClient(app)


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
