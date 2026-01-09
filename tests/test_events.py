import asyncio

import pytest

from polytrader.events import MARKET_DATA, EventBus, Topic
from polytrader.types import MarketDataEvent


def test_subscribe_creates_queue() -> None:
    bus = EventBus()
    test_topic = Topic[str]("test")
    queue = bus.subscribe(test_topic)
    assert isinstance(queue, asyncio.Queue)


async def test_publish_subscribe_single_message() -> None:
    bus = EventBus()
    test_topic = Topic[str]("test")
    queue = bus.subscribe(test_topic)

    await bus.publish(test_topic, "hello")
    msg = await queue.get()

    assert msg == "hello"


async def test_multiple_subscribers_same_topic() -> None:
    bus = EventBus()
    test_topic = Topic[str]("test")
    queue1 = bus.subscribe(test_topic)
    queue2 = bus.subscribe(test_topic)

    await bus.publish(test_topic, "hello")

    msg1 = await queue1.get()
    msg2 = await queue2.get()

    assert msg1 == "hello"
    assert msg2 == "hello"


async def test_topic_isolation() -> None:
    bus = EventBus()
    topic1 = Topic[str]("topic1")
    topic2 = Topic[str]("topic2")
    queue1 = bus.subscribe(topic1)
    queue2 = bus.subscribe(topic2)

    await bus.publish(topic1, "msg1")
    await bus.publish(topic2, "msg2")

    msg1 = await queue1.get()
    msg2 = await queue2.get()

    assert msg1 == "msg1"
    assert msg2 == "msg2"


async def test_publish_to_nonexistent_topic() -> None:
    bus = EventBus()
    nonexistent_topic = Topic[str]("nonexistent")
    await bus.publish(nonexistent_topic, "message")


async def test_multiple_messages_same_topic() -> None:
    bus = EventBus()
    test_topic = Topic[str]("test")
    queue = bus.subscribe(test_topic)

    await bus.publish(test_topic, "msg1")
    await bus.publish(test_topic, "msg2")
    await bus.publish(test_topic, "msg3")

    assert await queue.get() == "msg1"
    assert await queue.get() == "msg2"
    assert await queue.get() == "msg3"


async def test_complex_message_types() -> None:
    bus = EventBus()
    queue = bus.subscribe(MARKET_DATA)

    event = MarketDataEvent(
        market_slug="test-market",
        outcome="UP",
        best_bid=0.49,
        best_ask=0.51,
    )

    await bus.publish(MARKET_DATA, event)
    received = await queue.get()

    assert received == event
    assert isinstance(received, MarketDataEvent)
    assert received.market_slug == "test-market"


async def test_multiple_topics_multiple_subscribers() -> None:
    bus = EventBus()

    market_data_queue = bus.subscribe(MARKET_DATA)
    proposals_topic = Topic[str]("proposals")
    orders_topic = Topic[str]("orders")
    proposal_queue = bus.subscribe(proposals_topic)
    order_queue1 = bus.subscribe(orders_topic)
    order_queue2 = bus.subscribe(orders_topic)

    await bus.publish(
        MARKET_DATA, MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.49, best_ask=0.51)
    )
    await bus.publish(proposals_topic, "proposal1")
    await bus.publish(orders_topic, "order1")

    event = await market_data_queue.get()
    assert isinstance(event, MarketDataEvent)
    assert await proposal_queue.get() == "proposal1"
    assert await order_queue1.get() == "order1"
    assert await order_queue2.get() == "order1"


async def test_subscribe_after_publish() -> None:
    bus = EventBus()
    test_topic = Topic[str]("test")

    await bus.publish(test_topic, "msg1")

    queue = bus.subscribe(test_topic)
    await bus.publish(test_topic, "msg2")

    msg = await queue.get()
    assert msg == "msg2"

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(queue.get(), timeout=0.1)


async def test_concurrent_publish_subscribe() -> None:
    bus = EventBus()
    test_topic = Topic[str]("test")
    queue = bus.subscribe(test_topic)

    await asyncio.gather(
        bus.publish(test_topic, "msg1"),
        bus.publish(test_topic, "msg2"),
        bus.publish(test_topic, "msg3"),
    )

    messages = set()
    for _ in range(3):
        messages.add(await queue.get())

    assert messages == {"msg1", "msg2", "msg3"}
