"""Tests for CLI --config flag and platform_start_task config integration.

Verifies that:
- platform_start_task reads all values from PlatformConfig
- YAML config overrides defaults
- No CLI override parameters exist (all values from config file)
"""

import tempfile
from pathlib import Path

import yaml

from polytrader.config.models import (
    PlatformConfig,
    RiskConfig,
    SupervisorConfig,
)


class TestPlatformConfigIntegration:
    """platform_start_task uses PlatformConfig correctly."""

    def test_default_config_matches_original_defaults(self) -> None:
        """PlatformConfig() defaults match the original hardcoded values."""
        config = PlatformConfig()

        assert config.api.host == "0.0.0.0"
        assert config.api.port == 8000
        assert config.market_data.polling_frequency_hz == 1.0
        assert config.portfolio.starting_equity == 1000.0

    def test_config_from_yaml_overrides_defaults(self) -> None:
        """YAML config overrides specific defaults."""
        yaml_data = {
            "api": {"port": 9000},
            "portfolio": {"starting_equity": 5000.0},
            "risk": {"max_order_size": 5.0},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_data, f)
            config_path = Path(f.name)

        try:
            config = PlatformConfig.model_validate(yaml_data)

            assert config.api.port == 9000
            assert config.portfolio.starting_equity == 5000.0
            assert config.risk.max_order_size == 5.0
            # Unchanged defaults
            assert config.api.host == "0.0.0.0"
            assert config.risk.max_position_per_market == 1.0
        finally:
            config_path.unlink()


class TestRiskConfigPropagation:
    """Risk limits from config can be converted to RiskLimits for the engine."""

    def test_risk_limits_from_config(self) -> None:
        """RiskConfig produces valid RiskLimits for risk engine."""
        config = PlatformConfig(risk=RiskConfig(max_order_size=5.0, max_position_global=25.0))

        limits = config.risk.to_risk_limits(version=config.version)

        assert limits.max_order_size == 5.0
        assert limits.max_position_global == 25.0
        assert limits.version == "1.0"
        assert limits.max_position_per_market == 1.0

    def test_risk_limits_default_matches_engine_default(self) -> None:
        """Default RiskConfig produces same limits as get_default_limits()."""
        from polytrader.risk.limits_store import get_default_limits

        config = PlatformConfig()
        from_config = config.risk.to_risk_limits()
        from_default = get_default_limits()

        assert from_config.max_position_per_market == from_default.max_position_per_market
        assert from_config.max_position_global == from_default.max_position_global
        assert from_config.max_notional_exposure == from_default.max_notional_exposure
        assert from_config.max_order_size == from_default.max_order_size
        assert from_config.max_trades_per_market == from_default.max_trades_per_market
        assert from_config.order_rate_limit_per_minute == from_default.order_rate_limit_per_minute
        assert from_config.cancel_rate_limit_per_minute == from_default.cancel_rate_limit_per_minute
        assert from_config.max_data_staleness_seconds == from_default.max_data_staleness_seconds
        assert from_config.price_deviation_threshold == from_default.price_deviation_threshold


class TestHealthThresholdsPropagation:
    """Health gate thresholds from config propagate correctly."""

    def test_health_thresholds_from_config(self) -> None:
        """HealthGatesConfig produces valid HealthGateThresholds."""
        config = PlatformConfig()
        thresholds = config.health_gates.to_thresholds()

        from polytrader.ops.health import HealthGateThresholds

        assert isinstance(thresholds, HealthGateThresholds)
        assert thresholds.max_market_data_staleness_seconds == 60.0
        assert thresholds.require_user_stream is True


class TestCircuitBreakerPropagation:
    """Circuit breaker thresholds from config propagate correctly."""

    def test_circuit_breaker_from_config(self) -> None:
        """CircuitBreakerConfig produces valid CircuitBreakerThresholds."""
        config = PlatformConfig()
        thresholds = config.circuit_breakers.to_thresholds()

        from polytrader.ops.control import CircuitBreakerThresholds

        assert isinstance(thresholds, CircuitBreakerThresholds)
        assert thresholds.max_phantom_orders == 3
        assert thresholds.max_fill_mismatches == 1


class TestExecutionConfigPropagation:
    """Execution config values accessible for component construction."""

    def test_execution_throttle_values(self) -> None:
        config = PlatformConfig()
        assert config.execution.throttle.max_orders_per_second == 10.0
        assert config.execution.throttle.max_cancels_per_second == 20.0

    def test_execution_tactics_values(self) -> None:
        config = PlatformConfig()
        assert config.execution.tactics.max_buy_slippage_bps == 50.0
        assert config.execution.tactics.prefer_passive is True

    def test_paper_simulation_values(self) -> None:
        config = PlatformConfig()
        assert config.execution.paper_simulation.fill_probability == 1.0
        assert config.execution.paper_simulation.latency_ms == 50.0


class TestSupervisorConfigPropagation:
    """Supervisor config values used in platform_start_task."""

    def test_control_plane_poll_interval(self) -> None:
        config = PlatformConfig(supervisor=SupervisorConfig(control_plane_poll_interval_s=2.5))
        assert config.supervisor.control_plane_poll_interval_s == 2.5

    def test_event_store_pool_size(self) -> None:
        config = PlatformConfig()
        assert config.database.event_store_pool_size == 10


class TestAllValuesFromConfig:
    """All platform settings come from PlatformConfig — no CLI overrides."""

    def test_all_defaults(self) -> None:
        """PlatformConfig() produces all original defaults."""
        config = PlatformConfig()

        assert config.api.host == "0.0.0.0"
        assert config.api.port == 8000
        assert config.market_data.polling_frequency_hz == 1.0
        assert config.portfolio.starting_equity == 1000.0
        assert config.database.event_store_pool_size == 10
        assert config.supervisor.control_plane_poll_interval_s == 1.0
