from polytrader.events.types import MarketDataEvent
from polytrader.store import MemoryMarketDataStore


def test_memory_market_data_store_add() -> None:
    store = MemoryMarketDataStore()
    event = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.49, best_ask=0.51)

    store.add(event)

    latest = store.latest("test", "UP")
    assert latest == event


def test_memory_market_data_store_latest() -> None:
    store = MemoryMarketDataStore()
    event1 = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.49, best_ask=0.51)
    event2 = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.50, best_ask=0.52)

    store.add(event1)
    store.add(event2)

    latest = store.latest("test", "UP")
    assert latest == event2


def test_memory_market_data_store_latest_none() -> None:
    store = MemoryMarketDataStore()

    latest = store.latest("nonexistent", "UP")
    assert latest is None


def test_memory_market_data_store_history() -> None:
    store = MemoryMarketDataStore()
    event1 = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.49, best_ask=0.51)
    event2 = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.50, best_ask=0.52)
    event3 = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.51, best_ask=0.53)

    store.add(event1)
    store.add(event2)
    store.add(event3)

    history = store.history("test", "UP")
    assert history == [event1, event2, event3]


def test_memory_market_data_store_history_empty() -> None:
    store = MemoryMarketDataStore()

    history = store.history("nonexistent", "UP")
    assert history == []


def test_memory_market_data_store_separate_markets() -> None:
    store = MemoryMarketDataStore()
    event1 = MarketDataEvent(market_slug="market1", outcome="UP", best_bid=0.49, best_ask=0.51)
    event2 = MarketDataEvent(market_slug="market2", outcome="UP", best_bid=0.50, best_ask=0.52)

    store.add(event1)
    store.add(event2)

    assert store.latest("market1", "UP") == event1
    assert store.latest("market2", "UP") == event2


def test_memory_market_data_store_separate_outcomes() -> None:
    store = MemoryMarketDataStore()
    event_up = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.49, best_ask=0.51)
    event_down = MarketDataEvent(market_slug="test", outcome="DOWN", best_bid=0.50, best_ask=0.52)

    store.add(event_up)
    store.add(event_down)

    assert store.latest("test", "UP") == event_up
    assert store.latest("test", "DOWN") == event_down


def test_memory_market_data_store_window_limit() -> None:
    store = MemoryMarketDataStore(window=3)

    event1 = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.49, best_ask=0.51)
    event2 = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.50, best_ask=0.52)
    event3 = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.51, best_ask=0.53)
    event4 = MarketDataEvent(market_slug="test", outcome="UP", best_bid=0.52, best_ask=0.54)

    store.add(event1)
    store.add(event2)
    store.add(event3)
    store.add(event4)

    history = store.history("test", "UP")
    assert len(history) == 3
    assert history == [event2, event3, event4]
    assert event1 not in history
