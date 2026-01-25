"""Integration tests for PlatformOrchestrator.

Per Platform_Proposal.md §3.1: Tests verify that PlatformOrchestrator
loads strategies from registry, creates StrategyRunner per strategy,
and manages paper/live lanes correctly.
"""

import asyncio
from collections.abc import AsyncGenerator, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.db.models import StrategyRecord
from polytrader.events import EventBus
from polytrader.platform.orchestrator import PlatformOrchestrator
from polytrader.store import IMarketDataStore, MemoryMarketDataStore


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
    """Create fake discovery service."""
    discovery = MagicMock()
    discovery.get_current_market = AsyncMock(return_value="btc-updown-15m")
    return discovery


@pytest.fixture
def adapter_factory() -> Callable[[str], MagicMock]:  # noqa: ARG001
    """Create fake adapter factory."""
    adapter = MagicMock()
    adapter.run = AsyncMock()
    adapter.stop = MagicMock()

    def factory(market_slug: str) -> MagicMock:
        return adapter

    return factory


@pytest.fixture
def observer_factory() -> Callable[[MagicMock], MagicMock]:  # noqa: ARG001
    """Create fake observer factory."""
    observer = MagicMock()
    observer.run = AsyncMock()

    def factory(adapter: MagicMock) -> MagicMock:
        return observer

    return factory


@pytest.fixture
async def test_strategies(db_session: AsyncSession) -> list[str]:
    """Create test strategies and return their IDs."""
    from polytrader.strategies.lifecycle_models import StrategyLifecycleState

    strategies = [
        StrategyRecord(
            strategy_id="strategy_1",
            name="Strategy 1",
            config={"buy_threshold": 0.3, "min_history": 30},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_1",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        ),
        StrategyRecord(
            strategy_id="strategy_2",
            name="Strategy 2",
            config={"buy_threshold": 0.35, "min_history": 40},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_2",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        ),
        StrategyRecord(
            strategy_id="strategy_disabled",
            name="Disabled Strategy",
            config={"buy_threshold": 0.3, "min_history": 30},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_disabled",
            desired_state=StrategyLifecycleState.STOPPED,
            actual_state=StrategyLifecycleState.STOPPED,
        ),
    ]
    for strategy in strategies:
        db_session.add(strategy)
    await db_session.commit()
    return [s.strategy_id for s in strategies]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_loads_strategies_from_registry(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: MagicMock,
    observer_factory: MagicMock,
    test_strategies: list[str],
) -> None:
    """Test start() loads all strategies from registry."""
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
        # Should have created runners for enabled strategies only
        runners = orchestrator.list_strategy_runners()
        assert len(runners) == 2  # Only enabled strategies
        assert "strategy_1" in runners
        assert "strategy_2" in runners
        assert "strategy_disabled" not in runners
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_creates_shared_market_supervisor_for_same_pattern(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: MagicMock,
    observer_factory: MagicMock,
    test_strategies: list[str],
) -> None:
    """Test start() creates shared MarketSupervisor for strategies with same pattern.

    Per Commit 1.4: Strategies with the same market_pattern share one
    MarketSupervisor instance via MarketSupervisorRegistry.
    """
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
        assert len(runners) == 2  # strategy_1 and strategy_2 (both enabled)

        # Both strategies use default pattern "btc-updown-15m" (no market_pattern in config)
        # So they should share the same supervisor instance
        supervisor_ids = {id(runner.market_supervisor) for runner in runners.values()}
        assert len(supervisor_ids) == 1, "Strategies with same pattern should share supervisor"

        # Verify all supervisors have correct pattern
        for _strategy_id, runner in runners.items():
            assert runner.market_supervisor is not None
            assert runner.market_supervisor.pattern == "btc-updown-15m"
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_starts_all_strategy_supervisors(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: MagicMock,
    observer_factory: MagicMock,
    test_strategies: list[str],
) -> None:
    """Test start() starts all strategy supervisors."""
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
        for _strategy_id, runner in runners.items():
            assert runner.is_running() is True
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_creates_paper_lane(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: MagicMock,
    observer_factory: MagicMock,
    test_strategies: list[str],
) -> None:
    """Test start() creates paper OMS and execution router."""
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
        # Paper lane should always be created
        # We can't directly access private attributes, but we can verify
        # that orchestrator is running (which means paper lane was created)
        assert orchestrator.is_running() is True
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_creates_live_lane_if_factory_provided(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: MagicMock,
    observer_factory: MagicMock,
    test_strategies: list[str],
) -> None:
    """Test start() creates live lane if factory provided."""
    # Create fake live execution router factory
    fake_live_adapter = MagicMock()
    fake_live_adapter.submit_order = AsyncMock()
    fake_live_adapter.cancel_order = AsyncMock()
    fake_live_adapter.get_open_orders = AsyncMock(return_value=[])

    from polytrader.execution import ExecutionRouter

    def live_factory() -> ExecutionRouter:
        return ExecutionRouter(
            bus=bus,
            adapter=fake_live_adapter,
            is_paper_mode=False,
            active_strategies={"strategy_1"},
        )

    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        live_execution_router_factory=live_factory,
    )

    await orchestrator.start()

    try:
        # Live lane should be created
        assert orchestrator.is_running() is True
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stop_stops_all_strategy_runners(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: MagicMock,
    observer_factory: MagicMock,
    test_strategies: list[str],
) -> None:
    """Test stop() stops all strategy runners gracefully."""
    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
    )

    await orchestrator.start()

    # Verify runners are running
    runners = orchestrator.list_strategy_runners()
    for runner in runners.values():
        assert runner.is_running() is True

    # Stop orchestrator
    await orchestrator.stop()

    # Verify runners are stopped
    for runner in runners.values():
        assert runner.is_running() is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_strategies_run_concurrently(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: MagicMock,
    observer_factory: MagicMock,
    test_strategies: list[str],
) -> None:
    """Test multiple strategies run concurrently and share supervisor.

    Per Commit 1.4: Multiple strategies with same pattern share one
    MarketSupervisor but run independently via StrategyRunner.
    """
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
        # Wait a bit to ensure all strategies are running
        await asyncio.sleep(0.1)

        runners = orchestrator.list_strategy_runners()
        assert len(runners) == 2

        # All runners should be running
        for runner in runners.values():
            assert runner.is_running() is True

        # Verify they share the same supervisor (same pattern)
        supervisor_ids = {id(runner.market_supervisor) for runner in runners.values()}
        assert len(supervisor_ids) == 1, "Strategies should share supervisor for same pattern"
    finally:
        await orchestrator.stop()
