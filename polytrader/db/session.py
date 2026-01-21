"""Database session helpers for async SQLAlchemy."""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from polytrader.config import get_database_url


def to_async_db_url(database_url: str) -> str:
    """Convert database URL to async psycopg format."""
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


class DatabaseSessionManager:
    """Async database session manager."""

    def __init__(self, database_url: str | None = None, pool_size: int = 5) -> None:
        if database_url is None:
            database_url = get_database_url()
        async_url = to_async_db_url(database_url)
        self._engine: AsyncEngine = create_async_engine(async_url, pool_size=pool_size)
        self._Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False
        )

    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Get session factory."""
        return self._Session

    async def dispose(self) -> None:
        """Dispose engine resources."""
        await self._engine.dispose()
