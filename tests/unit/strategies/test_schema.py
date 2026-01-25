"""Unit tests for strategy parameter schema validation.

Per testing.mdc: Unit tests must be deterministic, fast, and isolated.
All validation logic is pure (no side effects, no I/O).
"""

import pytest

from polytrader.strategies.schema import (
    ParameterDefinition,
    ParameterSchema,
    ValidationError,
)


class TestParameterDefinition:
    """Tests for ParameterDefinition dataclass."""

    def test_create_required_parameter(self) -> None:
        """Test creating a required parameter."""
        param = ParameterDefinition(
            name="buy_threshold",
            type=float,
            required=True,
            default=None,
            description="Price threshold for BUY signals",
            min_value=0.0,
            max_value=1.0,
        )

        assert param.name == "buy_threshold"
        assert param.type is float
        assert param.required is True
        assert param.default is None
        assert param.min_value == 0.0
        assert param.max_value == 1.0

    def test_create_optional_parameter(self) -> None:
        """Test creating an optional parameter with default."""
        param = ParameterDefinition(
            name="min_history",
            type=int,
            required=False,
            default=30,
            description="Minimum history ticks required",
            min_value=0,
        )

        assert param.name == "min_history"
        assert param.type is int
        assert param.required is False
        assert param.default == 30
        assert param.min_value == 0
        assert param.max_value is None

    def test_required_parameter_must_have_none_default(self) -> None:
        """Test that required parameters must have default=None."""
        with pytest.raises(ValueError, match="default must be None if required=True"):
            ParameterDefinition(
                name="test_param",
                type=float,
                required=True,
                default=0.5,  # Invalid: required but has default
                description="Test parameter",
            )

    def test_optional_parameter_must_have_default(self) -> None:
        """Test that optional parameters must have a default value."""
        with pytest.raises(ValueError, match="default must be provided if required=False"):
            ParameterDefinition(
                name="test_param",
                type=float,
                required=False,
                default=None,  # Invalid: optional but no default
                description="Test parameter",
            )

    def test_min_max_only_for_numeric_types(self) -> None:
        """Test that min_value/max_value only valid for numeric types."""
        with pytest.raises(ValueError, match="min_value/max_value only valid for numeric types"):
            ParameterDefinition(
                name="test_param",
                type=str,
                required=True,
                default=None,
                description="Test parameter",
                min_value=0,  # Invalid: str is not numeric
            )

    def test_min_value_must_be_less_than_max_value(self) -> None:
        """Test that min_value must be <= max_value."""
        with pytest.raises(ValueError, match="min_value.*> max_value"):
            ParameterDefinition(
                name="test_param",
                type=float,
                required=True,
                default=None,
                description="Test parameter",
                min_value=1.0,
                max_value=0.5,  # Invalid: min > max
            )

    def test_validate_value_type_check(self) -> None:
        """Test that validate_value checks parameter type."""
        param = ParameterDefinition(
            name="buy_threshold",
            type=float,
            required=True,
            default=None,
            description="Price threshold",
        )

        # Valid type
        errors = param.validate_value(0.5)
        assert errors == []

        # Invalid type
        errors = param.validate_value("0.5")
        assert len(errors) == 1
        assert "must be float" in errors[0]

    def test_validate_value_numeric_bounds(self) -> None:
        """Test that validate_value checks numeric bounds."""
        param = ParameterDefinition(
            name="buy_threshold",
            type=float,
            required=True,
            default=None,
            description="Price threshold",
            min_value=0.0,
            max_value=1.0,
        )

        # Valid value
        errors = param.validate_value(0.5)
        assert errors == []

        # Below minimum
        errors = param.validate_value(-0.1)
        assert len(errors) == 1
        assert "less than minimum" in errors[0]

        # Above maximum
        errors = param.validate_value(1.5)
        assert len(errors) == 1
        assert "greater than maximum" in errors[0]

        # At boundaries (should be valid)
        errors = param.validate_value(0.0)
        assert errors == []

        errors = param.validate_value(1.0)
        assert errors == []

    def test_validate_value_custom_validator(self) -> None:
        """Test that validate_value runs custom validation function."""

        def is_positive(value: float) -> bool:
            return value > 0

        param = ParameterDefinition(
            name="target_profit",
            type=float,
            required=True,
            default=None,
            description="Target profit",
            validation=is_positive,
        )

        # Valid value (passes custom validator)
        errors = param.validate_value(10.0)
        assert errors == []

        # Invalid value (fails custom validator)
        errors = param.validate_value(-5.0)
        assert len(errors) == 1
        assert "custom validation failed" in errors[0]

    def test_validate_value_custom_validator_exception(self) -> None:
        """Test that custom validator exceptions are caught."""

        def failing_validator(value: float) -> bool:
            raise RuntimeError("Validator error")

        param = ParameterDefinition(
            name="test_param",
            type=float,
            required=True,
            default=None,
            description="Test parameter",
            validation=failing_validator,
        )

        errors = param.validate_value(0.5)
        assert len(errors) == 1
        assert "custom validation raised exception" in errors[0]

    def test_validate_value_default_type_check(self) -> None:
        """Test that default value type is validated on creation."""
        # Valid default type
        param1 = ParameterDefinition(
            name="test_param",
            type=float,
            required=False,
            default=0.5,
            description="Test parameter",
        )
        assert param1.default == 0.5

        # Invalid default type (should raise on creation)
        with pytest.raises(ValidationError, match="must be float"):
            ParameterDefinition(
                name="test_param",
                type=float,
                required=False,
                default="0.5",  # Wrong type
                description="Test parameter",
            )


