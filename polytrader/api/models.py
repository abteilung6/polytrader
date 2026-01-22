"""Pydantic models for control API request/response types.

All endpoints return Pydantic models (not dicts) to enable:
- Type safety in Python
- Automatic validation
- OpenAPI spec generation
- TypeScript client generation (future)
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

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


class StrategyResponse(BaseModel):
    """Strategy registry entry response."""

    strategy_id: str = Field(description="Strategy identifier")
    name: str = Field(description="Human-readable strategy name")
    description: str | None = Field(default=None, description="Strategy description")
    config: dict = Field(description="Strategy configuration (JSONB)")
    enabled: bool = Field(description="Whether strategy is enabled")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class StrategiesResponse(BaseModel):
    """List of strategies response."""

    strategies: list[StrategyResponse] = Field(description="List of strategies")


class LiveStrategiesResponse(BaseModel):
    """Active live strategies response."""

    active_strategies: list[str] = Field(description="List of active strategy IDs")


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
    """Request to create a new strategy."""

    strategy_id: str = Field(description="Strategy identifier")
    name: str = Field(description="Human-readable strategy name")
    description: str | None = Field(default=None, description="Strategy description")
    config: dict = Field(description="Strategy configuration (JSONB)")
    enabled: bool = Field(default=True, description="Whether strategy is enabled")


class UpdateStrategyRequest(BaseModel):
    """Request to update an existing strategy."""

    name: str | None = Field(default=None, description="Strategy name")
    description: str | None = Field(default=None, description="Strategy description")
    config: dict | None = Field(default=None, description="Strategy configuration")
    enabled: bool | None = Field(default=None, description="Whether strategy is enabled")


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
