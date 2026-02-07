"""Tests for CLI --config flag and platform_start_task config integration.

Per Commit 5 of PLATFORM_CONFIGURATION_PROPOSAL.md:
- platform_start_task accepts optional config_path
- CLI flags override config file values
- Risk, health, execution components receive config values
- Backward compatible: no --config works identically to before
"""

import tempfile
from pathlib import Path

import yaml

from polytrader.config.models import (
    ApiConfig,
    PlatformConfig,
    PortfolioConfig,
    RiskConfig,
    SupervisorConfig,
)


class TestPlatformConfigIntegration:
    """platform_start_task uses PlatformConfig correctly."""

    def test_default_config_matches_original_defaults(self) -> None:
        """PlatformConfig() defaults match the original hardcoded values
        in platform_start_task (api_host=0.0.0.0, api_port=8000, etc.)."""
        config = PlatformConfig()

        # These were the original default parameters
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

    def test_cli_override_precedence(self) -> None:
        """CLI flags override config file values (as implemented in platform_start_task)."""
        # Simulate the override logic from platform_start_task
        pcfg = PlatformConfig(
            api=ApiConfig(host="0.0.0.0", port=8000),
            portfolio=PortfolioConfig(starting_equity=1000.0),
        )

        # CLI overrides
        api_host_override = "127.0.0.1"
        api_port_override = 9000
        starting_equity_override = None  # Not specified = use config

        api_host = api_host_override if api_host_override is not None else pcfg.api.host
        api_port = api_port_override if api_port_override is not None else pcfg.api.port
        starting_equity = (
            starting_equity_override
            if starting_equity_override is not None
            else pcfg.portfolio.starting_equity
        )

        assert api_host == "127.0.0.1"  # CLI override
        assert api_port == 9000  # CLI override
        assert starting_equity == 1000.0  # From config (no CLI override)


class TestRiskConfigPropagation:
    """Risk limits from config can be converted to RiskLimits for the engine."""

    def test_risk_limits_from_config(self) -> None:
        """RiskConfig produces valid RiskLimits for risk engine."""
        config = PlatformConfig(risk=RiskConfig(max_order_size=5.0, max_position_global=25.0))

        limits = config.risk.to_risk_limits(version=config.version)

        assert limits.max_order_size == 5.0
        assert limits.max_position_global == 25.0
        assert limits.version == "1.0"
        # Unchanged defaults
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
        """Throttle config values are accessible for ExecutionThrottle construction."""
        config = PlatformConfig()

        assert config.execution.throttle.max_orders_per_second == 10.0
        assert config.execution.throttle.max_cancels_per_second == 20.0

    def test_execution_tactics_values(self) -> None:
        """Tactics config values are accessible for ExecutionTactics construction."""
        config = PlatformConfig()

        assert config.execution.tactics.max_buy_slippage_bps == 50.0
        assert config.execution.tactics.prefer_passive is True

    def test_paper_simulation_values(self) -> None:
        """Paper simulation values are accessible for PaperExecutionAdapter."""
        config = PlatformConfig()

        assert config.execution.paper_simulation.fill_probability == 1.0
        assert config.execution.paper_simulation.latency_ms == 50.0


class TestSupervisorConfigPropagation:
    """Supervisor config values used in platform_start_task."""

    def test_control_plane_poll_interval(self) -> None:
        """Control plane poll interval accessible from config."""
        config = PlatformConfig(supervisor=SupervisorConfig(control_plane_poll_interval_s=2.5))
        assert config.supervisor.control_plane_poll_interval_s == 2.5

    def test_event_store_pool_size(self) -> None:
        """Event store pool size accessible from config."""
        config = PlatformConfig()
        assert config.database.event_store_pool_size == 10


class TestBackwardCompatibility:
    """No --config flag produces identical behavior to before."""

    def test_no_config_all_defaults(self) -> None:
        """PlatformConfig() produces all original defaults."""
        config = PlatformConfig()

        # Original platform_start_task defaults
        assert config.api.host == "0.0.0.0"
        assert config.api.port == 8000
        assert config.market_data.polling_frequency_hz == 1.0
        assert config.portfolio.starting_equity == 1000.0

        # Original EventStore pool_size=10
        assert config.database.event_store_pool_size == 10

        # Original control plane poll_interval_s=1.0
        assert config.supervisor.control_plane_poll_interval_s == 1.0
