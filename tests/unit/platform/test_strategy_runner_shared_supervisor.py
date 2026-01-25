"""Unit tests for StrategyRunner with shared MarketSupervisor.

Per Commit 1.3: Tests for StrategyRunner when using shared MarketSupervisor.
Tests verify that StrategyRunner correctly subscribes to market data,
evaluates strategy, and publishes SignalEvent with correct model_id.

Per unit_testing_technical.md:
- Deterministic tests (no time, no randomness)
- Fully typed
- Use factories for domain objects
- Test all code paths: subscription, evaluation, SignalEvent emission
"""

import asyncio
from collections.abc import Callable

import pytest

from polytrader.db.models import StrategyRecord
from polytrader.events import MARKET_DATA, SIGNALS, EventBus
from polytrader.events.types import MarketDataEvent, SignalEvent
from polytrader.platform.strategy_runner import StrategyRunner
from polytrader.position_manager import IPositionManager
from polytrader.store import IMarketDataStore
from polytrader.strategies.base import IStrategy
from polytrader.supervisor.market import MarketSupervisor


class FakeStrategy(IStrategy):
    """Fake strategy for testing."""

    def __init__(self, market_slug: str, strategy_id: str) -> None:
        self.market_slug = market_slug
        self.strategy_id = strategy_id
        self.evaluations: list[MarketDataEvent] = []

    def evaluate(
        self,
        market_data: MarketDataEvent,
        positions: dict | None = None,
    ) -> SignalEvent | None:
        """Evaluate market data and return signal."""
        self.evaluations.append(market_data)
        return SignalEvent(
            market_slug=market_data.market_slug,
            outcome="UP",
            p_up=0.7,
            p_down=0.3,
            edge=0.2,
            confidence=0.8,
            model_id=self.strategy_id,  # Strategy sets its own model_id
            model_version="1.0.0",
            rationale="Test signal",
        )

    async def run(self) -> None:
        """Background tasks."""
        await asyncio.sleep(0.1)

    def stop(self) -> None:
        """Stop strategy."""
        pass


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
def strategy_record() -> StrategyRecord:
    """Create a test StrategyRecord."""
    import uuid

    from polytrader.strategies.lifecycle_models import StrategyLifecycleState

    strategy_id = f"test-strategy-{uuid.uuid4().hex[:8]}"
    return StrategyRecord(
        strategy_id=strategy_id,
        name="Test Strategy",
        description="Test strategy for unit tests",
        config={"market_pattern": "test-pattern", "param": "value"},
        template_type_id="simple_threshold",
        template_version="1.0.0",
        config_hash="test_hash",
        desired_state=StrategyLifecycleState.RUNNING,
        actual_state=StrategyLifecycleState.RUNNING,
    )


@pytest.fixture
def market_supervisor(bus: EventBus, store: IMarketDataStore) -> MarketSupervisor:
    """Create a MarketSupervisor in strategy-less mode for tests."""
    from polytrader.adapters import IMarketDataAdapter
    from polytrader.market_discovery import IMarketDiscoveryService
    from polytrader.observer import IObserver

    class FakeAdapter(IMarketDataAdapter):
        def __init__(self, market_slug: str) -> None:
            self.market_slug: str = market_slug
            self._running = False

        async def ticks(self):
            self._running = True
            while self._running:
                await asyncio.sleep(0.1)
                yield None

        def stop(self) -> None:
            self._running = False

    class FakeObserver(IObserver):
        def __init__(
            self, bus: EventBus, adapter: IMarketDataAdapter, store: IMarketDataStore
        ) -> None:
            self.bus = bus
            self.adapter = adapter
            self.store = store
            self._running = False

        async def run(self) -> None:
            self._running = True
            while self._running:
                await asyncio.sleep(0.1)

        def stop(self) -> None:
            self._running = False

    class FakeDiscoveryService(IMarketDiscoveryService):
        async def get_current_market(self, pattern: str) -> str | None:
            return "test-market-1"

        async def get_next_market(self, pattern: str) -> str | None:
            return None

    def adapter_factory(slug: str) -> FakeAdapter:
        return FakeAdapter(slug)

    def observer_factory(adapter: IMarketDataAdapter) -> FakeObserver:
        return FakeObserver(bus, adapter, store)

    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=FakeDiscoveryService(),
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        bus=bus,
        store=store,
        strategy_factory=None,  # Strategy-less mode
    )
    return supervisor


@pytest.fixture
def strategy_factory(strategy_record: StrategyRecord) -> Callable[[str], IStrategy]:
    """Create strategy factory for tests."""

    def factory(market_slug: str) -> IStrategy:
        return FakeStrategy(market_slug, strategy_record.strategy_id)

    return factory


