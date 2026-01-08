from polytrader.store import MemoryTickStore
from polytrader.types import MarketTick


def test_memory_tick_store_add() -> None:
    store = MemoryTickStore()
    tick = MarketTick(ts=1.0, market_slug="test", outcome="UP", best_bid=0.49, best_ask=0.51)

    store.add(tick)

    latest = store.latest("test", "UP")
    assert latest == tick


def test_memory_tick_store_latest() -> None:
    store = MemoryTickStore()
    tick1 = MarketTick(ts=1.0, market_slug="test", outcome="UP", best_bid=0.49, best_ask=0.51)
    tick2 = MarketTick(ts=2.0, market_slug="test", outcome="UP", best_bid=0.50, best_ask=0.52)

    store.add(tick1)
    store.add(tick2)

    latest = store.latest("test", "UP")
    assert latest == tick2


def test_memory_tick_store_latest_none() -> None:
    store = MemoryTickStore()

    latest = store.latest("nonexistent", "UP")
    assert latest is None


def test_memory_tick_store_history() -> None:
    store = MemoryTickStore()
    tick1 = MarketTick(ts=1.0, market_slug="test", outcome="UP", best_bid=0.49, best_ask=0.51)
    tick2 = MarketTick(ts=2.0, market_slug="test", outcome="UP", best_bid=0.50, best_ask=0.52)
    tick3 = MarketTick(ts=3.0, market_slug="test", outcome="UP", best_bid=0.51, best_ask=0.53)

    store.add(tick1)
    store.add(tick2)
    store.add(tick3)

    history = store.history("test", "UP")
    assert history == [tick1, tick2, tick3]


def test_memory_tick_store_history_empty() -> None:
    store = MemoryTickStore()

    history = store.history("nonexistent", "UP")
    assert history == []


def test_memory_tick_store_separate_markets() -> None:
    store = MemoryTickStore()
    tick1 = MarketTick(ts=1.0, market_slug="market1", outcome="UP", best_bid=0.49, best_ask=0.51)
    tick2 = MarketTick(ts=2.0, market_slug="market2", outcome="UP", best_bid=0.50, best_ask=0.52)

    store.add(tick1)
    store.add(tick2)

    assert store.latest("market1", "UP") == tick1
    assert store.latest("market2", "UP") == tick2


def test_memory_tick_store_separate_outcomes() -> None:
    store = MemoryTickStore()
    tick_up = MarketTick(ts=1.0, market_slug="test", outcome="UP", best_bid=0.49, best_ask=0.51)
    tick_down = MarketTick(ts=2.0, market_slug="test", outcome="DOWN", best_bid=0.50, best_ask=0.52)

    store.add(tick_up)
    store.add(tick_down)

    assert store.latest("test", "UP") == tick_up
    assert store.latest("test", "DOWN") == tick_down


def test_memory_tick_store_window_limit() -> None:
    store = MemoryTickStore(window=3)

    tick1 = MarketTick(ts=1.0, market_slug="test", outcome="UP", best_bid=0.49, best_ask=0.51)
    tick2 = MarketTick(ts=2.0, market_slug="test", outcome="UP", best_bid=0.50, best_ask=0.52)
    tick3 = MarketTick(ts=3.0, market_slug="test", outcome="UP", best_bid=0.51, best_ask=0.53)
    tick4 = MarketTick(ts=4.0, market_slug="test", outcome="UP", best_bid=0.52, best_ask=0.54)

    store.add(tick1)
    store.add(tick2)
    store.add(tick3)
    store.add(tick4)

    history = store.history("test", "UP")
    assert len(history) == 3
    assert history == [tick2, tick3, tick4]
    assert tick1 not in history
