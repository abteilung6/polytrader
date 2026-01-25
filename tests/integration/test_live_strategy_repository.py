"""Integration tests for LiveStrategyRepository.

Tests verify that LiveStrategyRepository provides correct operations
for live strategy activation using real database.
"""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.db.models import StrategyRecord
from polytrader.platform.control import LiveStrategyRepository


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
async def repository(db_session: AsyncSession) -> LiveStrategyRepository:
    """Create LiveStrategyRepository for testing."""
    return LiveStrategyRepository(db_session)


@pytest.fixture
async def test_strategies(db_session: AsyncSession) -> list[str]:
    """Create test strategies and return their IDs."""
    from polytrader.strategies.lifecycle_models import StrategyLifecycleState

    strategies = [
        StrategyRecord(
            strategy_id="strategy_1",
            name="Strategy 1",
            config={"type": "simple_threshold"},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_1",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        ),
        StrategyRecord(
            strategy_id="strategy_2",
            name="Strategy 2",
            config={"type": "simple_threshold"},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_2",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        ),
    ]
    for strategy in strategies:
        db_session.add(strategy)
    await db_session.commit()
    return [s.strategy_id for s in strategies]


class TestListActive:
    """Test list_active() method."""

    @pytest.mark.asyncio
    async def test_list_active_returns_empty_set_initially(
        self, repository: LiveStrategyRepository
    ) -> None:
        """Test that list_active() returns empty set initially."""
        active = await repository.list_active()
        assert active == set()

    @pytest.mark.asyncio
    async def test_list_active_returns_correct_set_after_activate(
        self,
        repository: LiveStrategyRepository,
        test_strategies: list[str],
    ) -> None:
        """Test that list_active() returns correct set after activate."""
        # Activate first strategy
        await repository.activate(
            test_strategies[0],
            activated_by="operator",
            reason="Enable for testing",
        )

        active = await repository.list_active()
        assert active == {test_strategies[0]}

        # Activate second strategy
        await repository.activate(
            test_strategies[1],
            activated_by="operator",
            reason="Enable for testing",
        )

        active = await repository.list_active()
        assert active == {test_strategies[0], test_strategies[1]}


class TestActivate:
    """Test activate() method."""

    @pytest.mark.asyncio
    async def test_activate_adds_strategy_to_active_set(
        self,
        repository: LiveStrategyRepository,
        test_strategies: list[str],
    ) -> None:
        """Test that activate() adds strategy to active set."""
        await repository.activate(
            test_strategies[0],
            activated_by="operator",
            reason="Enable for testing",
        )

        active = await repository.list_active()
        assert test_strategies[0] in active

    @pytest.mark.asyncio
    async def test_activate_with_multiple_strategies(
        self,
        repository: LiveStrategyRepository,
        test_strategies: list[str],
    ) -> None:
        """Test activate/deactivate with multiple strategies."""
        # Activate both strategies
        await repository.activate(
            test_strategies[0],
            activated_by="operator",
            reason="Enable strategy 1",
        )
        await repository.activate(
            test_strategies[1],
            activated_by="operator",
            reason="Enable strategy 2",
        )

        active = await repository.list_active()
        assert active == {test_strategies[0], test_strategies[1]}

    @pytest.mark.asyncio
    async def test_activate_non_existent_strategy_fails(
        self, repository: LiveStrategyRepository
    ) -> None:
        """Test that activate() fails for non-existent strategy_id."""
        import sqlalchemy.exc

        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await repository.activate(
                "non_existent",
                activated_by="operator",
                reason="Should fail",
            )


class TestDeactivate:
    """Test deactivate() method."""

    @pytest.mark.asyncio
    async def test_deactivate_removes_strategy_from_active_set(
        self,
        repository: LiveStrategyRepository,
        test_strategies: list[str],
    ) -> None:
        """Test that deactivate() removes strategy from active set."""
        # Activate both strategies
        await repository.activate(
            test_strategies[0],
            activated_by="operator",
            reason="Enable strategy 1",
        )
        await repository.activate(
            test_strategies[1],
            activated_by="operator",
            reason="Enable strategy 2",
        )

        # Deactivate first strategy
        await repository.deactivate(
            test_strategies[0],
            activated_by="operator",
            reason="Disable strategy 1",
        )

        active = await repository.list_active()
        assert active == {test_strategies[1]}

    @pytest.mark.asyncio
    async def test_deactivate_handles_never_activated_strategy(
        self,
        repository: LiveStrategyRepository,
        test_strategies: list[str],
    ) -> None:
        """Test that deactivate() handles strategy that was never activated."""
        # Deactivate strategy that was never activated (should not fail)
        await repository.deactivate(
            test_strategies[0],
            activated_by="operator",
            reason="Deactivate never-activated strategy",
        )

        active = await repository.list_active()
        assert test_strategies[0] not in active
