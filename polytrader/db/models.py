"""SQLAlchemy ORM models for database tables.

This module defines the database schema using SQLAlchemy ORM.
Per architecture.mdc: Database models are separated from business logic.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class EventRecord(Base):
    """SQLAlchemy ORM model for events table.

    This model provides:
    - Type-safe database operations
    - Automatic type conversions (UUID, datetime, JSONB)
    - Clean query interface
    - Integration with Alembic autogenerate

    Per architecture.mdc §G: Event store is append-only.
    Base Event fields are stored as columns for efficient querying.
    Event-specific fields are stored in JSONB column.
    """

    __tablename__ = "events"

    # Primary key with automatic UUID conversion
    event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        comment="Unique event identifier (UUID)",
    )

    # Timestamps with automatic conversion
    ts_wall: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        comment="Wall-clock time in ISO format (UTC)",
    )
    ts_mono: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Monotonic timestamp for ordering",
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Record creation timestamp",
    )

    # Text fields
    correlation_id: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Correlation ID for tracing",
    )
    run_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Process run ID",
    )
    schema_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="1.0",
        comment="Event schema version",
    )
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Event source component",
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Event class name",
    )

    # JSONB with automatic serialization
    event_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Event-specific fields (JSONB)",
    )

    # Table constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "source IN ('mdp', 'strategy', 'portfolio', 'risk', 'oms', 'exec', "
            "'execution', 'posttrade', 'ops', 'adapter')",
            name="events_source_check",
        ),
        CheckConstraint("ts_mono >= 0", name="events_ts_mono_check"),
        # Indexes for common query patterns
        Index("idx_events_ts_mono", "ts_mono"),  # For chronological queries
        Index("idx_events_event_type", "event_type"),  # For type filtering
        Index("idx_events_correlation_id", "correlation_id"),  # For correlation queries
        Index("idx_events_run_id", "run_id"),  # For run-based queries
    )


class MarketTickRecord(Base):
    """SQLAlchemy ORM model for market_ticks table.

    This model provides:
    - Type-safe database operations for market tick time-series data
    - Automatic type conversions (UUID, datetime, NUMERIC)
    - Clean query interface
    - Integration with Alembic autogenerate

    Per proposal: Market ticks are stored in a partitioned table optimized
    for time-series queries. The table is partitioned by ts_wall (daily partitions).

    Note:
        - Primary key includes ts_wall (required for partitioned tables)
        - Computed fields (mid, spread, spread_bps) are stored for query efficiency
        - NUMERIC types used for financial precision (avoid floating-point errors)
    """

    __tablename__ = "market_ticks"

    # Primary key (includes ts_wall for partitioning)
    tick_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        comment="Unique tick identifier (UUID, derived from MarketDataEvent.event_id)",
    )
    ts_wall: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        primary_key=True,
        comment="Wall-clock time in UTC (partitioning key)",
    )

    # Timestamps
    ts_mono: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Monotonic timestamp for ordering",
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Record insertion timestamp",
    )

    # Market identifiers
    market_slug: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Polymarket market identifier",
    )
    outcome: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Market outcome: UP or DOWN",
    )

    # Price data (NUMERIC for financial precision)
    best_bid: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
        comment="Best bid price (0-1 range)",
    )
    best_ask: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
        comment="Best ask price (0-1 range)",
    )

    # Computed fields (stored for query efficiency)
    mid: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
        comment="Mid-market price: (best_bid + best_ask) / 2",
    )
    spread: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
        comment="Bid-ask spread: best_ask - best_bid",
    )
    spread_bps: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        comment="Spread in basis points: spread * 10000",
    )

    # References
    event_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        comment="Reference to events.event_id (nullable)",
    )
    run_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Process run ID for correlation",
    )

    # Table constraints and indexes
    # Note: Indexes are created in migration, not here, because:
    # 1. BRIN indexes require raw SQL
    # 2. Partitioned tables have special index requirements
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('UP', 'DOWN')",
            name="market_ticks_outcome_check",
        ),
        CheckConstraint(
            "best_bid >= 0 AND best_bid <= 1",
            name="market_ticks_best_bid_check",
        ),
        CheckConstraint(
            "best_ask >= 0 AND best_ask <= 1",
            name="market_ticks_best_ask_check",
        ),
        CheckConstraint(
            "ts_mono >= 0",
            name="market_ticks_ts_mono_check",
        ),
    )


class StrategyRecord(Base):
    """SQLAlchemy ORM model for strategy_instances table.

    This model provides:
    - Type-safe database operations for strategy instances
    - Automatic type conversions (JSONB, timestamps, UUIDs)
    - Clean query interface
    - Integration with Alembic autogenerate

    Per STRATEGY_ARCHITECTURE_PROPOSAL.md: Strategy instances are runtime
    configurations of strategy templates with lifecycle state machine and
    reproducibility metadata.
    """

    __tablename__ = "strategy_instances"

    # Primary key
    strategy_id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        comment="Unique strategy instance identifier",
    )

    # Strategy Template Reference
    template_type_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Strategy template type identifier (e.g., 'simple_threshold')",
    )
    template_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Resolved template version (e.g., '1.0.0')",
    )

    # Metadata
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable strategy name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Strategy description",
    )
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Strategy configuration (JSONB, validated against template schema)",
    )
    config_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA256 hash of config (for reproducibility)",
    )

    # Lifecycle State Machine (replaces enabled boolean)
    desired_state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="STOPPED",
        comment=(
            "Desired lifecycle state "
            "(STOPPED | STARTING | RUNNING | PAUSED | DRAINING | STOPPING | ERROR)"
        ),
    )
    actual_state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="STOPPED",
        comment="Actual runtime state (same enum as desired_state)",
    )
    last_transition_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="Timestamp of last state change",
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Last error message (if ERROR state)",
    )

    # Reproducibility Metadata
    template_code_ref: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Git SHA / build artifact digest of template code",
    )
    dependency_set: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Versions of key libs / model artifacts (JSONB)",
    )
    market_data_snapshot_ref: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Market data stream ID / snapshot reference",
    )

    # Deployment Tracking
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        comment="UUID for each activation (correlates logs/metrics/events)",
    )
    run_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Process run_id when strategy is active",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Record creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Record update timestamp",
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            (
                "desired_state IN "
                "('STOPPED', 'STARTING', 'RUNNING', 'PAUSED', 'DRAINING', 'STOPPING', 'ERROR')"
            ),
            name="strategy_instances_desired_state_check",
        ),
        CheckConstraint(
            (
                "actual_state IN "
                "('STOPPED', 'STARTING', 'RUNNING', 'PAUSED', 'DRAINING', 'STOPPING', 'ERROR')"
            ),
            name="strategy_instances_actual_state_check",
        ),
    )


class ExecutionControlRecord(Base):
    """SQLAlchemy ORM model for execution_control table.

    This model provides:
    - Type-safe database operations for execution control (singleton)
    - Optimistic concurrency control via version field
    - Automatic type conversions (timestamps)

    Per Platform_Proposal.md: Execution control is a singleton table
    (id = 1 only) that tracks whether live execution is enabled.
    The version field enables optimistic concurrency control.
    """

    __tablename__ = "execution_control"

    # Singleton primary key (id = 1 only)
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        default=1,
        comment="Singleton ID (always 1)",
    )

    # Execution state
    execution_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="Whether live execution is enabled",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
        comment="Version for optimistic concurrency control",
    )

    # Audit fields
    updated_by: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="User/system that made the update",
    )
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Reason for the update",
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Update timestamp",
    )

    # Table constraints
    __table_args__ = (CheckConstraint("id = 1", name="execution_control_singleton_check"),)


class LiveStrategyActivationRecord(Base):
    """SQLAlchemy ORM model for live_strategy_activation table.

    This model provides:
    - Type-safe database operations for live strategy activation
    - Foreign key relationship to strategies table
    - Automatic type conversions (timestamps)

    Per Platform_Proposal.md: Tracks which strategies are active
    for live trading. Only active strategies can execute live orders.
    """

    __tablename__ = "live_strategy_activation"

    # Primary key (foreign key to strategy_instances)
    strategy_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("strategy_instances.strategy_id", ondelete="CASCADE"),
        primary_key=True,
        comment="Strategy identifier (FK to strategy_instances.strategy_id)",
    )

    # Activation state
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="Whether strategy is active for live trading",
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="Timestamp when strategy was activated",
    )
    activated_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="User/system that activated the strategy",
    )
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Reason for activation",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Record creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Record update timestamp",
    )

    # Table constraints and indexes
    # Note: Partial index (WHERE active = true) will be created in migration
    __table_args__ = (Index("idx_live_strategy_active", "active"),)


class ControlCommandRecord(Base):
    """SQLAlchemy ORM model for control_commands table.

    This model provides:
    - Type-safe database operations for control command queue
    - Idempotency support via client_request_id
    - Optimistic concurrency control via expected_version
    - Automatic type conversions (UUID, timestamps)

    Per Platform_Proposal.md: Control commands queue stores pending
    commands for execution control and strategy activation. Commands
    are processed asynchronously by the control plane service.
    """

    __tablename__ = "control_commands"

    # Primary key
    command_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
        comment="Unique command identifier (UUID)",
    )

    # Command details
    command_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Command type: enable_execution, disable_execution, "
        "add_active_strategy, remove_active_strategy",
    )
    strategy_id: Mapped[str | None] = mapped_column(
        String(100),
        ForeignKey("strategy_instances.strategy_id", ondelete="SET NULL"),
        nullable=True,
        comment="Strategy identifier (nullable for enable/disable commands)",
    )

    # Idempotency and concurrency control
    client_request_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Client request ID for idempotency (nullable)",
    )
    expected_version: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Expected version for optimistic concurrency control",
    )

    # Command metadata
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Reason for the command",
    )
    issued_by: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="User/system that issued the command",
    )

    # Command status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="pending",
        comment="Command status: pending, applied, failed",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if command failed",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Command creation timestamp",
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="Timestamp when command was applied",
    )

    # Table constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "command_type IN ('enable_execution', 'disable_execution', "
            "'add_active_strategy', 'remove_active_strategy')",
            name="control_commands_command_type_check",
        ),
        CheckConstraint(
            "status IN ('pending', 'applied', 'failed')",
            name="control_commands_status_check",
        ),
        Index("idx_control_commands_pending", "status"),
        # Note: Unique index for idempotency will be created in migration
        # with COALESCE for NULL strategy_id and WHERE clause for client_request_id
    )
