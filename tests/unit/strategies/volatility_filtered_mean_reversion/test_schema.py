"""Unit tests for VFMR parameter schema.

Per testing.mdc: Unit tests must be deterministic, fast, and isolated.
Schema validation is pure (no side effects, no I/O).
Mirrors simple_threshold/test_schema.py patterns.
"""

from polytrader.strategies.schema import ParameterSchema
from polytrader.strategies.volatility_filtered_mean_reversion.schema import (
    VFMR_SCHEMA,
)


class TestVfmrSchema:
    """Tests for VFMR_SCHEMA."""

    def test_schema_is_parameter_schema(self) -> None:
        """Schema is a ParameterSchema instance."""
        assert isinstance(VFMR_SCHEMA, ParameterSchema)

    def test_schema_has_expected_parameters(self) -> None:
        """Schema has all flat VFMR parameters."""
        expected = {
            "interval_minutes",
            "anchor_window",
            "atr_window",
            "ema_fast",
            "ema_slow",
            "trend_threshold",
            "entry_z",
            "exit_z",
            "risk_per_trade_pct",
            "max_position_notional_pct",
            "max_trades_per_hour",
            "cooldown_candles_after_loss",
        }
        assert set(VFMR_SCHEMA.parameters.keys()) == expected

    def test_interval_minutes_default_and_bounds(self) -> None:
        """interval_minutes: default 15, int, min 1, max 60."""
        p = VFMR_SCHEMA.parameters["interval_minutes"]
        assert p.name == "interval_minutes"
        assert p.type is int
        assert p.required is False
        assert p.default == 15
        assert p.min_value == 1
        assert p.max_value == 60

    def test_anchor_window_default_and_bounds(self) -> None:
        """anchor_window: default 96, int, min 2, max 500."""
        p = VFMR_SCHEMA.parameters["anchor_window"]
        assert p.name == "anchor_window"
        assert p.type is int
        assert p.required is False
        assert p.default == 96
        assert p.min_value == 2
        assert p.max_value == 500

    def test_entry_z_default_and_bounds(self) -> None:
        """entry_z: default 1.5, float, min 0.5, max 5.0."""
        p = VFMR_SCHEMA.parameters["entry_z"]
        assert p.default == 1.5
        assert p.type is float
        assert p.min_value == 0.5
        assert p.max_value == 5.0

    def test_validate_empty_config_uses_defaults(self) -> None:
        """Empty config is valid (all optional with defaults)."""
        errors = VFMR_SCHEMA.validate({})
        assert errors == []

    def test_validate_config_with_defaults(self) -> None:
        """Config with default values is valid."""
        config = {
            "interval_minutes": 15,
            "anchor_window": 96,
            "atr_window": 14,
            "ema_fast": 20,
            "ema_slow": 80,
            "trend_threshold": 0.5,
            "entry_z": 1.5,
            "exit_z": 0.3,
            "risk_per_trade_pct": 0.25,
            "max_position_notional_pct": 100.0,
            "max_trades_per_hour": 4,
            "cooldown_candles_after_loss": 1,
        }
        errors = VFMR_SCHEMA.validate(config)
        assert errors == []

    def test_validate_anchor_window_below_minimum(self) -> None:
        """anchor_window below 2 is invalid."""
        config = {"anchor_window": 1}
        errors = VFMR_SCHEMA.validate(config)
        assert len(errors) >= 1
        assert any("anchor_window" in err and "less than minimum" in err for err in errors)

    def test_validate_entry_z_above_maximum(self) -> None:
        """entry_z above 5.0 is invalid."""
        config = {"entry_z": 6.0}
        errors = VFMR_SCHEMA.validate(config)
        assert len(errors) >= 1
        assert any("entry_z" in err and "greater than maximum" in err for err in errors)

    def test_validate_wrong_type_anchor_window(self) -> None:
        """anchor_window must be int."""
        config = {"anchor_window": "96"}
        errors = VFMR_SCHEMA.validate(config)
        assert len(errors) == 1
        assert "anchor_window" in errors[0]
        assert "must be int" in errors[0]

    def test_validate_wrong_type_entry_z(self) -> None:
        """entry_z must be float."""
        config = {"entry_z": 1}  # int not float — schema says float
        # int 1 may be accepted if schema coerces; ParameterDefinition validates type strictly
        errors = VFMR_SCHEMA.validate(config)
        assert len(errors) == 1
        assert "entry_z" in errors[0]
        assert "must be float" in errors[0]

    def test_validate_unknown_parameter(self) -> None:
        """Unknown parameters are rejected."""
        config = {
            "anchor_window": 96,
            "unknown_param": "value",
        }
        errors = VFMR_SCHEMA.validate(config)
        assert len(errors) == 1
        assert "Unknown parameters" in errors[0]
        assert "unknown_param" in errors[0]

    def test_apply_defaults_empty_config(self) -> None:
        """apply_defaults fills all missing parameters."""
        config: dict[str, object] = {}
        result = VFMR_SCHEMA.apply_defaults(config)

        assert result["interval_minutes"] == 15
        assert result["anchor_window"] == 96
        assert result["atr_window"] == 14
        assert result["ema_fast"] == 20
        assert result["ema_slow"] == 80
        assert result["trend_threshold"] == 0.5
        assert result["entry_z"] == 1.5
        assert result["exit_z"] == 0.3
        assert result["risk_per_trade_pct"] == 0.25
        assert result["max_position_notional_pct"] == 100.0
        assert result["max_trades_per_hour"] == 4
        assert result["cooldown_candles_after_loss"] == 1

    def test_apply_defaults_partial_config(self) -> None:
        """apply_defaults only fills missing parameters."""
        config = {"interval_minutes": 1, "anchor_window": 48, "entry_z": 2.0}
        result = VFMR_SCHEMA.apply_defaults(config)

        assert result["interval_minutes"] == 1
        assert result["anchor_window"] == 48
        assert result["entry_z"] == 2.0
        assert result["atr_window"] == 14
        assert result["exit_z"] == 0.3

    def test_get_required_parameters_empty(self) -> None:
        """All VFMR params optional; get_required_parameters returns empty."""
        required = VFMR_SCHEMA.get_required_parameters()
        assert required == []

    def test_validate_exit_z_at_boundaries(self) -> None:
        """exit_z at min 0 and max 2.0 is valid."""
        errors_min = VFMR_SCHEMA.validate({"exit_z": 0.0})
        assert errors_min == []
        errors_max = VFMR_SCHEMA.validate({"exit_z": 2.0})
        assert errors_max == []
