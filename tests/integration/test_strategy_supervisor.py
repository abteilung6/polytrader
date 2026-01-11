"""Integration tests for strategy + supervisor."""

import asyncio

import pytest

from polytrader.events import MARKET_DATA, SIGNALS, EventBus, MemoryEventStore
from polytrader.events.types import SignalEvent
from polytrader.store import MemoryMarketDataStore
from polytrader.strategies import IStrategy
from polytrader.supervisor import MarketSupervisor
from polytrader.types import MarketDataEvent, Outcome, Position

# Rebuild SignalEvent model to resolve forward references
# This is needed because SignalEvent uses Outcome which is a forward reference
SignalEvent.model_rebuild()


class SignalGeneratingStrategy(IStrategy):
    """Test strategy that generates signals."""

    def __init__(self, market_slug: str) -> None:
        self.market_slug = market_slug
        self._running = False
        self.evaluations: list[MarketDataEvent] = []

    def evaluate(
        self,
        market_data: MarketDataEvent,
        positions: dict[tuple[str, str], Position] | None = None,
    ) -> SignalEvent | None:
        """Generate signal if price < 0.30."""
        self.evaluations.append(market_data)

        # Simple rule: generate signal if price is attractive
        if market_data.mid < 0.30:
            outcome: Outcome = market_data.outcome  # Type hint for Pydantic
            return SignalEvent(
                market_slug=market_data.market_slug,
                outcome=outcome,
                p_up=0.85 if outcome == "UP" else 0.15,
                p_down=0.15 if outcome == "UP" else 0.85,
                edge=0.55,
                confidence=0.80,
                model_id="test_strategy",
                model_version="1.0.0",
                rationale=f"Price {market_data.mid:.4f} < 0.30",
                correlation_id=market_data.correlation_id,
            )
        return None

    async def run(self) -> None:
        """Optional background tasks (not needed for this strategy)."""
        self._running = True

    def stop(self) -> None:
        """Stop background tasks."""
        self._running = False


class FakeAdapter:
    """Fake adapter that emits market data events."""

    def __init__(self, market_slug: str) -> None:
        self.market_slug = market_slug
        self._running = False

    async def ticks(self):
        """Emit test market data events."""
        self._running = True
        count = 0
        while self._running and count < 3:
            await asyncio.sleep(0.05)
            yield MarketDataEvent(
                market_slug=self.market_slug,
                outcome="UP",
                best_bid=0.25,
                best_ask=0.30,
            )
            count += 1

    def stop(self) -> None:
        self._running = False


class FakeObserver:
    """Fake observer that publishes market data events."""

    def __init__(self, bus: EventBus, adapter, store) -> None:
        self.bus = bus
        self.adapter = adapter
        self.store = store
        self._running = False

    async def run(self) -> None:
        """Publish market data events from adapter."""
        self._running = True
        async for event in self.adapter.ticks():
            if not self._running:
                break
            self.store.add(event)
            await self.bus.publish(MARKET_DATA, event)

    def stop(self) -> None:
        self._running = False


class FakeDiscoveryService:
    """Fake discovery service."""

    def __init__(self, initial_market: str) -> None:
        self.current_market = initial_market

    async def get_current_market(self, pattern: str) -> str | None:
        return self.current_market

    async def get_next_market(self, pattern: str) -> str | None:
        """Get next market (not used in these tests)."""
        return None


