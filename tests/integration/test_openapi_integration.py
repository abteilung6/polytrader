"""Integration tests for OpenAPI schema integration in API responses.

Per Commit 21: Tests verify that OpenAPI schemas are properly included
in strategy type API responses and are accurate and complete.

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
def test_openapi_schema_in_template_list_response(client: TestClient) -> None:
    """Test that OpenAPI schemas are included in template list response.

    Per Commit 21: GET /api/v1/state/strategies/templates should include
    parameter_schema with complete OpenAPI JSON Schema.
    """
    response = client.get("/api/v1/state/strategies/templates")

    assert response.status_code == 200
    data = response.json()

    # Find simple_threshold template
    simple_threshold = next((t for t in data["types"] if t["type_id"] == "simple_threshold"), None)
    assert simple_threshold is not None

    # Verify parameter_schema is present and is valid OpenAPI schema
    assert "parameter_schema" in simple_threshold
    schema = simple_threshold["parameter_schema"]

    # Verify OpenAPI schema structure
    assert schema["type"] == "object"
    assert "properties" in schema
    assert isinstance(schema["properties"], dict)

    # Verify buy_threshold parameter schema
    assert "buy_threshold" in schema["properties"]
    buy_threshold = schema["properties"]["buy_threshold"]
    assert buy_threshold["type"] == "number"
    assert buy_threshold["default"] == 0.30
    assert buy_threshold["minimum"] == 0.0
    assert buy_threshold["maximum"] == 1.0
    assert "description" in buy_threshold
    assert "Price threshold" in buy_threshold["description"]

    # Verify min_history parameter schema
    assert "min_history" in schema["properties"]
    min_history = schema["properties"]["min_history"]
    assert min_history["type"] == "integer"
    assert min_history["default"] == 30
    assert min_history["minimum"] == 0
    assert "description" in min_history


@pytest.mark.integration
def test_openapi_schema_in_template_detail_response(client: TestClient) -> None:
    """Test that OpenAPI schemas are included in template detail response.

    Per Commit 21: GET /api/v1/state/strategies/templates/{type_id} should include
    parameter_schema with complete OpenAPI JSON Schema.
    """
    response = client.get("/api/v1/state/strategies/templates/simple_threshold")

    assert response.status_code == 200
    data = response.json()

    # Verify parameter_schema is present
    assert "parameter_schema" in data
    schema = data["parameter_schema"]

    # Verify OpenAPI schema structure
    assert schema["type"] == "object"
    assert "properties" in schema
    assert len(schema["properties"]) == 2  # buy_threshold and min_history

    # Verify all properties have required fields
    for param_name, param_schema in schema["properties"].items():
        assert "type" in param_schema
        assert "description" in param_schema
        # Optional parameters should have defaults
        if param_name in ["buy_threshold", "min_history"]:
            assert "default" in param_schema


@pytest.mark.integration
def test_openapi_schema_in_template_version_response(client: TestClient) -> None:
    """Test that OpenAPI schemas are included in template version response.

    Per Commit 21: GET /api/v1/state/strategies/templates/{type_id}/versions/{version}
    should include parameter_schema with complete OpenAPI JSON Schema.
    """
    response = client.get("/api/v1/state/strategies/templates/simple_threshold/versions/1.0.0")

    assert response.status_code == 200
    data = response.json()

    # Verify parameter_schema is present
    assert "parameter_schema" in data
    schema = data["parameter_schema"]

    # Verify OpenAPI schema structure
    assert schema["type"] == "object"
    assert "properties" in schema

    # Verify schema accuracy - all properties should match expected structure
    assert "buy_threshold" in schema["properties"]
    assert "min_history" in schema["properties"]


@pytest.mark.integration
def test_openapi_schema_completeness(client: TestClient) -> None:
    """Test that OpenAPI schemas are complete with all required fields.

    Per Commit 21: Schemas must include type, properties, descriptions,
    defaults, and min/max constraints where applicable.
    """
    response = client.get("/api/v1/state/strategies/templates/simple_threshold")

    assert response.status_code == 200
    data = response.json()
    schema = data["parameter_schema"]

    # Verify top-level structure
    assert "type" in schema
    assert "properties" in schema

    # Verify each property has complete information
    for param_name, param_schema in schema["properties"].items():
        # Required fields
        assert "type" in param_schema, f"Missing 'type' for {param_name}"
        assert "description" in param_schema, f"Missing 'description' for {param_name}"

        # Optional fields (should be present for simple_threshold)
        if param_name == "buy_threshold":
            assert "default" in param_schema
            assert "minimum" in param_schema
            assert "maximum" in param_schema
        elif param_name == "min_history":
            assert "default" in param_schema
            assert "minimum" in param_schema


@pytest.mark.integration
def test_openapi_schema_accuracy(client: TestClient) -> None:
    """Test that OpenAPI schemas accurately reflect parameter definitions.

    Per Commit 21: Schema values must match actual parameter definitions.
    """
    response = client.get("/api/v1/state/strategies/templates/simple_threshold")

    assert response.status_code == 200
    data = response.json()
    schema = data["parameter_schema"]

    # Verify buy_threshold accuracy
    buy_threshold = schema["properties"]["buy_threshold"]
    assert buy_threshold["type"] == "number"  # float → number
    assert buy_threshold["default"] == 0.30
    assert buy_threshold["minimum"] == 0.0
    assert buy_threshold["maximum"] == 1.0

    # Verify min_history accuracy
    min_history = schema["properties"]["min_history"]
    assert min_history["type"] == "integer"  # int → integer
    assert min_history["default"] == 30
    assert min_history["minimum"] == 0

    # Verify no required parameters (both are optional)
    assert "required" not in schema or len(schema.get("required", [])) == 0


@pytest.mark.integration
def test_openapi_schema_consistency_across_endpoints(client: TestClient) -> None:
    """Test that OpenAPI schemas are consistent across different endpoints.

    Per Commit 21: Same template should return same schema regardless of endpoint.
    """
    # Get schema from list endpoint
    list_response = client.get("/api/v1/state/strategies/templates")
    list_data = list_response.json()
    list_template = next(
        (t for t in list_data["types"] if t["type_id"] == "simple_threshold"), None
    )
    assert list_template is not None, "simple_threshold template not found"
    list_schema = list_template["parameter_schema"]

    # Get schema from detail endpoint
    detail_response = client.get("/api/v1/state/strategies/templates/simple_threshold")
    detail_data = detail_response.json()
    detail_schema = detail_data["parameter_schema"]

    # Get schema from version endpoint
    version_response = client.get(
        "/api/v1/state/strategies/templates/simple_threshold/versions/1.0.0"
    )
    version_data = version_response.json()
    version_schema = version_data["parameter_schema"]

    # All schemas should be identical
    assert list_schema == detail_schema
    assert detail_schema == version_schema
