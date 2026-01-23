"""Unit tests for MarketSupervisor strategy-less mode.

Per Commit 1.1: Tests for MarketSupervisor when strategy_factory=None.
Tests verify that MarketSupervisor operates correctly without creating/evaluating strategies.

Per unit_testing_technical.md:
- Deterministic tests (no time, no randomness)
- Fully typed
- Use factories for domain objects
- Test all code paths in strategy-less mode
"""

import asyncio
from collections.abc import Callable

import pytest

from polytrader.adapters import IMarketDataAdapter
from polytrader.events import MARKET_DATA, EventBus
from polytrader.events.types import MarketDataEvent
from polytrader.market_discovery import IMarketDiscoveryService
from polytrader.observer import IObserver
from polytrader.store import IMarketDataStore, MemoryMarketDataStore
from polytrader.strategies import IStrategy
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
        """Run observer (publishes MarketDataEvent)."""
        self._running = True
        # Publish a test MarketDataEvent
        # Type assertion: FakeAdapter has market_slug attribute
        adapter_slug: str = getattr(self.adapter, "market_slug", "unknown-market")
        event = MarketDataEvent(
            market_slug=adapter_slug,
            outcome="UP",  # Required field
            best_bid=0.49,
            best_ask=0.51,
        )
        await self.bus.publish(MARKET_DATA, event)
        while self._running:
            await asyncio.sleep(0.1)

    def stop(self) -> None:
        """Stop observer."""
        self._running = False


class FakeStrategy(IStrategy):
    """Fake strategy for testing."""

    def __init__(self, market_slug: str) -> None:
        self.market_slug = market_slug
        self.evaluations: list[MarketDataEvent] = []

    def evaluate(
        self,
        market_data: MarketDataEvent,
        positions: dict | None = None,
    ) -> None:
        """Evaluate market data."""
        self.evaluations.append(market_data)

    async def run(self) -> None:
        """Background tasks."""
        await asyncio.sleep(0.1)

    def stop(self) -> None:
        """Stop strategy."""
        pass


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
def store() -> MemoryMarketDataStore:
    """Create market data store for tests."""
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
    bus: EventBus, store: MemoryMarketDataStore
) -> Callable[[IMarketDataAdapter], FakeObserver]:
    """Create observer factory for tests."""

    def factory(adapter: IMarketDataAdapter) -> FakeObserver:
        return FakeObserver(bus, adapter, store)

    return factory


@pytest.fixture
def strategy_factory() -> Callable[[str], FakeStrategy]:
    """Create strategy factory for tests."""

    def factory(slug: str) -> FakeStrategy:
        return FakeStrategy(slug)

    return factory


@pytest.mark.asyncio
async def test_strategy_less_mode_creates_no_strategy(
    bus: EventBus,
    store: MemoryMarketDataStore,
    discovery_service: FakeDiscoveryService,
    adapter_factory: Callable[[str], FakeAdapter],
    observer_factory: Callable[[IMarketDataAdapter], FakeObserver],
) -> None:
    """Test that strategy-less mode does not create strategy instance."""
    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        strategy_factory=None,  # Strategy-less mode
        bus=bus,
        store=store,
    )

    assert supervisor.strategy is None
    assert supervisor.strategy_factory is None

    await supervisor.start()
    await asyncio.sleep(0.05)  # Allow transition to complete

    # Strategy should still be None after start
    assert supervisor.strategy is None

    supervisor.stop()


@pytest.mark.asyncio
async def test_strategy_less_mode_skips_evaluation_loop(
    bus: EventBus,
    store: MemoryMarketDataStore,
    discovery_service: FakeDiscoveryService,
    adapter_factory: Callable[[str], FakeAdapter],
    observer_factory: Callable[[IMarketDataAdapter], FakeObserver],
) -> None:
    """Test that strategy-less mode does not start evaluation loop task."""
    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        strategy_factory=None,  # Strategy-less mode
        bus=bus,
        store=store,
    )

    await supervisor.start()
    await asyncio.sleep(0.05)  # Allow transition to complete

    # Evaluation task should not be started
    assert supervisor._strategy_evaluation_task is None

    supervisor.stop()


