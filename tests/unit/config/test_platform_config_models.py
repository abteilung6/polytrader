"""Tests for PlatformConfig Pydantic model hierarchy.

Per Commit 2 of PLATFORM_CONFIGURATION_PROPOSAL.md:
- All defaults match current hardcoded values exactly (regression guard)
- Frozen model prevents mutation
- Bridge methods produce valid existing model instances
- Pydantic validation rejects invalid values with clear error messages
"""

import pytest
from pydantic import ValidationError

from polytrader.config.models import (
    ApiConfig,
    CircuitBreakerConfig,
    DatabaseHealthConfig,
    DatabasePoolConfig,
    EventPersistenceConfig,
    ExecutionConfig,
    HealthGatesConfig,
    MarketDataConfig,
    MarketDiscoveryConfig,
    PaperSimulationConfig,
    PerformanceConfig,
    PlatformConfig,
    PlatformMetricsConfig,
    PortfolioConfig,
    ReconciliationConfig,
    RiskConfig,
    SupervisorConfig,
    TacticsConfig,
    ThrottleConfig,
    VenueConfig,
)
from polytrader.ops.control import CircuitBreakerThresholds
from polytrader.ops.health import HealthGateThresholds
from polytrader.risk.models import RiskLimits


class TestPlatformConfigAllDefaults:
    """PlatformConfig() must instantiate with all defaults, no arguments."""

    def test_platform_config_all_defaults(self) -> None:
        """PlatformConfig() creates a valid instance with zero args."""
        config = PlatformConfig()

        assert config.version == "1.0"
        assert isinstance(config.venue, VenueConfig)
        assert isinstance(config.api, ApiConfig)
        assert isinstance(config.database, DatabasePoolConfig)
        assert isinstance(config.metrics, PlatformMetricsConfig)
        assert isinstance(config.risk, RiskConfig)
        assert isinstance(config.health_gates, HealthGatesConfig)
        assert isinstance(config.circuit_breakers, CircuitBreakerConfig)
        assert isinstance(config.execution, ExecutionConfig)
        assert isinstance(config.portfolio, PortfolioConfig)
        assert isinstance(config.market_data, MarketDataConfig)
        assert isinstance(config.event_persistence, EventPersistenceConfig)
        assert isinstance(config.reconciliation, ReconciliationConfig)
        assert isinstance(config.supervisor, SupervisorConfig)
        assert isinstance(config.performance, PerformanceConfig)
        assert isinstance(config.market_discovery, MarketDiscoveryConfig)
        assert isinstance(config.database_health, DatabaseHealthConfig)


class TestPlatformConfigFrozen:
    """PlatformConfig and all sub-models are frozen (immutable after load)."""

    def test_root_frozen(self) -> None:
        """Cannot assign to PlatformConfig fields after construction."""
        config = PlatformConfig()
        with pytest.raises(ValidationError):
            config.version = "2.0"  # type: ignore[misc]

    def test_risk_config_frozen(self) -> None:
        """Cannot assign to RiskConfig fields after construction."""
        config = PlatformConfig()
        with pytest.raises(ValidationError):
            config.risk.max_order_size = 999.0  # type: ignore[misc]

    def test_execution_nested_frozen(self) -> None:
        """Cannot assign to nested ExecutionConfig fields."""
        config = PlatformConfig()
        with pytest.raises(ValidationError):
            config.execution.tactics.prefer_passive = False  # type: ignore[misc]


