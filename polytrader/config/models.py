"""Platform configuration Pydantic models.

Defines the canonical PlatformConfig model hierarchy for all platform-owned
policy: risk limits, health gates, circuit breakers, execution, market data,
event persistence, reconciliation, supervisor, performance, and infrastructure.

All defaults match the current hardcoded values across the codebase exactly,
ensuring zero behavioral change when no config file is provided.

Per trading.mdc §7: All limits must be validated, versioned, and auditable.
Per observability.mdc §1: Config is hashed and emitted as ConfigLoadedEvent.

Secrets (PRIVATE_KEY, DB_PASSWORD, etc.) are NOT part of this model.
They remain in .env via pydantic-settings BaseSettings classes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from polytrader.ops.control import CircuitBreakerThresholds
    from polytrader.ops.health import HealthGateThresholds
    from polytrader.risk.models import RiskLimits

# ---------------------------------------------------------------------------
# Venue / Exchange Connectivity
# ---------------------------------------------------------------------------


class VenueConfig(BaseModel):
    """Venue/exchange connectivity settings.

    Per architecture.mdc §1.A: Adapters connect to venue feeds.
    """

    model_config = ConfigDict(frozen=True)

    clob_api_url: str = Field(
        default="https://clob.polymarket.com",
        description="CLOB API base URL",
    )
    chain_id: int = Field(
        default=137,
        description="Blockchain chain ID (137 = Polygon mainnet)",
    )


# ---------------------------------------------------------------------------
# Control API
# ---------------------------------------------------------------------------


class ApiConfig(BaseModel):
    """Control API server settings."""

    model_config = ConfigDict(frozen=True)

    host: str = Field(
        default="0.0.0.0",
        description="API server bind host",
    )
    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="API server port",
    )
    cors_allowed_origins: list[str] = Field(
        default=["*"],
        description="CORS allowed origins",
    )


# ---------------------------------------------------------------------------
# Database Connection Pools (credentials stay in .env)
# ---------------------------------------------------------------------------


class DatabasePoolConfig(BaseModel):
    """Database connection pool tuning. Credentials remain in .env."""

    model_config = ConfigDict(frozen=True)

    event_store_pool_size: int = Field(
        default=10,
        ge=1,
        le=100,
        description="SQLAlchemy pool size for PostgreSQL event store",
    )
    tick_store_pool_size: int = Field(
        default=5,
        ge=1,
        le=100,
        description="SQLAlchemy pool size for tick store",
    )


# ---------------------------------------------------------------------------
# Metrics & Observability
# ---------------------------------------------------------------------------


class PlatformMetricsConfig(BaseModel):
    """Metrics and observability settings.

    Per observability.mdc §4: Minimum metric set required.
    """

    model_config = ConfigDict(frozen=True)

    backend: Literal["prometheus", "memory"] = Field(
        default="prometheus",
        description="Metrics backend: 'prometheus' or 'memory'",
    )
    port: int = Field(
        default=9100,
        ge=1,
        le=65535,
        description="Metrics server port (separate from control API)",
    )
    histogram_max_size: int = Field(
        default=1000,
        gt=0,
        description="Maximum histogram sample size",
    )


# ---------------------------------------------------------------------------
# Pre-Trade Risk Limits (Hard Gate)
# ---------------------------------------------------------------------------


class RiskConfig(BaseModel):
    """Pre-trade risk limits configuration.

    Per trading.mdc §4: Risk checks emit allowed/denied, reason codes.
    Per flows.mdc §6: Risk is a hard veto gate before OMS submission.

    All defaults match polytrader/risk/models.py RiskLimits exactly.
    """

    model_config = ConfigDict(frozen=True)

    max_position_per_market: float = Field(
        default=1.0,
        gt=0,
        description="Maximum position size per market/outcome (USD)",
    )
    max_position_global: float = Field(
        default=10.0,
        gt=0,
        description="Maximum total position size across all markets (USD)",
    )
    max_notional_exposure: float = Field(
        default=100.0,
        gt=0,
        description="Maximum notional exposure (USD)",
    )
    max_order_size: float = Field(
        default=10.0,
        gt=0,
        description="Maximum size for a single order (USD)",
    )
    max_trades_per_market: int = Field(
        default=1,
        ge=0,
        description="Maximum number of trades per market/outcome",
    )
    order_rate_limit_per_minute: int = Field(
        default=60,
        ge=0,
        description="Maximum orders per minute",
    )
    cancel_rate_limit_per_minute: int = Field(
        default=120,
        ge=0,
        description="Maximum cancels per minute",
    )
    max_data_staleness_seconds: float = Field(
        default=5.0,
        gt=0,
        description="Maximum age of market data before rejecting (seconds)",
    )
    price_deviation_threshold: float = Field(
        default=0.1,
        gt=0,
        le=1.0,
        description="Maximum price deviation from mid (fraction, e.g., 0.1 = 10%)",
    )

    def to_risk_limits(self, version: str = "1.0") -> RiskLimits:
        """Convert to the existing RiskLimits model used by the risk engine.

        Args:
            version: Risk limits version for auditability (per trading.mdc §7).

        Returns:
            RiskLimits instance with matching field values.
        """
        from polytrader.risk.models import RiskLimits as _RiskLimits

        return _RiskLimits(
            version=version,
            max_position_per_market=self.max_position_per_market,
            max_position_global=self.max_position_global,
            max_notional_exposure=self.max_notional_exposure,
            max_order_size=self.max_order_size,
            max_trades_per_market=self.max_trades_per_market,
            order_rate_limit_per_minute=self.order_rate_limit_per_minute,
            cancel_rate_limit_per_minute=self.cancel_rate_limit_per_minute,
            max_data_staleness_seconds=self.max_data_staleness_seconds,
            price_deviation_threshold=self.price_deviation_threshold,
        )


# ---------------------------------------------------------------------------
# Health Gates (startup + runtime)
# ---------------------------------------------------------------------------


class HealthGatesConfig(BaseModel):
    """Health gate thresholds for startup and runtime gating.

    Per flows.mdc §2: All gates must pass before enabling execution.

    All defaults match polytrader/ops/health.py HealthGateThresholds exactly.
    """

    model_config = ConfigDict(frozen=True)

    max_market_data_staleness_seconds: float = Field(
        default=60.0,
        ge=0.0,
        description="Maximum age of market data before considered stale (seconds)",
    )
    max_reconciliation_divergences: int = Field(
        default=0,
        ge=0,
        description="Maximum number of reconciliation divergences before unhealthy",
    )
    max_error_rate: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Maximum error rate (0-1) before considered unhealthy",
    )
    require_user_stream: bool = Field(
        default=True,
        description="Whether user stream connection is required (True for live trading)",
    )

    def to_thresholds(self) -> HealthGateThresholds:
        """Convert to the existing HealthGateThresholds model used by HealthService.

        Returns:
            HealthGateThresholds instance with matching field values.
        """
        from polytrader.ops.health import HealthGateThresholds as _HealthGateThresholds

        return _HealthGateThresholds(
            max_market_data_staleness_seconds=self.max_market_data_staleness_seconds,
            max_reconciliation_divergences=self.max_reconciliation_divergences,
            max_error_rate=self.max_error_rate,
            require_user_stream=self.require_user_stream,
        )


# ---------------------------------------------------------------------------
# Circuit Breakers
# ---------------------------------------------------------------------------


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker thresholds.

    Per flows.mdc §13: Circuit breakers trigger on severe divergence.

    All defaults match polytrader/ops/control.py CircuitBreakerThresholds exactly.
    """

    model_config = ConfigDict(frozen=True)

    max_phantom_orders: int = Field(
        default=3,
        ge=0,
        description="Maximum phantom orders (OMS has, venue doesn't) before trigger",
    )
    max_orphan_orders: int = Field(
        default=3,
        ge=0,
        description="Maximum orphan orders (venue has, OMS doesn't) before trigger",
    )
    max_fill_mismatches: int = Field(
        default=1,
        ge=0,
        description="Maximum fill mismatches before trigger",
    )
    require_error_severity: bool = Field(
        default=True,
        description="If True, only trigger on ERROR severity divergences",
    )

    def to_thresholds(self) -> CircuitBreakerThresholds:
        """Convert to the existing CircuitBreakerThresholds model.

        Returns:
            CircuitBreakerThresholds instance with matching field values.
        """
        from polytrader.ops.control import (
            CircuitBreakerThresholds as _CircuitBreakerThresholds,
        )

        return _CircuitBreakerThresholds(
            max_phantom_orders=self.max_phantom_orders,
            max_orphan_orders=self.max_orphan_orders,
            max_fill_mismatches=self.max_fill_mismatches,
            require_error_severity=self.require_error_severity,
        )


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


