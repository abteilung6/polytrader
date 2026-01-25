"""add_strategy_lifecycle_and_metadata

Revision ID: d156ab13dab9
Revises: 669d44032370
Create Date: 2026-01-25 18:21:00.000000

Per STRATEGY_ARCHITECTURE_PROPOSAL.md: Add strategy lifecycle state machine
and reproducibility metadata. Replace 'enabled' boolean with state machine.
Rename table from 'strategies' to 'strategy_instances'.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d156ab13dab9"
down_revision: str | None = "669d44032370"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: Drop old strategies table, create new strategy_instances table."""
    # Drop foreign key constraints that reference the old table
    op.drop_constraint(
        "control_commands_strategy_id_fkey",
        "control_commands",
        type_="foreignkey",
    )
    op.drop_constraint(
        "live_strategy_activation_strategy_id_fkey",
        "live_strategy_activation",
        type_="foreignkey",
    )

    # Clear strategy_id references in control_commands (since we're dropping the table)
    op.execute("UPDATE control_commands SET strategy_id = NULL WHERE strategy_id IS NOT NULL")

    # Delete all rows from live_strategy_activation (since we're dropping the strategies table)
    op.execute("DELETE FROM live_strategy_activation")

    # Drop the old strategies table
    op.drop_table("strategies")

    # Create new strategy_instances table
    op.create_table(
        "strategy_instances",
        sa.Column(
            "strategy_id",
            sa.String(length=100),
            nullable=False,
            comment="Unique strategy instance identifier",
        ),
        sa.Column(
            "template_type_id",
            sa.String(length=100),
            nullable=False,
            comment="Strategy template type identifier (e.g., 'simple_threshold')",
        ),
        sa.Column(
            "template_version",
            sa.String(length=50),
            nullable=False,
            comment="Resolved template version (e.g., '1.0.0')",
        ),
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
            comment="Human-readable strategy name",
        ),
        sa.Column("description", sa.Text(), nullable=True, comment="Strategy description"),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Strategy configuration (JSONB, validated against template schema)",
        ),
        sa.Column(
            "config_hash",
            sa.String(length=64),
            nullable=False,
            comment="SHA256 hash of config (for reproducibility)",
        ),
        sa.Column(
            "desired_state",
            sa.String(length=20),
            nullable=False,
            server_default="STOPPED",
            comment=(
                "Desired lifecycle state "
                "(STOPPED | STARTING | RUNNING | PAUSED | DRAINING | STOPPING | ERROR)"
            ),
        ),
        sa.Column(
            "actual_state",
            sa.String(length=20),
            nullable=False,
            server_default="STOPPED",
            comment="Actual runtime state (same enum as desired_state)",
        ),
        sa.Column(
            "last_transition_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Timestamp of last state change",
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
            comment="Last error message (if ERROR state)",
        ),
        sa.Column(
            "template_code_ref",
            sa.String(length=100),
            nullable=True,
            comment="Git SHA / build artifact digest of template code",
        ),
        sa.Column(
            "dependency_set",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Versions of key libs / model artifacts (JSONB)",
        ),
        sa.Column(
            "market_data_snapshot_ref",
            sa.String(length=255),
            nullable=True,
            comment="Market data stream ID / snapshot reference",
        ),
        sa.Column(
            "deployment_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="UUID for each activation (correlates logs/metrics/events)",
        ),
        sa.Column(
            "run_id",
            sa.String(length=100),
            nullable=True,
            comment="Process run_id when strategy is active",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Record creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Record update timestamp",
        ),
        sa.PrimaryKeyConstraint("strategy_id"),
        sa.CheckConstraint(
            (
                "desired_state IN "
                "('STOPPED', 'STARTING', 'RUNNING', 'PAUSED', 'DRAINING', 'STOPPING', 'ERROR')"
            ),
            name="strategy_instances_desired_state_check",
        ),
        sa.CheckConstraint(
            (
                "actual_state IN "
                "('STOPPED', 'STARTING', 'RUNNING', 'PAUSED', 'DRAINING', 'STOPPING', 'ERROR')"
            ),
            name="strategy_instances_actual_state_check",
        ),
    )

    # Recreate foreign key constraints pointing to new table
    op.create_foreign_key(
        "control_commands_strategy_id_fkey",
        "control_commands",
        "strategy_instances",
        ["strategy_id"],
        ["strategy_id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "live_strategy_activation_strategy_id_fkey",
        "live_strategy_activation",
        "strategy_instances",
        ["strategy_id"],
        ["strategy_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Downgrade schema: Drop strategy_instances table, recreate old strategies table."""
    # Drop foreign key constraints
    op.drop_constraint(
        "control_commands_strategy_id_fkey",
        "control_commands",
        type_="foreignkey",
    )
    op.drop_constraint(
        "live_strategy_activation_strategy_id_fkey",
        "live_strategy_activation",
        type_="foreignkey",
    )

    # Drop new table
    op.drop_table("strategy_instances")

    # Recreate old strategies table
    op.create_table(
        "strategies",
        sa.Column(
            "strategy_id",
            sa.String(length=100),
            nullable=False,
            comment="Unique strategy identifier",
        ),
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
            comment="Human-readable strategy name",
        ),
        sa.Column("description", sa.Text(), nullable=True, comment="Strategy description"),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Strategy configuration (JSONB)",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default="true",
            nullable=False,
            comment="Whether strategy is enabled",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Record creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Record update timestamp",
        ),
        sa.PrimaryKeyConstraint("strategy_id"),
    )

    # Recreate foreign key constraints pointing to old table
    op.create_foreign_key(
        "control_commands_strategy_id_fkey",
        "control_commands",
        "strategies",
        ["strategy_id"],
        ["strategy_id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "live_strategy_activation_strategy_id_fkey",
        "live_strategy_activation",
        "strategies",
        ["strategy_id"],
        ["strategy_id"],
        ondelete="CASCADE",
    )