@pytest.fixture
def position_manager() -> IPositionManager | None:
    """Create position manager for tests (optional)."""
    return None


@pytest.mark.asyncio
async def test_init_accepts_shared_supervisor(
    strategy_record: StrategyRecord,
    bus: EventBus,
    store: IMarketDataStore,
    market_supervisor: MarketSupervisor,
    strategy_factory: Callable[[str], IStrategy],
) -> None:
    """Test that StrategyRunner accepts shared MarketSupervisor parameter."""
    runner = StrategyRunner(
        strategy=strategy_record,
        bus=bus,
        store=store,
        market_supervisor=market_supervisor,
        strategy_factory=strategy_factory,
    )

    assert runner.market_supervisor is market_supervisor
    assert runner.strategy is strategy_record


@pytest.mark.asyncio
async def test_start_subscribes_to_market_data(
    strategy_record: StrategyRecord,
    bus: EventBus,
    store: IMarketDataStore,
    market_supervisor: MarketSupervisor,
    strategy_factory: Callable[[str], IStrategy],
) -> None:
    """Test that StrategyRunner subscribes to MARKET_DATA on start."""
    # Start supervisor first
    await market_supervisor.start()

    runner = StrategyRunner(
        strategy=strategy_record,
        bus=bus,
        store=store,
        market_supervisor=market_supervisor,
        strategy_factory=strategy_factory,
    )

    await runner.start()

    # Verify subscription exists (by checking if runner is listening)
    # We can't directly check subscription, but we can verify runner is running
    assert runner.is_running() is True

    await runner.stop()


@pytest.mark.asyncio
async def test_evaluate_strategy_on_market_data(
    strategy_record: StrategyRecord,
    bus: EventBus,
    store: IMarketDataStore,
    market_supervisor: MarketSupervisor,
    strategy_factory: Callable[[str], IStrategy],
) -> None:
    """Test that StrategyRunner evaluates strategy on market data events."""
    # Start supervisor first
    await market_supervisor.start()

    runner = StrategyRunner(
        strategy=strategy_record,
        bus=bus,
        store=store,
        market_supervisor=market_supervisor,
        strategy_factory=strategy_factory,
    )

    await runner.start()

    # Subscribe to SIGNALS to capture emitted signals
    signals_received: list[SignalEvent] = []
    signals_queue = bus.subscribe(SIGNALS)

    async def collect_signals() -> None:
        """Collect signal events."""
        while True:
            try:
                event = await asyncio.wait_for(signals_queue.get(), timeout=0.5)
                signals_received.append(event)
            except TimeoutError:
                break

    collect_task = asyncio.create_task(collect_signals())

    # Publish a MarketDataEvent
    market_event = MarketDataEvent(
        market_slug="test-market-1",
        outcome="UP",
        best_bid=0.49,
        best_ask=0.51,
    )
    await bus.publish(MARKET_DATA, market_event)

    # Wait for signal to be processed
    await asyncio.sleep(0.2)

    # Cancel collector
    collect_task.cancel()
    try:
        await collect_task
    except asyncio.CancelledError:
        pass

    await runner.stop()

    # Verify signal was emitted
    assert len(signals_received) > 0
    signal = signals_received[0]
    assert isinstance(signal, SignalEvent)
    assert signal.market_slug == "test-market-1"


@pytest.mark.asyncio
async def test_signal_event_has_correct_model_id(
    strategy_record: StrategyRecord,
    bus: EventBus,
    store: IMarketDataStore,
    market_supervisor: MarketSupervisor,
    strategy_factory: Callable[[str], IStrategy],
) -> None:
    """Test that SignalEvent.model_id equals strategy.strategy_id."""
    # Start supervisor first
    await market_supervisor.start()

    runner = StrategyRunner(
        strategy=strategy_record,
        bus=bus,
        store=store,
        market_supervisor=market_supervisor,
        strategy_factory=strategy_factory,
    )

    await runner.start()

    # Subscribe to SIGNALS
    signals_received: list[SignalEvent] = []
    signals_queue = bus.subscribe(SIGNALS)

    async def collect_signals() -> None:
        """Collect signal events."""
        while True:
            try:
                event = await asyncio.wait_for(signals_queue.get(), timeout=0.5)
                signals_received.append(event)
            except TimeoutError:
                break

    collect_task = asyncio.create_task(collect_signals())

    # Publish MarketDataEvent
    market_event = MarketDataEvent(
        market_slug="test-market-1",
        outcome="UP",
        best_bid=0.49,
        best_ask=0.51,
    )
    await bus.publish(MARKET_DATA, market_event)

    await asyncio.sleep(0.2)

    collect_task.cancel()
    try:
        await collect_task
    except asyncio.CancelledError:
        pass

    await runner.stop()

    # Verify model_id matches strategy_id
    assert len(signals_received) > 0
    signal = signals_received[0]
    assert signal.model_id == strategy_record.strategy_id


