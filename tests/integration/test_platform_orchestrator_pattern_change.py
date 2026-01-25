"""Integration tests for PlatformOrchestrator pattern change handling.

Per Commit 2.2: Tests verify that PlatformOrchestrator can handle
strategy pattern changes at runtime by migrating StrategyRunner to
a new supervisor gracefully.

Per testing.md: Integration tests for pattern migration with
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_strategy_pattern_migrates_runner(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: Callable[[str], MagicMock],
    observer_factory: Callable[[MagicMock], MagicMock],
) -> None:
    """Test that updating strategy pattern migrates runner to new supervisor."""
    # Create strategy with initial pattern
    strategy = StrategyRecord(
        strategy_id="strategy_migrate",
        name="Migrating Strategy",
        config={
            "type": "simple_threshold",
            "market_pattern": "btc-updown-15m",
            "buy_threshold": 0.3,
        },
        template_type_id="simple_threshold",
        template_version="1.0.0",
        config_hash="hash_migrate",
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
        # Verify strategy is running with initial pattern
        runners = orchestrator.list_strategy_runners()
        assert "strategy_migrate" in runners
        runner = runners["strategy_migrate"]
        old_supervisor = runner.market_supervisor
        assert old_supervisor.pattern == "btc-updown-15m"

        # Update strategy pattern in database
        strategy.config["market_pattern"] = "eth-updown-15m"
        await db_session.commit()

        # Update strategy in orchestrator (should detect pattern change)
        await orchestrator.update_strategy("strategy_migrate")

        # Verify runner migrated to new supervisor
        runners_after = orchestrator.list_strategy_runners()
        assert "strategy_migrate" in runners_after
        new_runner = runners_after["strategy_migrate"]
        new_supervisor = new_runner.market_supervisor
        assert new_supervisor.pattern == "eth-updown-15m"
        assert new_supervisor is not old_supervisor, "Should have different supervisor"
        assert new_runner.is_running() is True, "Runner should still be running"
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_strategy_pattern_releases_old_supervisor(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: Callable[[str], MagicMock],
    observer_factory: Callable[[MagicMock], MagicMock],
) -> None:
    """Test that pattern change releases old supervisor if no other strategies use it."""
    # Create two strategies with same pattern
    strategy1 = StrategyRecord(
        strategy_id="strategy_1",
        name="Strategy 1",
        config={
            "type": "simple_threshold",
            "market_pattern": "btc-updown-15m",
            "buy_threshold": 0.3,
        },
        template_type_id="simple_threshold",
        template_version="1.0.0",
        config_hash="hash_1",
        desired_state=StrategyLifecycleState.RUNNING,
        actual_state=StrategyLifecycleState.RUNNING,
    )
    strategy2 = StrategyRecord(
        strategy_id="strategy_2",
        name="Strategy 2",
        config={
            "type": "simple_threshold",
            "market_pattern": "btc-updown-15m",
            "buy_threshold": 0.35,
        },
        template_type_id="simple_threshold",
        template_version="1.0.0",
        config_hash="hash_2",
        desired_state=StrategyLifecycleState.RUNNING,
        actual_state=StrategyLifecycleState.RUNNING,
    )
    db_session.add(strategy1)
    db_session.add(strategy2)
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
        # Both strategies share same supervisor
        runners = orchestrator.list_strategy_runners()
        supervisor_btc = runners["strategy_1"].market_supervisor
        assert supervisor_btc is runners["strategy_2"].market_supervisor

        # Update strategy_1 to different pattern
        strategy1.config["market_pattern"] = "eth-updown-15m"
        await db_session.commit()
        await orchestrator.update_strategy("strategy_1")

        # strategy_1 should have new supervisor
        runners_after = orchestrator.list_strategy_runners()
        assert runners_after["strategy_1"].market_supervisor.pattern == "eth-updown-15m"
        assert runners_after["strategy_1"].market_supervisor is not supervisor_btc

        # strategy_2 should still use old supervisor (btc pattern)
        assert runners_after["strategy_2"].market_supervisor is supervisor_btc
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_strategy_pattern_joins_existing_supervisor(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: Callable[[str], MagicMock],
    observer_factory: Callable[[MagicMock], MagicMock],
) -> None:
    """Test that pattern change joins existing supervisor if other strategies use it."""
    # Create two strategies with different patterns
    strategy1 = StrategyRecord(
        strategy_id="strategy_1",
        name="Strategy 1",
        config={
            "type": "simple_threshold",
            "market_pattern": "btc-updown-15m",
            "buy_threshold": 0.3,
        },
        template_type_id="simple_threshold",
        template_version="1.0.0",
        config_hash="hash_1",
        desired_state=StrategyLifecycleState.RUNNING,
        actual_state=StrategyLifecycleState.RUNNING,
    )
    strategy2 = StrategyRecord(
        strategy_id="strategy_2",
        name="Strategy 2",
        config={
            "type": "simple_threshold",
            "market_pattern": "eth-updown-15m",
            "buy_threshold": 0.35,
        },
        template_type_id="simple_threshold",
        template_version="1.0.0",
        config_hash="hash_2",
        desired_state=StrategyLifecycleState.RUNNING,
        actual_state=StrategyLifecycleState.RUNNING,
    )
    db_session.add(strategy1)
    db_session.add(strategy2)
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
        # Strategies have different supervisors
        runners = orchestrator.list_strategy_runners()
        supervisor_eth = runners["strategy_2"].market_supervisor
        assert supervisor_eth.pattern == "eth-updown-15m"

        # Update strategy_1 to join strategy_2's pattern
        strategy1.config["market_pattern"] = "eth-updown-15m"
        await db_session.commit()
        await orchestrator.update_strategy("strategy_1")

        # Both strategies should share same supervisor now
        runners_after = orchestrator.list_strategy_runners()
        assert runners_after["strategy_1"].market_supervisor is supervisor_eth
        assert runners_after["strategy_2"].market_supervisor is supervisor_eth
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_strategy_no_pattern_change_no_migration(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: Callable[[str], MagicMock],
    observer_factory: Callable[[MagicMock], MagicMock],
) -> None:
    """Test that updating strategy without pattern change doesn't migrate runner."""
    # Create strategy
    strategy = StrategyRecord(
        strategy_id="strategy_no_change",
        name="No Change Strategy",
        config={
            "type": "simple_threshold",
            "market_pattern": "btc-updown-15m",
            "buy_threshold": 0.3,
        },
        template_type_id="simple_threshold",
        template_version="1.0.0",
        config_hash="hash_no_change",
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
        # Get initial runner and supervisor
        runners = orchestrator.list_strategy_runners()
        runner_before = runners["strategy_no_change"]
        supervisor_before = runner_before.market_supervisor

        # Update strategy config (but not pattern)
        strategy.config["buy_threshold"] = 0.35
        await db_session.commit()
        await orchestrator.update_strategy("strategy_no_change")

        # Runner and supervisor should be unchanged
        runners_after = orchestrator.list_strategy_runners()
        runner_after = runners_after["strategy_no_change"]
        supervisor_after = runner_after.market_supervisor
        assert runner_after is runner_before, "Runner should be same instance"
        assert supervisor_after is supervisor_before, "Supervisor should be same instance"
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_nonexistent_strategy_raises_error(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: Callable[[str], MagicMock],
    observer_factory: Callable[[MagicMock], MagicMock],
) -> None:
    """Test that updating non-existent strategy raises error."""
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
        # Try to update non-existent strategy
        with pytest.raises(ValueError, match="Strategy not found"):
            await orchestrator.update_strategy("nonexistent_strategy")
    finally:
        await orchestrator.stop()
