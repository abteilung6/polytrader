"""Tests for risk limits store.

Per testing.mdc §2: Test limits version changes are detected/audited.
"""

import pytest

from polytrader.risk.limits_store import get_default_limits, load_limits_from_config
from polytrader.risk.models import RiskLimits


class TestGetDefaultLimits:
    """Tests for get_default_limits function."""

    def test_get_default_limits_returns_valid_limits(self) -> None:
        """Test that get_default_limits returns a valid RiskLimits instance."""
        limits = get_default_limits()

        assert isinstance(limits, RiskLimits)
        assert limits.version == "1.0"

    def test_get_default_limits_has_conservative_values(self) -> None:
        """Test that default limits have conservative values."""
        limits = get_default_limits()

        # Conservative defaults for safety
        assert limits.max_position_per_market == 1.0
        assert limits.max_position_global == 10.0
        assert limits.max_notional_exposure == 100.0
        assert limits.max_order_size == 10.0
        assert limits.max_trades_per_market == 1
        assert limits.order_rate_limit_per_minute == 60
        assert limits.cancel_rate_limit_per_minute == 120
        assert limits.max_data_staleness_seconds == 5.0
        assert limits.price_deviation_threshold == 0.1

    def test_get_default_limits_has_version(self) -> None:
        """Test that default limits have a version for auditability."""
        limits = get_default_limits()

        assert limits.version == "1.0"
        assert isinstance(limits.version, str)

    def test_get_default_limits_matches_model_defaults(self) -> None:
        """Test that default limits match RiskLimits model defaults."""
        limits_from_store = get_default_limits()
        limits_from_model = RiskLimits()

        # Should have same values (single source of truth)
        assert limits_from_store.version == limits_from_model.version
        assert (
            limits_from_store.max_position_per_market == limits_from_model.max_position_per_market
        )
        assert limits_from_store.max_position_global == limits_from_model.max_position_global
        assert limits_from_store.max_notional_exposure == limits_from_model.max_notional_exposure
        assert limits_from_store.max_order_size == limits_from_model.max_order_size
        assert limits_from_store.max_trades_per_market == limits_from_model.max_trades_per_market
        assert (
            limits_from_store.order_rate_limit_per_minute
            == limits_from_model.order_rate_limit_per_minute
        )
        assert (
            limits_from_store.cancel_rate_limit_per_minute
            == limits_from_model.cancel_rate_limit_per_minute
        )
        assert (
            limits_from_store.max_data_staleness_seconds
            == limits_from_model.max_data_staleness_seconds
        )
        assert (
            limits_from_store.price_deviation_threshold
            == limits_from_model.price_deviation_threshold
        )


