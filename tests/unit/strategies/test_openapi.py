"""Unit tests for OpenAPI schema generation.

Per Commit 20: Tests for parameter_schema_to_openapi() function.
Tests verify correct conversion of ParameterSchema to OpenAPI JSON Schema.

Per testing.mdc: Unit tests must be deterministic, fast, and isolated.
"""

from polytrader.strategies.openapi import parameter_schema_to_openapi
from polytrader.strategies.schema import ParameterDefinition, ParameterSchema


class TestParameterSchemaToOpenAPI:
    """Tests for parameter_schema_to_openapi() function."""

    def test_converts_schema_to_openapi_format(self) -> None:
        """Test that schema is converted to OpenAPI format."""
        schema = ParameterSchema(
            parameters={
                "buy_threshold": ParameterDefinition(
                    name="buy_threshold",
                    type=float,
                    required=False,
                    default=0.30,
                    description="Price threshold",
                    min_value=0.0,
                    max_value=1.0,
                )
            }
        )

        result = parameter_schema_to_openapi(schema)

        assert result["type"] == "object"
        assert "properties" in result
        assert "buy_threshold" in result["properties"]

    def test_type_mapping_int_to_integer(self) -> None:
        """Test that int type maps to 'integer' in OpenAPI."""
        schema = ParameterSchema(
            parameters={
                "min_history": ParameterDefinition(
                    name="min_history",
                    type=int,
                    required=False,
                    default=30,
                    description="Minimum history",
                )
            }
        )

        result = parameter_schema_to_openapi(schema)
        prop = result["properties"]["min_history"]

        assert prop["type"] == "integer"
        assert prop["default"] == 30

    def test_type_mapping_float_to_number(self) -> None:
        """Test that float type maps to 'number' in OpenAPI."""
        schema = ParameterSchema(
            parameters={
                "buy_threshold": ParameterDefinition(
                    name="buy_threshold",
                    type=float,
                    required=False,
                    default=0.30,
                    description="Price threshold",
                )
            }
        )

        result = parameter_schema_to_openapi(schema)
        prop = result["properties"]["buy_threshold"]

        assert prop["type"] == "number"
        assert prop["default"] == 0.30

    def test_type_mapping_str_to_string(self) -> None:
        """Test that str type maps to 'string' in OpenAPI."""
        schema = ParameterSchema(
            parameters={
                "market_pattern": ParameterDefinition(
                    name="market_pattern",
                    type=str,
                    required=True,
                    default=None,
                    description="Market pattern",
                )
            }
        )

        result = parameter_schema_to_openapi(schema)
        prop = result["properties"]["market_pattern"]

        assert prop["type"] == "string"

    def test_type_mapping_bool_to_boolean(self) -> None:
        """Test that bool type maps to 'boolean' in OpenAPI."""
        schema = ParameterSchema(
            parameters={
                "enabled": ParameterDefinition(
                    name="enabled",
                    type=bool,
                    required=False,
                    default=True,
                    description="Whether enabled",
                )
            }
        )

        result = parameter_schema_to_openapi(schema)
        prop = result["properties"]["enabled"]

        assert prop["type"] == "boolean"
        assert prop["default"] is True

    def test_unknown_type_maps_to_string(self) -> None:
        """Test that unknown types map to 'string' as fallback."""
        # Use a type that's not in our mapping
        # Note: We use a tuple type which isn't in our mapping, but we need to provide
        # a default value since required=False. We'll use an empty tuple as default.
        schema = ParameterSchema(
            parameters={
                "custom_param": ParameterDefinition(
                    name="custom_param",
                    type=tuple,  # Not in our mapping
                    required=False,
                    default=(),  # Provide default for required=False
                    description="Custom parameter",
                )
            }
        )

        result = parameter_schema_to_openapi(schema)
        prop = result["properties"]["custom_param"]

        assert prop["type"] == "string"  # Fallback

    def test_includes_default_values(self) -> None:
        """Test that default values are included in OpenAPI schema."""
        schema = ParameterSchema(
            parameters={
                "buy_threshold": ParameterDefinition(
                    name="buy_threshold",
                    type=float,
                    required=False,
                    default=0.30,
                    description="Price threshold",
                )
            }
        )

        result = parameter_schema_to_openapi(schema)
        prop = result["properties"]["buy_threshold"]

        assert prop["default"] == 0.30

    def test_includes_min_max_for_numeric_types(self) -> None:
        """Test that min/max values are included for numeric types."""
        schema = ParameterSchema(
            parameters={
                "buy_threshold": ParameterDefinition(
                    name="buy_threshold",
                    type=float,
                    required=False,
                    default=0.30,
                    description="Price threshold",
                    min_value=0.0,
                    max_value=1.0,
                ),
                "min_history": ParameterDefinition(
                    name="min_history",
                    type=int,
                    required=False,
                    default=30,
                    description="Minimum history",
                    min_value=0,
                ),
            }
        )

        result = parameter_schema_to_openapi(schema)

        # Check float with min and max
        buy_threshold_prop = result["properties"]["buy_threshold"]
        assert buy_threshold_prop["minimum"] == 0.0
        assert buy_threshold_prop["maximum"] == 1.0

        # Check int with min only
        min_history_prop = result["properties"]["min_history"]
        assert min_history_prop["minimum"] == 0
        assert "maximum" not in min_history_prop

    def test_includes_descriptions(self) -> None:
        """Test that parameter descriptions are included."""
        schema = ParameterSchema(
            parameters={
                "buy_threshold": ParameterDefinition(
                    name="buy_threshold",
                    type=float,
                    required=False,
                    default=0.30,
                    description="Price threshold for BUY signals",
                )
            }
        )

        result = parameter_schema_to_openapi(schema)
        prop = result["properties"]["buy_threshold"]

        assert prop["description"] == "Price threshold for BUY signals"

    def test_required_parameters_in_required_list(self) -> None:
        """Test that required parameters are listed in 'required' array."""
        schema = ParameterSchema(
            parameters={
                "required_param": ParameterDefinition(
                    name="required_param",
                    type=str,
                    required=True,
                    default=None,
                    description="Required parameter",
                ),
                "optional_param": ParameterDefinition(
                    name="optional_param",
                    type=int,
                    required=False,
                    default=10,
                    description="Optional parameter",
                ),
            }
        )

        result = parameter_schema_to_openapi(schema)

        assert "required" in result
        assert "required_param" in result["required"]
        assert "optional_param" not in result["required"]

    def test_no_required_list_if_no_required_parameters(self) -> None:
        """Test that 'required' array is omitted if no parameters are required."""
        schema = ParameterSchema(
            parameters={
                "optional_param": ParameterDefinition(
                    name="optional_param",
                    type=int,
                    required=False,
                    default=10,
                    description="Optional parameter",
                )
            }
        )

        result = parameter_schema_to_openapi(schema)

        assert "required" not in result

    def test_all_parameters_included(self) -> None:
        """Test that all parameters from schema are included in OpenAPI schema."""
        schema = ParameterSchema(
            parameters={
                "param1": ParameterDefinition(
                    name="param1",
                    type=float,
                    required=False,
                    default=0.5,
                    description="Parameter 1",
                ),
                "param2": ParameterDefinition(
                    name="param2",
                    type=int,
                    required=True,
                    default=None,
                    description="Parameter 2",
                ),
                "param3": ParameterDefinition(
                    name="param3",
                    type=str,
                    required=False,
                    default="default",
                    description="Parameter 3",
                ),
            }
        )

        result = parameter_schema_to_openapi(schema)

        assert len(result["properties"]) == 3
        assert "param1" in result["properties"]
        assert "param2" in result["properties"]
        assert "param3" in result["properties"]

    def test_complex_schema_with_all_features(self) -> None:
        """Test schema with all features: types, defaults, min/max, required/optional."""
        schema = ParameterSchema(
            parameters={
                "required_int": ParameterDefinition(
                    name="required_int",
                    type=int,
                    required=True,
                    default=None,
                    description="Required integer",
                    min_value=0,
                    max_value=100,
                ),
                "optional_float": ParameterDefinition(
                    name="optional_float",
                    type=float,
                    required=False,
                    default=0.5,
                    description="Optional float",
                    min_value=0.0,
                    max_value=1.0,
                ),
                "optional_bool": ParameterDefinition(
                    name="optional_bool",
                    type=bool,
                    required=False,
                    default=True,
                    description="Optional boolean",
                ),
                "optional_string": ParameterDefinition(
                    name="optional_string",
                    type=str,
                    required=False,
                    default="default",
                    description="Optional string",
                ),
            }
        )

        result = parameter_schema_to_openapi(schema)

        # Verify structure
        assert result["type"] == "object"
        assert len(result["properties"]) == 4
        assert "required" in result
        assert len(result["required"]) == 1
        assert "required_int" in result["required"]

        # Verify required_int
        required_int = result["properties"]["required_int"]
        assert required_int["type"] == "integer"
        assert required_int["minimum"] == 0
        assert required_int["maximum"] == 100
        assert "default" not in required_int  # Required params don't have defaults

        # Verify optional_float
        optional_float = result["properties"]["optional_float"]
        assert optional_float["type"] == "number"
        assert optional_float["default"] == 0.5
        assert optional_float["minimum"] == 0.0
        assert optional_float["maximum"] == 1.0

        # Verify optional_bool
        optional_bool = result["properties"]["optional_bool"]
        assert optional_bool["type"] == "boolean"
        assert optional_bool["default"] is True

        # Verify optional_string
        optional_string = result["properties"]["optional_string"]
        assert optional_string["type"] == "string"
        assert optional_string["default"] == "default"