class ThrottleConfig(BaseModel):
    """Execution throttle settings (non-risk rate limiting).

    Per flows.mdc §8: Execution applies throttling.
    """

    model_config = ConfigDict(frozen=True)

    max_orders_per_second: float = Field(
        default=10.0,
        gt=0,
        description="Maximum orders per second",
    )
    max_cancels_per_second: float = Field(
        default=20.0,
        gt=0,
        description="Maximum cancels per second",
    )


class TacticsConfig(BaseModel):
    """Execution tactics settings (slippage bands, passive preference).

    Per flows.mdc §8: Execution applies pricing rules and post-only preference.
    """

    model_config = ConfigDict(frozen=True)

    max_buy_slippage_bps: float = Field(
        default=50.0,
        ge=0,
        description="Max buy slippage in basis points (50 = 0.5%)",
    )
    max_sell_slippage_bps: float = Field(
        default=50.0,
        ge=0,
        description="Max sell slippage in basis points (50 = 0.5%)",
    )
    prefer_passive: bool = Field(
        default=True,
        description="Prefer post-only / maker orders",
    )


class PaperSimulationConfig(BaseModel):
    """Paper execution simulation settings.

    Per architecture.mdc §H: Adapters are IO-only; fill simulation is deterministic.
    """

    model_config = ConfigDict(frozen=True)

    fill_probability: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Probability of fill (0-1)",
    )
    rejection_probability: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Probability of rejection (0-1)",
    )
    latency_ms: float = Field(
        default=50.0,
        ge=0.0,
        description="Simulated latency in milliseconds",
    )
    slippage_bps: float = Field(
        default=10.0,
        ge=0.0,
        description="Slippage in basis points for simulation",
    )