class TestParameterSchema:
    """Tests for ParameterSchema dataclass."""

    def test_create_schema(self) -> None:
        """Test creating a parameter schema."""
        schema = ParameterSchema(
            parameters={
                "buy_threshold": ParameterDefinition(
                    name="buy_threshold",
                    type=float,
                    required=True,
                    default=None,
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

        assert len(schema.parameters) == 2
        assert "buy_threshold" in schema.parameters
        assert "min_history" in schema.parameters

    def test_schema_must_have_at_least_one_parameter(self) -> None:
        """Test that schema must have at least one parameter."""
        with pytest.raises(ValueError, match="must have at least one parameter"):
            ParameterSchema(parameters={})

    def test_validate_required_parameter_missing(self) -> None:
        """Test validation fails when required parameter is missing."""
        schema = ParameterSchema(
            parameters={
                "buy_threshold": ParameterDefinition(
                    name="buy_threshold",
                    type=float,
                    required=True,
                    default=None,
                    description="Price threshold",
                ),
            }
        )

        errors = schema.validate({})
        assert len(errors) == 1
        assert "buy_threshold: required parameter missing" in errors[0]

    def test_validate_optional_parameter_missing(self) -> None:
        """Test validation passes when optional parameter is missing."""
        schema = ParameterSchema(
            parameters={
                "buy_threshold": ParameterDefinition(
                    name="buy_threshold",
                    type=float,
                    required=True,
                    default=None,
                    description="Price threshold",
                ),
                "min_history": ParameterDefinition(
                    name="min_history",
                    type=int,
                    required=False,
                    default=30,
                    description="Minimum history",
                ),
            }
        )

        errors = schema.validate({"buy_threshold": 0.5})
        assert errors == []

    def test_validate_unknown_parameter(self) -> None:
        """Test validation fails when unknown parameter is present."""
        schema = ParameterSchema(
            parameters={
                "buy_threshold": ParameterDefinition(
                    name="buy_threshold",
                    type=float,
                    required=True,
                    default=None,
                    description="Price threshold",
                ),
            }
        )

        errors = schema.validate({"buy_threshold": 0.5, "unknown_param": "value"})
        assert len(errors) == 1
        assert "Unknown parameters" in errors[0]
        assert "unknown_param" in errors[0]

    def test_validate_type_mismatch(self) -> None:
        """Test validation fails when parameter type is wrong."""
        schema = ParameterSchema(
            parameters={
                "buy_threshold": ParameterDefinition(
                    name="buy_threshold",
                    type=float,
                    required=True,
                    default=None,
                    description="Price threshold",
                ),
            }
        )

        errors = schema.validate({"buy_threshold": "0.5"})  # String instead of float
        assert len(errors) == 1
        assert "must be float" in errors[0]

    def test_validate_numeric_bounds(self) -> None:
        """Test validation checks numeric bounds."""
        schema = ParameterSchema(
            parameters={
                "buy_threshold": ParameterDefinition(
                    name="buy_threshold",
                    type=float,
                    required=True,
                    default=None,
                    description="Price threshold",
                    min_value=0.0,
                    max_value=1.0,
                ),
            }
        )

        # Valid value
        errors = schema.validate({"buy_threshold": 0.5})
        assert errors == []

        # Below minimum
        errors = schema.validate({"buy_threshold": -0.1})
        assert len(errors) == 1
        assert "less than minimum" in errors[0]

        # Above maximum
        errors = schema.validate({"buy_threshold": 1.5})
        assert len(errors) == 1
        assert "greater than maximum" in errors[0]

    def test_validate_multiple_errors(self) -> None:
        """Test validation collects all errors."""
        schema = ParameterSchema(
            parameters={
                "buy_threshold": ParameterDefinition(
                    name="buy_threshold",
                    type=float,
                    required=True,
                    default=None,
                    description="Price threshold",
                    min_value=0.0,
                    max_value=1.0,
                ),
                "min_history": ParameterDefinition(
                    name="min_history",
                    type=int,
                    required=True,
                    default=None,
                    description="Minimum history",
                    min_value=0,
                ),
            }
        )

        errors = schema.validate(
            {
                "buy_threshold": 1.5,  # Above max
                "min_history": -10,  # Below min
            }
        )

        assert len(errors) == 2
        assert any("buy_threshold" in err and "greater than maximum" in err for err in errors)
        assert any("min_history" in err and "less than minimum" in err for err in errors)

    def test_apply_defaults(self) -> None:
        """Test that apply_defaults fills in missing optional parameters."""
        schema = ParameterSchema(
            parameters={
                "buy_threshold": ParameterDefinition(
                    name="buy_threshold",
                    type=float,
                    required=True,
                    default=None,
                    description="Price threshold",
                ),
                "min_history": ParameterDefinition(
                    name="min_history",
                    type=int,
                    required=False,
                    default=30,
                    description="Minimum history",
                ),
            }
        )

        config = {"buy_threshold": 0.5}
        result = schema.apply_defaults(config)

        assert result["buy_threshold"] == 0.5
        assert result["min_history"] == 30  # Default applied

    def test_apply_defaults_preserves_existing_values(self) -> None:
        """Test that apply_defaults doesn't override existing values."""
        schema = ParameterSchema(
            parameters={
                "min_history": ParameterDefinition(
                    name="min_history",
                    type=int,
                    required=False,
                    default=30,
                    description="Minimum history",
                ),
            }
        )

        config = {"min_history": 50}
        result = schema.apply_defaults(config)

        assert result["min_history"] == 50  # Existing value preserved

    def test_apply_defaults_does_not_modify_input(self) -> None:
        """Test that apply_defaults doesn't modify input dictionary."""
        schema = ParameterSchema(
            parameters={
                "min_history": ParameterDefinition(
                    name="min_history",
                    type=int,
                    required=False,
                    default=30,
                    description="Minimum history",
                ),
            }
        )

        config = {"buy_threshold": 0.5}
        original_config = dict(config)

        result = schema.apply_defaults(config)

        # Input should be unchanged
        assert config == original_config
        # Result should be new dict
        assert result is not config

    def test_get_required_parameters(self) -> None:
        """Test that get_required_parameters returns only required params."""
        schema = ParameterSchema(
            parameters={
                "buy_threshold": ParameterDefinition(
                    name="buy_threshold",
                    type=float,
                    required=True,
                    default=None,
                    description="Price threshold",
                ),
                "min_history": ParameterDefinition(
                    name="min_history",
                    type=int,
                    required=False,
                    default=30,
                    description="Minimum history",
                ),
            }
        )

        required = schema.get_required_parameters()
        assert required == ["buy_threshold"]
        assert "min_history" not in required

    def test_validate_all_parameter_types(self) -> None:
        """Test validation works for all supported types."""
        schema = ParameterSchema(
            parameters={
                "float_param": ParameterDefinition(
                    name="float_param",
                    type=float,
                    required=True,
                    default=None,
                    description="Float parameter",
                ),
                "int_param": ParameterDefinition(
                    name="int_param",
                    type=int,
                    required=True,
                    default=None,
                    description="Integer parameter",
                ),
                "str_param": ParameterDefinition(
                    name="str_param",
                    type=str,
                    required=True,
                    default=None,
                    description="String parameter",
                ),
                "bool_param": ParameterDefinition(
                    name="bool_param",
                    type=bool,
                    required=True,
                    default=None,
                    description="Boolean parameter",
                ),
            }
        )

        # Valid config
        errors = schema.validate(
            {
                "float_param": 0.5,
                "int_param": 42,
                "str_param": "test",
                "bool_param": True,
            }
        )
        assert errors == []

        # Invalid types
        errors = schema.validate(
            {
                "float_param": "0.5",  # Wrong type
                "int_param": 42.0,  # Wrong type (float instead of int)
                "str_param": 123,  # Wrong type
                "bool_param": "true",  # Wrong type
            }
        )
        assert len(errors) == 4  # All should fail type check