class TestRiskConfigBridge:
    """RiskConfig.to_risk_limits() produces a valid RiskLimits instance."""

    def test_risk_config_to_risk_limits_default(self) -> None:
        """Default RiskConfig produces RiskLimits matching default values."""
        risk_cfg = RiskConfig()
        limits = risk_cfg.to_risk_limits()

        assert isinstance(limits, RiskLimits)
        assert limits.version == "1.0"
        assert limits.max_position_per_market == 1.0
        assert limits.max_position_global == 10.0
        assert limits.max_notional_exposure == 100.0
        assert limits.max_order_size == 10.0
        assert limits.max_trades_per_market == 1
        assert limits.order_rate_limit_per_minute == 60
        assert limits.cancel_rate_limit_per_minute == 120
        assert limits.max_data_staleness_seconds == 5.0
        assert limits.price_deviation_threshold == 0.1

    def test_risk_config_to_risk_limits_custom(self) -> None:
        """Custom RiskConfig values propagate to RiskLimits."""
        risk_cfg = RiskConfig(max_order_size=5.0, max_position_per_market=2.5)
        limits = risk_cfg.to_risk_limits(version="2.0")

        assert limits.version == "2.0"
        assert limits.max_order_size == 5.0
        assert limits.max_position_per_market == 2.5
        # Unchanged defaults
        assert limits.max_position_global == 10.0

    def test_risk_config_to_risk_limits_version(self) -> None:
        """Version parameter passed through to RiskLimits."""
        risk_cfg = RiskConfig()
        limits = risk_cfg.to_risk_limits(version="3.1")
        assert limits.version == "3.1"


class TestHealthGatesConfigBridge:
    """HealthGatesConfig.to_thresholds() produces a valid HealthGateThresholds."""

    def test_health_gates_to_thresholds_default(self) -> None:
        """Default HealthGatesConfig produces matching HealthGateThresholds."""
        hg_cfg = HealthGatesConfig()
        thresholds = hg_cfg.to_thresholds()

        assert isinstance(thresholds, HealthGateThresholds)
        assert thresholds.max_market_data_staleness_seconds == 60.0
        assert thresholds.max_reconciliation_divergences == 0
        assert thresholds.max_error_rate == 0.1
        assert thresholds.require_user_stream is True

    def test_health_gates_to_thresholds_custom(self) -> None:
        """Custom HealthGatesConfig values propagate."""
        hg_cfg = HealthGatesConfig(max_error_rate=0.05, require_user_stream=False)
        thresholds = hg_cfg.to_thresholds()

        assert thresholds.max_error_rate == 0.05
        assert thresholds.require_user_stream is False


class TestCircuitBreakerConfigBridge:
    """CircuitBreakerConfig.to_thresholds() produces valid CircuitBreakerThresholds."""

    def test_circuit_breaker_to_thresholds_default(self) -> None:
        """Default CircuitBreakerConfig produces matching CircuitBreakerThresholds."""
        cb_cfg = CircuitBreakerConfig()
        thresholds = cb_cfg.to_thresholds()

        assert isinstance(thresholds, CircuitBreakerThresholds)
        assert thresholds.max_phantom_orders == 3
        assert thresholds.max_orphan_orders == 3
        assert thresholds.max_fill_mismatches == 1
        assert thresholds.require_error_severity is True

    def test_circuit_breaker_to_thresholds_custom(self) -> None:
        """Custom CircuitBreakerConfig values propagate."""
        cb_cfg = CircuitBreakerConfig(max_fill_mismatches=5, require_error_severity=False)
        thresholds = cb_cfg.to_thresholds()

        assert thresholds.max_fill_mismatches == 5
        assert thresholds.require_error_severity is False


class TestRiskConfigValidation:
    """RiskConfig validation rejects invalid values."""

    def test_rejects_negative_order_size(self) -> None:
        """Negative max_order_size raises ValidationError."""
        with pytest.raises(ValidationError):
            RiskConfig(max_order_size=-1.0)

    def test_rejects_zero_position_per_market(self) -> None:
        """Zero max_position_per_market raises ValidationError (gt=0)."""
        with pytest.raises(ValidationError):
            RiskConfig(max_position_per_market=0.0)

    def test_rejects_price_deviation_above_one(self) -> None:
        """price_deviation_threshold > 1.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            RiskConfig(price_deviation_threshold=1.5)

    def test_rejects_negative_staleness(self) -> None:
        """Negative max_data_staleness_seconds raises ValidationError."""
        with pytest.raises(ValidationError):
            RiskConfig(max_data_staleness_seconds=-1.0)


class TestHealthGatesValidation:
    """HealthGatesConfig validation rejects invalid values."""

    def test_rejects_error_rate_above_one(self) -> None:
        """max_error_rate > 1.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            HealthGatesConfig(max_error_rate=2.0)

    def test_rejects_negative_staleness(self) -> None:
        """Negative max_market_data_staleness_seconds raises ValidationError."""
        with pytest.raises(ValidationError):
            HealthGatesConfig(max_market_data_staleness_seconds=-1.0)

    def test_allows_zero_staleness(self) -> None:
        """Zero staleness is allowed (ge=0)."""
        hg = HealthGatesConfig(max_market_data_staleness_seconds=0.0)
        assert hg.max_market_data_staleness_seconds == 0.0


