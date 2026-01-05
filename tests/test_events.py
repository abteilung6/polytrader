import asyncio

import pytest

from polytrader.events import EventBus
from polytrader.types import MarketTick


def test_subscribe_creates_queue() -> None:
    bus = EventBus()
    queue = bus.subscribe("test")
    assert isinstance(queue, asyncio.Queue)


async def test_publish_subscribe_single_message() -> None:
    bus = EventBus()
    queue = bus.subscribe("test")

    await bus.publish("test", "hello")
    msg = await queue.get()

    assert msg == "hello"


async def test_multiple_subscribers_same_topic() -> None:
    bus = EventBus()
    queue1 = bus.subscribe("test")
    queue2 = bus.subscribe("test")

    await bus.publish("test", "hello")

    msg1 = await queue1.get()
    msg2 = await queue2.get()

    assert msg1 == "hello"
    assert msg2 == "hello"


async def test_topic_isolation() -> None:
    bus = EventBus()
    queue1 = bus.subscribe("topic1")
    queue2 = bus.subscribe("topic2")

    await bus.publish("topic1", "msg1")
    await bus.publish("topic2", "msg2")

    msg1 = await queue1.get()
    msg2 = await queue2.get()

    assert msg1 == "msg1"
    assert msg2 == "msg2"


async def test_publish_to_nonexistent_topic() -> None:
    bus = EventBus()
    await bus.publish("nonexistent", "message")


async def test_multiple_messages_same_topic() -> None:
    bus = EventBus()
    queue = bus.subscribe("test")

    await bus.publish("test", "msg1")
    await bus.publish("test", "msg2")
    await bus.publish("test", "msg3")

    assert await queue.get() == "msg1"
    assert await queue.get() == "msg2"
    assert await queue.get() == "msg3"


async def test_complex_message_types() -> None:
    bus = EventBus()
    queue = bus.subscribe("ticks")

    tick = MarketTick(
        ts=1234567890.0,
        market_id="test-market",
        outcome="UP",
        best_bid=0.49,
        best_ask=0.51,
    )

    await bus.publish("ticks", tick)
    received = await queue.get()

    assert received == tick
    assert isinstance(received, MarketTick)
    assert received.market_id == "test-market"


async def test_multiple_topics_multiple_subscribers() -> None:
    bus = EventBus()

    tick_queue = bus.subscribe("ticks")
    proposal_queue = bus.subscribe("proposals")
    order_queue1 = bus.subscribe("orders")
    order_queue2 = bus.subscribe("orders")

    await bus.publish("ticks", "tick1")
    await bus.publish("proposals", "proposal1")
    await bus.publish("orders", "order1")

    assert await tick_queue.get() == "tick1"
    assert await proposal_queue.get() == "proposal1"
    assert await order_queue1.get() == "order1"
    assert await order_queue2.get() == "order1"


async def test_subscribe_after_publish() -> None:
    bus = EventBus()

    await bus.publish("test", "msg1")

    queue = bus.subscribe("test")
    await bus.publish("test", "msg2")

    msg = await queue.get()
    assert msg == "msg2"

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(queue.get(), timeout=0.1)


async def test_concurrent_publish_subscribe() -> None:
    bus = EventBus()
    queue = bus.subscribe("test")

    await asyncio.gather(
        bus.publish("test", "msg1"),
        bus.publish("test", "msg2"),
        bus.publish("test", "msg3"),
    )

    messages = set()
    for _ in range(3):
        messages.add(await queue.get())

    assert messages == {"msg1", "msg2", "msg3"}
