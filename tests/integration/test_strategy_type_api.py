"""Integration tests for strategy template discovery API endpoints.

Per Commit 15: Tests for template discovery endpoints:
- GET /api/v1/strategies/templates (list all templates)
- GET /api/v1/strategies/templates/{type_id} (get template details)
- GET /api/v1/strategies/templates/{type_id}/versions/{version} (get version)

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
def test_list_strategy_templates(client: TestClient) -> None:
    """Test listing all strategy templates.

    Per Commit 15: GET /api/v1/strategies/templates should return
    all registered strategy templates with their versions.
    """
    response = client.get("/api/v1/state/strategies/templates")

    assert response.status_code == 200
    data = response.json()

    # Should have types field
    assert "types" in data
    assert isinstance(data["types"], list)

    # Should have at least simple_threshold template
    types = data["types"]
    assert len(types) > 0

    # Find simple_threshold template
    simple_threshold = next((t for t in types if t["type_id"] == "simple_threshold"), None)
    assert simple_threshold is not None

    # Verify template structure
    assert simple_threshold["type_id"] == "simple_threshold"
    assert simple_threshold["name"] == "Simple Threshold Strategy"
    assert "BUY signals" in simple_threshold["description"]
    assert "available_versions" in simple_threshold
    assert isinstance(simple_threshold["available_versions"], list)
    assert "1.0.0" in simple_threshold["available_versions"]

    # Verify parameter schema
    assert "parameter_schema" in simple_threshold
    schema = simple_threshold["parameter_schema"]
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "buy_threshold" in schema["properties"]
    assert "min_history" in schema["properties"]

    # Verify buy_threshold parameter
    buy_threshold_param = schema["properties"]["buy_threshold"]
    assert buy_threshold_param["type"] == "number"
    assert buy_threshold_param["default"] == 0.30
    assert buy_threshold_param["minimum"] == 0.0
    assert buy_threshold_param["maximum"] == 1.0
    assert "Price threshold" in buy_threshold_param["description"]

    # Verify min_history parameter
    min_history_param = schema["properties"]["min_history"]
    assert min_history_param["type"] == "integer"
    assert min_history_param["default"] == 30
    assert min_history_param["minimum"] == 0
    assert "Minimum history ticks" in min_history_param["description"]


@pytest.mark.integration
def test_get_strategy_template(client: TestClient) -> None:
    """Test getting a specific strategy template.

    Per Commit 15: GET /api/v1/strategies/templates/{type_id} should return
    template details including all available versions.
    """
    response = client.get("/api/v1/state/strategies/templates/simple_threshold")

    assert response.status_code == 200
    data = response.json()

    # Verify template structure
    assert data["type_id"] == "simple_threshold"
    assert data["name"] == "Simple Threshold Strategy"
    assert "BUY signals" in data["description"]
    assert "available_versions" in data
    assert isinstance(data["available_versions"], list)
    assert "1.0.0" in data["available_versions"]

    # Verify parameter schema
    assert "parameter_schema" in data
    schema = data["parameter_schema"]
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "buy_threshold" in schema["properties"]
    assert "min_history" in schema["properties"]


@pytest.mark.integration
def test_get_strategy_template_not_found(client: TestClient) -> None:
    """Test getting a non-existent strategy template.

    Per Commit 15: GET /api/v1/strategies/templates/{type_id} should return
    404 if template type not found.
    """
    response = client.get("/api/v1/state/strategies/templates/nonexistent_template")

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "error" in data["detail"]
    assert "Template not found" in data["detail"]["error"]
    assert "nonexistent_template" in data["detail"]["detail"]


@pytest.mark.integration
def test_get_strategy_template_version(client: TestClient) -> None:
    """Test getting a specific strategy template version.

    Per Commit 15: GET /api/v1/strategies/templates/{type_id}/versions/{version}
    should return template details for a specific version.
    """
    response = client.get("/api/v1/state/strategies/templates/simple_threshold/versions/1.0.0")

    assert response.status_code == 200
    data = response.json()

    # Verify template structure
    assert data["type_id"] == "simple_threshold"
    assert data["name"] == "Simple Threshold Strategy"
    assert "BUY signals" in data["description"]
    assert "available_versions" in data
    assert data["available_versions"] == ["1.0.0"]  # Single version

    # Verify parameter schema
    assert "parameter_schema" in data
    schema = data["parameter_schema"]
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "buy_threshold" in schema["properties"]
    assert "min_history" in schema["properties"]


@pytest.mark.integration
def test_get_strategy_template_version_not_found_type(client: TestClient) -> None:
    """Test getting a version for a non-existent template type.

    Per Commit 15: GET /api/v1/strategies/templates/{type_id}/versions/{version}
    should return 404 if template type not found.
    """
    response = client.get("/api/v1/state/strategies/templates/nonexistent_template/versions/1.0.0")

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "error" in data["detail"]
    assert "Template version not found" in data["detail"]["error"]


@pytest.mark.integration
def test_get_strategy_template_version_not_found_version(client: TestClient) -> None:
    """Test getting a non-existent version for an existing template.

    Per Commit 15: GET /api/v1/strategies/templates/{type_id}/versions/{version}
    should return 404 if version not found.
    """
    response = client.get("/api/v1/state/strategies/templates/simple_threshold/versions/999.0.0")

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "error" in data["detail"]
    assert "Template version not found" in data["detail"]["error"]
