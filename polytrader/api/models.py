"""Pydantic models for control API request/response types.

All endpoints return Pydantic models (not dicts) to enable:
- Type safety in Python
- Automatic validation
- OpenAPI spec generation
- TypeScript client generation (future)
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, computed_field, model_validator

# ============================================================================
# Health & Status Models
# ============================================================================


class HealthGateStatus(BaseModel):
    """Individual health gate status."""

    status: Literal["ok", "degraded", "down"] = Field(
        description="Gate status: ok, degraded, or down"
    )
    message: str | None = Field(default=None, description="Optional status message")


class HealthGates(BaseModel):
    """All health gates status."""

    db: HealthGateStatus = Field(description="Database connectivity")
    market_data_freshness: HealthGateStatus = Field(description="Market data staleness check")
    event_bus_lag: HealthGateStatus = Field(description="Event bus processing lag")
    venue_connectivity: HealthGateStatus = Field(description="Venue API connectivity")
    risk_engine: HealthGateStatus = Field(description="Risk engine health")
    clock_skew_ms: int = Field(description="Clock skew in milliseconds")


class HealthResponse(BaseModel):
    """System health response with gates."""

    overall: Literal["ok", "degraded", "down"] = Field(
        description="Overall status (worst gate status)"
    )
    gates: HealthGates = Field(description="Individual gate statuses")


# ============================================================================
# Execution Control Models
# ============================================================================


class ExecutionStateResponse(BaseModel):
    """Execution control state response."""

    execution_enabled: bool = Field(description="Whether execution is enabled")
    version: int = Field(description="Version for optimistic concurrency")
    updated_at: datetime = Field(description="Last update timestamp")
    updated_by: str = Field(description="User/system that made the update")
    reason: str = Field(description="Reason for the update")


# ============================================================================
# Strategy Models
# ============================================================================


# StrategyLifecycleState is imported from polytrader.strategies.lifecycle_models
# For API models, we use a Literal type alias for OpenAPI generation
StrategyLifecycleState = Literal[
    "STOPPED", "STARTING", "RUNNING", "PAUSED", "DRAINING", "STOPPING", "ERROR"
]


class VersionSelectorRequest(BaseModel):
    """Version selector request model.

    Per Commit 14: VersionSelectorRequest allows clients to specify
    either an exact version or a channel selector for strategy templates.

    Attributes:
        exact: Exact version string (e.g., "1.2.3") or None
        channel: Channel name ("stable", "beta", "dev") or None
        major: Major version number for channel selection (e.g., 1) or None
    """

    exact: str | None = Field(default=None, description="Exact version string (e.g., '1.2.3')")
    channel: Literal["stable", "beta", "dev"] | None = Field(
        default=None, description="Channel name for version selection"
    )
    major: int | None = Field(
        default=None, description="Major version number for channel selection"
    )

    @model_validator(mode="after")
    def validate_selector(self) -> "VersionSelectorRequest":
        """Validate that selector has exactly one of exact or channel."""
        if self.exact is None and self.channel is None:
            raise ValueError("VersionSelectorRequest must have either 'exact' or 'channel'")

        if self.exact is not None and self.channel is not None:
            raise ValueError("VersionSelectorRequest cannot have both 'exact' and 'channel'")

        if self.major is not None and self.channel is None:
            raise ValueError("'major' can only be specified with 'channel'")

        return self


class RunIdentityResponse(BaseModel):
    """Reproducibility metadata response.

    Per Commit 14: RunIdentityResponse exposes reproducibility metadata
    for strategy instances, enabling deterministic replay.

    Attributes:
        template_code_ref: Git SHA / build artifact digest of template code
        config_hash: SHA256 hash of config (for reproducibility)
        dependency_set: Versions of key libs / model artifacts
        market_data_snapshot_ref: Market data stream ID / snapshot reference
    """

    template_code_ref: str | None = Field(
        default=None, description="Git SHA / build artifact digest of template code"
    )
    config_hash: str = Field(description="SHA256 hash of config (for reproducibility)")
    dependency_set: dict[str, str] | None = Field(
        default=None, description="Versions of key libs / model artifacts"
    )
    market_data_snapshot_ref: str | None = Field(
        default=None, description="Market data stream ID / snapshot reference"
    )


class StrategyTypeResponse(BaseModel):
    """Strategy template type response.

    Per Commit 14: StrategyTypeResponse exposes strategy template information
    for discovery and selection.

    Attributes:
        type_id: Template type identifier (e.g., 'simple_threshold')
        name: Human-readable template name
        description: Template description
        available_versions: List of available versions
        parameter_schema: OpenAPI-compatible parameter schema
    """

    type_id: str = Field(description="Template type identifier (e.g., 'simple_threshold')")
    name: str = Field(description="Human-readable template name")
    description: str = Field(description="Template description")
    available_versions: list[str] = Field(description="List of available versions")
    parameter_schema: dict = Field(description="OpenAPI-compatible parameter schema")


class StrategyTypesResponse(BaseModel):
    """List of strategy types response."""

    types: list[StrategyTypeResponse] = Field(description="List of strategy templates")


class StrategyResponse(BaseModel):
    """Strategy registry entry response.

    Per Commit 14: StrategyResponse includes all new fields for template
    reference, lifecycle state, and reproducibility metadata.
    """

    strategy_id: str = Field(description="Strategy identifier")
    name: str = Field(description="Human-readable strategy name")
    description: str | None = Field(default=None, description="Strategy description")
    config: dict = Field(description="Strategy configuration (JSONB)")

    # Template Reference
    template_type_id: str = Field(description="Template type identifier (e.g., 'simple_threshold')")
    template_version: str = Field(description="Resolved template version (e.g., '1.0.0')")

    # Lifecycle State (replaces enabled boolean)
    desired_state: StrategyLifecycleState = Field(
        description="Desired lifecycle state (STOPPED | STARTING | RUNNING | etc.)"
    )
    actual_state: StrategyLifecycleState = Field(
        description="Actual runtime state (STOPPED | STARTING | RUNNING | etc.)"
    )
    last_transition_at: datetime | None = Field(
        default=None, description="Timestamp of last state change"
    )
    last_error: str | None = Field(default=None, description="Last error message (if ERROR state)")

    # Reproducibility Metadata
    run_identity: RunIdentityResponse | None = Field(
        default=None, description="Reproducibility metadata"
    )

    # Deployment Tracking
    deployment_id: str | None = Field(
        default=None, description="UUID for each activation (correlates logs/metrics/events)"
    )
    run_id: str | None = Field(default=None, description="Process run_id when strategy is active")

    # Timestamps
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")

    # Backward compatibility: enabled field derived from desired_state
    @computed_field
    def enabled(self) -> bool:
        """Whether strategy is enabled (derived from desired_state == RUNNING)."""
        return self.desired_state == "RUNNING"


class StrategiesResponse(BaseModel):
    """List of strategies response."""

    strategies: list[StrategyResponse] = Field(description="List of strategies")


class LiveStrategiesResponse(BaseModel):
    """Active live strategies response."""

    active_strategies: list[str] = Field(description="List of active strategy IDs")


class StrategySignalItem(BaseModel):
    """Single signal record for strategy-scoped signals API.

    Mirrors SignalEvent fields (event_id, ts_wall, market, scores).
    """

    event_id: str = Field(description="Event identifier (UUID)")
    ts_wall: datetime = Field(description="Wall-clock time (UTC, ISO 8601)")
    market_slug: str = Field(description="Market identifier")
    outcome: str = Field(description="Outcome: UP or DOWN")
    p_up: float = Field(ge=0.0, le=1.0, description="Probability UP wins")
    p_down: float = Field(ge=0.0, le=1.0, description="Probability DOWN wins")
    edge: float = Field(description="Edge/confidence score")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence level")
    model_id: str = Field(description="Strategy/model identifier")
    model_version: str = Field(description="Model version")
    snapshot_hash: str | None = Field(default=None, description="Input snapshot hash")
    rationale: str | None = Field(default=None, description="Human-readable rationale")


class StrategySignalsResponse(BaseModel):
    """Paginated list of signals for a strategy."""

    items: list[StrategySignalItem] = Field(description="Signal records (newest first)")
    next_cursor: str | None = Field(
        default=None,
        description="Opaque cursor for next page; absent if no more",
    )


class StrategyOrderItem(BaseModel):
    """Single order record for strategy-scoped orders API.

    Mirrors OrderCreatedEvent + intent (order_id, ts_wall, market, side, size, status).
    execution_mode indicates paper vs live so UI can show Paper/Live badge.
    """

    order_id: str = Field(description="Internal order UUID")
    client_order_id: str = Field(description="Idempotency key")
    ts_wall: datetime = Field(description="Wall-clock time (UTC, ISO 8601)")
    market_slug: str = Field(description="Market identifier")
    side: str = Field(description="Trade side: BUY or SELL")
    size: float = Field(gt=0, description="Order size in USD")
    limit_price: float = Field(gt=0, le=1, description="Limit price (0-1 range)")
    status: str = Field(description="Order status (e.g. PENDING_SUBMIT, LIVE, FILLED, REJECTED)")
    execution_mode: Literal["paper", "live"] = Field(
        description="Paper or live execution; UI shows Paper/Live badge"
    )


class StrategyOrdersResponse(BaseModel):
    """Paginated list of orders for a strategy."""

    items: list[StrategyOrderItem] = Field(description="Order records (newest first)")
    next_cursor: str | None = Field(
        default=None,
        description="Opaque cursor for next page; absent if no more",
    )


# ============================================================================
# Past Performance Models (StrategyClosedTradeEvent read path)
# ============================================================================


class ClosedTradeItem(BaseModel):
    """Single closed trade for strategy performance API.

    Per proposal-past-performance-tab: One row per StrategyClosedTradeEvent.
    entry_time/exit_time are monotonic timestamps; exit_ts_wall is wall-clock for display.
    """

    market_slug: str = Field(description="Market identifier")
    outcome: Literal["UP", "DOWN"] = Field(description="Outcome traded")
    entry_time: float = Field(description="Entry time (monotonic)")
    exit_time: float = Field(description="Exit time (monotonic)")
    exit_ts_wall: datetime = Field(description="Exit wall-clock time (UTC)")
    entry_price: float = Field(gt=0, le=1, description="Average entry price")
    exit_price: float = Field(
        ge=0, le=1,
        description="Exit fill/settlement price (0 allowed for binary settlement)",
    )
    size: float = Field(gt=0, description="Position size in USD")
    pnl: float = Field(description="Realized P&L in USD")
    pnl_pct: float = Field(description="Realized P&L as percentage")
    result: Literal["WIN", "LOSS", "BREAKEVEN"] = Field(
        description="WIN if pnl > 0, LOSS if pnl < 0, BREAKEVEN if pnl == 0"
    )
    execution_mode: Literal["paper", "live"] = Field(description="Paper or live execution")
    duration_seconds: float = Field(
        ge=0,
        description="Trade duration (exit_time - entry_time) in seconds",
    )


class PerformanceSummary(BaseModel):
    """Aggregate performance metrics for the returned closed trades.

    Computed from the items in this response (page-scoped).
    When items are empty, total_trades=0, total_realized_pnl=0, win_rate_pct=None.
    """

    total_realized_pnl: float = Field(description="Sum of P&L over returned trades (USD)")
    total_trades: int = Field(ge=0, description="Number of trades in this page")
    win_rate_pct: float | None = Field(
        default=None,
        description="Percentage of WIN results (0-100); None if no trades",
    )
    current_drawdown: float | None = Field(
        default=None,
        description="Current drawdown (Phase 2: from equity curve)",
    )
    max_drawdown: float | None = Field(
        default=None,
        description="Max drawdown (Phase 2: from equity curve)",
    )


class PerformanceResponse(BaseModel):
    """Past performance for a strategy: summary + paginated closed trades."""

    summary: PerformanceSummary = Field(description="Aggregates over returned items")
    items: list[ClosedTradeItem] = Field(
        description="Closed trades (newest first)",
        default_factory=list,
    )
    next_cursor: str | None = Field(
        default=None,
        description="Opaque cursor for next page; absent if no more",
    )


# ============================================================================
# Command Models
# ============================================================================


class CommandEnvelopeResponse(BaseModel):
    """Command envelope response (standardized for all commands)."""

    command_id: str = Field(description="Command identifier (UUID)")
    status: Literal["pending", "applied", "failed"] = Field(description="Command status")
    submitted_at: datetime = Field(description="Command submission timestamp")
    links: dict[str, str] = Field(description="Related resource links", default_factory=dict)


class CommandStatusResponse(BaseModel):
    """Command status response."""

    command_id: str = Field(description="Command identifier (UUID)")
    type: Literal[
        "enable_execution",
        "disable_execution",
        "add_active_strategy",
        "remove_active_strategy",
    ] = Field(description="Command type")
    status: Literal["pending", "applied", "failed"] = Field(description="Command status")
    error_message: str | None = Field(default=None, description="Error message if failed")
    created_at: datetime = Field(description="Command creation timestamp")
    applied_at: datetime | None = Field(
        default=None, description="Timestamp when command was applied"
    )
    reason: str = Field(description="Reason for the command")
    issued_by: str = Field(description="User/system that issued the command")


# ============================================================================
# Request Models
# ============================================================================


class EnableExecutionRequest(BaseModel):
    """Request to enable execution."""

    expected_version: int | None = Field(
        default=None,
        description="Expected version for optimistic concurrency control",
    )
    reason: str = Field(description="Reason for enabling execution")
    issued_by: str = Field(description="User/system issuing the command")
    client_request_id: str = Field(description="Client request ID for idempotency")


class DisableExecutionRequest(BaseModel):
    """Request to disable execution."""

    expected_version: int | None = Field(
        default=None,
        description="Expected version for optimistic concurrency control",
    )
    reason: str = Field(description="Reason for disabling execution")
    issued_by: str = Field(description="User/system issuing the command")
    client_request_id: str = Field(description="Client request ID for idempotency")


class ActivateStrategyRequest(BaseModel):
    """Request to activate strategy for live trading."""

    reason: str = Field(description="Reason for activation")
    issued_by: str = Field(description="User/system issuing the command")
    client_request_id: str = Field(description="Client request ID for idempotency")


class DeactivateStrategyRequest(BaseModel):
    """Request to deactivate strategy for live trading."""

    reason: str = Field(description="Reason for deactivation")
    issued_by: str = Field(description="User/system issuing the command")
    client_request_id: str = Field(description="Client request ID for idempotency")


class CreateStrategyRequest(BaseModel):
    """Request to create a new strategy.

    Per Commit 14: CreateStrategyRequest includes version_selector and
    desired_state instead of enabled boolean.
    """

    strategy_id: str = Field(description="Strategy identifier")
    name: str = Field(description="Human-readable strategy name")
    description: str | None = Field(default=None, description="Strategy description")
    config: dict = Field(description="Strategy configuration (JSONB)")

    # Template Reference
    template_type_id: str = Field(description="Template type identifier (e.g., 'simple_threshold')")
    version_selector: VersionSelectorRequest = Field(
        description="Version selector (exact version or channel)"
    )

    # Lifecycle State (replaces enabled boolean)
    desired_state: StrategyLifecycleState = Field(
        default="STOPPED",
        description="Desired lifecycle state (default: STOPPED)",
    )


class UpdateStrategyRequest(BaseModel):
    """Request to update an existing strategy.

    Per Commit 14: UpdateStrategyRequest includes desired_state instead
    of enabled boolean.
    """

    name: str | None = Field(default=None, description="Strategy name")
    description: str | None = Field(default=None, description="Strategy description")
    config: dict | None = Field(default=None, description="Strategy configuration")
    desired_state: StrategyLifecycleState | None = Field(
        default=None, description="Desired lifecycle state"
    )


class ValidateStrategyConfigRequest(BaseModel):
    """Request to validate a strategy configuration.

    Per Commit 16: ValidateStrategyConfigRequest allows clients to validate
    configurations before creating strategy instances.

    Attributes:
        template_type_id: Template type identifier (e.g., 'simple_threshold')
        version_selector: Version selector (exact version or channel)
        config: Configuration dictionary to validate
    """

    template_type_id: str = Field(description="Template type identifier (e.g., 'simple_threshold')")
    version_selector: VersionSelectorRequest = Field(
        description="Version selector (exact version or channel)"
    )
    config: dict = Field(description="Strategy configuration to validate")


class ValidateStrategyConfigResponse(BaseModel):
    """Response from strategy configuration validation.

    Per Commit 16: ValidateStrategyConfigResponse provides validation results
    with clear error messages and warnings.

    Attributes:
        valid: Whether the configuration is valid
        errors: List of validation error messages (empty if valid)
        warnings: List of validation warnings (optional issues)
        template_type_id: Template type identifier used for validation
        template_version: Resolved template version used for validation
    """

    valid: bool = Field(description="Whether the configuration is valid")
    errors: list[str] = Field(default_factory=list, description="List of validation error messages")
    warnings: list[str] = Field(
        default_factory=list, description="List of validation warnings (optional issues)"
    )
    template_type_id: str = Field(description="Template type identifier used for validation")
    template_version: str = Field(description="Resolved template version used for validation")


# ============================================================================
# Error Response Models
# ============================================================================


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(description="Error message")
    detail: str | None = Field(default=None, description="Error details")
    code: str | None = Field(default=None, description="Error code")


class VersionConflictResponse(BaseModel):
    """Version conflict error response (409 Conflict)."""

    error: str = Field(default="Version conflict")
    expected_version: int = Field(description="Version that was expected")
    actual_version: int = Field(description="Current version")
    detail: str = Field(description="Explanation of the version conflict")


# ============================================================================
# Market Data API Models
# ============================================================================


class MarketTickResponse(BaseModel):
    """Market tick response model.

    Represents a single market tick with price data and timestamps.
    Used for both latest tick and historical ticks endpoints.
    """

    tick_id: UUID = Field(description="Unique tick identifier")
    ts_wall: datetime = Field(description="Wall-clock timestamp (UTC)")
    ts_mono: float = Field(description="Monotonic timestamp")
    market_slug: str = Field(description="Market identifier")
    outcome: str = Field(description="Market outcome: UP or DOWN")
    best_bid: Decimal = Field(description="Best bid price (0-1 range)")
    best_ask: Decimal = Field(description="Best ask price (0-1 range)")
    mid: Decimal = Field(description="Mid-market price")
    spread: Decimal = Field(description="Bid-ask spread")
    spread_bps: Decimal = Field(description="Spread in basis points")


class HistoricalTicksResponse(BaseModel):
    """Historical ticks response.

    For a 15-minute market window, all ticks should fit in a single response.
    Use from_ts/to_ts to narrow the time range if needed.
    """

    ticks: list[MarketTickResponse] = Field(description="List of ticks (ordered by ts_wall)")
    count: int = Field(description="Number of ticks returned")


class MarketInfoResponse(BaseModel):
    """Market information response.

    Represents a market/outcome pair with latest tick timestamp, active status,
    and optional market window start/end (derived from slug).
    """

    market_slug: str = Field(description="Market identifier")
    outcome: str = Field(description="Market outcome: UP or DOWN")
    latest_tick_ts: datetime | None = Field(description="Latest tick timestamp (null if no data)")
    active: bool = Field(description="Whether market is currently active (current window)")
    start_date: datetime | None = Field(
        default=None,
        description="Start of the market window (UTC, ISO 8601). Null if slug cannot be parsed.",
    )
    end_date: datetime | None = Field(
        default=None,
        description="End of the market window (UTC, ISO 8601). Null if slug cannot be parsed.",
    )


class MarketsResponse(BaseModel):
    """Markets list response.

    Markets are ordered by latest_tick_ts descending (newest first).
    Markets with null latest_tick_ts appear last.
    """

    markets: list[MarketInfoResponse] = Field(description="List of markets (ordered newest first)")
    count: int = Field(description="Number of markets")
