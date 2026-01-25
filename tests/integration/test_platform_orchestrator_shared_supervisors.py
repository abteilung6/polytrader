"""Integration tests for PlatformOrchestrator with shared MarketSupervisors.

Per Commit 1.4: Tests verify that PlatformOrchestrator correctly groups
strategies by market_pattern and creates shared MarketSupervisor instances.

Per testing.md: Integration tests for multi-strategy scenarios with
real StrategyRegistry, mock factories, and EventBus.
"""

from collections.abc import AsyncGenerator, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.db.models import StrategyRecord
from polytrader.events import EventBus
from polytrader.platform.orchestrator import PlatformOrchestrator
from polytrader.store import IMarketDataStore, MemoryMarketDataStore
from polytrader.strategies.lifecycle_models import StrategyLifecycleState


@pytest.fixture
async def db_session(
    postgres_test_url: str, postgres_db: None
) -> AsyncGenerator[AsyncSession, None]:
    """Provide SQLAlchemy session for tests."""
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
def bus() -> EventBus:
    """Create event bus for tests."""
    return EventBus()


@pytest.fixture
def store() -> IMarketDataStore:
    """Create market data store for tests."""
    return MemoryMarketDataStore()


@pytest.fixture
def discovery_service() -> MagicMock:
    """Create mock discovery service."""
    discovery = MagicMock()
    discovery.get_current_market = AsyncMock(return_value="test-market-1")
    discovery.get_next_market = AsyncMock(return_value=None)
    return discovery


@pytest.fixture
def adapter_factory() -> Callable[[str], MagicMock]:
    """Create mock adapter factory."""
    adapter = MagicMock()
    adapter.market_slug = "test-market-1"
    adapter.ticks = AsyncMock(return_value=iter([]))
    adapter.stop = MagicMock()

    def factory(slug: str) -> MagicMock:
        adapter.market_slug = slug
        return adapter

    return factory


@pytest.fixture
def observer_factory() -> Callable[[MagicMock], MagicMock]:
    """Create mock observer factory."""
    observer = MagicMock()
    observer.run = AsyncMock()
    observer.stop = MagicMock()

    def factory(adapter: MagicMock) -> MagicMock:  # noqa: ARG001
        return observer

    return factory


