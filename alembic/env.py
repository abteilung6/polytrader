"""Alembic environment configuration for async psycopg3.

This configuration supports async migrations using psycopg3.
Uses our existing database configuration from polytrader.config.
"""

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from polytrader.config import get_database_url
from polytrader.db.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# Set database URL from our config (if not already set in alembic.ini or env)
# This allows alembic.ini or ALEMBIC_SQLALCHEMY_URL env var to override
if not config.get_main_option("sqlalchemy.url"):
    # Check environment variable first (for tests)
    env_url = os.environ.get("ALEMBIC_SQLALCHEMY_URL")
    if env_url:
        config.set_main_option("sqlalchemy.url", env_url)
    else:
        try:
            db_url = get_database_url()
            # Convert to SQLAlchemy format (postgresql+psycopg://)
            # Our URL is already in postgresql:// format, just add +psycopg
            if db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
            config.set_main_option("sqlalchemy.url", db_url)
        except Exception as e:
            # If config loading fails, provide helpful error message
            import sys

            print(
                f"Error: Failed to load database configuration: {e}",
                file=sys.stderr,
            )
            print(
                "Please ensure .env file exists with DB_HOST, DB_PORT, DB_DATABASE, "
                "DB_USER, DB_PASSWORD",
                file=sys.stderr,
            )
            print(
                "Or set ALEMBIC_SQLALCHEMY_URL environment variable directly.",
                file=sys.stderr,
            )
            # Re-raise so user sees the actual error
            raise


def do_run_migrations(connection: Connection) -> None:
    """Run migrations in sync context (called from async)."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Enable type comparison for autogenerate
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in async mode using psycopg3."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        # Run sync migrations code in async context
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    # Convert to postgresql+psycopg:// if needed
    if url and url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
