"""Integration test fixtures and configuration.

This module provides shared fixtures for integration tests, including
PostgreSQL database fixtures for event store testing with parallel execution support.
"""

import os
import subprocess
import time
from collections.abc import AsyncGenerator

import psycopg
import pytest
from psycopg import AsyncConnection

# These values must match docker-compose.test.yml environment variables.
# If you change these, update docker-compose.test.yml accordingly.
TEST_DB_USER = "test_user"
TEST_DB_PASSWORD = "test_password"
TEST_DB_NAME = "polytrader_test"  # Base name (worker-specific names append _gw0, etc.)
TEST_DB_PORT = 5433
TEST_DB_HOST = "localhost"


def get_worker_id() -> str | None:
    """Get pytest-xdist worker ID if running in parallel mode.

    Returns:
        Worker ID (e.g., 'gw0', 'gw1') or None if sequential execution
    """
    return os.environ.get("PYTEST_XDIST_WORKER")


def get_test_database_name(worker_id: str | None = None) -> str:
    """Get test database name for current worker.

    Args:
        worker_id: pytest-xdist worker ID (e.g., 'gw0')

    Returns:
        Database name (e.g., 'polytrader_test_gw0' or 'polytrader_test')
    """
    if worker_id:
        return f"{TEST_DB_NAME}_{worker_id}"
    return TEST_DB_NAME


