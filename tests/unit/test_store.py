from polytrader.events.types import MarketDataEvent
from polytrader.store import (
    DualViewMarketDataStore,
    IDualViewMarketDataStore,
    MemoryMarketDataStore,
    PatternKeyedMarketDataStore,
    resolve_store_view,
    slug_to_pattern,
)


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


def test_slug_to_pattern_strips_trailing_timestamp() -> None:
    """Slug with trailing -digits maps to pattern (same market across 15m rolls)."""
    assert slug_to_pattern("btc-updown-15m-1769980500") == "btc-updown-15m"
    assert slug_to_pattern("btc-updown-15m-1769981400") == "btc-updown-15m"
    assert slug_to_pattern("eth-updown-1h-1769980500") == "eth-updown-1h"


def test_slug_to_pattern_no_trailing_digits_returns_slug() -> None:
    """Slug without trailing -digits is returned unchanged."""
    assert slug_to_pattern("btc-updown-15m") == "btc-updown-15m"
    assert slug_to_pattern("test-market") == "test-market"


def test_pattern_keyed_store_same_pattern_shares_history() -> None:
    """Slugs under same pattern share history for warm start on slug roll."""
    store = PatternKeyedMarketDataStore()
    # Add events for first slug (e.g. btc-updown-15m-1769981400)
    e1 = MarketDataEvent(
        market_slug="btc-updown-15m-1769981400",
        outcome="UP",
        best_bid=0.49,
        best_ask=0.51,
    )
    e2 = MarketDataEvent(
        market_slug="btc-updown-15m-1769981400",
        outcome="UP",
        best_bid=0.50,
        best_ask=0.52,
    )
    store.add(e1)
    store.add(e2)
    # Query by second slug (e.g. after 15m roll to 1769980500) — same pattern, shared history
    history = store.history("btc-updown-15m-1769980500", "UP")
    assert len(history) == 2
    assert history == [e1, e2]
    assert store.latest("btc-updown-15m-1769980500", "UP") == e2


# --- resolve_store_view and IDualViewMarketDataStore ---


def test_dual_view_store_satisfies_protocol() -> None:
    """DualViewMarketDataStore is isinstance IDualViewMarketDataStore for typed resolution."""
    store = DualViewMarketDataStore()
    assert isinstance(store, IDualViewMarketDataStore)


def test_resolve_store_view_dual_view_use_pattern_returns_pattern_store() -> None:
    """When store is dual-view and use_pattern_history True, returns pattern_store."""
    dual = DualViewMarketDataStore()
    view = resolve_store_view(dual, use_pattern_history=True)
    assert view is dual.pattern_store
    assert isinstance(view, PatternKeyedMarketDataStore)


def test_resolve_store_view_dual_view_no_pattern_returns_slug_store() -> None:
    """When store is dual-view and use_pattern_history False, returns slug_store."""
    dual = DualViewMarketDataStore()
    view = resolve_store_view(dual, use_pattern_history=False)
    assert view is dual.slug_store
    assert isinstance(view, MemoryMarketDataStore)


def test_resolve_store_view_plain_store_returns_unchanged() -> None:
    """When store is not dual-view, returns the same store for both flags."""
    plain = MemoryMarketDataStore()
    view_pattern = resolve_store_view(plain, use_pattern_history=True)
    view_slug = resolve_store_view(plain, use_pattern_history=False)
    assert view_pattern is plain
    assert view_slug is plain
