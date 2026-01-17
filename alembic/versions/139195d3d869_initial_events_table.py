"""initial_events_table

Revision ID: 139195d3d869
Revises:
Create Date: 2025-01-15 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "139195d3d869"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create initial events table.

    This migration creates the events table with:
    - Base Event fields as columns (event_id, ts_wall, ts_mono, etc.)
    - Event-specific fields in JSONB column
    - Constraints (source check, ts_mono check)
    """
    # Create events table
    op.execute("""
        CREATE TABLE IF NOT EXISTS events (
            -- Base Event fields (from Event base class)
            event_id UUID PRIMARY KEY,
            ts_wall TIMESTAMPTZ NOT NULL,
            ts_mono DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,

            -- Correlation and context
            correlation_id TEXT,
            run_id TEXT NOT NULL,
            schema_version TEXT NOT NULL DEFAULT '1.0',

            -- Event metadata
            source TEXT NOT NULL,
            event_type TEXT NOT NULL,

            -- Event-specific fields (JSONB)
            event_data JSONB NOT NULL,

            -- Constraints
            CONSTRAINT events_source_check CHECK (
                source IN (
                    'mdp', 'strategy', 'portfolio', 'risk', 'oms', 'exec',
                    'execution', 'posttrade', 'ops', 'adapter'
                )
            ),
            CONSTRAINT events_ts_mono_check CHECK (ts_mono >= 0)
        )
    """)


def downgrade() -> None:
    """Drop events table."""
    op.execute("DROP TABLE IF EXISTS events")
