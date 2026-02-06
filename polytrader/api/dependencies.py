"""FastAPI dependency providers for control API.

Provides dependency injection for repositories and services.
Enables clean testing by allowing dependency override.
"""

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from polytrader.config import get_database_url
from polytrader.db.repository import EventRepository, MarketTickRepository
from polytrader.platform.control import (
    ControlCommandRepository,
    ExecutionControlRepository,
    LiveStrategyRepository,
)
from polytrader.platform.registry import StrategyRegistry
from polytrader.strategies.registration import register_all_strategies
from polytrader.strategies.registry import StrategyRegistry as InMemoryStrategyRegistry

if TYPE_CHECKING:
    from polytrader.platform.orchestrator import PlatformOrchestrator

# Global engine and session factory (created on first use)
_engine: AsyncEngine | None = None
_Session: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    """Get or create database engine (singleton).

    Returns:
        SQLAlchemy async engine
    """
    global _engine
    if _engine is None:
        # Get database URL from config
        db_url = get_database_url()
        # Convert to SQLAlchemy async format
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
        _engine = create_async_engine(db_url, echo=False)
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create session factory (singleton).

    Returns:
        SQLAlchemy async session factory
    """
    global _Session
    if _Session is None:
        engine = _get_engine()
        _Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return _Session


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide database session for API endpoints.

    This is a FastAPI dependency that provides a database session.
    The session is automatically closed after the request.

    Yields:
        SQLAlchemy async session

    Example:
        @router.get("/endpoint")
        async def endpoint(
            session: AsyncSession = Depends(get_db_session)
        ):
            # Use session
            ...
    """
    Session = _get_session_factory()
    async with Session() as session:
        try:
            yield session
        finally:
            await session.close()


def get_control_command_repo(
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> ControlCommandRepository:
    """Provide ControlCommandRepository.

    Args:
        session: Database session (injected via FastAPI)

    Returns:
        ControlCommandRepository instance
    """
    return ControlCommandRepository(session)


def get_execution_control_repo(
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> ExecutionControlRepository:
    """Provide ExecutionControlRepository.

    Args:
        session: Database session (injected via FastAPI)

    Returns:
        ExecutionControlRepository instance
    """
    return ExecutionControlRepository(session)


def get_live_strategy_repo(
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> LiveStrategyRepository:
    """Provide LiveStrategyRepository.

    Args:
        session: Database session (injected via FastAPI)

    Returns:
        LiveStrategyRepository instance
    """
    return LiveStrategyRepository(session)


def get_strategy_registry(
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> StrategyRegistry:
    """Provide StrategyRegistry.

    Args:
        session: Database session (injected via FastAPI)

    Returns:
        StrategyRegistry instance
    """
    return StrategyRegistry(session)


def get_event_repository(
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> EventRepository:
    """Provide EventRepository.

    Args:
        session: Database session (injected via FastAPI)

    Returns:
        EventRepository instance
    """
    return EventRepository(session)


# Global in-memory strategy template registry (singleton)
_in_memory_registry: InMemoryStrategyRegistry | None = None


def get_in_memory_strategy_registry() -> InMemoryStrategyRegistry:
    """Provide in-memory strategy template registry (singleton).

    Per Commit 15: In-memory registry is used for template discovery.
    Registry is initialized on first access and reused for all requests.

    Returns:
        InMemoryStrategyRegistry instance (singleton, initialized with all templates)
    """
    global _in_memory_registry
    if _in_memory_registry is None:
        _in_memory_registry = InMemoryStrategyRegistry()
        register_all_strategies(_in_memory_registry)
    return _in_memory_registry


def get_orchestrator(request: Request) -> "PlatformOrchestrator | None":
    """Provide platform orchestrator from app state when running under platform task.

    Returns None when not set (e.g. in tests or when API is run standalone).
    Used to add newly created RUNNING strategies to the running orchestrator.
    """
    return getattr(request.app.state, "orchestrator", None)


def get_market_tick_repository(
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> MarketTickRepository:
    """Provide MarketTickRepository.

    Args:
        session: Database session (injected via FastAPI)

    Returns:
        MarketTickRepository instance
    """
    return MarketTickRepository(session)