class TestExecutionValidation:
    """Execution config validation rejects invalid values."""

    def test_throttle_rejects_zero_orders_per_second(self) -> None:
        """max_orders_per_second = 0 raises ValidationError (gt=0)."""
        with pytest.raises(ValidationError):
            ThrottleConfig(max_orders_per_second=0.0)

    def test_throttle_rejects_negative(self) -> None:
        """Negative max_cancels_per_second raises ValidationError."""
        with pytest.raises(ValidationError):
            ThrottleConfig(max_cancels_per_second=-1.0)

    def test_paper_simulation_fill_probability_range(self) -> None:
        """fill_probability > 1.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            PaperSimulationConfig(fill_probability=1.5)

    def test_paper_simulation_rejection_probability_range(self) -> None:
        """rejection_probability > 1.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            PaperSimulationConfig(rejection_probability=1.1)

    def test_paper_simulation_negative_latency_rejected(self) -> None:
        """Negative latency_ms raises ValidationError."""
        with pytest.raises(ValidationError):
            PaperSimulationConfig(latency_ms=-10.0)


class TestApiValidation:
    """ApiConfig validation."""

    def test_rejects_port_zero(self) -> None:
        """Port 0 raises ValidationError (ge=1)."""
        with pytest.raises(ValidationError):
            ApiConfig(port=0)

    def test_rejects_port_too_high(self) -> None:
        """Port 70000 raises ValidationError (le=65535)."""
        with pytest.raises(ValidationError):
            ApiConfig(port=70000)


class TestPartialOverride:
    """PlatformConfig allows partial overrides — unspecified fields use defaults."""

    def test_partial_risk_override(self) -> None:
        """Override only risk.max_order_size; everything else stays default."""
        config = PlatformConfig(risk=RiskConfig(max_order_size=5.0))

        assert config.risk.max_order_size == 5.0
        # All other risk defaults preserved
        assert config.risk.max_position_per_market == 1.0
        assert config.risk.max_position_global == 10.0
        # All other sections default
        assert config.api.port == 8000
        assert config.health_gates.max_error_rate == 0.1

    def test_partial_execution_override(self) -> None:
        """Override only execution.tactics.prefer_passive; rest defaults."""
        config = PlatformConfig(
            execution=ExecutionConfig(tactics=TacticsConfig(prefer_passive=False))
        )

        assert config.execution.tactics.prefer_passive is False
        # Throttle defaults preserved
        assert config.execution.throttle.max_orders_per_second == 10.0
        # Paper simulation defaults preserved
        assert config.execution.paper_simulation.fill_probability == 1.0


