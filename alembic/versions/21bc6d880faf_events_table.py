"""initial_events_table

Revision ID: 21bc6d880faf
Revises:
Create Date: 2026-01-17 18:47:42.690305

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "21bc6d880faf"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create initial events table.

    This migration creates the events table with:
    - Base Event fields as columns (event_id, ts_wall, ts_mono, etc.)
    - Event-specific fields in JSONB column
    - Constraints (source check, ts_mono check)
    - Indexes for common query patterns
    """
    # Create events table
    op.create_table(
        "events",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            comment="Unique event identifier (UUID)",
        ),
        sa.Column(
            "ts_wall",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            comment="Wall-clock time in ISO format (UTC)",
        ),
        sa.Column(
            "ts_mono",
            sa.DOUBLE_PRECISION(),
            nullable=False,
            comment="Monotonic timestamp for ordering",
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Record creation timestamp",
        ),
        sa.Column(
            "correlation_id",
            sa.Text(),
            nullable=True,
            comment="Correlation ID for tracing",
        ),
        sa.Column(
            "run_id",
            sa.Text(),
            nullable=False,
            comment="Process run ID",
        ),
        sa.Column(
            "schema_version",
            sa.String(length=50),
            nullable=False,
            server_default="1.0",
            comment="Event schema version",
        ),
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            comment="Event source component",
        ),
        sa.Column(
            "event_type",
            sa.String(length=100),
            nullable=False,
            comment="Event class name",
        ),
        sa.Column(
            "event_data",
            postgresql.JSONB(),
            nullable=False,
            comment="Event-specific fields (JSONB)",
        ),
        sa.CheckConstraint(
            "source IN ('mdp', 'strategy', 'portfolio', 'risk', 'oms', 'exec', "
            "'execution', 'posttrade', 'ops', 'adapter')",
            name="events_source_check",
        ),
        sa.CheckConstraint("ts_mono >= 0", name="events_ts_mono_check"),
    )

    # Create indexes for common query patterns
    op.create_index("idx_events_ts_mono", "events", ["ts_mono"], unique=False)
    op.create_index("idx_events_event_type", "events", ["event_type"], unique=False)
    op.create_index("idx_events_correlation_id", "events", ["correlation_id"], unique=False)
    op.create_index("idx_events_run_id", "events", ["run_id"], unique=False)


def downgrade() -> None:
    """Drop events table."""
    op.drop_index("idx_events_run_id", table_name="events")
    op.drop_index("idx_events_correlation_id", table_name="events")
    op.drop_index("idx_events_event_type", table_name="events")
    op.drop_index("idx_events_ts_mono", table_name="events")
    op.drop_table("events")
