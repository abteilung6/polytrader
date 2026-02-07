"""add strategy_closed_trades table

Revision ID: a065833f01c0
Revises: d156ab13dab9
Create Date: 2026-02-07 17:21:46.529113

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a065833f01c0"
down_revision: str | Sequence[str] | None = "d156ab13dab9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "strategy_closed_trades",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            comment="Unique row identifier (UUID)",
        ),
        sa.Column(
            "event_id",
            sa.UUID(),
            nullable=False,
            comment="Reference to events.event_id (dedup key)",
        ),
        sa.Column(
            "strategy_id",
            sa.String(length=100),
            nullable=False,
            comment="FK-like ref to strategy_instances.strategy_id",
        ),
        sa.Column("execution_mode", sa.String(length=10), nullable=False, comment="paper or live"),
        sa.Column(
            "exit_ts_wall",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            comment="Wall-clock exit time (UTC) — primary windowing column",
        ),
        sa.Column("entry_time", sa.Float(), nullable=False, comment="Monotonic entry timestamp"),
        sa.Column("exit_time", sa.Float(), nullable=False, comment="Monotonic exit timestamp"),
        sa.Column(
            "pnl",
            sa.Float(),
            nullable=False,
            comment="Realized P&L in USD (currently gross of fees — see proposal §9)",
        ),
        sa.Column("pnl_pct", sa.Float(), nullable=False, comment="P&L as percentage"),
        sa.Column(
            "result", sa.String(length=12), nullable=False, comment="WIN, LOSS, or BREAKEVEN"
        ),
        sa.Column("size", sa.Float(), nullable=False, comment="Position size (USD)"),
        sa.Column(
            "duration_seconds",
            sa.Float(),
            nullable=False,
            comment="exit_time - entry_time in seconds",
        ),
        sa.Column("market_slug", sa.Text(), nullable=False, comment="Market identifier"),
        sa.Column("outcome", sa.Text(), nullable=False, comment="UP or DOWN"),
        sa.Column("entry_price", sa.Float(), nullable=False, comment="Average entry price"),
        sa.Column("exit_price", sa.Float(), nullable=False, comment="Exit/settlement price"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Record insertion timestamp",
        ),
        sa.CheckConstraint("execution_mode IN ('paper', 'live')", name="sct_execution_mode_check"),
        sa.CheckConstraint("outcome IN ('UP', 'DOWN')", name="sct_outcome_check"),
        sa.CheckConstraint("result IN ('WIN', 'LOSS', 'BREAKEVEN')", name="sct_result_check"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index(
        "idx_sct_exit_ts_wall", "strategy_closed_trades", ["exit_ts_wall"], unique=False
    )
    op.create_index(
        "idx_sct_mode_exit_ts",
        "strategy_closed_trades",
        ["execution_mode", "exit_ts_wall"],
        unique=False,
    )
    op.create_index(
        "idx_sct_strategy_exit_ts",
        "strategy_closed_trades",
        ["strategy_id", "exit_ts_wall"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_sct_strategy_exit_ts", table_name="strategy_closed_trades")
    op.drop_index("idx_sct_mode_exit_ts", table_name="strategy_closed_trades")
    op.drop_index("idx_sct_exit_ts_wall", table_name="strategy_closed_trades")
    op.drop_table("strategy_closed_trades")