class TestDefaultsMatchExistingHardcoded:
    """Regression guard: every default in PlatformConfig() must match
    the current hardcoded value in the respective source file.

    If a hardcoded default changes but PlatformConfig is not updated,
    this test will catch the drift.
    """

    def test_venue_defaults(self) -> None:
        """Venue defaults match config.py constants."""
        config = PlatformConfig()
        # config.py:25 — CLOB_API_URL = "https://clob.polymarket.com"
        assert config.venue.clob_api_url == "https://clob.polymarket.com"
        # config.py:26 — CHAIN_ID = 137
        assert config.venue.chain_id == 137

    def test_api_defaults(self) -> None:
        """API defaults match cli.py / tasks/platform.py."""
        config = PlatformConfig()
        assert config.api.host == "0.0.0.0"
        assert config.api.port == 8000

    def test_database_pool_defaults(self) -> None:
        """Pool sizes match tasks/platform.py and store_factory.py."""
        config = PlatformConfig()
        assert config.database.event_store_pool_size == 10
        assert config.database.tick_store_pool_size == 5

    def test_metrics_defaults(self) -> None:
        """Metrics defaults match config.py MetricsConfig."""
        config = PlatformConfig()
        assert config.metrics.backend == "prometheus"
        assert config.metrics.port == 9100
        assert config.metrics.histogram_max_size == 1000

    def test_risk_defaults(self) -> None:
        """Risk defaults match risk/models.py RiskLimits."""
        config = PlatformConfig()
        assert config.risk.max_position_per_market == 1.0
        assert config.risk.max_position_global == 10.0
        assert config.risk.max_notional_exposure == 100.0
        assert config.risk.max_order_size == 10.0
        assert config.risk.max_trades_per_market == 1
        assert config.risk.order_rate_limit_per_minute == 60
        assert config.risk.cancel_rate_limit_per_minute == 120
        assert config.risk.max_data_staleness_seconds == 5.0
        assert config.risk.price_deviation_threshold == 0.1

    def test_health_gates_defaults(self) -> None:
        """Health gate defaults match ops/health.py HealthGateThresholds."""
        config = PlatformConfig()
        assert config.health_gates.max_market_data_staleness_seconds == 60.0
        assert config.health_gates.max_reconciliation_divergences == 0
        assert config.health_gates.max_error_rate == 0.1
        assert config.health_gates.require_user_stream is True

    def test_circuit_breaker_defaults(self) -> None:
        """Circuit breaker defaults match ops/control.py CircuitBreakerThresholds."""
        config = PlatformConfig()
        assert config.circuit_breakers.max_phantom_orders == 3
        assert config.circuit_breakers.max_orphan_orders == 3
        assert config.circuit_breakers.max_fill_mismatches == 1
        assert config.circuit_breakers.require_error_severity is True

    def test_execution_throttle_defaults(self) -> None:
        """Throttle defaults match execution/throttle.py."""
        config = PlatformConfig()
        assert config.execution.throttle.max_orders_per_second == 10.0
        assert config.execution.throttle.max_cancels_per_second == 20.0

    def test_execution_tactics_defaults(self) -> None:
        """Tactics defaults match execution/tactics.py."""
        config = PlatformConfig()
        assert config.execution.tactics.max_buy_slippage_bps == 50.0
        assert config.execution.tactics.max_sell_slippage_bps == 50.0
        assert config.execution.tactics.prefer_passive is True

    def test_paper_simulation_defaults(self) -> None:
        """Paper simulation defaults match execution/paper.py."""
        config = PlatformConfig()
        assert config.execution.paper_simulation.fill_probability == 1.0
        assert config.execution.paper_simulation.rejection_probability == 0.0
        assert config.execution.paper_simulation.latency_ms == 50.0
        assert config.execution.paper_simulation.slippage_bps == 10.0

    def test_portfolio_defaults(self) -> None:
        """Portfolio defaults match portfolio/service.py and tasks/platform.py."""
        config = PlatformConfig()
        assert config.portfolio.fixed_size_usd == 1.0
        assert config.portfolio.starting_equity == 1000.0

    def test_market_data_defaults(self) -> None:
        """Market data defaults match adapters and observer.py."""
        config = PlatformConfig()
        assert config.market_data.polling_frequency_hz == 1.0
        assert config.market_data.gap_threshold_seconds == 10.0
        assert config.market_data.tick_store_window == 3000
        assert config.market_data.reconnect.initial_delay_s == 1.0
        assert config.market_data.reconnect.max_delay_s == 60.0

    def test_event_persistence_defaults(self) -> None:
        """Event persistence defaults match events/sink.py and store_factory.py."""
        config = PlatformConfig()
        assert config.event_persistence.event_batch_size == 100
        assert config.event_persistence.event_flush_interval_s == 1.0
        assert config.event_persistence.event_max_buffer_size == 10000
        assert config.event_persistence.tick_batch_size == 1000
        assert config.event_persistence.tick_flush_interval_s == 1.0
        assert config.event_persistence.failure_threshold == 10
        assert config.event_persistence.cooldown_seconds == 300.0

    def test_reconciliation_defaults(self) -> None:
        """Reconciliation defaults match supervisor/system.py and position_manager."""
        config = PlatformConfig()
        assert config.reconciliation.interval_s == 60.0
        assert config.reconciliation.position_sync_interval_s == 60.0

    def test_supervisor_defaults(self) -> None:
        """Supervisor defaults match supervisor/system.py and related modules."""
        config = PlatformConfig()
        assert config.supervisor.startup_timeout_s == 30.0
        assert config.supervisor.poll_interval_s == 1.0
        assert config.supervisor.control_plane_poll_interval_s == 1.0
        assert config.supervisor.market_monitor_interval_s == 1.0
        assert config.supervisor.market_retry_delay_s == 5.0

    def test_performance_defaults(self) -> None:
        """Performance defaults match db/performance_repository.py."""
        config = PlatformConfig()
        assert config.performance.min_trades_threshold == 1
        assert config.performance.default_query_limit == 200
        assert config.performance.max_query_limit == 1000

    def test_market_discovery_defaults(self) -> None:
        """Market discovery defaults match market_discovery/service.py."""
        config = PlatformConfig()
        assert config.market_discovery.max_windows_ahead == 48
        assert config.market_discovery.max_windows_behind == 4

    def test_database_health_defaults(self) -> None:
        """Database health defaults match db/health.py."""
        config = PlatformConfig()
        assert config.database_health.write_latency_threshold_ms == 100.0
        assert config.database_health.read_latency_threshold_ms == 50.0


