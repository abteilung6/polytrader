"""Integration tests for control API command endpoints.

Tests POST endpoints for creating commands:
- POST /commands/execution/enable
- POST /commands/execution/disable
- POST /commands/live-strategies/{strategy_id}/activate
- POST /commands/live-strategies/{strategy_id}/deactivate
- POST /commands/strategies (create)
- PATCH /commands/strategies/{strategy_id} (update)

Tests idempotency, version checks, and command envelope responses.
"""

from collections.abc import AsyncGenerator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.api.app import create_app
from polytrader.api.dependencies import get_db_session


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

    # Clean up strategies table at test start
    async def cleanup_strategies() -> None:
        """Clean up strategies table."""
        from sqlalchemy import text

        async with Session() as session:
            try:
                await session.execute(text("TRUNCATE TABLE strategy_instances CASCADE"))
                await session.commit()
            except Exception:
                await session.rollback()

    # Run cleanup synchronously using asyncio
    import asyncio

    asyncio.run(cleanup_strategies())

    app = create_app()

    # Override get_db_session to use test database session
    async def override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        """Override dependency to use test database session."""
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    yield TestClient(app)

    # Cleanup: remove dependency override and clean up strategies
    app.dependency_overrides.clear()
    asyncio.run(cleanup_strategies())


@pytest.fixture
def test_strategy(client: TestClient) -> str:
    """Create a test strategy via API and return strategy_id."""
    import uuid

    strategy_id = f"test-strategy-{uuid.uuid4().hex[:8]}"
    request = {
        "strategy_id": strategy_id,
        "name": "Test Strategy",
        "description": "Test strategy for API tests",
        "config": {"buy_threshold": 0.3, "min_history": 30},
        "template_type_id": "simple_threshold",
        "version_selector": {"exact": "1.0.0"},
        "desired_state": "RUNNING",
    }
    response = client.post("/api/v1/commands/strategies", json=request)
    assert response.status_code == 201
    return strategy_id


def test_enable_execution_creates_command(client: TestClient) -> None:
    """Test POST /commands/execution/enable creates command, returns envelope."""
    request = {
        "reason": "Enable for testing",
        "issued_by": "operator",
        "client_request_id": "req-enable-1",
    }

    response = client.post("/api/v1/commands/execution/enable", json=request)
    assert response.status_code == 200
    data = response.json()
    assert "command_id" in data
    assert "status" in data
    assert data["status"] == "pending"
    assert "submitted_at" in data
    assert "links" in data
    assert "status" in data["links"]

    # Verify Pydantic model structure
    from polytrader.api.models import CommandEnvelopeResponse

    CommandEnvelopeResponse(**data)  # Should not raise


def test_enable_execution_idempotency(client: TestClient) -> None:
    """Test idempotency: duplicate client_request_id returns existing command_id."""
    request = {
        "reason": "Enable for testing",
        "issued_by": "operator",
        "client_request_id": "req-enable-idempotent",
    }

    # First request
    response1 = client.post("/api/v1/commands/execution/enable", json=request)
    assert response1.status_code == 200
    command_id_1 = response1.json()["command_id"]

    # Duplicate request (same client_request_id)
    response2 = client.post("/api/v1/commands/execution/enable", json=request)
    assert response2.status_code == 200
    command_id_2 = response2.json()["command_id"]

    # Should return same command_id
    assert command_id_1 == command_id_2


def test_enable_execution_version_conflict(client: TestClient) -> None:
    """Test version conflict returns 409."""
    # Get current version
    state_response = client.get("/api/v1/state/execution")
    current_version = state_response.json()["version"]

    # Request with wrong version
    request = {
        "expected_version": current_version + 10,  # Wrong version
        "reason": "Enable with wrong version",
        "issued_by": "operator",
        "client_request_id": "req-version-conflict",
    }

    response = client.post("/api/v1/commands/execution/enable", json=request)
    assert response.status_code == 409
    data = response.json()
    assert "expected_version" in data or "detail" in data


def test_enable_execution_version_match(client: TestClient) -> None:
    """Test version check: expected_version match -> 200 OK, command created."""
    # Get current version
    state_response = client.get("/api/v1/state/execution")
    current_version = state_response.json()["version"]

    # Request with correct version
    request = {
        "expected_version": current_version,
        "reason": "Enable with correct version",
        "issued_by": "operator",
        "client_request_id": "req-version-match",
    }

    response = client.post("/api/v1/commands/execution/enable", json=request)
    assert response.status_code == 200
    data = response.json()
    assert "command_id" in data
    assert data["status"] == "pending"


