"""Strategy registry repository.

Provides type-safe CRUD operations for strategy registry using SQLAlchemy ORM.
Per architecture.mdc: Database operations are separated from business logic.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from polytrader.db.models import StrategyRecord


class StrategyRegistry:
    """Repository for strategy registry operations.

    Provides type-safe CRUD operations using SQLAlchemy ORM.
    All type conversions (JSONB, timestamps) are handled automatically.

    Example:
        >>> async with Session() as session:
        ...     registry = StrategyRegistry(session)
        ...     strategies = await registry.list_strategies()
        ...     strategy = await registry.get_strategy("simple_threshold")
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize registry with database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def list_strategies(self) -> list[StrategyRecord]:
        """List all strategies in registry.

        Returns:
            List of StrategyRecord objects, ordered by strategy_id

        Example:
            >>> strategies = await registry.list_strategies()
            >>> for strategy in strategies:
            ...     print(f"{strategy.strategy_id}: {strategy.name}")
        """
        query = select(StrategyRecord).order_by(StrategyRecord.strategy_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_strategy(self, strategy_id: str) -> StrategyRecord | None:
        """Get strategy by ID.

        Args:
            strategy_id: Strategy identifier

        Returns:
            StrategyRecord if found, None otherwise

        Example:
            >>> strategy = await registry.get_strategy("simple_threshold")
            >>> if strategy:
            ...     print(f"Config: {strategy.config}")
        """
        query = select(StrategyRecord).where(StrategyRecord.strategy_id == strategy_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_strategy(self, strategy: StrategyRecord) -> None:
        """Create new strategy in registry.

        Args:
            strategy: StrategyRecord to create

        Raises:
            sqlalchemy.exc.IntegrityError: If strategy_id already exists

        Example:
            >>> from polytrader.db.models import StrategyRecord
            >>> from polytrader.strategies.lifecycle_models import StrategyLifecycleState
            >>> strategy = StrategyRecord(
            ...     strategy_id="my_strategy",
            ...     name="My Strategy",
            ...     config={"type": "simple_threshold", "buy_threshold": 0.3},
            ...     template_type_id="simple_threshold",
            ...     template_version="1.0.0",
            ...     config_hash="hash_123",
            ...     desired_state=StrategyLifecycleState.RUNNING,
            ...     actual_state=StrategyLifecycleState.RUNNING,
            ... )
            >>> await registry.create_strategy(strategy)
        """
        self.session.add(strategy)
        await self.session.commit()

    async def update_strategy(self, strategy: StrategyRecord) -> None:
        """Update existing strategy in registry.

        Args:
            strategy: StrategyRecord with updated fields (strategy_id must exist)

        Raises:
            ValueError: If strategy_id does not exist

        Example:
            >>> strategy = await registry.get_strategy("simple_threshold")
            >>> strategy.config = {"type": "simple_threshold", "buy_threshold": 0.35}
            >>> await registry.update_strategy(strategy)
        """
        # Merge updates existing record or creates new one
        # We use merge to handle the case where the strategy might have been
        # loaded in a different session
        await self.session.merge(strategy)
        await self.session.commit()
