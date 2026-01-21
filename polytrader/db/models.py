"""SQLAlchemy ORM models for database tables.

This module defines the database schema using SQLAlchemy ORM.
Per architecture.mdc: Database models are separated from business logic.
"""

from datetime import datetime
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


class StrategyRecord(Base):
    """Strategy registry table.

    Stores strategy definitions and configuration for platform control.
    """

    __tablename__ = "strategies"

    strategy_id: Mapped[str] = mapped_column(
        String(200),
        primary_key=True,
        comment="Strategy identifier",
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="Strategy name")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Strategy configuration (JSONB)",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
        comment="Whether strategy is enabled",
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("idx_strategies_enabled", "enabled"),)


class PlatformStateRecord(Base):
    """Singleton table for platform state (active strategy, execution flag)."""

    __tablename__ = "platform_state"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="Singleton row id (use 1)",
    )
    active_strategy_id: Mapped[str | None] = mapped_column(
        String(200),
        ForeignKey("strategies.strategy_id", ondelete="SET NULL"),
        nullable=True,
        comment="Active strategy for live trading",
    )
    execution_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="Whether live execution is enabled",
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Last updater (operator/system)",
    )
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Reason for last update",
    )


class ControlCommandRecord(Base):
    """Control commands table for runtime operations."""

    __tablename__ = "control_commands"

    command_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        comment="Control command identifier",
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    command_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Command type (enable_execution, disable_execution, select_live_strategy)",
    )
    strategy_id: Mapped[str | None] = mapped_column(
        String(200),
        ForeignKey("strategies.strategy_id", ondelete="SET NULL"),
        nullable=True,
        comment="Strategy identifier (optional)",
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Issuer (operator/system)",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="pending",
        comment="pending/applied/failed",
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="Applied timestamp",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Failure reason (if failed)",
    )

    __table_args__ = (
        Index("idx_control_commands_status", "status"),
        Index("idx_control_commands_created_at", "created_at"),
    )