@pytest.mark.asyncio
async def test_supervisor_evaluates_strategy_on_market_data() -> None:
    """Test that supervisor calls evaluate() on market data events."""
    bus = EventBus(store=MemoryEventStore())
    store = MemoryMarketDataStore()
    market_slug = "test-market-1"
    discovery = FakeDiscoveryService(initial_market=market_slug)

    def adapter_factory(slug: str):
        return FakeAdapter(slug)

    def observer_factory(adapter, bus=bus, store=store):
        return FakeObserver(bus, adapter, store)

    def strategy_factory(slug: str) -> IStrategy:
        return SignalGeneratingStrategy(slug)

    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=discovery,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        strategy_factory=strategy_factory,
        bus=bus,
        store=store,
        position_manager=None,  # No position manager in test
        monitor_interval=1.0,
    )

    # Subscribe to signals
    signals_published = []
    signals_queue = bus.subscribe(SIGNALS)

    async def collect_signals() -> None:
        """Collect signals."""
        try:
            while True:
                signal = await asyncio.wait_for(signals_queue.get(), timeout=0.5)
                signals_published.append(signal)
        except TimeoutError:
            pass

    collect_task = asyncio.create_task(collect_signals())
    await supervisor.start()
    supervisor_task = asyncio.create_task(supervisor.run())

    # Wait for evaluation
    await asyncio.sleep(0.3)

    # Verify strategy was evaluated
    assert supervisor.strategy is not None
    assert isinstance(supervisor.strategy, SignalGeneratingStrategy)
    assert len(supervisor.strategy.evaluations) > 0

    # Verify signals were published
    assert len(signals_published) > 0, "Expected at least one signal to be published"
    signal = signals_published[0]
    assert isinstance(signal, SignalEvent)
    assert signal.market_slug == market_slug
    assert signal.outcome == "UP"
    assert signal.p_up == 0.85
    assert signal.model_id == "test_strategy"

    supervisor.stop()
    supervisor_task.cancel()
    collect_task.cancel()

    try:
        await supervisor_task
    except asyncio.CancelledError:
        pass
    try:
        await collect_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_strategy_signal_published_to_portfolio() -> None:
    """Test that signals are published to portfolio layer (SIGNALS topic)."""
    bus = EventBus(store=MemoryEventStore())
    store = MemoryMarketDataStore()
    market_slug = "test-market-1"
    discovery = FakeDiscoveryService(initial_market=market_slug)

    def adapter_factory(slug: str):
        return FakeAdapter(slug)

    def observer_factory(adapter, bus=bus, store=store):
        return FakeObserver(bus, adapter, store)

    def strategy_factory(slug: str) -> IStrategy:
        return SignalGeneratingStrategy(slug)

    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=discovery,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        strategy_factory=strategy_factory,
        bus=bus,
        store=store,
    )

    # Subscribe to SIGNALS topic
    signals_received = []
    signals_queue = bus.subscribe(SIGNALS)

    async def collect_signals() -> None:
        """Collect signals from SIGNALS topic."""
        try:
            while True:
                signal = await asyncio.wait_for(signals_queue.get(), timeout=0.5)
                signals_received.append(signal)
        except TimeoutError:
            pass

    collect_task = asyncio.create_task(collect_signals())
    await supervisor.start()
    supervisor_task = asyncio.create_task(supervisor.run())

    # Wait for signals
    await asyncio.sleep(0.3)

    # Verify signals were published to SIGNALS topic
    assert len(signals_received) > 0
    for signal in signals_received:
        assert isinstance(signal, SignalEvent)
        assert signal.source.value == "strategy"

    supervisor.stop()
    supervisor_task.cancel()
    collect_task.cancel()

    try:
        await supervisor_task
    except asyncio.CancelledError:
        pass
    try:
        await collect_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_strategy_evaluation_latency() -> None:
    """Test that evaluation is fast (< 1ms for simple strategies)."""
    import time

    strategy = SignalGeneratingStrategy("test-market")
    event = MarketDataEvent(
        market_slug="test-market",
        outcome="UP",
        best_bid=0.25,
        best_ask=0.30,
    )

    # Benchmark evaluation
    latencies = []
    for _ in range(100):
        start = time.perf_counter()
        strategy.evaluate(event)
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

    avg_latency = sum(latencies) / len(latencies)
    max_latency = max(latencies)

    # Average should be < 1ms, max should be < 5ms (accounting for system variance)
    assert avg_latency < 1.0, f"Average latency {avg_latency:.3f}ms, expected < 1ms"
    assert max_latency < 5.0, f"Max latency {max_latency:.3f}ms, expected < 5ms"
