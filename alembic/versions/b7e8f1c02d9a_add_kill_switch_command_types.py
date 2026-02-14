"""add kill_switch command types to control_commands

Revision ID: b7e8f1c02d9a
Revises: a065833f01c0
Create Date: 2026-02-08

Allow command_type kill_switch_activate and kill_switch_reset for audit records.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e8f1c02d9a"
down_revision: str | Sequence[str] | None = "a065833f01c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Allow kill_switch_activate and kill_switch_reset in control_commands."""
    op.drop_constraint(
        "control_commands_command_type_check",
        "control_commands",
        type_="check",
    )
    op.execute(
        """
        ALTER TABLE control_commands
        ADD CONSTRAINT control_commands_command_type_check
        CHECK (command_type IN (
            'enable_execution', 'disable_execution',
            'add_active_strategy', 'remove_active_strategy',
            'kill_switch_activate', 'kill_switch_reset'
        ))
        """
    )


def downgrade() -> None:
    """Revert to original command_type constraint."""
    op.drop_constraint(
        "control_commands_command_type_check",
        "control_commands",
        type_="check",
    )
    op.execute(
        """
        ALTER TABLE control_commands
        ADD CONSTRAINT control_commands_command_type_check
        CHECK (command_type IN (
            'enable_execution', 'disable_execution',
            'add_active_strategy', 'remove_active_strategy'
        ))
        """
    )
