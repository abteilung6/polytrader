"""Database migrations using Alembic.

This module provides helpers for running Alembic migrations programmatically.
"""

import asyncio
import os
from pathlib import Path

from alembic import command
from alembic import config as alembic_config


async def run_migrations(connection_url: str) -> None:
    """Run Alembic migrations programmatically (async wrapper).

    This is a compatibility wrapper for tests that need to run migrations
    with a specific connection URL. Alembic runs in a thread pool to avoid
    blocking the async event loop.

    Args:
        connection_url: PostgreSQL connection URL (postgresql://...)
    """
    # Convert to SQLAlchemy format
    if connection_url.startswith("postgresql://"):
        sqlalchemy_url = connection_url.replace("postgresql://", "postgresql+psycopg://", 1)
    else:
        sqlalchemy_url = connection_url

    # Set environment variable for Alembic
    os.environ["ALEMBIC_SQLALCHEMY_URL"] = sqlalchemy_url

    # Get Alembic config - use absolute path so %(here)s resolves correctly
    # __file__ is polytrader/db/migrations/__init__.py
    # We need to go up 4 levels to get to project root:
    # migrations -> db -> polytrader -> project_root
    alembic_ini_path = Path(__file__).parent.parent.parent.parent / "alembic.ini"
    alembic_dir = alembic_ini_path.parent / "alembic"
    cfg = alembic_config.Config(str(alembic_ini_path.resolve()))

    # Ensure script_location is set (Alembic uses get_alembic_option which
    # looks in [alembic] section). The ini file should have it, but in some
    # contexts (like parallel tests) it might not resolve. Set it explicitly
    # with absolute path to be safe.
    script_location = cfg.get_alembic_option("script_location")
    if not script_location:
        # Set absolute path explicitly - use set_main_option (which sets in [alembic] section)
        cfg.set_main_option("script_location", str(alembic_dir.resolve()))

    # Override URL
    cfg.set_main_option("sqlalchemy.url", sqlalchemy_url)

    # Run migrations in thread pool (Alembic is sync, but we're in async context)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: command.upgrade(cfg, "head"))