@pytest.fixture(scope="session", autouse=True)
def ensure_postgres_test_running():
    """Ensure test PostgreSQL is running before tests start.

    This fixture automatically starts the test database if it's not running.
    It runs once per test session and ensures the database is ready.
    """
    # Check if container is running
    result = subprocess.run(
        ["docker", "ps", "--filter", "name=polytrader-postgres-test", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    )

    container_running = "polytrader-postgres-test" in result.stdout

    if not container_running:
        # Start test database
        subprocess.run(["make", "test-db-up"], check=False)
        # Give it a moment to start
        time.sleep(2)

    # Wait for readiness (up to 30 seconds)
    for _attempt in range(30):
        result = subprocess.run(
            ["docker", "exec", "polytrader-postgres-test", "pg_isready", "-U", TEST_DB_USER],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            break
        time.sleep(1)
    else:
        pytest.fail("PostgreSQL test database not ready after 30 seconds")

    yield

    # Cleanup: don't stop the database (it's shared across tests)
    # Tests can stop it manually with: make test-db-down


@pytest.fixture(scope="session")
async def postgres_test_database() -> AsyncGenerator[str, None]:
    """Create and manage test database for current worker.

    Creates a separate database for each pytest-xdist worker to enable
    parallel execution without interference.

    Yields:
        Database name (e.g., 'polytrader_test_gw0' or 'polytrader_test')

    Note:
        Database is created at session start and dropped at session end.
        For sequential execution (no worker ID), uses default 'polytrader_test'.
    """
    worker_id = get_worker_id()
    db_name = get_test_database_name(worker_id)

    # Connect to default 'postgres' database to create test database
    admin_url = (
        f"postgresql://{TEST_DB_USER}:{TEST_DB_PASSWORD}@{TEST_DB_HOST}:{TEST_DB_PORT}/postgres"
    )

    try:
        # Use autocommit=True for CREATE DATABASE (cannot run in transaction)
        async with await psycopg.AsyncConnection.connect(admin_url, autocommit=True) as admin_conn:
            # Create database if it doesn't exist
            async with admin_conn.cursor() as cur:
                await cur.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (db_name,),
                )
                exists = await cur.fetchone()

                if not exists:
                    # Create database (autocommit mode, no transaction)
                    await cur.execute(f'CREATE DATABASE "{db_name}"')
                    print(f"Created test database: {db_name}")

        yield db_name

    finally:
        # Cleanup: Drop database after all tests in worker complete
        # Only drop if it's a worker-specific database (not the default)
        if worker_id:
            try:
                # Use autocommit=True for DROP DATABASE (cannot run in transaction)
                async with await psycopg.AsyncConnection.connect(
                    admin_url, autocommit=True
                ) as admin_conn:
                    async with admin_conn.cursor() as cur:
                        # Terminate all connections to the database first
                        await cur.execute(
                            """
                            SELECT pg_terminate_backend(pid)
                            FROM pg_stat_activity
                            WHERE datname = %s AND pid <> pg_backend_pid()
                            """,
                            (db_name,),
                        )

                        # Drop database (autocommit mode, no transaction)
                        await cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
                        print(f"Dropped test database: {db_name}")
            except Exception as e:
                # Log but don't fail - database might already be dropped
                print(f"Warning: Failed to drop database {db_name}: {e}")


@pytest.fixture(scope="session")
def postgres_test_url(postgres_test_database: str) -> str:
    """Get PostgreSQL connection URL for current worker's database.

    Args:
        postgres_test_database: Database name from postgres_test_database fixture

    Returns:
        PostgreSQL connection URL for worker-specific database
    """
    return f"postgresql://{TEST_DB_USER}:{TEST_DB_PASSWORD}@{TEST_DB_HOST}:{TEST_DB_PORT}/{postgres_test_database}"


@pytest.fixture
async def postgres_connection(postgres_test_url: str) -> AsyncGenerator[AsyncConnection, None]:
    """Create a PostgreSQL connection for testing.

    Args:
        postgres_test_url: PostgreSQL connection URL

    Yields:
        AsyncConnection to PostgreSQL database

    Note:
        Connection is automatically closed after test.
    """
    conn = await psycopg.AsyncConnection.connect(postgres_test_url)
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def postgres_db(
    postgres_connection: AsyncConnection, postgres_test_url: str
) -> AsyncGenerator[None, None]:
    """Ensure database is migrated and clean before and after test.

    This fixture:
    1. Runs migrations automatically (idempotent - safe to run multiple times)
    2. Truncates all tables before test
    3. Truncates all tables after test

    Args:
        postgres_connection: PostgreSQL connection (to worker-specific database)
        postgres_test_url: PostgreSQL connection URL (needed for migrations)

    Yields:
        None (cleanup happens automatically)

    Note:
        This fixture operates on worker-specific database, so parallel execution is safe.
        Migrations are run automatically, so tests don't need to call run_migrations().
    """
    # Run migrations first (idempotent - Alembic handles this)
    from polytrader.db.migrations import run_migrations

    # Check if database is in inconsistent state (tables exist but alembic_version is empty)
    async with postgres_connection.cursor() as cur:
        await cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'alembic_version'
            )
        """)
        row = await cur.fetchone()
        assert row is not None
        alembic_exists = row[0]

        if alembic_exists:
            await cur.execute("SELECT COUNT(*) FROM alembic_version")
            row = await cur.fetchone()
            assert row is not None
            alembic_count = row[0]
        else:
            alembic_count = 0

        await cur.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'public'
                AND table_name != 'alembic_version'
        """)
        row = await cur.fetchone()
        assert row is not None
        other_tables_count = row[0]

    # If tables exist but alembic_version is empty, drop all tables to start fresh
    # This handles inconsistent database state from previous test runs
    if other_tables_count > 0 and alembic_count == 0:
        async with postgres_connection.cursor() as cur:
            await cur.execute("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                    AND tablename != 'alembic_version'
            """)
            tables_to_drop = [row[0] for row in await cur.fetchall()]
            if tables_to_drop:
                # Drop tables in reverse dependency order (CASCADE handles most cases)
                for table in tables_to_drop:
                    await cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
                await postgres_connection.commit()

    await run_migrations(postgres_test_url)

    # Truncate all tables before test (if any exist)
    # Exclude alembic_version (Alembic's migration tracking table)
    async with postgres_connection.cursor() as cur:
        await cur.execute("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
                AND tablename != 'alembic_version'
        """)
        tables = [row[0] for row in await cur.fetchall()]

    if tables:
        async with postgres_connection.cursor() as cur:
            await cur.execute("TRUNCATE TABLE {} CASCADE".format(", ".join(tables)))
            await postgres_connection.commit()

    # Re-insert initial execution_control row if it was truncated
    # (migration creates it, but truncation removes it)
    async with postgres_connection.cursor() as cur:
        await cur.execute("""
            SELECT COUNT(*) FROM execution_control WHERE id = 1
        """)
        row = await cur.fetchone()
        assert row is not None
        count = row[0]
        if count == 0:
            await cur.execute("""
                INSERT INTO execution_control (
                    id, execution_enabled, updated_by, reason, version
                )
                VALUES (1, false, 'system', 'Initial state: execution disabled by default', 1)
                ON CONFLICT (id) DO NOTHING
            """)
            await postgres_connection.commit()

    yield

    # Cleanup: truncate all tables after test (get fresh list in case new tables were created)
    # Exclude alembic_version (Alembic's migration tracking table)
    # Rollback any failed transaction first
    try:
        await postgres_connection.rollback()
    except Exception:
        pass  # Ignore if no transaction to rollback

    try:
        async with postgres_connection.cursor() as cur:
            await cur.execute("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                    AND tablename != 'alembic_version'
            """)
            tables_after = [row[0] for row in await cur.fetchall()]

        if tables_after:
            async with postgres_connection.cursor() as cur:
                await cur.execute("TRUNCATE TABLE {} CASCADE".format(", ".join(tables_after)))
                await postgres_connection.commit()

        # Re-insert initial execution_control row if it was truncated
        async with postgres_connection.cursor() as cur:
            await cur.execute("""
                SELECT COUNT(*) FROM execution_control WHERE id = 1
            """)
            row = await cur.fetchone()
            assert row is not None
            count = row[0]
            if count == 0:
                await cur.execute("""
                    INSERT INTO execution_control (
                        id, execution_enabled, updated_by, reason, version
                    )
                    VALUES (1, false, 'system', 'Initial state: execution disabled by default', 1)
                    ON CONFLICT (id) DO NOTHING
                """)
                await postgres_connection.commit()
    except Exception:
        # If cleanup fails, rollback and continue (test may have left transaction in bad state)
        try:
            await postgres_connection.rollback()
        except Exception:
            pass