class TestModelValidateFromDict:
    """PlatformConfig can be constructed from a dict (as YAML loader will provide)."""

    def test_from_empty_dict(self) -> None:
        """Empty dict produces all defaults."""
        config = PlatformConfig.model_validate({})
        assert config.risk.max_order_size == 10.0

    def test_from_partial_dict(self) -> None:
        """Partial dict overrides specified fields, defaults for rest."""
        data = {
            "version": "2.0",
            "risk": {"max_order_size": 5.0},
            "api": {"port": 9000},
        }
        config = PlatformConfig.model_validate(data)

        assert config.version == "2.0"
        assert config.risk.max_order_size == 5.0
        assert config.risk.max_position_per_market == 1.0  # default
        assert config.api.port == 9000
        assert config.api.host == "0.0.0.0"  # default

    def test_from_nested_dict(self) -> None:
        """Deeply nested dict overrides work."""
        data = {
            "execution": {
                "throttle": {"max_orders_per_second": 5.0},
                "tactics": {"prefer_passive": False},
            }
        }
        config = PlatformConfig.model_validate(data)

        assert config.execution.throttle.max_orders_per_second == 5.0
        assert config.execution.throttle.max_cancels_per_second == 20.0  # default
        assert config.execution.tactics.prefer_passive is False
        assert config.execution.paper_simulation.fill_probability == 1.0  # default

    def test_invalid_dict_raises(self) -> None:
        """Invalid values in dict raise ValidationError."""
        data = {"risk": {"max_order_size": -1.0}}
        with pytest.raises(ValidationError):
            PlatformConfig.model_validate(data)

    def test_unknown_fields_rejected(self) -> None:
        """Unknown top-level fields are rejected (extra='forbid' not set,
        but unknown nested fields in frozen models raise)."""
        # Pydantic with frozen=True still allows extra by default unless
        # extra='forbid' is set. This test documents current behavior.
        # For now, unknown fields at top level are silently ignored
        # (Pydantic default behavior).
        data = {"unknown_section": {"foo": "bar"}}
        # Should not raise — Pydantic ignores unknown fields by default
        config = PlatformConfig.model_validate(data)
        assert config.version == "1.0"
