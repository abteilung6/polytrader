"""Integration tests for platform database schema.

Per Commit 1.2: Test that migration creates tables with correct schema,
constraints, indexes, and initial data.
"""

import psycopg.errors
import pytest
from psycopg import AsyncConnection


@pytest.mark.integration
class TestPlatformSchema:
    """Test platform database schema (strategies, execution_control, etc.)."""

    async def test_strategies_table_exists(
        self, postgres_db: None, postgres_connection: AsyncConnection
    ) -> None:
        """Test that strategies table exists with correct columns."""
        async with postgres_connection.cursor() as cur:
            await cur.execute(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'strategies'
                ORDER BY ordinal_position
                """
            )
            columns = {row[0]: row[1:] for row in await cur.fetchall()}

        assert "strategy_id" in columns
        assert columns["strategy_id"][0] == "character varying"  # VARCHAR
        assert columns["strategy_id"][1] == "NO"  # NOT NULL

        assert "name" in columns
        assert columns["name"][0] == "character varying"
        assert columns["name"][1] == "NO"

        assert "description" in columns
        assert columns["description"][0] == "text"
        assert columns["description"][1] == "YES"  # NULLABLE

        assert "config" in columns
        assert columns["config"][0] == "jsonb"

        assert "enabled" in columns
        assert columns["enabled"][0] == "boolean"
        assert "true" in columns["enabled"][2]  # DEFAULT true

        assert "created_at" in columns
        assert "updated_at" in columns

    async def test_execution_control_table_exists(
        self, postgres_db: None, postgres_connection: AsyncConnection
    ) -> None:
        """Test that execution_control table exists with correct columns."""
        async with postgres_connection.cursor() as cur:
            await cur.execute(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'execution_control'
                ORDER BY ordinal_position
                """
            )
            columns = {row[0]: row[1:] for row in await cur.fetchall()}

        assert "id" in columns
        assert columns["id"][0] == "integer"
        assert columns["id"][1] == "NO"

        assert "execution_enabled" in columns
        assert columns["execution_enabled"][0] == "boolean"
        assert "false" in columns["execution_enabled"][2]  # DEFAULT false

        assert "version" in columns
        assert columns["version"][0] == "integer"
        assert columns["version"][1] == "NO"
        assert "1" in columns["version"][2]  # DEFAULT 1

        assert "updated_by" in columns
        assert "reason" in columns
        assert "updated_at" in columns

    async def test_execution_control_singleton_constraint(
        self, postgres_db: None, postgres_connection: AsyncConnection
    ) -> None:
        """Test that execution_control enforces singleton (id = 1 only)."""
        # Try to insert row with id != 1 (should fail)
        with pytest.raises(psycopg.errors.CheckViolation) as exc_info:
            async with postgres_connection.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO execution_control (
                        id, execution_enabled, updated_by, reason, version
                    )
                    VALUES (2, false, 'test', 'test', 1)
                    """
                )
                await postgres_connection.commit()
        # Verify error mentions the constraint
        e = exc_info.value
        assert "execution_control_singleton_check" in str(e) or "check" in str(e).lower()

    async def test_execution_control_initial_row(
        self, postgres_db: None, postgres_connection: AsyncConnection
    ) -> None:
        """Test that execution_control has initial row with version = 1."""
        async with postgres_connection.cursor() as cur:
            await cur.execute("SELECT id, execution_enabled, version FROM execution_control")
            row = await cur.fetchone()

        assert row is not None
        assert row[0] == 1  # id = 1
        assert row[1] is False  # execution_enabled = false
        assert row[2] == 1  # version = 1

    async def test_live_strategy_activation_table_exists(
        self, postgres_db: None, postgres_connection: AsyncConnection
    ) -> None:
        """Test that live_strategy_activation table exists with correct columns."""
        async with postgres_connection.cursor() as cur:
            await cur.execute(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'live_strategy_activation'
                ORDER BY ordinal_position
                """
            )
            columns = {row[0]: row[1:] for row in await cur.fetchall()}

        assert "strategy_id" in columns
        assert columns["strategy_id"][0] == "character varying"
        assert columns["strategy_id"][1] == "NO"

        assert "active" in columns
        assert columns["active"][0] == "boolean"
        assert "false" in columns["active"][2]  # DEFAULT false

        assert "activated_at" in columns
        assert "activated_by" in columns
        assert "reason" in columns
        assert "created_at" in columns
        assert "updated_at" in columns

    async def test_live_strategy_activation_foreign_key(
        self, postgres_db: None, postgres_connection: AsyncConnection
    ) -> None:
        """Test that live_strategy_activation has foreign key to strategies."""
        async with postgres_connection.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    tc.constraint_name,
                    tc.table_name,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.table_name = 'live_strategy_activation'
                    AND tc.constraint_type = 'FOREIGN KEY'
                """
            )
            fks = await cur.fetchall()

        assert len(fks) > 0
        fk = fks[0]
        assert fk[1] == "live_strategy_activation"
        assert fk[2] == "strategy_id"
        assert fk[3] == "strategies"
        assert fk[4] == "strategy_id"

    async def test_control_commands_table_exists(
        self, postgres_db: None, postgres_connection: AsyncConnection
    ) -> None:
        """Test that control_commands table exists with correct columns."""
        async with postgres_connection.cursor() as cur:
            await cur.execute(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'control_commands'
                ORDER BY ordinal_position
                """
            )
            columns = {row[0]: row[1:] for row in await cur.fetchall()}

        assert "command_id" in columns
        assert columns["command_id"][0] == "uuid"

        assert "command_type" in columns
        assert columns["command_type"][0] == "character varying"
        assert columns["command_type"][1] == "NO"

        assert "strategy_id" in columns
        assert columns["strategy_id"][1] == "YES"  # NULLABLE

        assert "client_request_id" in columns
        assert columns["client_request_id"][0] == "character varying"
        assert columns["client_request_id"][1] == "YES"  # NULLABLE

        assert "expected_version" in columns
        assert columns["expected_version"][0] == "integer"
        assert columns["expected_version"][1] == "YES"  # NULLABLE

        assert "reason" in columns
        assert "issued_by" in columns
        assert "status" in columns
        assert "error_message" in columns
        assert "created_at" in columns
        assert "applied_at" in columns

    async def test_control_commands_idempotency_index(
        self, postgres_db: None, postgres_connection: AsyncConnection
    ) -> None:
        """Test that unique index on (command_type, strategy_id, client_request_id) exists."""
        async with postgres_connection.cursor() as cur:
            await cur.execute(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'control_commands'
                    AND indexname = 'idx_control_commands_idempotency'
                """
            )
            index = await cur.fetchone()

        assert index is not None
        assert "UNIQUE" in index[1].upper()
        assert "command_type" in index[1]
        assert "COALESCE" in index[1]  # Should use COALESCE for NULL strategy_id
        assert "client_request_id" in index[1]
        assert "WHERE" in index[1].upper()  # Should have WHERE clause

    async def test_control_commands_idempotency_enforces_uniqueness(
        self, postgres_db: None, postgres_connection: AsyncConnection
    ) -> None:
        """Test that idempotency index prevents duplicate commands."""
        # First, create a strategy (required for FK)
        async with postgres_connection.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO strategies (strategy_id, name, config)
                VALUES ('test_strategy', 'Test Strategy', '{}')
                """
            )
            await postgres_connection.commit()

        # Insert first command with client_request_id
        async with postgres_connection.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO control_commands (
                    command_type, strategy_id, client_request_id, reason, issued_by
                )
                VALUES ('add_active_strategy', 'test_strategy', 'req-123', 'test', 'test')
                """
            )
            await postgres_connection.commit()

        # Try to insert duplicate (should fail)
        with pytest.raises(psycopg.errors.UniqueViolation) as exc_info:
            async with postgres_connection.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO control_commands (
                        command_type, strategy_id, client_request_id, reason, issued_by
                    )
                    VALUES ('add_active_strategy', 'test_strategy', 'req-123', 'test', 'test')
                    """
                )
                await postgres_connection.commit()
        # Verify error mentions the index
        e = exc_info.value
        assert "idx_control_commands_idempotency" in str(e) or "unique" in str(e).lower()

    async def test_partial_indexes_exist(
        self, postgres_db: None, postgres_connection: AsyncConnection
    ) -> None:
        """Test that partial indexes (WHERE clauses) exist."""
        async with postgres_connection.cursor() as cur:
            # Check pending commands index
            await cur.execute(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE tablename = 'control_commands'
                    AND indexname = 'idx_control_commands_pending'
                """
            )
            pending_index = await cur.fetchone()

            # Check active strategies index
            await cur.execute(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE tablename = 'live_strategy_activation'
                    AND indexname = 'idx_live_strategy_active'
                """
            )
            active_index = await cur.fetchone()

        assert pending_index is not None
        assert "WHERE" in pending_index[0].upper()
        assert "status" in pending_index[0]

        assert active_index is not None
        assert "WHERE" in active_index[0].upper()
        assert "active" in active_index[0]
