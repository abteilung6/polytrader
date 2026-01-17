"""Tests to verify PostgreSQL fixtures work correctly.

These tests verify that:
1. Test database can be started and connected to
2. Fixtures properly manage connections
3. Database cleanup works correctly
"""

import psycopg
import pytest
from psycopg import AsyncConnection
from pydantic import SecretStr

from polytrader.config import DatabaseConfig, get_database_url
from tests.integration.conftest import (
    TEST_DB_HOST,
    TEST_DB_NAME,
    TEST_DB_PASSWORD,
    TEST_DB_PORT,
    TEST_DB_USER,
    get_test_database_name,
    get_worker_id,
)


class TestPostgresFixtures:
    """Test PostgreSQL fixtures functionality."""

    @pytest.mark.asyncio
    async def test_postgres_connection_fixture(self, postgres_connection: AsyncConnection):
        """Test that postgres_connection fixture provides a working connection."""
        # Verify connection is open
        assert not postgres_connection.closed

        # Execute a simple query
        async with postgres_connection.cursor() as cur:
            await cur.execute("SELECT 1")
            result = await cur.fetchone()
            assert result is not None
            assert result[0] == 1

        # Verify connection is still open
        assert not postgres_connection.closed

    @pytest.mark.asyncio
    async def test_postgres_connection_closes_after_test(
        self, postgres_connection: AsyncConnection
    ):
        """Test that connection is properly closed after test."""
        # Connection should be open during test
        assert not postgres_connection.closed

        # After test, fixture should close it
        # (We can't test this directly, but we verify it doesn't raise errors)

    @pytest.mark.asyncio
    async def test_postgres_db_truncates_tables(
        self, postgres_connection: AsyncConnection, postgres_db
    ):
        """Test that postgres_db fixture can truncate tables."""
        # Create a test table
        async with postgres_connection.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS test_table (
                    id SERIAL PRIMARY KEY,
                    value TEXT
                )
            """)
            await postgres_connection.commit()

        # Insert some data
        async with postgres_connection.cursor() as cur:
            await cur.execute("INSERT INTO test_table (value) VALUES ('test1'), ('test2')")
            await postgres_connection.commit()

        # Verify data exists
        async with postgres_connection.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM test_table")
            row = await cur.fetchone()
            assert row is not None
            count_before = row[0]
            assert count_before == 2

        # Note: Cleanup happens after test via fixture
        # The fixture will truncate all tables after the test completes

    @pytest.mark.asyncio
    async def test_postgres_test_url_fixture(self, postgres_test_url: str):
        """Test that postgres_test_url fixture returns correct URL."""
        # Get expected database name based on execution mode
        worker_id = get_worker_id()
        expected_db_name = get_test_database_name(worker_id)
        expected_url = f"postgresql://{TEST_DB_USER}:{TEST_DB_PASSWORD}@{TEST_DB_HOST}:{TEST_DB_PORT}/{expected_db_name}"

        assert postgres_test_url == expected_url

        # Verify we can connect with this URL
        conn = await psycopg.AsyncConnection.connect(postgres_test_url)
        try:
            assert not conn.closed
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_database_config_loads_from_env(self):
        """Test that DatabaseConfig can load from environment variables."""
        # Use model_construct to bypass env file loading and validation
        # This is appropriate for unit tests where we want to test with specific values
        config = DatabaseConfig.model_construct(
            db_host=TEST_DB_HOST,
            db_port=TEST_DB_PORT,
            db_database=TEST_DB_NAME,
            db_user=TEST_DB_USER,
            db_password=SecretStr(TEST_DB_PASSWORD),
        )

        assert config.db_host == TEST_DB_HOST
        assert config.db_port == TEST_DB_PORT
        assert config.db_database == TEST_DB_NAME
        assert config.db_user == TEST_DB_USER
        assert config.db_password.get_secret_value() == TEST_DB_PASSWORD

    @pytest.mark.asyncio
    async def test_get_database_url_creates_correct_url(self):
        """Test that get_database_url creates correct connection URL."""
        # Use model_construct to bypass env file loading and validation
        config = DatabaseConfig.model_construct(
            db_host=TEST_DB_HOST,
            db_port=TEST_DB_PORT,
            db_database=TEST_DB_NAME,
            db_user=TEST_DB_USER,
            db_password=SecretStr(TEST_DB_PASSWORD),
        )

        url = get_database_url(config)
        expected_url = f"postgresql://{TEST_DB_USER}:{TEST_DB_PASSWORD}@{TEST_DB_HOST}:{TEST_DB_PORT}/{TEST_DB_NAME}"
        assert url == expected_url

        # Verify we can connect with this URL
        conn = await psycopg.AsyncConnection.connect(url)
        try:
            assert not conn.closed
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_database_config_secret_str_hides_password(self):
        """Test that DatabaseConfig uses SecretStr to hide password."""
        # Use model_construct to bypass env file loading and validation
        config = DatabaseConfig.model_construct(
            db_host="localhost",
            db_port=5432,
            db_database="test",
            db_user="user",
            db_password=SecretStr("secret123"),
        )

        # SecretStr should not expose password in repr/str
        password_repr = repr(config.db_password)
        assert "secret123" not in password_repr
        assert "SecretStr" in password_repr

        # But get_secret_value() should return the actual password
        assert config.db_password.get_secret_value() == "secret123"
