import asyncio
from collections.abc import AsyncIterator

from polytrader.adapters import IMarketDataAdapter
from polytrader.events import MARKET_DATA, EventBus
from polytrader.observer import Observer
from polytrader.store import MemoryMarketDataStore
from polytrader.types import MarketDataEvent


class FakeMarketDataAdapter(IMarketDataAdapter):
    def __init__(self, events: list[MarketDataEvent]) -> None:
        self._events = events

    async def ticks(self) -> AsyncIterator[MarketDataEvent]:
        for event in self._events:
            yield event


async def test_observer_publishes_ticks() -> None:
    bus = EventBus()
    store = MemoryMarketDataStore()
    event1 = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.49, best_ask=0.51)
    event2 = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.50, best_ask=0.52)

    adapter = FakeMarketDataAdapter([event1, event2])
    observer = Observer(bus, adapter, store)

    queue = bus.subscribe(MARKET_DATA)

    task = asyncio.create_task(observer.run())

    received_event1 = await asyncio.wait_for(queue.get(), timeout=1.0)
    received_event2 = await asyncio.wait_for(queue.get(), timeout=1.0)

    assert received_event1 == event1
    assert received_event2 == event2

    assert store.latest("test", "UP") == event2
    assert store.history("test", "UP") == [event1, event2]

    await asyncio.wait_for(task, timeout=1.0)


async def test_observer_multiple_subscribers() -> None:
    bus = EventBus()
    store = MemoryMarketDataStore()
    event = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.49, best_ask=0.51)

    adapter = FakeMarketDataAdapter([event])
    observer = Observer(bus, adapter, store)

    queue1 = bus.subscribe(MARKET_DATA)
    queue2 = bus.subscribe(MARKET_DATA)

    task = asyncio.create_task(observer.run())

    received1 = await asyncio.wait_for(queue1.get(), timeout=1.0)
    received2 = await asyncio.wait_for(queue2.get(), timeout=1.0)

    assert received1 == event
    assert received2 == event

    assert store.latest("test", "UP") == event

    await asyncio.wait_for(task, timeout=1.0)


async def test_observer_stops_when_stopped() -> None:
    bus = EventBus()
    store = MemoryMarketDataStore()
    event1 = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.49, best_ask=0.51)

    async def slow_events():
        yield event1
        await asyncio.sleep(0.1)
        yield MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.50, best_ask=0.52)

    class SlowAdapter:
        async def ticks(self):
            async for event in slow_events():
                yield event

    adapter = SlowAdapter()
    observer = Observer(bus, adapter, store)

    queue = bus.subscribe(MARKET_DATA)

    task = asyncio.create_task(observer.run())
    await asyncio.sleep(0.01)

    received = await queue.get()
    assert received == event1
    assert store.latest("test", "UP") == event1

    observer.stop()
    await asyncio.sleep(0.05)

    assert queue.empty()

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
