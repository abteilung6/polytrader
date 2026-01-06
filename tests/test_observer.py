import asyncio
from collections.abc import AsyncIterator

from polytrader.adapters import IMarketDataAdapter
from polytrader.events import EventBus
from polytrader.observer import Observer
from polytrader.types import MarketTick


class FakeMarketDataAdapter(IMarketDataAdapter):
    def __init__(self, ticks: list[MarketTick]) -> None:
        self._ticks = ticks

    async def ticks(self) -> AsyncIterator[MarketTick]:
        for tick in self._ticks:
            yield tick


async def test_observer_publishes_ticks() -> None:
    bus = EventBus()
    tick1 = MarketTick(ts=1.0, market_id="test", outcome="UP", best_bid=0.49, best_ask=0.51)
    tick2 = MarketTick(ts=2.0, market_id="test", outcome="UP", best_bid=0.50, best_ask=0.52)

    adapter = FakeMarketDataAdapter([tick1, tick2])
    observer = Observer(bus, adapter)

    queue = bus.subscribe("ticks")

    task = asyncio.create_task(observer.run())

    received_tick1 = await asyncio.wait_for(queue.get(), timeout=1.0)
    received_tick2 = await asyncio.wait_for(queue.get(), timeout=1.0)

    assert received_tick1 == tick1
    assert received_tick2 == tick2

    await asyncio.wait_for(task, timeout=1.0)


async def test_observer_multiple_subscribers() -> None:
    bus = EventBus()
    tick = MarketTick(ts=1.0, market_id="test", outcome="UP", best_bid=0.49, best_ask=0.51)

    adapter = FakeMarketDataAdapter([tick])
    observer = Observer(bus, adapter)

    queue1 = bus.subscribe("ticks")
    queue2 = bus.subscribe("ticks")

    task = asyncio.create_task(observer.run())

    received1 = await asyncio.wait_for(queue1.get(), timeout=1.0)
    received2 = await asyncio.wait_for(queue2.get(), timeout=1.0)

    assert received1 == tick
    assert received2 == tick

    await asyncio.wait_for(task, timeout=1.0)


async def test_observer_stops_when_stopped() -> None:
    bus = EventBus()
    tick = MarketTick(ts=1.0, market_id="test", outcome="UP", best_bid=0.49, best_ask=0.51)

    async def slow_ticks():
        yield tick
        await asyncio.sleep(0.1)
        yield MarketTick(ts=2.0, market_id="test", outcome="UP", best_bid=0.50, best_ask=0.52)

    class SlowAdapter:
        async def ticks(self):
            async for tick in slow_ticks():
                yield tick

    adapter = SlowAdapter()
    observer = Observer(bus, adapter)

    queue = bus.subscribe("ticks")

    task = asyncio.create_task(observer.run())
    await asyncio.sleep(0.01)

    received = await queue.get()
    assert received == tick

    observer.stop()
    await asyncio.sleep(0.05)

    assert queue.empty()

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
