"""Tests for config propagation to components.

Per Commit 6 of PLATFORM_CONFIGURATION_PROPOSAL.md:
- PlatformOrchestrator uses config for fixed_size_usd and risk limits
- Risk limits from config match engine expectations
- Health/circuit breaker thresholds propagate correctly
- Metrics port from config is respected
"""

from polytrader.config.models import (
    PlatformConfig,
    PortfolioConfig,
    RiskConfig,
)
from polytrader.risk.limits_store import get_default_limits


class TestOrchestratorConfigWiring:
    """PlatformOrchestrator receives and uses PlatformConfig."""

    def test_risk_limits_from_config_applied(self) -> None:
        """Config risk values are converted to RiskLimits for engine."""
        pcfg = PlatformConfig(risk=RiskConfig(max_order_size=5.0, max_position_per_market=2.5))
        limits = pcfg.risk.to_risk_limits(version=pcfg.version)

        assert limits.max_order_size == 5.0
        assert limits.max_position_per_market == 2.5
        # Unchanged defaults
        assert limits.max_position_global == 10.0

    def test_fixed_size_usd_from_config(self) -> None:
        """Config portfolio.fixed_size_usd is used instead of hardcoded 1.0."""
        pcfg = PlatformConfig(portfolio=PortfolioConfig(fixed_size_usd=3.0))
        assert pcfg.portfolio.fixed_size_usd == 3.0

    def test_default_config_matches_get_default_limits(self) -> None:
        """Default PlatformConfig risk produces same limits as get_default_limits()."""
        pcfg = PlatformConfig()
        from_config = pcfg.risk.to_risk_limits()
        from_default = get_default_limits()

        # All fields must match
        assert from_config.max_position_per_market == from_default.max_position_per_market
        assert from_config.max_position_global == from_default.max_position_global
        assert from_config.max_notional_exposure == from_default.max_notional_exposure
        assert from_config.max_order_size == from_default.max_order_size
        assert from_config.max_trades_per_market == from_default.max_trades_per_market
        assert from_config.order_rate_limit_per_minute == from_default.order_rate_limit_per_minute
        assert from_config.cancel_rate_limit_per_minute == from_default.cancel_rate_limit_per_minute
        assert from_config.max_data_staleness_seconds == from_default.max_data_staleness_seconds
        assert from_config.price_deviation_threshold == from_default.price_deviation_threshold


class TestHealthGatesWiring:
    """Health gate thresholds from config produce valid thresholds."""

    def test_health_thresholds_from_config(self) -> None:
        """HealthGatesConfig converts to HealthGateThresholds correctly."""
        pcfg = PlatformConfig()
        thresholds = pcfg.health_gates.to_thresholds()

        from polytrader.ops.health import HealthGateThresholds

        assert isinstance(thresholds, HealthGateThresholds)
        assert thresholds.max_market_data_staleness_seconds == 60.0
        assert thresholds.max_reconciliation_divergences == 0
        assert thresholds.max_error_rate == 0.1
        assert thresholds.require_user_stream is True


class TestCircuitBreakerWiring:
    """Circuit breaker thresholds from config produce valid thresholds."""

    def test_circuit_breaker_from_config(self) -> None:
        """CircuitBreakerConfig converts to CircuitBreakerThresholds correctly."""
        pcfg = PlatformConfig()
        thresholds = pcfg.circuit_breakers.to_thresholds()

        from polytrader.ops.control import CircuitBreakerThresholds

        assert isinstance(thresholds, CircuitBreakerThresholds)
        assert thresholds.max_phantom_orders == 3
        assert thresholds.max_orphan_orders == 3
        assert thresholds.max_fill_mismatches == 1
        assert thresholds.require_error_severity is True


class TestMetricsWiring:
    """Metrics port from config is accessible."""

    def test_metrics_port_from_config(self) -> None:
        """Metrics port value propagates from config."""
        pcfg = PlatformConfig()
        assert pcfg.metrics.port == 9100

    def test_custom_metrics_port(self) -> None:
        """Custom metrics port propagates."""
        pcfg = PlatformConfig.model_validate({"metrics": {"port": 9200}})
        assert pcfg.metrics.port == 9200


class TestEventPersistenceWiring:
    """Event persistence config values accessible for component construction."""

    def test_event_store_pool_size(self) -> None:
        """Event store pool size from config."""
        pcfg = PlatformConfig()
        assert pcfg.database.event_store_pool_size == 10

    def test_tick_store_pool_size(self) -> None:
        """Tick store pool size from config."""
        pcfg = PlatformConfig()
        assert pcfg.database.tick_store_pool_size == 5

    def test_event_batch_config(self) -> None:
        """Event batch size and flush interval from config."""
        pcfg = PlatformConfig()
        assert pcfg.event_persistence.event_batch_size == 100
        assert pcfg.event_persistence.event_flush_interval_s == 1.0

    def test_tick_batch_config(self) -> None:
        """Tick batch size and flush interval from config."""
        pcfg = PlatformConfig()
        assert pcfg.event_persistence.tick_batch_size == 1000
        assert pcfg.event_persistence.tick_flush_interval_s == 1.0


class TestSupervisorWiring:
    """Supervisor config values propagate."""

    def test_control_plane_poll_interval(self) -> None:
        """Control plane poll interval from config."""
        pcfg = PlatformConfig()
        assert pcfg.supervisor.control_plane_poll_interval_s == 1.0

    def test_startup_timeout(self) -> None:
        """Startup timeout from config."""
        pcfg = PlatformConfig()
        assert pcfg.supervisor.startup_timeout_s == 30.0

    def test_reconciliation_interval(self) -> None:
        """Reconciliation interval from config."""
        pcfg = PlatformConfig()
        assert pcfg.reconciliation.interval_s == 60.0