def test_disable_execution_creates_command(client: TestClient) -> None:
    """Test POST /commands/execution/disable creates command."""
    request = {
        "reason": "Disable for testing",
        "issued_by": "operator",
        "client_request_id": "req-disable-1",
    }

    response = client.post("/api/v1/commands/execution/disable", json=request)
    assert response.status_code == 200
    data = response.json()
    assert "command_id" in data
    assert data["status"] == "pending"


def test_activate_strategy_creates_command(client: TestClient, test_strategy: str) -> None:
    """Test POST /commands/live-strategies/{strategy_id}/activate creates command."""
    request = {
        "reason": "Activate for testing",
        "issued_by": "operator",
        "client_request_id": "req-activate-1",
    }

    response = client.post(
        f"/api/v1/commands/live-strategies/{test_strategy}/activate", json=request
    )
    assert response.status_code == 200
    data = response.json()
    assert "command_id" in data
    assert data["status"] == "pending"


def test_deactivate_strategy_creates_command(client: TestClient, test_strategy: str) -> None:
    """Test POST /commands/live-strategies/{strategy_id}/deactivate creates command."""
    request = {
        "reason": "Deactivate for testing",
        "issued_by": "operator",
        "client_request_id": "req-deactivate-1",
    }

    response = client.post(
        f"/api/v1/commands/live-strategies/{test_strategy}/deactivate", json=request
    )
    assert response.status_code == 200
    data = response.json()
    assert "command_id" in data
    assert data["status"] == "pending"


def test_create_strategy(client: TestClient) -> None:
    """Test POST /commands/strategies creates strategy."""
    import uuid

    strategy_id = f"new-strategy-{uuid.uuid4().hex[:8]}"
    request = {
        "strategy_id": strategy_id,
        "name": "New Strategy",
        "description": "A new strategy",
        "config": {"buy_threshold": 0.3, "min_history": 30},
        "template_type_id": "simple_threshold",
        "version_selector": {"exact": "1.0.0"},
        "desired_state": "RUNNING",
    }

    response = client.post("/api/v1/commands/strategies", json=request)
    assert response.status_code == 201
    data = response.json()
    assert data["strategy_id"] == strategy_id
    assert data["name"] == "New Strategy"
    assert data["enabled"] is True  # Computed field derived from desired_state == RUNNING

    # Verify Pydantic model structure
    from polytrader.api.models import StrategyResponse

    StrategyResponse(**data)  # Should not raise


def test_create_strategy_duplicate(client: TestClient, test_strategy: str) -> None:
    """Test POST /commands/strategies returns 409 for duplicate strategy_id."""
    request = {
        "strategy_id": test_strategy,
        "name": "Duplicate Strategy",
        "config": {"buy_threshold": 0.3, "min_history": 30},
        "template_type_id": "simple_threshold",
        "version_selector": {"exact": "1.0.0"},
        "desired_state": "RUNNING",
    }

    response = client.post("/api/v1/commands/strategies", json=request)
    assert response.status_code == 409
    data = response.json()
    assert "error" in data or "detail" in data


def test_update_strategy(client: TestClient, test_strategy: str) -> None:
    """Test PATCH /commands/strategies/{strategy_id} updates strategy."""
    request = {
        "name": "Updated Strategy Name",
        "desired_state": "STOPPED",
    }

    response = client.patch(f"/api/v1/commands/strategies/{test_strategy}", json=request)
    assert response.status_code == 200
    data = response.json()
    assert data["strategy_id"] == test_strategy
    assert data["name"] == "Updated Strategy Name"
    assert data["enabled"] is False  # Computed field derived from desired_state == STOPPED


def test_update_strategy_not_found(client: TestClient) -> None:
    """Test PATCH /commands/strategies/{strategy_id} returns 404 for non-existent."""
    request = {
        "name": "Updated Name",
    }

    response = client.patch("/api/v1/commands/strategies/non-existent-strategy", json=request)
    assert response.status_code == 404
    data = response.json()
    assert "error" in data or "detail" in data


def test_command_envelope_structure(client: TestClient) -> None:
    """Test command envelope response structure (command_id, status, links)."""
    request = {
        "reason": "Test envelope structure",
        "issued_by": "operator",
        "client_request_id": "req-envelope-test",
    }

    response = client.post("/api/v1/commands/execution/enable", json=request)
    assert response.status_code == 200
    data = response.json()

    # Verify envelope structure
    assert "command_id" in data
    assert "status" in data
    assert "submitted_at" in data
    assert "links" in data
    assert isinstance(data["links"], dict)
    assert "status" in data["links"]

    # Verify status link points to correct endpoint
    status_link = data["links"]["status"]
    assert status_link.startswith("/api/v1/state/commands/")
    assert data["command_id"] in status_link