class ExecutionConfig(BaseModel):
    """Execution layer settings: throttle, tactics, and paper simulation."""

    model_config = ConfigDict(frozen=True)

    throttle: ThrottleConfig = Field(default_factory=ThrottleConfig)
    tactics: TacticsConfig = Field(default_factory=TacticsConfig)
    paper_simulation: PaperSimulationConfig = Field(default_factory=PaperSimulationConfig)


# ---------------------------------------------------------------------------
# Portfolio & Sizing
# ---------------------------------------------------------------------------


class PortfolioConfig(BaseModel):
    """Portfolio and sizing settings."""

    model_config = ConfigDict(frozen=True)

    fixed_size_usd: float = Field(
        default=1.0,
        gt=0,
        description="Default fixed order size (USD)",
    )
    starting_equity: float = Field(
        default=1000.0,
        gt=0,
        description="Starting equity for paper trading (USD)",
    )


# ---------------------------------------------------------------------------
# Market Data
# ---------------------------------------------------------------------------


class ReconnectConfig(BaseModel):
    """WebSocket/adapter reconnect settings."""

    model_config = ConfigDict(frozen=True)

    initial_delay_s: float = Field(
        default=1.0,
        gt=0,
        description="Initial reconnect delay (seconds)",
    )
    max_delay_s: float = Field(
        default=60.0,
        gt=0,
        description="Maximum reconnect delay (seconds)",
    )


class MarketDataConfig(BaseModel):
    """Market data ingest and storage settings.

    Per flows.mdc §3: Market data normalized, gap-detected, staleness-tracked.
    """

    model_config = ConfigDict(frozen=True)

    polling_frequency_hz: float = Field(
        default=1.0,
        gt=0,
        description="Adapter polling frequency in Hz",
    )
    gap_threshold_seconds: float = Field(
        default=10.0,
        gt=0,
        description="Emit DataGapEvent if gap exceeds this (seconds)",
    )
    tick_store_window: int = Field(
        default=3000,
        gt=0,
        description="In-memory tick buffer size per market",
    )
    reconnect: ReconnectConfig = Field(default_factory=ReconnectConfig)


# ---------------------------------------------------------------------------
# Event Persistence
# ---------------------------------------------------------------------------


class EventPersistenceConfig(BaseModel):
    """Event sink and tick storage persistence settings.

    Per observability.mdc §1: Events are append-only and persisted.
    """

    model_config = ConfigDict(frozen=True)

    event_batch_size: int = Field(
        default=100,
        gt=0,
        description="Events per batch write",
    )
    event_flush_interval_s: float = Field(
        default=1.0,
        gt=0,
        description="Event flush interval (seconds)",
    )
    event_max_buffer_size: int = Field(
        default=10000,
        gt=0,
        description="Maximum in-memory event buffer size",
    )
    tick_batch_size: int = Field(
        default=1000,
        gt=0,
        description="Ticks per batch write",
    )
    tick_flush_interval_s: float = Field(
        default=1.0,
        gt=0,
        description="Tick flush interval (seconds)",
    )
    failure_threshold: int = Field(
        default=10,
        gt=0,
        description="Consecutive failures before sink circuit break",
    )
    cooldown_seconds: float = Field(
        default=300.0,
        gt=0,
        description="Cooldown after sink circuit break (seconds)",
    )


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


