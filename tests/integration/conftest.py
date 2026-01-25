"""Integration test fixtures and configuration.

This module provides shared fixtures for integration tests, including
PostgreSQL database fixtures for event store testing with parallel execution support.
"""

import os
import subprocess
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import psycopg
import pytest
from psycopg import AsyncConnection

if TYPE_CHECKING:
    from collections.abc import Callable
    from unittest.mock import MagicMock

    from sqlalchemy.ext.asyncio import AsyncSession

    from polytrader.adapters import IMarketDataAdapter
    from polytrader.events import EventBus
    from polytrader.observer import IObserver
    from polytrader.store import IMarketDataStore

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


# Shared fixtures for orchestrator and strategy tests
# These fixtures are used across multiple test files to avoid duplication


@pytest.fixture
async def db_session(
    postgres_test_url: str, postgres_db: None
) -> AsyncGenerator["AsyncSession", None]:
    """Provide SQLAlchemy session for tests.

    This fixture creates an async SQLAlchemy session and automatically
    truncates the strategy_instances table before and after each test.

    Args:
        postgres_test_url: PostgreSQL connection URL from postgres_test_url fixture
        postgres_db: Database migration fixture (ensures schema is up to date)

    Yields:
        AsyncSession: SQLAlchemy async session

    Note:
        This fixture is shared across multiple orchestrator and strategy tests.
        It automatically cleans up strategy_instances table for test isolation.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    sqlalchemy_url = postgres_test_url
    if sqlalchemy_url.startswith("postgresql://"):
        sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+psycopg://", 1)

    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        # Clean up strategies table
        from sqlalchemy import text

        await session.execute(text("TRUNCATE TABLE strategy_instances CASCADE"))
        await session.commit()

        yield session

        # Cleanup
        await session.execute(text("TRUNCATE TABLE strategy_instances CASCADE"))
        await session.commit()

    await engine.dispose()


@pytest.fixture
def bus() -> "EventBus":
    """Create event bus for tests.

    Returns:
        EventBus: Fresh event bus instance for each test
    """
    from polytrader.events import EventBus

    return EventBus()


@pytest.fixture
def store() -> "IMarketDataStore":
    """Create market data store for tests.

    Returns:
        IMarketDataStore: Fresh in-memory market data store for each test
    """
    from polytrader.store import MemoryMarketDataStore

    return MemoryMarketDataStore()


@pytest.fixture
def discovery_service() -> "MagicMock":
    """Create mock discovery service for tests.

    Returns:
        MagicMock: Mock discovery service with get_current_market and get_next_market methods

    Note:
        Default market is "btc-updown-15m". Tests can override this by
        modifying the mock's return_value.
    """
    from unittest.mock import AsyncMock, MagicMock

    discovery = MagicMock()
    discovery.get_current_market = AsyncMock(return_value="btc-updown-15m")
    discovery.get_next_market = AsyncMock(return_value=None)
    return discovery


@pytest.fixture
def adapter_factory() -> "Callable[[str], MagicMock]":
    """Create mock adapter factory for tests.

    Returns:
        Callable[[str], MagicMock]: Factory function that creates mock adapters

    Note:
        Default market_slug is "btc-updown-15m". The factory updates
        the adapter's market_slug based on the provided slug parameter.
    """
    from typing import cast
    from unittest.mock import AsyncMock, MagicMock

    adapter = MagicMock()
    adapter.market_slug = "btc-updown-15m"
    adapter.ticks = AsyncMock(return_value=iter([]))
    adapter.stop = MagicMock()

    def factory(slug: str) -> MagicMock:
        adapter.market_slug = slug
        return adapter

    return cast("Callable[[str], MagicMock]", factory)


@pytest.fixture
def observer_factory() -> "Callable[[IMarketDataAdapter], IObserver]":
    """Create mock observer factory for tests.

    Returns:
        Callable[[IMarketDataAdapter], IObserver]: Factory function that creates mock observers

    Note:
        The factory ignores the adapter parameter and returns a mock observer
        with run() and stop() methods.
    """
    from typing import cast
    from unittest.mock import AsyncMock, MagicMock

    observer = MagicMock()
    observer.run = AsyncMock()
    observer.stop = MagicMock()

    def factory(adapter: "IMarketDataAdapter") -> "IObserver":  # noqa: ARG001
        return cast("IObserver", observer)

    return cast("Callable[[IMarketDataAdapter], IObserver]", factory)
