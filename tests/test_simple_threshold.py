import asyncio

import pytest

from polytrader.events import PROPOSALS, EventBus
from polytrader.models import SimpleThresholdModel
from polytrader.store import MemoryTickStore
from polytrader.types import MarketTick


async def test_simple_threshold_model_buy_proposal() -> None:
    bus = EventBus()
    store = MemoryTickStore()
    model = SimpleThresholdModel(
        bus, store, market_id="test", outcome="UP", buy_threshold=0.30, sell_threshold=0.50
    )

    proposal_queue = bus.subscribe(PROPOSALS)

    for i in range(30):
        tick = MarketTick(ts=float(i), market_id="test", outcome="UP", best_bid=0.40, best_ask=0.42)
        store.add(tick)

    tick = MarketTick(ts=30.0, market_id="test", outcome="UP", best_bid=0.28, best_ask=0.30)
    store.add(tick)

    await model.on_tick(tick)

    proposal = await asyncio.wait_for(proposal_queue.get(), timeout=1.0)

    assert proposal.side == "BUY"
    assert proposal.market_id == "test"
    assert proposal.outcome == "UP"
    assert proposal.limit_price == 0.30
    assert proposal.size == 1.0
    assert "below buy threshold" in proposal.reason


async def test_simple_threshold_model_sell_proposal() -> None:
    bus = EventBus()
    store = MemoryTickStore()
    model = SimpleThresholdModel(
        bus, store, market_id="test", outcome="UP", buy_threshold=0.30, sell_threshold=0.50
    )

    proposal_queue = bus.subscribe(PROPOSALS)

    for i in range(30):
        tick = MarketTick(ts=float(i), market_id="test", outcome="UP", best_bid=0.40, best_ask=0.42)
        store.add(tick)

    tick = MarketTick(ts=30.0, market_id="test", outcome="UP", best_bid=0.51, best_ask=0.53)
    store.add(tick)

    await model.on_tick(tick)

    proposal = await asyncio.wait_for(proposal_queue.get(), timeout=1.0)

    assert proposal.side == "SELL"
    assert proposal.market_id == "test"
    assert proposal.outcome == "UP"
    assert proposal.limit_price == 0.51
    assert proposal.size == 1.0
    assert "above sell threshold" in proposal.reason


async def test_simple_threshold_model_ignores_wrong_market() -> None:
    bus = EventBus()
    store = MemoryTickStore()
    model = SimpleThresholdModel(
        bus, store, market_id="test", outcome="UP", buy_threshold=0.30, sell_threshold=0.50
    )

    proposal_queue = bus.subscribe(PROPOSALS)

    for i in range(30):
        tick = MarketTick(ts=float(i), market_id="test", outcome="UP", best_bid=0.40, best_ask=0.42)
        store.add(tick)

    tick = MarketTick(ts=30.0, market_id="other", outcome="UP", best_bid=0.29, best_ask=0.31)
    store.add(tick)

    await model.on_tick(tick)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(proposal_queue.get(), timeout=0.1)


async def test_simple_threshold_model_ignores_wrong_outcome() -> None:
    bus = EventBus()
    store = MemoryTickStore()
    model = SimpleThresholdModel(
        bus, store, market_id="test", outcome="UP", buy_threshold=0.30, sell_threshold=0.50
    )

    proposal_queue = bus.subscribe(PROPOSALS)

    for i in range(30):
        tick = MarketTick(ts=float(i), market_id="test", outcome="UP", best_bid=0.40, best_ask=0.42)
        store.add(tick)

    tick = MarketTick(ts=30.0, market_id="test", outcome="DOWN", best_bid=0.29, best_ask=0.31)
    store.add(tick)

    await model.on_tick(tick)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(proposal_queue.get(), timeout=0.1)


async def test_simple_threshold_model_requires_minimum_history() -> None:
    bus = EventBus()
    store = MemoryTickStore()
    model = SimpleThresholdModel(
        bus, store, market_id="test", outcome="UP", buy_threshold=0.30, sell_threshold=0.50
    )

    proposal_queue = bus.subscribe(PROPOSALS)

    for i in range(29):
        tick = MarketTick(ts=float(i), market_id="test", outcome="UP", best_bid=0.29, best_ask=0.31)
        store.add(tick)

    tick = MarketTick(ts=29.0, market_id="test", outcome="UP", best_bid=0.29, best_ask=0.31)
    store.add(tick)

    await model.on_tick(tick)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(proposal_queue.get(), timeout=0.1)


async def test_simple_threshold_model_no_proposal_in_range() -> None:
    bus = EventBus()
    store = MemoryTickStore()
    model = SimpleThresholdModel(
        bus, store, market_id="test", outcome="UP", buy_threshold=0.30, sell_threshold=0.50
    )

    proposal_queue = bus.subscribe(PROPOSALS)

    for i in range(30):
        tick = MarketTick(ts=float(i), market_id="test", outcome="UP", best_bid=0.40, best_ask=0.42)
        store.add(tick)

    tick = MarketTick(ts=30.0, market_id="test", outcome="UP", best_bid=0.40, best_ask=0.42)
    store.add(tick)

    await model.on_tick(tick)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(proposal_queue.get(), timeout=0.1)


async def test_simple_threshold_model_both_thresholds() -> None:
    bus = EventBus()
    store = MemoryTickStore()
    model = SimpleThresholdModel(
        bus, store, market_id="test", outcome="UP", buy_threshold=0.30, sell_threshold=0.50
    )

    proposal_queue = bus.subscribe(PROPOSALS)

    for i in range(30):
        tick = MarketTick(ts=float(i), market_id="test", outcome="UP", best_bid=0.40, best_ask=0.42)
        store.add(tick)

    tick_buy = MarketTick(ts=30.0, market_id="test", outcome="UP", best_bid=0.28, best_ask=0.30)
    store.add(tick_buy)
    tick_sell = MarketTick(ts=31.0, market_id="test", outcome="UP", best_bid=0.51, best_ask=0.53)
    store.add(tick_sell)

    await model.on_tick(tick_buy)
    await model.on_tick(tick_sell)

    proposal1 = await asyncio.wait_for(proposal_queue.get(), timeout=1.0)
    proposal2 = await asyncio.wait_for(proposal_queue.get(), timeout=1.0)

    assert proposal1.side == "BUY"
    assert proposal2.side == "SELL"