class ReconciliationConfig(BaseModel):
    """Reconciliation intervals.

    Per flows.mdc §12: Continuous reconciliation against venue truth.
    """

    model_config = ConfigDict(frozen=True)

    interval_s: float = Field(
        default=60.0,
        gt=0,
        description="Run reconciliation every N seconds",
    )
    position_sync_interval_s: float = Field(
        default=60.0,
        gt=0,
        description="Sync positions with venue every N seconds",
    )


# ---------------------------------------------------------------------------
# Supervisor & Startup
# ---------------------------------------------------------------------------


class SupervisorConfig(BaseModel):
    """Supervisor timing and startup settings.

    Per flows.mdc §2: Boot and safety gating.
    """

    model_config = ConfigDict(frozen=True)

    startup_timeout_s: float = Field(
        default=30.0,
        gt=0,
        description="Maximum time to start all services (seconds)",
    )
    poll_interval_s: float = Field(
        default=1.0,
        gt=0,
        description="Main supervisor poll interval (seconds)",
    )
    control_plane_poll_interval_s: float = Field(
        default=1.0,
        gt=0,
        description="Control plane command polling interval (seconds)",
    )
    market_monitor_interval_s: float = Field(
        default=1.0,
        gt=0,
        description="Market supervisor monitor interval (seconds)",
    )
    market_retry_delay_s: float = Field(
        default=5.0,
        gt=0,
        description="Delay before retrying failed market supervision (seconds)",
    )


# ---------------------------------------------------------------------------
# Performance & Evidence
# ---------------------------------------------------------------------------


class PerformanceConfig(BaseModel):
    """Performance tracking and evidence tier settings.

    Per performance.mdc §2: Evidence before ranking.
    """

    model_config = ConfigDict(frozen=True)

    min_trades_threshold: int = Field(
        default=1,
        ge=0,
        description="Minimum trades for TRACKING evidence tier",
    )
    default_query_limit: int = Field(
        default=200,
        gt=0,
        description="Default query result limit",
    )
    max_query_limit: int = Field(
        default=1000,
        gt=0,
        description="Maximum query result limit",
    )


# ---------------------------------------------------------------------------
# Market Discovery
# ---------------------------------------------------------------------------


class MarketDiscoveryConfig(BaseModel):
    """Market discovery window settings."""

    model_config = ConfigDict(frozen=True)

    max_windows_ahead: int = Field(
        default=48,
        gt=0,
        description="Maximum windows ahead (e.g. 48 = 12h for 15-min markets)",
    )
    max_windows_behind: int = Field(
        default=4,
        gt=0,
        description="Maximum windows behind (e.g. 4 = 1h for 15-min markets)",
    )


# ---------------------------------------------------------------------------
# Database Health Monitoring
# ---------------------------------------------------------------------------


class DatabaseHealthConfig(BaseModel):
    """Database health monitoring thresholds."""

    model_config = ConfigDict(frozen=True)

    write_latency_threshold_ms: float = Field(
        default=100.0,
        gt=0,
        description="Write latency threshold (milliseconds)",
    )
    read_latency_threshold_ms: float = Field(
        default=50.0,
        gt=0,
        description="Read latency threshold (milliseconds)",
    )


# ---------------------------------------------------------------------------
# Root Platform Config
# ---------------------------------------------------------------------------


class PlatformConfig(BaseModel):
    """Root platform configuration.

    Validated atomically on load. Frozen after construction.
    All defaults match current hardcoded values across the codebase exactly.

    Per trading.mdc §7: Config must be validated, versioned, and auditable.
    Per observability.mdc §1: Config hash emitted as ConfigLoadedEvent.

    Secrets (PRIVATE_KEY, DB_PASSWORD) are NOT part of this model.
    """

    model_config = ConfigDict(frozen=True)

    version: str = Field(
        default="1.0",
        description="Config schema version for audit trail",
    )

    venue: VenueConfig = Field(default_factory=VenueConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    database: DatabasePoolConfig = Field(default_factory=DatabasePoolConfig)
    metrics: PlatformMetricsConfig = Field(default_factory=PlatformMetricsConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    health_gates: HealthGatesConfig = Field(default_factory=HealthGatesConfig)
    circuit_breakers: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    portfolio: PortfolioConfig = Field(default_factory=PortfolioConfig)
    market_data: MarketDataConfig = Field(default_factory=MarketDataConfig)
    event_persistence: EventPersistenceConfig = Field(default_factory=EventPersistenceConfig)
    reconciliation: ReconciliationConfig = Field(default_factory=ReconciliationConfig)
    supervisor: SupervisorConfig = Field(default_factory=SupervisorConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    market_discovery: MarketDiscoveryConfig = Field(default_factory=MarketDiscoveryConfig)
    database_health: DatabaseHealthConfig = Field(default_factory=DatabaseHealthConfig)
