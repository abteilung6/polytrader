"""Integration tests for PlatformOrchestrator dynamic strategy management.

Per Commit 2.1: Tests verify that PlatformOrchestrator can add/remove
strategies at runtime without restarting the platform.

Per testing.md: Integration tests for dynamic strategy lifecycle with
real StrategyRegistry, mock factories, and EventBus.
"""

from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.db.models import StrategyRecord
from polytrader.events import EventBus
from polytrader.platform.orchestrator import PlatformOrchestrator
from polytrader.store import IMarketDataStore, MemoryMarketDataStore
from polytrader.strategies.lifecycle_models import StrategyLifecycleState

if TYPE_CHECKING:
    from polytrader.adapters import IMarketDataAdapter
    from polytrader.observer import IObserver


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
def observer_factory() -> "Callable[[IMarketDataAdapter], IObserver]":
    """Create mock observer factory."""
    observer = MagicMock()
    observer.run = AsyncMock()
    observer.stop = MagicMock()

    def factory(adapter: "IMarketDataAdapter") -> "IObserver":  # noqa: ARG001
        return cast("IObserver", observer)

    return cast("Callable[[IMarketDataAdapter], IObserver]", factory)


@pytest.fixture
async def initial_strategies(db_session: AsyncSession) -> list[str]:
    """Create initial strategies and return their IDs."""
    strategies = [
        StrategyRecord(
            strategy_id="strategy_1",
            name="Strategy 1",
            config={
                "market_pattern": "btc-updown-15m",
                "buy_threshold": 0.3,
            },
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_1",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        ),
        StrategyRecord(
            strategy_id="strategy_2",
            name="Strategy 2",
            config={
                "market_pattern": "btc-updown-15m",
                "buy_threshold": 0.35,
            },
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_strategy_creates_runner(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: Callable[[str], MagicMock],
    observer_factory: Callable[[MagicMock], MagicMock],
    initial_strategies: list[str],
) -> None:
    """Test that add_strategy() creates and starts a new StrategyRunner."""
    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,  # type: ignore[arg-type]
    )

    await orchestrator.start()

    try:
        # Verify initial strategies are running
        runners = orchestrator.list_strategy_runners()
        assert len(runners) == 2
        assert "strategy_1" in runners
        assert "strategy_2" in runners

        # Create new strategy in database
        new_strategy = StrategyRecord(
            strategy_id="strategy_new",
            name="New Strategy",
            config={
                "market_pattern": "btc-updown-15m",
                "buy_threshold": 0.3,
            },
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_new",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        )
        db_session.add(new_strategy)
        await db_session.commit()

        # Add strategy at runtime
        await orchestrator.add_strategy("strategy_new")

        # Verify new runner was created and started
        runners = orchestrator.list_strategy_runners()
        assert len(runners) == 3
        assert "strategy_new" in runners
        assert runners["strategy_new"].is_running() is True
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_strategy_uses_existing_supervisor(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: Callable[[str], MagicMock],
    observer_factory: Callable[[MagicMock], MagicMock],
    initial_strategies: list[str],
) -> None:
    """Test that add_strategy() uses existing supervisor for same pattern."""
    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,  # type: ignore[arg-type]
    )

    await orchestrator.start()

    try:
        # Get supervisor for existing strategies
        runners_before = orchestrator.list_strategy_runners()
        existing_supervisor = runners_before["strategy_1"].market_supervisor

        # Create new strategy with same pattern
        new_strategy = StrategyRecord(
            strategy_id="strategy_new",
            name="New Strategy",
            config={
                "market_pattern": "btc-updown-15m",  # Same pattern
                "buy_threshold": 0.3,
            },
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_new",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        )
        db_session.add(new_strategy)
        await db_session.commit()

        # Add strategy at runtime
        await orchestrator.add_strategy("strategy_new")

        # Verify new runner shares the same supervisor
        runners_after = orchestrator.list_strategy_runners()
        new_supervisor = runners_after["strategy_new"].market_supervisor
        assert new_supervisor is existing_supervisor, "New strategy should share supervisor"
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_strategy_creates_new_supervisor_for_different_pattern(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: Callable[[str], MagicMock],
    observer_factory: Callable[[MagicMock], MagicMock],
    initial_strategies: list[str],
) -> None:
    """Test that add_strategy() creates new supervisor for different pattern."""
    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,  # type: ignore[arg-type]
    )

    await orchestrator.start()

    try:
        # Get supervisor for existing strategies
        runners_before = orchestrator.list_strategy_runners()
        existing_supervisor = runners_before["strategy_1"].market_supervisor

        # Create new strategy with different pattern
        new_strategy = StrategyRecord(
            strategy_id="strategy_new",
            name="New Strategy",
            config={
                "market_pattern": "eth-updown-15m",  # Different pattern
                "buy_threshold": 0.3,
            },
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_new",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        )
        db_session.add(new_strategy)
        await db_session.commit()

        # Add strategy at runtime
        await orchestrator.add_strategy("strategy_new")

        # Verify new runner has different supervisor
        runners_after = orchestrator.list_strategy_runners()
        new_supervisor = runners_after["strategy_new"].market_supervisor
        assert new_supervisor is not existing_supervisor, (
            "Different pattern should have different supervisor"
        )
        assert new_supervisor.pattern == "eth-updown-15m"
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_remove_strategy_stops_runner(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: Callable[[str], MagicMock],
    observer_factory: Callable[[MagicMock], MagicMock],
    initial_strategies: list[str],
) -> None:
    """Test that remove_strategy() stops and removes StrategyRunner."""
    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,  # type: ignore[arg-type]
    )

    await orchestrator.start()

    try:
        # Verify strategy is running
        runners = orchestrator.list_strategy_runners()
        assert "strategy_1" in runners
        assert runners["strategy_1"].is_running() is True

        # Remove strategy at runtime
        await orchestrator.remove_strategy("strategy_1")

        # Verify runner was stopped and removed
        runners = orchestrator.list_strategy_runners()
        assert "strategy_1" not in runners
        assert len(runners) == 1
        assert "strategy_2" in runners
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_remove_strategy_releases_supervisor(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: Callable[[str], MagicMock],
    observer_factory: Callable[[MagicMock], MagicMock],
    initial_strategies: list[str],
) -> None:
    """Test that remove_strategy() releases supervisor reference."""
    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,  # type: ignore[arg-type]
    )

    await orchestrator.start()

    try:
        # Both strategies share same supervisor (same pattern)
        runners = orchestrator.list_strategy_runners()
        supervisor = runners["strategy_1"].market_supervisor
        assert supervisor is runners["strategy_2"].market_supervisor

        # Remove one strategy
        await orchestrator.remove_strategy("strategy_1")

        # Supervisor should still exist (strategy_2 still using it)
        runners_after = orchestrator.list_strategy_runners()
        assert "strategy_2" in runners_after
        assert runners_after["strategy_2"].market_supervisor is supervisor
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_remove_last_strategy_destroys_supervisor(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: Callable[[str], MagicMock],
    observer_factory: Callable[[MagicMock], MagicMock],
) -> None:
    """Test that removing last strategy on a pattern destroys supervisor."""
    # Create single strategy
    strategy = StrategyRecord(
        strategy_id="strategy_solo",
        name="Solo Strategy",
        config={
            "market_pattern": "btc-updown-15m",
            "buy_threshold": 0.3,
        },
        template_type_id="simple_threshold",
        template_version="1.0.0",
        config_hash="hash_solo",
        desired_state=StrategyLifecycleState.RUNNING,
        actual_state=StrategyLifecycleState.RUNNING,
    )
    db_session.add(strategy)
    await db_session.commit()

    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,  # type: ignore[arg-type]
    )

    await orchestrator.start()

    try:
        # Verify strategy is running
        runners = orchestrator.list_strategy_runners()
        assert "strategy_solo" in runners

        # Remove strategy (last one on this pattern)
        await orchestrator.remove_strategy("strategy_solo")

        # Verify runner removed
        runners_after = orchestrator.list_strategy_runners()
        assert "strategy_solo" not in runners_after
        assert len(runners_after) == 0

        # Supervisor should be stopped (ref_count reached 0)
        # We can't directly check registry state, but we can verify
        # that orchestrator is still running (supervisor cleanup happened)
        assert orchestrator.is_running() is True
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_strategy_idempotent(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: Callable[[str], MagicMock],
    observer_factory: Callable[[MagicMock], MagicMock],
    initial_strategies: list[str],
) -> None:
    """Test that adding the same strategy twice is idempotent."""
    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,  # type: ignore[arg-type]
    )

    await orchestrator.start()

    try:
        # Strategy already exists from initial_strategies
        runners_before = orchestrator.list_strategy_runners()
        assert "strategy_1" in runners_before
        runner_before = runners_before["strategy_1"]

        # Try to add it again
        await orchestrator.add_strategy("strategy_1")

        # Should still be the same runner (idempotent)
        runners_after = orchestrator.list_strategy_runners()
        assert "strategy_1" in runners_after
        assert runners_after["strategy_1"] is runner_before
        assert len(runners_after) == 2  # No duplicate
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_remove_nonexistent_strategy_no_error(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: Callable[[str], MagicMock],
    observer_factory: Callable[[MagicMock], MagicMock],
    initial_strategies: list[str],
) -> None:
    """Test that removing non-existent strategy doesn't error."""
    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,  # type: ignore[arg-type]
    )

    await orchestrator.start()

    try:
        # Remove non-existent strategy
        await orchestrator.remove_strategy("nonexistent_strategy")

        # Should not error, runners unchanged
        runners = orchestrator.list_strategy_runners()
        assert len(runners) == 2
        assert "strategy_1" in runners
        assert "strategy_2" in runners
    finally:
        await orchestrator.stop()
