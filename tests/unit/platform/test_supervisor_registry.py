"""Unit tests for MarketSupervisorRegistry.

Per Commit 1.2: Tests for MarketSupervisorRegistry with reference counting.
Tests verify that registry correctly manages shared MarketSupervisor instances.

Per unit_testing_technical.md:
- Deterministic tests (no time, no randomness)
- Fully typed
- Use factories for domain objects
- Test all code paths: get_or_create, release, stop_all, ref counting
"""

import asyncio
from collections.abc import Callable

import pytest

from polytrader.adapters import IMarketDataAdapter
from polytrader.events import EventBus
from polytrader.market_discovery import IMarketDiscoveryService
from polytrader.observer import IObserver
from polytrader.platform.supervisor_registry import MarketSupervisorRegistry
from polytrader.store import IMarketDataStore
from polytrader.supervisor.market import MarketSupervisor


class FakeAdapter(IMarketDataAdapter):
    """Fake adapter for testing."""

    def __init__(self, market_slug: str) -> None:
        self.market_slug: str = market_slug
        self._running = False

    async def ticks(self):
        """Yield market ticks (empty for test)."""
        self._running = True
        while self._running:
            await asyncio.sleep(0.1)
            yield None

    def stop(self) -> None:
        """Stop adapter."""
        self._running = False


class FakeObserver(IObserver):
    """Fake observer for testing."""

    def __init__(self, bus: EventBus, adapter: IMarketDataAdapter, store: IMarketDataStore) -> None:
        self.bus = bus
        self.adapter = adapter
        self.store = store
        self._running = False

    async def run(self) -> None:
        """Run observer."""
        self._running = True
        while self._running:
            await asyncio.sleep(0.1)

    def stop(self) -> None:
        """Stop observer."""
        self._running = False


class FakeDiscoveryService(IMarketDiscoveryService):
    """Fake discovery service for testing."""

    def __init__(self, initial_market: str | None = None) -> None:
        self.initial_market = initial_market
        self.current_market = initial_market

    async def get_current_market(self, pattern: str) -> str | None:
        """Get current market."""
        return self.current_market

    async def get_next_market(self, pattern: str) -> str | None:
        """Get next market."""
        return None


@pytest.fixture
def bus() -> EventBus:
    """Create event bus for tests."""
    return EventBus()


@pytest.fixture
def store() -> IMarketDataStore:
    """Create market data store for tests."""
    from polytrader.store import MemoryMarketDataStore

    return MemoryMarketDataStore()


@pytest.fixture
def discovery_service() -> FakeDiscoveryService:
    """Create discovery service for tests."""
    return FakeDiscoveryService(initial_market="test-market-1")


@pytest.fixture
def adapter_factory() -> Callable[[str], FakeAdapter]:
    """Create adapter factory for tests."""

    def factory(slug: str) -> FakeAdapter:
        return FakeAdapter(slug)

    return factory


@pytest.fixture
def observer_factory(
    bus: EventBus, store: IMarketDataStore
) -> Callable[[IMarketDataAdapter], FakeObserver]:
    """Create observer factory for tests."""

    def factory(adapter: IMarketDataAdapter) -> FakeObserver:
        return FakeObserver(bus, adapter, store)

    return factory


@pytest.fixture
def registry(
    discovery_service: FakeDiscoveryService,
    adapter_factory: Callable[[str], FakeAdapter],
    observer_factory: Callable[[IMarketDataAdapter], FakeObserver],
    bus: EventBus,
    store: IMarketDataStore,
) -> MarketSupervisorRegistry:
    """Create MarketSupervisorRegistry for tests."""
    return MarketSupervisorRegistry(
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        bus=bus,
        store=store,
    )


@pytest.mark.asyncio
async def test_get_or_create_creates_supervisor(
    registry: MarketSupervisorRegistry,
) -> None:
    """Test that first call to get_or_create creates supervisor."""
    pattern = "test-pattern"

    supervisor = await registry.get_or_create(pattern)

    assert supervisor is not None
    assert isinstance(supervisor, MarketSupervisor)
    assert supervisor.pattern == pattern
    assert supervisor.strategy_factory is None  # Strategy-less mode
    assert registry.get_ref_count(pattern) == 1


@pytest.mark.asyncio
async def test_get_or_create_returns_existing(
    registry: MarketSupervisorRegistry,
) -> None:
    """Test that subsequent calls return same supervisor."""
    pattern = "test-pattern"

    supervisor1 = await registry.get_or_create(pattern)
    supervisor2 = await registry.get_or_create(pattern)

    assert supervisor1 is supervisor2  # Same instance
    assert registry.get_ref_count(pattern) == 2


