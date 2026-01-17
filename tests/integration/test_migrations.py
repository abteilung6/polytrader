"""Integration tests for event store migrations.

Tests verify that:
1. Migration runner can create schema
2. Migrations are applied correctly
3. Migrations are idempotent
4. Schema matches specification
"""

import psycopg.errors
import pytest
from psycopg import AsyncConnection

from polytrader.db.migrations import run_migrations


class TestMigrationRunner:
    """Test migration runner functionality."""

    @pytest.mark.asyncio
    async def test_run_migrations_creates_alembic_version_table(
        self, postgres_connection: AsyncConnection, postgres_test_url: str
    ):
        """Test that alembic_version table is created if it doesn't exist."""
        # Run migrations
        await run_migrations(postgres_test_url)

        # Verify alembic_version table exists (Alembic's tracking table)
        async with postgres_connection.cursor() as cur:
            await cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'alembic_version'
                )
            """)
            result = await cur.fetchone()
            assert result is not None
            assert result[0] is True

        # Verify table structure
        async with postgres_connection.cursor() as cur:
            await cur.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'alembic_version'
                ORDER BY column_name
            """)
            columns = await cur.fetchall()
            column_dict = {col[0]: (col[1], col[2]) for col in columns}

            assert "version_num" in column_dict
            assert column_dict["version_num"][0] in ("text", "character varying")

    @pytest.mark.asyncio
    async def test_run_migrations_applies_initial_migration(
        self, postgres_connection: AsyncConnection, postgres_test_url: str
    ):
        """Test that initial migration (001) is applied."""
        # Run migrations
        await run_migrations(postgres_test_url)

        # Verify events table exists
        async with postgres_connection.cursor() as cur:
            await cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'events'
                )
            """)
            result = await cur.fetchone()
            assert result is not None
            assert result[0] is True

    @pytest.mark.asyncio
    async def test_run_migrations_tracks_applied_migrations(
        self, postgres_connection: AsyncConnection, postgres_test_url: str
    ):
        """Test that applied migrations are recorded in alembic_version."""
        # Run migrations
        await run_migrations(postgres_test_url)

        # Verify migration is tracked in alembic_version table
        async with postgres_connection.cursor() as cur:
            await cur.execute("SELECT version_num FROM alembic_version")
            rows = await cur.fetchall()
            versions = [row[0] for row in rows]

            # Alembic uses revision IDs (e.g., '139195d3d869')
            assert len(versions) > 0
            # Check that our initial migration revision is present
            assert any("139195d3d869" in v for v in versions)

    @pytest.mark.asyncio
    async def test_run_migrations_idempotent(
        self, postgres_connection: AsyncConnection, postgres_test_url: str
    ):
        """Test that running migrations twice doesn't cause errors."""
        # Run migrations first time
        await run_migrations(postgres_test_url)

        # Count applied migrations
        async with postgres_connection.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM alembic_version")
            row = await cur.fetchone()
            assert row is not None
            count_before = row[0]

        # Run migrations second time
        await run_migrations(postgres_test_url)

        # Verify no duplicate entries (Alembic is idempotent)
        async with postgres_connection.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM alembic_version")
            row = await cur.fetchone()
            assert row is not None
            count_after = row[0]

            assert count_after == count_before

        # Verify table still exists
        async with postgres_connection.cursor() as cur:
            await cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'events'
                )
            """)
            result = await cur.fetchone()
            assert result is not None
            assert result[0] is True

    @pytest.mark.asyncio
    async def test_run_migrations_skips_already_applied(
        self, postgres_connection: AsyncConnection, postgres_test_url: str
    ):
        """Test that already-applied migrations are skipped."""
        # Run migrations first time
        await run_migrations(postgres_test_url)

        # Get applied migrations
        async with postgres_connection.cursor() as cur:
            await cur.execute("SELECT version_num FROM alembic_version")
            versions_before = {row[0] for row in await cur.fetchall()}

        # Run migrations again (should skip - Alembic is idempotent)
        await run_migrations(postgres_test_url)

        # Verify same migrations are tracked
        async with postgres_connection.cursor() as cur:
            await cur.execute("SELECT version_num FROM alembic_version")
            versions_after = {row[0] for row in await cur.fetchall()}

            assert versions_after == versions_before


class TestMigrationSchema:
    """Test that migration creates correct schema."""

    @pytest.mark.asyncio
    async def test_migration_creates_events_table(
        self, postgres_connection: AsyncConnection, postgres_test_url: str
    ):
        """Test that events table is created with correct structure."""
        # Run migrations
        await run_migrations(postgres_test_url)

        # Get all columns
        async with postgres_connection.cursor() as cur:
            await cur.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'events'
                ORDER BY column_name
            """)
            columns = await cur.fetchall()
            column_dict = {
                col[0]: {"type": col[1], "nullable": col[2], "default": col[3]} for col in columns
            }

            # Verify required columns exist
            assert "event_id" in column_dict
            assert "ts_wall" in column_dict
            assert "ts_mono" in column_dict
            assert "created_at" in column_dict
            assert "correlation_id" in column_dict
            assert "run_id" in column_dict
            assert "schema_version" in column_dict
            assert "source" in column_dict
            assert "event_type" in column_dict
            assert "event_data" in column_dict

            # Verify types
            assert column_dict["event_id"]["type"] in ("uuid", "character")
            assert column_dict["ts_wall"]["type"] in ("timestamp with time zone", "timestamptz")
            assert column_dict["ts_mono"]["type"] in ("double precision", "numeric")
            assert column_dict["event_data"]["type"] in ("jsonb", "json")

            # Verify NOT NULL constraints
            assert column_dict["event_id"]["nullable"] == "NO"
            assert column_dict["ts_wall"]["nullable"] == "NO"
            assert column_dict["ts_mono"]["nullable"] == "NO"
            assert column_dict["run_id"]["nullable"] == "NO"
            assert column_dict["source"]["nullable"] == "NO"
            assert column_dict["event_type"]["nullable"] == "NO"
            assert column_dict["event_data"]["nullable"] == "NO"

            # Verify nullable columns
            assert column_dict["correlation_id"]["nullable"] == "YES"

            # Verify defaults
            assert column_dict["created_at"]["default"] is not None  # DEFAULT NOW()
            assert "1.0" in (column_dict["schema_version"]["default"] or "")

    @pytest.mark.asyncio
    async def test_migration_source_check_constraint(
        self, postgres_connection: AsyncConnection, postgres_test_url: str
    ):
        """Test that source CHECK constraint works."""
        # Run migrations
        await run_migrations(postgres_test_url)

        # Try to insert with invalid source
        async with postgres_connection.cursor() as cur:
            with pytest.raises(psycopg.errors.CheckViolation):
                await cur.execute(
                    "INSERT INTO events (event_id, ts_wall, ts_mono, run_id, source, event_type, event_data) VALUES (gen_random_uuid(), NOW(), %s, %s, %s, %s, '{}'::jsonb)",  # noqa: E501
                    (123.45, "test-run", "invalid_source", "TestEvent"),
                )
                await postgres_connection.commit()

    @pytest.mark.asyncio
    async def test_migration_ts_mono_check_constraint(
        self, postgres_connection: AsyncConnection, postgres_test_url: str
    ):
        """Test that ts_mono >= 0 constraint works."""
        # Run migrations
        await run_migrations(postgres_test_url)

        # Try to insert with negative ts_mono
        async with postgres_connection.cursor() as cur:
            with pytest.raises(psycopg.errors.CheckViolation):
                await cur.execute(
                    "INSERT INTO events (event_id, ts_wall, ts_mono, run_id, source, event_type, event_data) VALUES (gen_random_uuid(), NOW(), %s, %s, %s, %s, '{}'::jsonb)",  # noqa: E501
                    (-1.0, "test-run", "ops", "TestEvent"),
                )
                await postgres_connection.commit()

    @pytest.mark.asyncio
    async def test_migration_event_id_primary_key(
        self, postgres_connection: AsyncConnection, postgres_test_url: str
    ):
        """Test that event_id is PRIMARY KEY (unique, not null)."""
        # Run migrations
        await run_migrations(postgres_test_url)

        import uuid

        event_id = str(uuid.uuid4())

        # Insert first event
        async with postgres_connection.cursor() as cur:
            await cur.execute(
                "INSERT INTO events (event_id, ts_wall, ts_mono, run_id, source, event_type, event_data) VALUES (%s, NOW(), %s, %s, %s, %s, '{}'::jsonb)",  # noqa: E501
                (event_id, 123.45, "test-run", "ops", "TestEvent"),
            )
            await postgres_connection.commit()

        # Try to insert duplicate event_id
        async with postgres_connection.cursor() as cur:
            with pytest.raises(psycopg.errors.UniqueViolation):
                await cur.execute(
                    "INSERT INTO events (event_id, ts_wall, ts_mono, run_id, source, event_type, event_data) VALUES (%s, NOW(), %s, %s, %s, %s, '{}'::jsonb)",  # noqa: E501
                    (event_id, 123.46, "test-run", "ops", "TestEvent"),
                )
                await postgres_connection.commit()

    @pytest.mark.asyncio
    async def test_migration_created_at_default(
        self, postgres_connection: AsyncConnection, postgres_test_url: str
    ):
        """Test that created_at has DEFAULT NOW()."""
        # Run migrations
        await run_migrations(postgres_test_url)

        import uuid

        event_id = str(uuid.uuid4())

        # Insert event without created_at
        async with postgres_connection.cursor() as cur:
            await cur.execute(
                "INSERT INTO events (event_id, ts_wall, ts_mono, run_id, source, event_type, event_data) VALUES (%s, NOW(), %s, %s, %s, %s, '{}'::jsonb)",  # noqa: E501
                (event_id, 123.45, "test-run", "ops", "TestEvent"),
            )
            await postgres_connection.commit()

        # Verify created_at is set
        async with postgres_connection.cursor() as cur:
            await cur.execute("SELECT created_at FROM events WHERE event_id = %s", (event_id,))
            result = await cur.fetchone()
            assert result is not None
            assert result[0] is not None  # Should have a timestamp

    @pytest.mark.asyncio
    async def test_migration_allows_jsonb_insert(
        self, postgres_connection: AsyncConnection, postgres_test_url: str
    ):
        """Test that JSONB column accepts valid JSON."""
        # Run migrations
        await run_migrations(postgres_test_url)

        import json
        import uuid

        event_id = str(uuid.uuid4())
        event_data = {"test_key": "test_value", "number": 42}

        # Insert event with JSONB data
        async with postgres_connection.cursor() as cur:
            await cur.execute(
                "INSERT INTO events (event_id, ts_wall, ts_mono, run_id, source, event_type, event_data) VALUES (%s, NOW(), %s, %s, %s, %s, %s::jsonb)",  # noqa: E501
                (event_id, 123.45, "test-run", "ops", "TestEvent", json.dumps(event_data)),
            )
            await postgres_connection.commit()

        # Verify data stored correctly
        async with postgres_connection.cursor() as cur:
            await cur.execute("SELECT event_data FROM events WHERE event_id = %s", (event_id,))
            result = await cur.fetchone()
            assert result is not None
            retrieved_data = result[0]
            assert retrieved_data == event_data