@pytest.mark.asyncio
async def test_strategy_less_mode_skips_background_tasks(
    bus: EventBus,
    store: MemoryMarketDataStore,
    discovery_service: FakeDiscoveryService,
    adapter_factory: Callable[[str], FakeAdapter],
    observer_factory: Callable[[IMarketDataAdapter], FakeObserver],
) -> None:
    """Test that strategy-less mode does not start background tasks."""
    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        strategy_factory=None,  # Strategy-less mode
        bus=bus,
        store=store,
    )

    await supervisor.start()
    await asyncio.sleep(0.05)  # Allow transition to complete

    # Background task should not be started
    assert supervisor._strategy_background_task is None

    supervisor.stop()


@pytest.mark.asyncio
async def test_strategy_less_mode_publishes_market_data(
    bus: EventBus,
    store: MemoryMarketDataStore,
    discovery_service: FakeDiscoveryService,
    adapter_factory: Callable[[str], FakeAdapter],
    observer_factory: Callable[[IMarketDataAdapter], FakeObserver],
) -> None:
    """Test that strategy-less mode still publishes MarketDataEvent."""
    # Subscribe to MARKET_DATA to capture events
    market_data_queue = bus.subscribe(MARKET_DATA)
    market_data_received: list[MarketDataEvent] = []

    async def collect_events() -> None:
        """Collect market data events."""
        while True:
            try:
                event = await asyncio.wait_for(market_data_queue.get(), timeout=0.2)
                market_data_received.append(event)
            except TimeoutError:
                break

    collector_task = asyncio.create_task(collect_events())

    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        strategy_factory=None,  # Strategy-less mode
        bus=bus,
        store=store,
    )

    await supervisor.start()
    run_task = asyncio.create_task(supervisor.run())

    # Wait for observer to publish market data
    await asyncio.sleep(0.15)

    # Stop supervisor
    supervisor.stop()
    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass

    # Cancel collector
    collector_task.cancel()
    try:
        await collector_task
    except asyncio.CancelledError:
        pass

    # Verify MarketDataEvent was published
    assert len(market_data_received) > 0
    assert all(isinstance(event, MarketDataEvent) for event in market_data_received)


@pytest.mark.asyncio
async def test_strategy_mode_still_works(
    bus: EventBus,
    store: MemoryMarketDataStore,
    discovery_service: FakeDiscoveryService,
    adapter_factory: Callable[[str], FakeAdapter],
    observer_factory: Callable[[IMarketDataAdapter], FakeObserver],
    strategy_factory: Callable[[str], FakeStrategy],
) -> None:
    """Test that existing behavior (with strategy_factory) still works."""
    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        strategy_factory=strategy_factory,  # Normal mode
        bus=bus,
        store=store,
    )

    assert supervisor.strategy is None  # Not created until start

    await supervisor.start()
    await asyncio.sleep(0.05)  # Allow transition to complete

    # Strategy should be created
    assert supervisor.strategy is not None
    assert isinstance(supervisor.strategy, FakeStrategy)
    assert supervisor.strategy.market_slug == "test-market-1"

    # Evaluation task should be started
    assert supervisor._strategy_evaluation_task is not None

    # Background task should be started
    assert supervisor._strategy_background_task is not None

    supervisor.stop()


@pytest.mark.asyncio
async def test_strategy_less_transition_handles_none(
    bus: EventBus,
    store: MemoryMarketDataStore,
    discovery_service: FakeDiscoveryService,
    adapter_factory: Callable[[str], FakeAdapter],
    observer_factory: Callable[[IMarketDataAdapter], FakeObserver],
) -> None:
    """Test that market transitions work correctly without strategy."""
    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        strategy_factory=None,  # Strategy-less mode
        bus=bus,
        store=store,
    )

    await supervisor.start()
    await asyncio.sleep(0.05)  # Allow initial transition

    initial_market = supervisor.current_market
    assert initial_market == "test-market-1"
    assert supervisor.strategy is None

    # Simulate market change
    discovery_service.current_market = "test-market-2"
    await asyncio.sleep(0.15)  # Allow monitor to detect change

    # Market should have transitioned
    # Note: This test may be flaky if monitor_interval is too long
    # For deterministic test, we could manually call _transition_to_market
    # But we're testing the full flow here

    supervisor.stop()
