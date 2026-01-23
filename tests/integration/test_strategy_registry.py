"""Integration tests for StrategyRegistry.

Tests verify that StrategyRegistry provides correct CRUD operations
for strategy registry using real database.
"""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.db.models import StrategyRecord
from polytrader.platform.registry import StrategyRegistry


@pytest.fixture
async def db_session(
    postgres_test_url: str, postgres_db: None
) -> AsyncGenerator[AsyncSession, None]:
    """Provide SQLAlchemy session for tests."""
    # Convert URL to SQLAlchemy async format
    sqlalchemy_url = postgres_test_url
    if sqlalchemy_url.startswith("postgresql://"):
        sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+psycopg://", 1)

    # Create engine and session
    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def registry(db_session: AsyncSession) -> StrategyRegistry:
    """Create StrategyRegistry for testing."""
    return StrategyRegistry(db_session)


class TestListStrategies:
    """Test list_strategies() method."""

    @pytest.mark.asyncio
    async def test_list_strategies_returns_empty_list_initially(
        self, registry: StrategyRegistry
    ) -> None:
        """Test that list_strategies() returns empty list when no strategies exist."""
        strategies = await registry.list_strategies()
        assert strategies == []

    @pytest.mark.asyncio
    async def test_list_strategies_returns_all_strategies(
        self, registry: StrategyRegistry, db_session: AsyncSession
    ) -> None:
        """Test that list_strategies() returns all strategies."""
        # Create test strategies
        strategy1 = StrategyRecord(
            strategy_id="strategy_1",
            name="Strategy 1",
            config={"type": "simple_threshold", "buy_threshold": 0.3},
            enabled=True,
        )
        strategy2 = StrategyRecord(
            strategy_id="strategy_2",
            name="Strategy 2",
            config={"type": "simple_threshold", "buy_threshold": 0.4},
            enabled=False,
        )
        db_session.add(strategy1)
        db_session.add(strategy2)
        await db_session.commit()

        strategies = await registry.list_strategies()
        assert len(strategies) == 2
        strategy_ids = {s.strategy_id for s in strategies}
        assert "strategy_1" in strategy_ids
        assert "strategy_2" in strategy_ids


class TestGetStrategy:
    """Test get_strategy() method."""

    @pytest.mark.asyncio
    async def test_get_strategy_returns_none_for_non_existent_id(
        self, registry: StrategyRegistry
    ) -> None:
        """Test that get_strategy() returns None for non-existent strategy_id."""
        strategy = await registry.get_strategy("non_existent")
        assert strategy is None

    @pytest.mark.asyncio
    async def test_get_strategy_returns_strategy_by_id(
        self, registry: StrategyRegistry, db_session: AsyncSession
    ) -> None:
        """Test that get_strategy() returns strategy by ID."""
        # Create test strategy
        strategy = StrategyRecord(
            strategy_id="test_strategy",
            name="Test Strategy",
            description="Test description",
            config={"type": "simple_threshold", "buy_threshold": 0.3},
            enabled=True,
        )
        db_session.add(strategy)
        await db_session.commit()

        # Retrieve strategy
        retrieved = await registry.get_strategy("test_strategy")
        assert retrieved is not None
        assert retrieved.strategy_id == "test_strategy"
        assert retrieved.name == "Test Strategy"
        assert retrieved.description == "Test description"
        assert retrieved.config == {"type": "simple_threshold", "buy_threshold": 0.3}
        assert retrieved.enabled is True


class TestCreateStrategy:
    """Test create_strategy() method."""

    @pytest.mark.asyncio
    async def test_create_strategy_creates_new_strategy(self, registry: StrategyRegistry) -> None:
        """Test that create_strategy() creates new strategy."""
        strategy = StrategyRecord(
            strategy_id="new_strategy",
            name="New Strategy",
            config={"type": "simple_threshold", "buy_threshold": 0.3},
            enabled=True,
        )

        await registry.create_strategy(strategy)

        # Verify strategy was created
        retrieved = await registry.get_strategy("new_strategy")
        assert retrieved is not None
        assert retrieved.strategy_id == "new_strategy"
        assert retrieved.name == "New Strategy"
        assert retrieved.config == {"type": "simple_threshold", "buy_threshold": 0.3}

    @pytest.mark.asyncio
    async def test_create_strategy_duplicate_id_fails(
        self, registry: StrategyRegistry, db_session: AsyncSession
    ) -> None:
        """Test that create_strategy() fails for duplicate strategy_id."""
        # Create first strategy
        strategy1 = StrategyRecord(
            strategy_id="duplicate",
            name="Strategy 1",
            config={"type": "simple_threshold"},
            enabled=True,
        )
        db_session.add(strategy1)
        await db_session.commit()

        # Try to create duplicate
        strategy2 = StrategyRecord(
            strategy_id="duplicate",
            name="Strategy 2",
            config={"type": "simple_threshold"},
            enabled=True,
        )

        import sqlalchemy.exc

        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await registry.create_strategy(strategy2)


class TestUpdateStrategy:
    """Test update_strategy() method."""

    @pytest.mark.asyncio
    async def test_update_strategy_updates_existing_strategy(
        self, registry: StrategyRegistry, db_session: AsyncSession
    ) -> None:
        """Test that update_strategy() updates existing strategy."""
        # Create strategy
        strategy = StrategyRecord(
            strategy_id="update_test",
            name="Original Name",
            config={"type": "simple_threshold", "buy_threshold": 0.3},
            enabled=True,
        )
        db_session.add(strategy)
        await db_session.commit()

        # Update strategy
        strategy.name = "Updated Name"
        strategy.config = {"type": "simple_threshold", "buy_threshold": 0.35}
        strategy.enabled = False

        await registry.update_strategy(strategy)

        # Verify update
        retrieved = await registry.get_strategy("update_test")
        assert retrieved is not None
        assert retrieved.name == "Updated Name"
        assert retrieved.config == {"type": "simple_threshold", "buy_threshold": 0.35}
        assert retrieved.enabled is False
