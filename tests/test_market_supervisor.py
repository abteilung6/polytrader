import asyncio

from polytrader.adapters import IMarketDataAdapter
from polytrader.events import MARKET_CHANGE, EventBus
from polytrader.market_discovery import IMarketDiscoveryService
from polytrader.models.protocol import ITradingModel
from polytrader.observer import IObserver
from polytrader.order_manager import IOrderManager
from polytrader.store import MemoryTickStore
from polytrader.supervisor import MarketSupervisor
from polytrader.types import MarketChangeEvent


class FakeAdapter(IMarketDataAdapter):
    def __init__(self, market_slug: str) -> None:
        self.market_slug = market_slug
        self._running = False

    async def ticks(self):
        self._running = True
        while self._running:
            await asyncio.sleep(0.1)
            yield None

    def stop(self) -> None:
        self._running = False


class FakeObserver(IObserver):
    def __init__(self, bus: EventBus, adapter: IMarketDataAdapter, store) -> None:
        self._running = False

    async def run(self) -> None:
        self._running = True
        while self._running:
            await asyncio.sleep(0.1)

    def stop(self) -> None:
        self._running = False


class FakeModel(ITradingModel):
    def __init__(self, market_slug: str) -> None:
        self.market_slug = market_slug
        self._running = False

    async def run(self) -> None:
        self._running = True
        while self._running:
            await asyncio.sleep(0.1)

    async def on_tick(self, tick) -> None:
        pass

    def stop(self) -> None:
        self._running = False


class FakeOrderManager(IOrderManager):
    def __init__(self) -> None:
        self._running = False

    async def run(self) -> None:
        self._running = True
        while self._running:
            await asyncio.sleep(0.1)

    def stop(self) -> None:
        self._running = False


class FakeDiscoveryService(IMarketDiscoveryService):
    def __init__(self, initial_market: str | None = None) -> None:
        self.initial_market = initial_market
        self.current_market = initial_market
        self.calls: list[tuple[str, str]] = []

    async def get_current_market(self, pattern: str) -> str | None:
        self.calls.append(("get_current_market", pattern))
        return self.current_market

    async def get_next_market(self, pattern: str) -> str | None:
        self.calls.append(("get_next_market", pattern))
        return None


async def test_supervisor_initializes_with_market() -> None:
    """Test supervisor initializes with a discovered market."""
    bus = EventBus()
    store = MemoryTickStore()
    discovery = FakeDiscoveryService(initial_market="test-market-1")

    def adapter_factory(slug: str) -> FakeAdapter:
        return FakeAdapter(slug)

    def observer_factory(adapter: IMarketDataAdapter) -> FakeObserver:
        return FakeObserver(bus, adapter, store)

    def model_factory(slug: str) -> FakeModel:
        return FakeModel(slug)

    def order_manager_factory() -> FakeOrderManager:
        return FakeOrderManager()

    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=discovery,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        model_factory=model_factory,
        order_manager_factory=order_manager_factory,
        bus=bus,
        store=store,
        monitor_interval=0.1,
    )

    assert supervisor.current_market is None

    task = asyncio.create_task(supervisor.run())
    await asyncio.sleep(0.05)

    assert supervisor.current_market == "test-market-1"
    assert supervisor.adapter is not None
    assert supervisor.observer is not None
    assert supervisor.model is not None
    assert supervisor.order_manager is not None

    supervisor.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_supervisor_transitions_on_market_change() -> None:
    """Test supervisor transitions when market changes."""
    bus = EventBus()
    store = MemoryTickStore()
    discovery = FakeDiscoveryService(initial_market="test-market-1")

    def adapter_factory(slug: str) -> FakeAdapter:
        return FakeAdapter(slug)

    def observer_factory(adapter: IMarketDataAdapter) -> FakeObserver:
        return FakeObserver(bus, adapter, store)

    def model_factory(slug: str) -> FakeModel:
        return FakeModel(slug)

    def order_manager_factory() -> FakeOrderManager:
        return FakeOrderManager()

    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=discovery,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        model_factory=model_factory,
        order_manager_factory=order_manager_factory,
        bus=bus,
        store=store,
        monitor_interval=0.1,
    )

    task = asyncio.create_task(supervisor.run())
    await asyncio.sleep(0.05)

    assert supervisor.current_market == "test-market-1"
    old_adapter = supervisor.adapter

    discovery.current_market = "test-market-2"
    await asyncio.sleep(0.15)

    assert supervisor.current_market == "test-market-2"
    assert supervisor.adapter is not None
    assert supervisor.adapter != old_adapter
    assert isinstance(supervisor.adapter, FakeAdapter)
    assert supervisor.adapter.market_slug == "test-market-2"

    supervisor.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_supervisor_publishes_market_change_events() -> None:
    """Test supervisor publishes market change events."""
    bus = EventBus()
    store = MemoryTickStore()
    discovery = FakeDiscoveryService(initial_market="test-market-1")

    def adapter_factory(slug: str) -> FakeAdapter:
        return FakeAdapter(slug)

    def observer_factory(adapter: IMarketDataAdapter) -> FakeObserver:
        return FakeObserver(bus, adapter, store)

    def model_factory(slug: str) -> FakeModel:
        return FakeModel(slug)

    def order_manager_factory() -> FakeOrderManager:
        return FakeOrderManager()

    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=discovery,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        model_factory=model_factory,
        order_manager_factory=order_manager_factory,
        bus=bus,
        store=store,
        monitor_interval=0.1,
    )

    change_queue = bus.subscribe(MARKET_CHANGE)

    task = asyncio.create_task(supervisor.run())
    await asyncio.sleep(0.05)

    event = await asyncio.wait_for(change_queue.get(), timeout=0.5)
    assert isinstance(event, MarketChangeEvent)
    assert event.new_market == "test-market-1"
    assert event.old_market is None

    discovery.current_market = "test-market-2"
    await asyncio.sleep(0.15)

    event = await asyncio.wait_for(change_queue.get(), timeout=0.5)
    assert isinstance(event, MarketChangeEvent)
    assert event.new_market == "test-market-2"
    assert event.old_market == "test-market-1"

    supervisor.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_supervisor_stops_components_on_transition() -> None:
    """Test supervisor stops old components before starting new ones."""
    bus = EventBus()
    store = MemoryTickStore()
    discovery = FakeDiscoveryService(initial_market="test-market-1")

    def adapter_factory(slug: str) -> FakeAdapter:
        return FakeAdapter(slug)

    def observer_factory(adapter: IMarketDataAdapter) -> FakeObserver:
        return FakeObserver(bus, adapter, store)

    def model_factory(slug: str) -> FakeModel:
        return FakeModel(slug)

    def order_manager_factory() -> FakeOrderManager:
        return FakeOrderManager()

    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=discovery,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        model_factory=model_factory,
        order_manager_factory=order_manager_factory,
        bus=bus,
        store=store,
        monitor_interval=0.1,
    )

    task = asyncio.create_task(supervisor.run())
    await asyncio.sleep(0.05)

    old_observer = supervisor.observer
    old_model = supervisor.model
    old_order_manager = supervisor.order_manager

    assert isinstance(old_observer, FakeObserver)
    assert isinstance(old_model, FakeModel)
    assert isinstance(old_order_manager, FakeOrderManager)
    assert old_observer._running
    assert old_model._running
    assert old_order_manager._running

    discovery.current_market = "test-market-2"
    await asyncio.sleep(0.15)

    assert not old_observer._running
    assert not old_model._running
    assert not old_order_manager._running

    assert supervisor.observer is not None
    assert supervisor.model is not None
    assert supervisor.order_manager is not None

    supervisor.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
