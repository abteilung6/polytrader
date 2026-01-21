"""platform_control_tables

Revision ID: 7f2c5d3b1e9a
Revises: 21bc6d880faf
Create Date: 2026-01-21 20:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f2c5d3b1e9a"
down_revision: str | Sequence[str] | None = "21bc6d880faf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create platform control tables."""
    op.create_table(
        "strategies",
        sa.Column("strategy_id", sa.String(length=200), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_strategies_enabled", "strategies", ["enabled"], unique=False)

    op.create_table(
        "platform_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "active_strategy_id",
            sa.String(length=200),
            sa.ForeignKey("strategies.strategy_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "execution_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_by", sa.String(length=100), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
    )

    op.create_table(
        "control_commands",
        sa.Column("command_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("command_type", sa.String(length=50), nullable=False),
        sa.Column(
            "strategy_id",
            sa.String(length=200),
            sa.ForeignKey("strategies.strategy_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("issued_by", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("applied_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("idx_control_commands_status", "control_commands", ["status"], unique=False)
    op.create_index(
        "idx_control_commands_created_at", "control_commands", ["created_at"], unique=False
    )

    # Initialize singleton platform_state row
    op.execute("INSERT INTO platform_state (id, execution_enabled) VALUES (1, false)")


def downgrade() -> None:
    """Drop platform control tables."""
    op.drop_index("idx_control_commands_created_at", table_name="control_commands")
    op.drop_index("idx_control_commands_status", table_name="control_commands")
    op.drop_table("control_commands")

    op.drop_table("platform_state")

    op.drop_index("idx_strategies_enabled", table_name="strategies")
    op.drop_table("strategies")