@pytest.mark.integration
@pytest.mark.asyncio
async def test_orchestrator_groups_strategies_by_pattern(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: MagicMock,
    observer_factory: MagicMock,
) -> None:
    """Test that orchestrator groups strategies by market_pattern correctly."""
    # Create strategies with different patterns
    strategies = [
        StrategyRecord(
            strategy_id="strategy_pattern_a_1",
            name="Strategy Pattern A 1",
            config={
                "market_pattern": "pattern-a",
                "buy_threshold": 0.3,
            },
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_a_1",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        ),
        StrategyRecord(
            strategy_id="strategy_pattern_a_2",
            name="Strategy Pattern A 2",
            config={
                "market_pattern": "pattern-a",
                "buy_threshold": 0.35,
            },
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_a_2",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        ),
        StrategyRecord(
            strategy_id="strategy_pattern_b_1",
            name="Strategy Pattern B 1",
            config={
                "market_pattern": "pattern-b",
                "buy_threshold": 0.3,
            },
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_b_1",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        ),
    ]

    for strategy in strategies:
        db_session.add(strategy)
    await db_session.commit()

    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
    )

    await orchestrator.start()

    try:
        runners = orchestrator.list_strategy_runners()
        assert len(runners) == 3

        # Verify all runners have supervisors
        supervisors_by_pattern: dict[str, set] = {}
        for runner in runners.values():
            pattern = runner.market_supervisor.pattern
            if pattern not in supervisors_by_pattern:
                supervisors_by_pattern[pattern] = set()
            supervisors_by_pattern[pattern].add(id(runner.market_supervisor))

        # Pattern A should have 2 strategies sharing 1 supervisor
        assert "pattern-a" in supervisors_by_pattern
        assert len(supervisors_by_pattern["pattern-a"]) == 1

        # Pattern B should have 1 strategy with its own supervisor
        assert "pattern-b" in supervisors_by_pattern
        assert len(supervisors_by_pattern["pattern-b"]) == 1
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_orchestrator_creates_one_supervisor_per_pattern(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: MagicMock,
    observer_factory: MagicMock,
) -> None:
    """Test that orchestrator creates exactly one supervisor per unique pattern."""
    # Create 5 strategies with same pattern
    strategies = [
        StrategyRecord(
            strategy_id=f"strategy_{i}",
            name=f"Strategy {i}",
            config={
                "market_pattern": "btc-updown-15m",
                "buy_threshold": 0.3,
            },
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash=f"hash_{i}",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        )
        for i in range(5)
    ]

    for strategy in strategies:
        db_session.add(strategy)
    await db_session.commit()

    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
    )

    await orchestrator.start()

    try:
        runners = orchestrator.list_strategy_runners()
        assert len(runners) == 5

        # All runners should share the same supervisor instance
        supervisor_ids = {id(runner.market_supervisor) for runner in runners.values()}
        assert len(supervisor_ids) == 1, "All strategies should share one supervisor"

        # Verify all supervisors have the same pattern
        patterns = {runner.market_supervisor.pattern for runner in runners.values()}
        assert patterns == {"btc-updown-15m"}
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_orchestrator_passes_shared_supervisor_to_runners(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: MagicMock,
    observer_factory: MagicMock,
) -> None:
    """Test that runners receive shared supervisor instances."""
    # Create 3 strategies with same pattern
    strategies = [
        StrategyRecord(
            strategy_id=f"strategy_{i}",
            name=f"Strategy {i}",
            config={
                "market_pattern": "test-pattern",
                "buy_threshold": 0.3,
            },
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash=f"hash_{i}",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        )
        for i in range(3)
    ]

    for strategy in strategies:
        db_session.add(strategy)
    await db_session.commit()

    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
    )

    await orchestrator.start()

    try:
        runners = orchestrator.list_strategy_runners()
        assert len(runners) == 3

        # Get all supervisor instances
        supervisors = [runner.market_supervisor for runner in runners.values()]

        # All should be the same object (shared)
        assert all(supervisors[0] is supervisor for supervisor in supervisors)

        # Verify supervisor is in strategy-less mode (no strategy instance)
        assert supervisors[0].strategy is None
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_orchestrator_stop_releases_supervisors(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: MagicMock,
    observer_factory: MagicMock,
) -> None:
    """Test that orchestrator releases supervisors on stop."""
    strategies = [
        StrategyRecord(
            strategy_id="strategy_1",
            name="Strategy 1",
            config={
                "market_pattern": "test-pattern",
                "buy_threshold": 0.3,
            },
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_1",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        ),
    ]

    for strategy in strategies:
        db_session.add(strategy)
    await db_session.commit()

    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
    )

    await orchestrator.start()

    # Verify supervisor exists
    runners = orchestrator.list_strategy_runners()
    assert len(runners) == 1
    assert list(runners.values())[0].market_supervisor is not None

    # Stop orchestrator
    await orchestrator.stop()

    # Verify supervisor was stopped (registry manages lifecycle)
    # We can't directly check registry state, but we can verify orchestrator is stopped
    assert orchestrator.is_running() is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_strategies_same_pattern_share_supervisor(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: MagicMock,
    observer_factory: MagicMock,
) -> None:
    """Test that 10 strategies with same pattern share 1 supervisor."""
    # Create 10 strategies with same pattern
    strategies = [
        StrategyRecord(
            strategy_id=f"strategy_{i}",
            name=f"Strategy {i}",
            config={
                "market_pattern": "shared-pattern",
                "buy_threshold": 0.3,
            },
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash=f"hash_{i}",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        )
        for i in range(10)
    ]

    for strategy in strategies:
        db_session.add(strategy)
    await db_session.commit()

    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
    )

    await orchestrator.start()

    try:
        runners = orchestrator.list_strategy_runners()
        assert len(runners) == 10

        # All 10 strategies should share the same supervisor instance
        supervisor_ids = {id(runner.market_supervisor) for runner in runners.values()}
        assert len(supervisor_ids) == 1, "10 strategies should share 1 supervisor"

        # Verify supervisor pattern
        supervisor = list(runners.values())[0].market_supervisor
        assert supervisor.pattern == "shared-pattern"
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_strategies_different_patterns_separate_supervisors(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: MagicMock,
    observer_factory: MagicMock,
) -> None:
    """Test that strategies with different patterns get separate supervisors."""
    # Create strategies with 3 different patterns
    strategies = [
        StrategyRecord(
            strategy_id="strategy_pattern_1",
            name="Strategy Pattern 1",
            config={
                "market_pattern": "pattern-1",
                "buy_threshold": 0.3,
            },
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_pattern_1",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        ),
        StrategyRecord(
            strategy_id="strategy_pattern_2",
            name="Strategy Pattern 2",
            config={
                "market_pattern": "pattern-2",
                "buy_threshold": 0.3,
            },
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_pattern_2",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        ),
        StrategyRecord(
            strategy_id="strategy_pattern_3",
            name="Strategy Pattern 3",
            config={
                "market_pattern": "pattern-3",
                "buy_threshold": 0.3,
            },
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_pattern_3",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        ),
    ]

    for strategy in strategies:
        db_session.add(strategy)
    await db_session.commit()

    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
    )

    await orchestrator.start()

    try:
        runners = orchestrator.list_strategy_runners()
        assert len(runners) == 3

        # Each pattern should have its own supervisor
        supervisors_by_pattern: dict[str, object] = {}
        for runner in runners.values():
            pattern = runner.market_supervisor.pattern
            supervisor_id = id(runner.market_supervisor)
            if pattern not in supervisors_by_pattern:
                supervisors_by_pattern[pattern] = supervisor_id
            else:
                # Same pattern should share supervisor
                assert supervisors_by_pattern[pattern] == supervisor_id

        # Should have 3 different supervisors (one per pattern)
        unique_supervisors = set(supervisors_by_pattern.values())
        assert len(unique_supervisors) == 3, "3 patterns should have 3 separate supervisors"
    finally:
        await orchestrator.stop()
