"""Unit tests for simple threshold parameter schema.

Per testing.mdc: Unit tests must be deterministic, fast, and isolated.
Schema validation is pure (no side effects, no I/O).
"""

from polytrader.strategies.schema import ParameterSchema
from polytrader.strategies.simple_threshold.schema import SIMPLE_THRESHOLD_SCHEMA


class TestSimpleThresholdSchema:
    """Tests for SIMPLE_THRESHOLD_SCHEMA."""

    def test_schema_is_parameter_schema(self) -> None:
        """Test that schema is a ParameterSchema instance."""
        assert isinstance(SIMPLE_THRESHOLD_SCHEMA, ParameterSchema)

    def test_schema_has_buy_threshold_parameter(self) -> None:
        """Test that schema has buy_threshold parameter."""
        assert "buy_threshold" in SIMPLE_THRESHOLD_SCHEMA.parameters

        param = SIMPLE_THRESHOLD_SCHEMA.parameters["buy_threshold"]
        assert param.name == "buy_threshold"
        assert param.type is float
        assert param.required is False
        assert param.default == 0.30
        assert param.min_value == 0.0
        assert param.max_value == 1.0

    def test_schema_has_min_history_parameter(self) -> None:
        """Test that schema has min_history parameter."""
        assert "min_history" in SIMPLE_THRESHOLD_SCHEMA.parameters

        param = SIMPLE_THRESHOLD_SCHEMA.parameters["min_history"]
        assert param.name == "min_history"
        assert param.type is int
        assert param.required is False
        assert param.default == 30
        assert param.min_value == 0
        assert param.max_value is None

    def test_validate_empty_config_uses_defaults(self) -> None:
        """Test that empty config uses default values."""
        errors = SIMPLE_THRESHOLD_SCHEMA.validate({})
        assert errors == []

    def test_validate_config_with_defaults(self) -> None:
        """Test that config with default values is valid."""
        config = {"buy_threshold": 0.30, "min_history": 30}
        errors = SIMPLE_THRESHOLD_SCHEMA.validate(config)
        assert errors == []

    def test_validate_config_custom_values(self) -> None:
        """Test that config with custom values is valid."""
        config = {"buy_threshold": 0.25, "min_history": 50}
        errors = SIMPLE_THRESHOLD_SCHEMA.validate(config)
        assert errors == []

    def test_validate_buy_threshold_below_minimum(self) -> None:
        """Test that buy_threshold below minimum is invalid."""
        config = {"buy_threshold": -0.1, "min_history": 30}
        errors = SIMPLE_THRESHOLD_SCHEMA.validate(config)
        assert len(errors) >= 1
        assert any("buy_threshold" in err and "less than minimum" in err for err in errors)

    def test_validate_buy_threshold_above_maximum(self) -> None:
        """Test that buy_threshold above maximum is invalid."""
        config = {"buy_threshold": 1.5, "min_history": 30}
        errors = SIMPLE_THRESHOLD_SCHEMA.validate(config)
        assert len(errors) >= 1
        assert any("buy_threshold" in err and "greater than maximum" in err for err in errors)

    def test_validate_buy_threshold_at_boundaries(self) -> None:
        """Test that buy_threshold at boundaries is valid."""
        # At minimum
        config1 = {"buy_threshold": 0.0, "min_history": 30}
        errors1 = SIMPLE_THRESHOLD_SCHEMA.validate(config1)
        assert errors1 == []

        # At maximum
        config2 = {"buy_threshold": 1.0, "min_history": 30}
        errors2 = SIMPLE_THRESHOLD_SCHEMA.validate(config2)
        assert errors2 == []

    def test_validate_min_history_below_minimum(self) -> None:
        """Test that min_history below minimum is invalid."""
        config = {"buy_threshold": 0.30, "min_history": -10}
        errors = SIMPLE_THRESHOLD_SCHEMA.validate(config)
        assert len(errors) >= 1
        assert any("min_history" in err and "less than minimum" in err for err in errors)

    def test_validate_min_history_at_minimum(self) -> None:
        """Test that min_history at minimum is valid."""
        config = {"buy_threshold": 0.30, "min_history": 0}
        errors = SIMPLE_THRESHOLD_SCHEMA.validate(config)
        assert errors == []

    def test_validate_wrong_type_buy_threshold(self) -> None:
        """Test that wrong type for buy_threshold is invalid."""
        config = {"buy_threshold": "0.30", "min_history": 30}  # String instead of float
        errors = SIMPLE_THRESHOLD_SCHEMA.validate(config)
        assert len(errors) == 1
        assert "buy_threshold" in errors[0]
        assert "must be float" in errors[0]

    def test_validate_wrong_type_min_history(self) -> None:
        """Test that wrong type for min_history is invalid."""
        config = {"buy_threshold": 0.30, "min_history": "30"}  # String instead of int
        errors = SIMPLE_THRESHOLD_SCHEMA.validate(config)
        assert len(errors) == 1
        assert "min_history" in errors[0]
        assert "must be int" in errors[0]

    def test_validate_unknown_parameter(self) -> None:
        """Test that unknown parameters are rejected."""
        config = {"buy_threshold": 0.30, "min_history": 30, "unknown_param": "value"}
        errors = SIMPLE_THRESHOLD_SCHEMA.validate(config)
        assert len(errors) == 1
        assert "Unknown parameters" in errors[0]
        assert "unknown_param" in errors[0]

    def test_apply_defaults(self) -> None:
        """Test that apply_defaults fills in missing parameters."""
        config: dict[str, object] = {}
        result = SIMPLE_THRESHOLD_SCHEMA.apply_defaults(config)

        assert result["buy_threshold"] == 0.30
        assert result["min_history"] == 30

    def test_apply_defaults_partial_config(self) -> None:
        """Test that apply_defaults only fills missing parameters."""
        config = {"buy_threshold": 0.25}
        result = SIMPLE_THRESHOLD_SCHEMA.apply_defaults(config)

        assert result["buy_threshold"] == 0.25  # Preserved
        assert result["min_history"] == 30  # Default applied

    def test_apply_defaults_preserves_existing_values(self) -> None:
        """Test that apply_defaults doesn't override existing values."""
        config = {"buy_threshold": 0.25, "min_history": 50}
        result = SIMPLE_THRESHOLD_SCHEMA.apply_defaults(config)

        assert result["buy_threshold"] == 0.25
        assert result["min_history"] == 50

    def test_get_required_parameters(self) -> None:
        """Test that get_required_parameters returns empty list (all optional)."""
        required = SIMPLE_THRESHOLD_SCHEMA.get_required_parameters()
        assert required == []

    def test_validate_buy_threshold_bounds_check(self) -> None:
        """Test that bounds check for buy_threshold works."""
        # Valid value (within bounds)
        config1 = {"buy_threshold": 0.5, "min_history": 30}
        errors1 = SIMPLE_THRESHOLD_SCHEMA.validate(config1)
        assert errors1 == []

        # Invalid value (fails bounds check)
        config2 = {"buy_threshold": 1.5, "min_history": 30}
        errors2 = SIMPLE_THRESHOLD_SCHEMA.validate(config2)
        assert len(errors2) >= 1
        assert any("buy_threshold" in err for err in errors2)

    def test_validate_min_history_bounds_check(self) -> None:
        """Test that bounds check for min_history works."""
        # Valid value (within bounds)
        config1 = {"buy_threshold": 0.30, "min_history": 0}
        errors1 = SIMPLE_THRESHOLD_SCHEMA.validate(config1)
        assert errors1 == []

        # Invalid value (fails bounds check)
        config2 = {"buy_threshold": 0.30, "min_history": -1}
        errors2 = SIMPLE_THRESHOLD_SCHEMA.validate(config2)
        assert len(errors2) >= 1
        assert any("min_history" in err for err in errors2)