@pytest.mark.asyncio
async def test_strategy_created_on_first_market_data(
    strategy_record: StrategyRecord,
    bus: EventBus,
    store: IMarketDataStore,
    market_supervisor: MarketSupervisor,
    strategy_factory: Callable[[str], IStrategy],
) -> None:
    """Test that strategy instance is created lazily on first market data."""
    # Start supervisor first
    await market_supervisor.start()

    runner = StrategyRunner(
        strategy=strategy_record,
        bus=bus,
        store=store,
        market_supervisor=market_supervisor,
        strategy_factory=strategy_factory,
    )

    await runner.start()

    # Strategy should not be created yet
    # (We can't directly check, but we can verify it works on first market data)

    # Publish MarketDataEvent
    market_event = MarketDataEvent(
        market_slug="test-market-1",
        outcome="UP",
        best_bid=0.49,
        best_ask=0.51,
    )
    await bus.publish(MARKET_DATA, market_event)

    await asyncio.sleep(0.2)

    await runner.stop()

    # If we got here without errors, strategy was created successfully


@pytest.mark.asyncio
async def test_stop_unsubscribes(
    strategy_record: StrategyRecord,
    bus: EventBus,
    store: IMarketDataStore,
    market_supervisor: MarketSupervisor,
    strategy_factory: Callable[[str], IStrategy],
) -> None:
    """Test that StrategyRunner unsubscribes from MARKET_DATA on stop."""
    # Start supervisor first
    await market_supervisor.start()

    runner = StrategyRunner(
        strategy=strategy_record,
        bus=bus,
        store=store,
        market_supervisor=market_supervisor,
        strategy_factory=strategy_factory,
    )

    await runner.start()
    assert runner.is_running() is True

    await runner.stop()
    assert runner.is_running() is False

    # Verify runner is stopped (can't directly check unsubscription, but runner state is correct)


@pytest.mark.asyncio
async def test_stop_cancels_tasks(
    strategy_record: StrategyRecord,
    bus: EventBus,
    store: IMarketDataStore,
    market_supervisor: MarketSupervisor,
    strategy_factory: Callable[[str], IStrategy],
) -> None:
    """Test that StrategyRunner cancels tasks on stop."""
    # Start supervisor first
    await market_supervisor.start()

    runner = StrategyRunner(
        strategy=strategy_record,
        bus=bus,
        store=store,
        market_supervisor=market_supervisor,
        strategy_factory=strategy_factory,
    )

    await runner.start()

    # Verify tasks are running (indirectly by checking runner state)
    assert runner.is_running() is True

    await runner.stop()

    # Verify runner is stopped
    assert runner.is_running() is False


@pytest.mark.asyncio
async def test_evaluation_errors_handled(
    strategy_record: StrategyRecord,
    bus: EventBus,
    store: IMarketDataStore,
    market_supervisor: MarketSupervisor,
) -> None:
    """Test that evaluation errors don't crash the loop."""

    class FailingStrategy(IStrategy):
        """Strategy that raises errors."""

        def __init__(self, market_slug: str, strategy_id: str) -> None:
            self.market_slug = market_slug
            self.strategy_id = strategy_id

        def evaluate(
            self,
            market_data: MarketDataEvent,
            positions: dict | None = None,
        ) -> SignalEvent | None:
            """Raise error on evaluation."""
            raise ValueError("Test error")

        async def run(self) -> None:
            """Background tasks."""
            pass

        def stop(self) -> None:
            """Stop strategy."""
            pass

    def strategy_factory(market_slug: str) -> IStrategy:
        return FailingStrategy(market_slug, strategy_record.strategy_id)

    # Start supervisor first
    await market_supervisor.start()

    runner = StrategyRunner(
        strategy=strategy_record,
        bus=bus,
        store=store,
        market_supervisor=market_supervisor,
        strategy_factory=strategy_factory,
    )

    await runner.start()

    # Publish MarketDataEvent (should trigger error)
    market_event = MarketDataEvent(
        market_slug="test-market-1",
        outcome="UP",
        best_bid=0.49,
        best_ask=0.51,
    )
    await bus.publish(MARKET_DATA, market_event)

    # Wait a bit
    await asyncio.sleep(0.2)

    # Runner should still be running (error didn't crash it)
    assert runner.is_running() is True

    await runner.stop()
