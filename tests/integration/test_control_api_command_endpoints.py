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

import pytest
from fastapi.testclient import TestClient

from polytrader.api.app import create_app


@pytest.fixture
def client(postgres_db: None) -> TestClient:
    """Create FastAPI test client with real database."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def test_strategy(client: TestClient) -> str:
    """Create a test strategy via API and return strategy_id."""
    import uuid

    strategy_id = f"test-strategy-{uuid.uuid4().hex[:8]}"
    request = {
        "strategy_id": strategy_id,
        "name": "Test Strategy",
        "description": "Test strategy for API tests",
        "config": {"param": "value"},
        "enabled": True,
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
        "config": {"param": "value"},
        "enabled": True,
    }

    response = client.post("/api/v1/commands/strategies", json=request)
    assert response.status_code == 201
    data = response.json()
    assert data["strategy_id"] == strategy_id
    assert data["name"] == "New Strategy"
    assert data["enabled"] is True

    # Verify Pydantic model structure
    from polytrader.api.models import StrategyResponse

    StrategyResponse(**data)  # Should not raise


def test_create_strategy_duplicate(client: TestClient, test_strategy: str) -> None:
    """Test POST /commands/strategies returns 409 for duplicate strategy_id."""
    request = {
        "strategy_id": test_strategy,
        "name": "Duplicate Strategy",
        "config": {},
        "enabled": True,
    }

    response = client.post("/api/v1/commands/strategies", json=request)
    assert response.status_code == 409
    data = response.json()
    assert "error" in data or "detail" in data


def test_update_strategy(client: TestClient, test_strategy: str) -> None:
    """Test PATCH /commands/strategies/{strategy_id} updates strategy."""
    request = {
        "name": "Updated Strategy Name",
        "enabled": False,
    }

    response = client.patch(f"/api/v1/commands/strategies/{test_strategy}", json=request)
    assert response.status_code == 200
    data = response.json()
    assert data["strategy_id"] == test_strategy
    assert data["name"] == "Updated Strategy Name"
    assert data["enabled"] is False


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