@pytest.mark.asyncio
async def test_ref_count_increments(
    registry: MarketSupervisorRegistry,
) -> None:
    """Test that ref count increases on get_or_create."""
    pattern = "test-pattern"

    assert registry.get_ref_count(pattern) == 0

    await registry.get_or_create(pattern)
    assert registry.get_ref_count(pattern) == 1

    await registry.get_or_create(pattern)
    assert registry.get_ref_count(pattern) == 2

    await registry.get_or_create(pattern)
    assert registry.get_ref_count(pattern) == 3


@pytest.mark.asyncio
async def test_release_decrements_ref_count(
    registry: MarketSupervisorRegistry,
) -> None:
    """Test that ref count decreases on release."""
    pattern = "test-pattern"

    await registry.get_or_create(pattern)
    await registry.get_or_create(pattern)
    assert registry.get_ref_count(pattern) == 2

    await registry.release(pattern)
    assert registry.get_ref_count(pattern) == 1

    await registry.release(pattern)
    assert registry.get_ref_count(pattern) == 0


@pytest.mark.asyncio
async def test_release_destroys_on_zero(
    registry: MarketSupervisorRegistry,
) -> None:
    """Test that supervisor is destroyed when ref_count reaches 0."""
    pattern = "test-pattern"

    supervisor = await registry.get_or_create(pattern)
    assert registry.get_ref_count(pattern) == 1

    # Start supervisor to verify it's stopped
    await supervisor.start()
    assert supervisor._running is True

    await registry.release(pattern)
    assert registry.get_ref_count(pattern) == 0

    # Supervisor should be stopped and removed
    # Verify by trying to get it again (should create new one)
    supervisor2 = await registry.get_or_create(pattern)
    assert supervisor2 is not supervisor  # Different instance


@pytest.mark.asyncio
async def test_release_idempotent(
    registry: MarketSupervisorRegistry,
) -> None:
    """Test that multiple releases don't error."""
    pattern = "test-pattern"

    await registry.get_or_create(pattern)
    await registry.release(pattern)
    assert registry.get_ref_count(pattern) == 0

    # Release again (should not error)
    await registry.release(pattern)
    assert registry.get_ref_count(pattern) == 0

    # Release non-existent pattern (should not error)
    await registry.release("non-existent-pattern")
    assert registry.get_ref_count("non-existent-pattern") == 0


@pytest.mark.asyncio
async def test_stop_all_cleans_up(
    registry: MarketSupervisorRegistry,
) -> None:
    """Test that stop_all() stops all supervisors."""
    pattern1 = "pattern-1"
    pattern2 = "pattern-2"

    supervisor1 = await registry.get_or_create(pattern1)
    supervisor2 = await registry.get_or_create(pattern2)

    await supervisor1.start()
    await supervisor2.start()

    assert supervisor1._running is True
    assert supervisor2._running is True

    await registry.stop_all()

    # Supervisors should be stopped
    assert supervisor1._running is False
    assert supervisor2._running is False

    # Registry should be empty
    assert registry.get_ref_count(pattern1) == 0
    assert registry.get_ref_count(pattern2) == 0


@pytest.mark.asyncio
async def test_concurrent_get_or_create(
    registry: MarketSupervisorRegistry,
) -> None:
    """Test that multiple concurrent calls handled correctly."""
    pattern = "test-pattern"

    # Create multiple tasks that call get_or_create concurrently
    tasks = [registry.get_or_create(pattern) for _ in range(10)]
    supervisors = await asyncio.gather(*tasks)

    # All should return the same supervisor instance
    first_supervisor = supervisors[0]
    assert all(s is first_supervisor for s in supervisors)

    # Ref count should be correct
    assert registry.get_ref_count(pattern) == 10


@pytest.mark.asyncio
async def test_multiple_patterns_separate_supervisors(
    registry: MarketSupervisorRegistry,
) -> None:
    """Test that different patterns get separate supervisors."""
    pattern1 = "pattern-1"
    pattern2 = "pattern-2"

    supervisor1 = await registry.get_or_create(pattern1)
    supervisor2 = await registry.get_or_create(pattern2)

    assert supervisor1 is not supervisor2
    assert supervisor1.pattern == pattern1
    assert supervisor2.pattern == pattern2
    assert registry.get_ref_count(pattern1) == 1
    assert registry.get_ref_count(pattern2) == 1


@pytest.mark.asyncio
async def test_registry_creates_strategy_less_supervisor(
    registry: MarketSupervisorRegistry,
) -> None:
    """Test that registry creates supervisors in strategy-less mode."""
    pattern = "test-pattern"

    supervisor = await registry.get_or_create(pattern)

    # Verify strategy-less mode
    assert supervisor.strategy_factory is None
    assert supervisor.strategy is None

    # Start supervisor and verify no strategy is created
    await supervisor.start()
    await asyncio.sleep(0.05)  # Allow transition to complete

    assert supervisor.strategy is None
    assert supervisor._strategy_evaluation_task is None
    assert supervisor._strategy_background_task is None

    supervisor.stop()
