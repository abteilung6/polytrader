"""Integration tests for orchestrator strategy registration.

Per Commit 11: Verify that strategies are registered at orchestrator startup,
registry is available for factory creation, and no import-time side effects occur.

Per testing.mdc: Integration tests verify cross-component behavior.
"""

from collections.abc import AsyncGenerator, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.events import EventBus
from polytrader.platform.orchestrator import PlatformOrchestrator
from polytrader.store import IMarketDataStore, MemoryMarketDataStore
from polytrader.strategies.registry import StrategyRegistry as InMemoryStrategyRegistry


@pytest.fixture
async def db_session(
    postgres_test_url: str, postgres_db: None
) -> AsyncGenerator[AsyncSession, None]:
    """Provide SQLAlchemy session for tests."""
    from sqlalchemy import text

    sqlalchemy_url = postgres_test_url
    if sqlalchemy_url.startswith("postgresql://"):
        sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+psycopg://", 1)

    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        # Clean up strategy_instances table
        await session.execute(text("TRUNCATE TABLE strategy_instances CASCADE"))
        await session.commit()

        yield session

        # Cleanup
        await session.execute(text("TRUNCATE TABLE strategy_instances CASCADE"))
        await session.commit()

    await engine.dispose()


@pytest.fixture
def bus() -> EventBus:
    """Create EventBus for testing."""
    return EventBus()


@pytest.fixture
def store() -> IMarketDataStore:
    """Create market data store for testing."""
    return MemoryMarketDataStore()


@pytest.fixture
def discovery_service() -> MagicMock:
    """Create mock discovery service."""
    service = MagicMock()
    service.discover_markets = MagicMock(return_value=[])
    service.get_current_market = AsyncMock(return_value="btc-updown-15m")
    return service


@pytest.fixture
def adapter_factory() -> Callable[[str], MagicMock]:
    """Create mock adapter factory."""
    adapter = MagicMock()
    adapter.run = AsyncMock()
    adapter.stop = MagicMock()

    def factory(market_slug: str) -> MagicMock:  # noqa: ARG001
        return adapter

    return factory


@pytest.fixture
def observer_factory() -> Callable[[MagicMock], MagicMock]:
    """Create mock observer factory."""
    observer = MagicMock()
    observer.run = AsyncMock()

    def factory(adapter: MagicMock) -> MagicMock:  # noqa: ARG001
        return observer

    return factory


@pytest.mark.integration
@pytest.mark.asyncio
async def test_orchestrator_registers_strategies_on_startup(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: MagicMock,
    observer_factory: MagicMock,
) -> None:
    """Test that orchestrator registers strategies on startup.

    Per Commit 11: register_all_strategies() is called in start() method.
    """
    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
    )

    # Before start, registry should be None
    assert orchestrator._strategy_template_registry is None

    # Start orchestrator
    await orchestrator.start()

    try:
        # After start, registry should be initialized
        assert orchestrator._strategy_template_registry is not None

        # Registry should have registered templates
        templates = orchestrator._strategy_template_registry.list_templates()
        assert len(templates) > 0

        # Should have simple_threshold template registered
        template = orchestrator._strategy_template_registry.get("simple_threshold", "1.0.0")
        assert template.type_id == "simple_threshold"
        assert template.version == "1.0.0"
        assert template.name == "Simple Threshold Strategy"
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_orchestrator_registry_available_for_factory_creation(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: MagicMock,
    observer_factory: MagicMock,
) -> None:
    """Test that registry is available for factory creation.

    Per Commit 11: Registry stored in orchestrator is used by factory function.
    """
    from polytrader.db.models import StrategyRecord
    from polytrader.strategies.lifecycle_models import StrategyLifecycleState

    # Create a strategy instance in database
    strategy = StrategyRecord(
        strategy_id="test_strategy",
        name="Test Strategy",
        config={"buy_threshold": 0.3, "min_history": 30},
        template_type_id="simple_threshold",
        template_version="1.0.0",
        config_hash="test_hash",
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
        observer_factory=observer_factory,
    )

    await orchestrator.start()

    try:
        # Registry should be available
        assert orchestrator._strategy_template_registry is not None

        # Factory creation should work (uses registry)
        # This is tested indirectly through strategy runner creation
        # If factory creation fails, start() would raise an error
        runners = orchestrator.list_strategy_runners()
        # Strategy should have been created successfully
        assert "test_strategy" in runners
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_orchestrator_no_import_time_side_effects(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: MagicMock,
    observer_factory: MagicMock,
) -> None:
    """Test that importing orchestrator doesn't cause side effects.

    Per Commit 11: No import-time registration. Registration only happens
    when start() is called.
    """
    # Import should not register strategies
    # We verify this by checking that a fresh registry is empty
    fresh_registry = InMemoryStrategyRegistry()
    templates_before = fresh_registry.list_templates()
    assert len(templates_before) == 0

    # Creating orchestrator should not register strategies
    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
    )

    # Registry should still be None before start
    assert orchestrator._strategy_template_registry is None

    # Only after start() should strategies be registered
    await orchestrator.start()

    try:
        assert orchestrator._strategy_template_registry is not None
        templates_after = orchestrator._strategy_template_registry.list_templates()
        assert len(templates_after) > 0
    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_orchestrator_registry_contains_expected_templates(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: MagicMock,
    observer_factory: MagicMock,
) -> None:
    """Test that registry contains expected strategy templates.

    Per Commit 11: All strategies registered via register_all_strategies()
    should be available in the registry.
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
        registry = orchestrator._strategy_template_registry
        assert registry is not None

        # Should have simple_threshold template
        assert registry.has_template("simple_threshold", "1.0.0")

        # Template should have correct properties
        template = registry.get("simple_threshold", "1.0.0")
        assert template.type_id == "simple_threshold"
        assert template.version == "1.0.0"
        assert template.name == "Simple Threshold Strategy"
        assert "BUY signals" in template.description
        assert template.parameter_schema is not None
        assert "buy_threshold" in template.parameter_schema.parameters
        assert "min_history" in template.parameter_schema.parameters
        assert template.factory is not None
        assert callable(template.factory)
    finally:
        await orchestrator.stop()
