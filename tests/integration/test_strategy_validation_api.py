"""Integration tests for strategy configuration validation API endpoint.

Per Commit 16: Tests for POST /api/v1/state/strategies/validate endpoint
that validates configurations before creating strategy instances.

Per testing.mdc: Integration tests verify end-to-end API behavior.
"""

import pytest
from fastapi.testclient import TestClient

from polytrader.api.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Create FastAPI test client."""
    app = create_app()
    return TestClient(app)


@pytest.mark.integration
def test_validate_strategy_config_valid(client: TestClient) -> None:
    """Test validation with valid configuration.

    Per Commit 16: Valid config should return valid=True with no errors.
    """
    request = {
        "template_type_id": "simple_threshold",
        "version_selector": {"exact": "1.0.0"},
        "config": {"buy_threshold": 0.3, "min_history": 30},
    }

    response = client.post("/api/v1/state/strategies/validate", json=request)

    assert response.status_code == 200
    data = response.json()

    assert data["valid"] is True
    assert data["errors"] == []
    assert data["warnings"] == []
    assert data["template_type_id"] == "simple_threshold"
    assert data["template_version"] == "1.0.0"


@pytest.mark.integration
def test_validate_strategy_config_valid_with_defaults(client: TestClient) -> None:
    """Test validation with empty config (uses defaults).

    Per Commit 16: Empty config should be valid if all parameters have defaults.
    """
    request = {
        "template_type_id": "simple_threshold",
        "version_selector": {"exact": "1.0.0"},
        "config": {},
    }

    response = client.post("/api/v1/state/strategies/validate", json=request)

    assert response.status_code == 200
    data = response.json()

    assert data["valid"] is True
    assert data["errors"] == []
    assert data["template_type_id"] == "simple_threshold"
    assert data["template_version"] == "1.0.0"


@pytest.mark.integration
def test_validate_strategy_config_invalid_type(client: TestClient) -> None:
    """Test validation with invalid parameter type.

    Per Commit 16: Invalid type should return valid=False with error messages.
    """
    request = {
        "template_type_id": "simple_threshold",
        "version_selector": {"exact": "1.0.0"},
        "config": {"buy_threshold": "invalid", "min_history": 30},
    }

    response = client.post("/api/v1/state/strategies/validate", json=request)

    assert response.status_code == 200
    data = response.json()

    assert data["valid"] is False
    assert len(data["errors"]) > 0
    assert any("buy_threshold" in error.lower() for error in data["errors"])
    # Error message should indicate type mismatch
    # (could be "type", "expected", "got", "must be", etc.)
    assert any(
        keyword in error.lower()
        for error in data["errors"]
        for keyword in ["type", "expected", "got", "must be", "class"]
    )


@pytest.mark.integration
def test_validate_strategy_config_invalid_bounds(client: TestClient) -> None:
    """Test validation with out-of-bounds values.

    Per Commit 16: Out-of-bounds values should return valid=False with error messages.
    """
    request = {
        "template_type_id": "simple_threshold",
        "version_selector": {"exact": "1.0.0"},
        "config": {"buy_threshold": 1.5, "min_history": 30},  # buy_threshold > 1.0
    }

    response = client.post("/api/v1/state/strategies/validate", json=request)

    assert response.status_code == 200
    data = response.json()

    assert data["valid"] is False
    assert len(data["errors"]) > 0
    assert any("buy_threshold" in error.lower() for error in data["errors"])
    assert any("maximum" in error.lower() or "greater" in error.lower() for error in data["errors"])


@pytest.mark.integration
def test_validate_strategy_config_unknown_parameter(client: TestClient) -> None:
    """Test validation with unknown parameters.

    Per Commit 16: Unknown parameters should return valid=False with error messages.
    """
    request = {
        "template_type_id": "simple_threshold",
        "version_selector": {"exact": "1.0.0"},
        "config": {"buy_threshold": 0.3, "unknown_param": "value"},
    }

    response = client.post("/api/v1/state/strategies/validate", json=request)

    assert response.status_code == 200
    data = response.json()

    assert data["valid"] is False
    assert len(data["errors"]) > 0
    assert any("unknown" in error.lower() for error in data["errors"])
    assert any("unknown_param" in error.lower() for error in data["errors"])


@pytest.mark.integration
def test_validate_strategy_config_template_not_found(client: TestClient) -> None:
    """Test validation with non-existent template type.

    Per Commit 16: Non-existent template should return 400 error.
    """
    request = {
        "template_type_id": "nonexistent_template",
        "version_selector": {"exact": "1.0.0"},
        "config": {"buy_threshold": 0.3},
    }

    response = client.post("/api/v1/state/strategies/validate", json=request)

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "error" in data["detail"]
    assert "Template not found" in data["detail"]["error"]


@pytest.mark.integration
def test_validate_strategy_config_version_not_found(client: TestClient) -> None:
    """Test validation with non-existent version.

    Per Commit 16: Non-existent version should return 400 error.
    """
    request = {
        "template_type_id": "simple_threshold",
        "version_selector": {"exact": "999.0.0"},
        "config": {"buy_threshold": 0.3},
    }

    response = client.post("/api/v1/state/strategies/validate", json=request)

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "error" in data["detail"]
    assert "Version resolution failed" in data["detail"]["error"]


@pytest.mark.integration
def test_validate_strategy_config_channel_selector(client: TestClient) -> None:
    """Test validation with channel version selector.

    Per Commit 16: Channel selector should resolve to exact version and validate.
    """
    request = {
        "template_type_id": "simple_threshold",
        "version_selector": {"channel": "stable"},
        "config": {"buy_threshold": 0.3, "min_history": 30},
    }

    response = client.post("/api/v1/state/strategies/validate", json=request)

    assert response.status_code == 200
    data = response.json()

    assert data["valid"] is True
    assert data["errors"] == []
    assert data["template_type_id"] == "simple_threshold"
    assert data["template_version"] == "1.0.0"  # Resolved from channel


@pytest.mark.integration
def test_validate_strategy_config_multiple_errors(client: TestClient) -> None:
    """Test validation with multiple errors.

    Per Commit 16: Multiple validation errors should all be returned.
    """
    request = {
        "template_type_id": "simple_threshold",
        "version_selector": {"exact": "1.0.0"},
        "config": {
            "buy_threshold": "invalid",  # Wrong type
            "min_history": -10,  # Below minimum
            "unknown_param": "value",  # Unknown parameter
        },
    }

    response = client.post("/api/v1/state/strategies/validate", json=request)

    assert response.status_code == 200
    data = response.json()

    assert data["valid"] is False
    assert len(data["errors"]) >= 3  # At least 3 errors
    # Verify all error types are present
    assert any("buy_threshold" in error.lower() for error in data["errors"])
    assert any("min_history" in error.lower() for error in data["errors"])
    assert any("unknown" in error.lower() for error in data["errors"])
