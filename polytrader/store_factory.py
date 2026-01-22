"""Factory functions for creating market data stores.

Per architecture: Separates store creation from business logic.
Provides factory functions that handle database configuration and session management.
"""

from typing import TYPE_CHECKING

from polytrader.config import get_database_url
from polytrader.logging_config import logger

if TYPE_CHECKING:
    from polytrader.store import (
        IMarketDataStore,
        PostgreSQLMarketTickStore,
    )


def create_market_data_store(
    enable_postgres: bool = True,
    batch_size: int = 1000,
    flush_interval: float = 1.0,
) -> "IMarketDataStore":
    """Create market data store with optional PostgreSQL persistence.

    Per architecture: Creates composite store (memory + PostgreSQL) when database
    is configured, falls back to memory-only store if database is unavailable.

    Args:
        enable_postgres: If True, attempt to create PostgreSQL store (default: True)
        batch_size: Buffer size for PostgreSQL bulk inserts (default: 1000)
        flush_interval: Flush interval in seconds for PostgreSQL (default: 1.0)

    Returns:
        IMarketDataStore instance:
        - CompositeMarketDataStore (memory + PostgreSQL) if database is configured
        - MemoryMarketDataStore if database is not configured or enable_postgres=False

    Note:
        - Database configuration is optional (graceful degradation)
        - If database config is missing, returns memory-only store
        - Errors during PostgreSQL store creation are logged but don't fail
    """
    # Lazy import to avoid circular dependency
    from polytrader.store import (
        CompositeMarketDataStore,
        MemoryMarketDataStore,
    )

    # Always create memory store (primary, fast reads)
    memory_store = MemoryMarketDataStore()

    # Attempt to create PostgreSQL store if enabled
    if not enable_postgres:
        return memory_store

    try:
        # Check if database is configured
        database_url = get_database_url()
    except Exception as config_error:
        logger.debug(
            "Database configuration not available: {error}. Using memory-only store.",
            error=str(config_error),
            error_type=type(config_error).__name__,
        )
        return memory_store

    # Create PostgreSQL store
    try:
        postgres_store = _create_postgres_store(
            database_url=database_url,
            batch_size=batch_size,
            flush_interval=flush_interval,
        )
        logger.info(
            "Created composite market data store (memory + PostgreSQL). "
            "Ticks will be persisted to database."
        )
        return CompositeMarketDataStore(memory_store, postgres_store)
    except Exception as e:
        logger.warning(
            "Failed to create PostgreSQL market tick store: {error}. "
            "Using memory-only store. System will continue without tick persistence.",
            error=str(e),
            error_type=type(e).__name__,
        )
        return memory_store


def _create_postgres_store(
    database_url: str,
    batch_size: int = 1000,
    flush_interval: float = 1.0,
) -> "PostgreSQLMarketTickStore":
    """Create PostgreSQL market tick store with session management.

    Args:
        database_url: PostgreSQL connection URL
        batch_size: Buffer size for bulk inserts
        flush_interval: Flush interval in seconds

    Returns:
        PostgreSQLMarketTickStore instance

    Raises:
        RuntimeError: If database connection fails or migrations not run

    Note:
        This function creates a persistent session that lives for the lifetime
        of the store. The store's close() method should be called before shutdown.
        Migrations are assumed to be run already (by SystemSupervisor or manually).
        If migrations haven't been run, this will fail when trying to use the store.
    """
    # Lazy import to avoid circular dependency
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from polytrader.db.repository import MarketTickRepository
    from polytrader.store import PostgreSQLMarketTickStore

    # Convert URL to SQLAlchemy async format if needed
    sqlalchemy_url = database_url
    if sqlalchemy_url.startswith("postgresql://"):
        sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+psycopg://", 1)

    # Note: Migrations should be run by SystemSupervisor or manually before
    # creating the store. We don't run them here to avoid blocking in sync context.
    # If migrations haven't been run, the store will fail when trying to use it.

    # Create async engine and session factory
    engine = create_async_engine(sqlalchemy_url, echo=False, pool_size=5)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Create repository with session
    # Note: We create a session that will be used for the lifetime of the store
    # The store's close() method should be called to properly dispose of the engine
    session = Session()
    repository = MarketTickRepository(session)

    # Create store
    store = PostgreSQLMarketTickStore(
        repository=repository,
        batch_size=batch_size,
        flush_interval=flush_interval,
    )

    # Store engine reference for cleanup
    store._engine = engine

    return store
