import asyncio

import pytest

from polytrader.events import PROPOSALS, EventBus
from polytrader.models import SimpleThresholdModel
from polytrader.store import MemoryMarketDataStore
from polytrader.types import MarketDataEvent


async def test_simple_threshold_model_buy_proposal() -> None:
    bus = EventBus()
    store = MemoryMarketDataStore()
    model = SimpleThresholdModel(
        bus, store, market_slug="test", outcomes={"UP"}, buy_threshold=0.30, sell_threshold=0.50
    )

    proposal_queue = bus.subscribe(PROPOSALS)

    for _i in range(30):
        event = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.40, best_ask=0.42)
        store.add(event)

    event = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.28, best_ask=0.30)
    store.add(event)

    await model.on_tick(event)

    proposal = await asyncio.wait_for(proposal_queue.get(), timeout=1.0)

    assert proposal.side == "BUY"
    assert proposal.market_slug == "test"
    assert proposal.outcome == "UP"
    assert proposal.limit_price == 0.30
    assert proposal.size == 1.0
    assert "below buy threshold" in proposal.reason


async def test_simple_threshold_model_sell_proposal() -> None:
    bus = EventBus()
    store = MemoryMarketDataStore()
    model = SimpleThresholdModel(
        bus, store, market_slug="test", outcomes={"UP"}, buy_threshold=0.30, sell_threshold=0.50
    )

    proposal_queue = bus.subscribe(PROPOSALS)

    for _i in range(30):
        event = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.40, best_ask=0.42)
        store.add(event)

    event = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.51, best_ask=0.53)
    store.add(event)

    await model.on_tick(event)

    proposal = await asyncio.wait_for(proposal_queue.get(), timeout=1.0)

    assert proposal.side == "SELL"
    assert proposal.market_slug == "test"
    assert proposal.outcome == "UP"
    assert proposal.limit_price == 0.51
    assert proposal.size == 1.0
    assert "above sell threshold" in proposal.reason


async def test_simple_threshold_model_ignores_wrong_market() -> None:
    bus = EventBus()
    store = MemoryMarketDataStore()
    model = SimpleThresholdModel(
        bus, store, market_slug="test", outcomes={"UP"}, buy_threshold=0.30, sell_threshold=0.50
    )

    proposal_queue = bus.subscribe(PROPOSALS)

    for _i in range(30):
        event = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.40, best_ask=0.42)
        store.add(event)

    event = MarketDataEvent(market_slug="other", outcome="UP", best_bid=0.29, best_ask=0.31)
    store.add(event)

    await model.on_tick(event)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(proposal_queue.get(), timeout=0.1)


async def test_simple_threshold_model_ignores_wrong_outcome() -> None:
    bus = EventBus()
    store = MemoryMarketDataStore()
    model = SimpleThresholdModel(
        bus, store, market_slug="test", outcomes={"UP"}, buy_threshold=0.30, sell_threshold=0.50
    )

    proposal_queue = bus.subscribe(PROPOSALS)

    for _i in range(30):
        event = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.40, best_ask=0.42)
        store.add(event)

    event = MarketDataEvent(market_slug="test", outcome="DOWN", best_bid=0.29, best_ask=0.31)
    store.add(event)

    await model.on_tick(event)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(proposal_queue.get(), timeout=0.1)


async def test_simple_threshold_model_requires_minimum_history() -> None:
    bus = EventBus()
    store = MemoryMarketDataStore()
    model = SimpleThresholdModel(
        bus, store, market_slug="test", outcomes={"UP"}, buy_threshold=0.30, sell_threshold=0.50
    )

    proposal_queue = bus.subscribe(PROPOSALS)

    for _i in range(29):
        event = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.29, best_ask=0.31)
        store.add(event)

    event = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.29, best_ask=0.31)
    store.add(event)

    await model.on_tick(event)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(proposal_queue.get(), timeout=0.1)


async def test_simple_threshold_model_no_proposal_in_range() -> None:
    bus = EventBus()
    store = MemoryMarketDataStore()
    model = SimpleThresholdModel(
        bus, store, market_slug="test", outcomes={"UP"}, buy_threshold=0.30, sell_threshold=0.50
    )

    proposal_queue = bus.subscribe(PROPOSALS)

    for _i in range(30):
        event = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.40, best_ask=0.42)
        store.add(event)

    event = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.40, best_ask=0.42)
    store.add(event)

    await model.on_tick(event)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(proposal_queue.get(), timeout=0.1)


async def test_simple_threshold_model_both_thresholds() -> None:
    bus = EventBus()
    store = MemoryMarketDataStore()
    model = SimpleThresholdModel(
        bus, store, market_slug="test", outcomes={"UP"}, buy_threshold=0.30, sell_threshold=0.50
    )

    proposal_queue = bus.subscribe(PROPOSALS)

    for _i in range(30):
        event = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.40, best_ask=0.42)
        store.add(event)

    event_buy = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.28, best_ask=0.30)
    store.add(event_buy)
    event_sell = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.51, best_ask=0.53)
    store.add(event_sell)

    await model.on_tick(event_buy)
    await model.on_tick(event_sell)

    proposal1 = await asyncio.wait_for(proposal_queue.get(), timeout=1.0)
    proposal2 = await asyncio.wait_for(proposal_queue.get(), timeout=1.0)

    assert proposal1.side == "BUY"
    assert proposal2.side == "SELL"


async def test_simple_threshold_model_both_outcomes() -> None:
    """Test that model processes both UP and DOWN outcomes."""
    bus = EventBus()
    store = MemoryMarketDataStore()
    model = SimpleThresholdModel(
        bus,
        store,
        market_slug="test",
        outcomes={"UP", "DOWN"},
        buy_threshold=0.30,
        sell_threshold=0.50,
    )

    proposal_queue = bus.subscribe(PROPOSALS)

    # Populate history for both outcomes
    for _i in range(30):
        store.add(MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.40, best_ask=0.42))
        store.add(MarketDataEvent(market_slug="test", outcome="DOWN", best_bid=0.40, best_ask=0.42))

    # UP tick below threshold
    up_event = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.28, best_ask=0.30)
    store.add(up_event)
    await model.on_tick(up_event)

    # DOWN tick below threshold
    down_event = MarketDataEvent(market_slug="test", outcome="DOWN", best_bid=0.28, best_ask=0.30)
    store.add(down_event)
    await model.on_tick(down_event)

    # Should get proposals for both
    up_proposal = await asyncio.wait_for(proposal_queue.get(), timeout=1.0)
    down_proposal = await asyncio.wait_for(proposal_queue.get(), timeout=1.0)

    assert up_proposal.outcome == "UP"
    assert down_proposal.outcome == "DOWN"
    assert up_proposal.side == "BUY"
    assert down_proposal.side == "BUY"


async def test_simple_threshold_model_filters_outcome() -> None:
    """Test that model only processes configured outcomes."""
    bus = EventBus()
    store = MemoryMarketDataStore()
    model = SimpleThresholdModel(
        bus, store, market_slug="test", outcomes={"UP"}, buy_threshold=0.30, sell_threshold=0.50
    )

    proposal_queue = bus.subscribe(PROPOSALS)

    # Populate history for UP
    for _i in range(30):
        store.add(MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.40, best_ask=0.42))

    # DOWN tick (should be ignored)
    down_event = MarketDataEvent(market_slug="test", outcome="DOWN", best_bid=0.28, best_ask=0.30)
    await model.on_tick(down_event)

    # Should not generate proposal
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(proposal_queue.get(), timeout=0.1)