class TestLoadLimitsFromConfig:
    """Tests for load_limits_from_config function."""

    def test_load_limits_from_config_valid_config(self) -> None:
        """Test that valid config loads correctly."""
        config = {
            "version": "2.0",
            "max_order_size": 20.0,
            "max_position_per_market": 5.0,
        }

        limits = load_limits_from_config(config)

        assert limits.version == "2.0"
        assert limits.max_order_size == 20.0
        assert limits.max_position_per_market == 5.0
        # Other fields should use defaults
        assert limits.max_position_global == 10.0

    def test_load_limits_from_config_partial_config(self) -> None:
        """Test that partial config merges with defaults."""
        config = {
            "max_order_size": 15.0,
        }

        limits = load_limits_from_config(config)

        # Custom value
        assert limits.max_order_size == 15.0
        # Defaults for other fields
        assert limits.max_position_per_market == 1.0
        assert limits.max_position_global == 10.0
        assert limits.version == "1.0"  # Default version

    def test_load_limits_from_config_without_version(self) -> None:
        """Test that config without version defaults to "1.0"."""
        config = {
            "max_order_size": 20.0,
        }

        limits = load_limits_from_config(config)

        # Should default to "1.0" for auditability
        assert limits.version == "1.0"

    def test_load_limits_from_config_invalid_values(self) -> None:
        """Test that invalid values raise ValueError."""
        # Negative value
        config = {"max_order_size": -1.0}

        with pytest.raises(ValueError, match="Invalid risk limits configuration"):
            load_limits_from_config(config)

    def test_load_limits_from_config_negative_values(self) -> None:
        """Test that negative values raise ValueError."""
        config = {"max_position_per_market": -5.0}

        with pytest.raises(ValueError):
            load_limits_from_config(config)

    def test_load_limits_from_config_out_of_range(self) -> None:
        """Test that out-of-range values raise ValueError."""
        # price_deviation_threshold must be <= 1.0
        config = {"price_deviation_threshold": 1.5}

        with pytest.raises(ValueError):
            load_limits_from_config(config)

    def test_load_limits_from_config_zero_value(self) -> None:
        """Test that zero values for gt=0 fields raise ValueError."""
        # max_order_size must be > 0
        config = {"max_order_size": 0.0}

        with pytest.raises(ValueError):
            load_limits_from_config(config)

    def test_load_limits_from_config_empty_dict(self) -> None:
        """Test that empty dict uses all defaults."""
        limits = load_limits_from_config({})

        # Should use all defaults
        assert limits.version == "1.0"
        assert limits.max_order_size == 10.0
        assert limits.max_position_per_market == 1.0

    def test_load_limits_from_config_all_fields(self) -> None:
        """Test that all fields can be overridden."""
        config = {
            "version": "3.0",
            "max_position_per_market": 2.0,
            "max_position_global": 20.0,
            "max_notional_exposure": 200.0,
            "max_order_size": 25.0,
            "max_trades_per_market": 2,
            "order_rate_limit_per_minute": 120,
            "cancel_rate_limit_per_minute": 240,
            "max_data_staleness_seconds": 10.0,
            "price_deviation_threshold": 0.2,
        }

        limits = load_limits_from_config(config)

        assert limits.version == "3.0"
        assert limits.max_position_per_market == 2.0
        assert limits.max_position_global == 20.0
        assert limits.max_notional_exposure == 200.0
        assert limits.max_order_size == 25.0
        assert limits.max_trades_per_market == 2
        assert limits.order_rate_limit_per_minute == 120
        assert limits.cancel_rate_limit_per_minute == 240
        assert limits.max_data_staleness_seconds == 10.0
        assert limits.price_deviation_threshold == 0.2

    def test_load_limits_from_config_version_tracking(self) -> None:
        """Test that version is tracked for auditability per testing.mdc §2."""
        config_v1 = {"version": "1.0", "max_order_size": 10.0}
        config_v2 = {"version": "2.0", "max_order_size": 20.0}

        limits_v1 = load_limits_from_config(config_v1)
        limits_v2 = load_limits_from_config(config_v2)

        assert limits_v1.version == "1.0"
        assert limits_v2.version == "2.0"
        # Versions are different
        assert limits_v1.version != limits_v2.version

    def test_load_limits_from_config_version_auditability(self) -> None:
        """Test that version changes are detectable per testing.mdc §2."""
        config = {"version": "2.5", "max_order_size": 15.0}

        limits = load_limits_from_config(config)

        # Version should be preserved for auditability
        assert limits.version == "2.5"
        # Version should be accessible for audit logs
        assert isinstance(limits.version, str)

    def test_load_limits_from_config_invalid_type(self) -> None:
        """Test that invalid types raise ValueError."""
        # String instead of float
        config = {"max_order_size": "invalid"}

        with pytest.raises(ValueError):
            load_limits_from_config(config)

    def test_load_limits_from_config_unknown_field(self) -> None:
        """Test that unknown fields are ignored (Pydantic behavior)."""
        config = {
            "max_order_size": 20.0,
            "unknown_field": "value",  # Should be ignored
        }

        # Should not raise, but unknown field is ignored
        limits = load_limits_from_config(config)

        assert limits.max_order_size == 20.0
        # Unknown field should not be in the model
        assert not hasattr(limits, "unknown_field")
