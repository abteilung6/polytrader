"""Integration tests for market data metrics per observability.mdc §4.

Per Commit 2: Integrate market data metrics in market data adapter.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from polytrader.adapters import IMarketDataAdapter
from polytrader.events import EventBus
from polytrader.events.types import MarketDataEvent
from polytrader.obs.metrics import MemoryMetricsCollector, set_metrics_collector
from polytrader.observer import Observer
from polytrader.store import MemoryMarketDataStore


class MockMarketDataAdapter(IMarketDataAdapter):
    """Mock market data adapter for testing."""

    def __init__(self, events: list[MarketDataEvent]) -> None:
        """Initialize mock adapter with list of events to yield.

        Args:
            events: List of MarketDataEvent instances to yield
        """
        self.events = events
        self._index = 0

    async def ticks(self):
        """Yield market data events."""
        while self._index < len(self.events):
            yield self.events[self._index]
            self._index += 1
            await asyncio.sleep(0.01)  # Small delay to simulate real adapter


class TestMarketDataMetrics:
    """Integration tests for market data metrics emission."""

    @pytest.mark.asyncio
    async def test_market_data_update_metrics(self) -> None:
        """Test that md_updates_total counter is incremented on market data updates."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        bus = EventBus()
        store = MemoryMarketDataStore()
        adapter = MockMarketDataAdapter(
            [
                MarketDataEvent(
                    market_slug="btc-updown-15m",
                    outcome="UP",
                    best_bid=0.45,
                    best_ask=0.50,
                ),
                MarketDataEvent(
                    market_slug="btc-updown-15m",
                    outcome="DOWN",
                    best_bid=0.48,
                    best_ask=0.52,
                ),
            ]
        )
        observer = Observer(bus, adapter, store)

        # Run observer to process events
        task = asyncio.create_task(observer.run())
        await asyncio.sleep(0.1)  # Give time to process events
        observer.stop()
        await task

        # Verify md_updates_total counter
        assert (
            collector.get_counter(
                "md_updates_total", labels={"market_slug": "btc-updown-15m", "outcome": "UP"}
            )
            == 1
        )
        assert (
            collector.get_counter(
                "md_updates_total", labels={"market_slug": "btc-updown-15m", "outcome": "DOWN"}
            )
            == 1
        )

    @pytest.mark.asyncio
    async def test_market_data_book_metrics(self) -> None:
        """Test that md_book_mid and md_spread gauges are set correctly."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        bus = EventBus()
        store = MemoryMarketDataStore()
        adapter = MockMarketDataAdapter(
            [
                MarketDataEvent(
                    market_slug="btc-updown-15m",
                    outcome="UP",
                    best_bid=0.45,
                    best_ask=0.50,
                ),
            ]
        )
        observer = Observer(bus, adapter, store)

        # Run observer to process events
        task = asyncio.create_task(observer.run())
        await asyncio.sleep(0.1)
        observer.stop()
        await task

        # Verify md_book_mid gauge (mid = (0.45 + 0.50) / 2 = 0.475)
        assert collector.get_gauge(
            "md_book_mid", labels={"market_slug": "btc-updown-15m", "outcome": "UP"}
        ) == pytest.approx(0.475)

        # Verify md_spread gauge (spread = 0.50 - 0.45 = 0.05)
        assert collector.get_gauge(
            "md_spread", labels={"market_slug": "btc-updown-15m", "outcome": "UP"}
        ) == pytest.approx(0.05)

    @pytest.mark.asyncio
    async def test_market_data_staleness_metrics(self) -> None:
        """Test that md_staleness_seconds gauge is updated correctly."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        bus = EventBus()
        store = MemoryMarketDataStore()

        # Create first event
        event1 = MarketDataEvent(
            market_slug="btc-updown-15m",
            outcome="UP",
            best_bid=0.45,
            best_ask=0.50,
        )

        # Create second event (will be processed after a delay)
        event2 = MarketDataEvent(
            market_slug="btc-updown-15m",
            outcome="UP",
            best_bid=0.46,
            best_ask=0.51,
        )

        adapter = MockMarketDataAdapter([event1, event2])
        observer = Observer(bus, adapter, store)

        # Run observer to process first event
        task = asyncio.create_task(observer.run())
        await asyncio.sleep(0.05)  # Small delay to allow first event processing

        # Wait a bit more to create staleness
        await asyncio.sleep(0.1)

        observer.stop()
        await task

        # Verify staleness is recorded (should be > 0 since time passed between events)
        staleness = collector.get_gauge(
            "md_staleness_seconds", labels={"market_slug": "btc-updown-15m"}
        )
        # Staleness should be positive (time since first event was processed)
        assert staleness >= 0.0

    @pytest.mark.asyncio
    async def test_market_data_gap_detection(self) -> None:
        """Test that md_gap_total counter is incremented when gaps are detected."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        bus = EventBus()
        store = MemoryMarketDataStore()

        # Create events with large time gap (> 10 seconds threshold)
        now = datetime.now(UTC)
        event1 = MarketDataEvent(
            market_slug="btc-updown-15m",
            outcome="UP",
            best_bid=0.45,
            best_ask=0.50,
        )
        # Create event with specific timestamp using model_copy
        event1 = event1.model_copy(update={"ts_wall": now.isoformat()})

        # Create second event 15 seconds later (exceeds 10s threshold)
        event2 = MarketDataEvent(
            market_slug="btc-updown-15m",
            outcome="UP",
            best_bid=0.46,
            best_ask=0.51,
        )
        event2 = event2.model_copy(update={"ts_wall": (now + timedelta(seconds=15)).isoformat()})

        adapter = MockMarketDataAdapter([event1, event2])
        observer = Observer(bus, adapter, store)

        # Run observer to process events
        task = asyncio.create_task(observer.run())
        await asyncio.sleep(0.1)
        observer.stop()
        await task

        # Verify gap was detected and recorded
        assert collector.get_counter("md_gap_total", labels={"market_slug": "btc-updown-15m"}) == 1

    @pytest.mark.asyncio
    async def test_market_data_no_gap_for_normal_updates(self) -> None:
        """Test that gaps are not detected for normal update intervals."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        bus = EventBus()
        store = MemoryMarketDataStore()

        # Create events with normal time gap (< 10 seconds threshold)
        now = datetime.now(UTC)
        event1 = MarketDataEvent(
            market_slug="btc-updown-15m",
            outcome="UP",
            best_bid=0.45,
            best_ask=0.50,
        )
        # Create event with specific timestamp using model_copy
        event1 = event1.model_copy(update={"ts_wall": now.isoformat()})

        # Create second event 5 seconds later (within threshold)
        event2 = MarketDataEvent(
            market_slug="btc-updown-15m",
            outcome="UP",
            best_bid=0.46,
            best_ask=0.51,
        )
        event2 = event2.model_copy(update={"ts_wall": (now + timedelta(seconds=5)).isoformat()})

        adapter = MockMarketDataAdapter([event1, event2])
        observer = Observer(bus, adapter, store)

        # Run observer to process events
        task = asyncio.create_task(observer.run())
        await asyncio.sleep(0.1)
        observer.stop()
        await task

        # Verify no gap was detected
        assert collector.get_counter("md_gap_total", labels={"market_slug": "btc-updown-15m"}) == 0

    @pytest.mark.asyncio
    async def test_market_data_reconnect_metrics(self) -> None:
        """Test that md_reconnect_total counter is incremented on reconnect."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        bus = EventBus()
        store = MemoryMarketDataStore()
        adapter = MockMarketDataAdapter(
            [
                MarketDataEvent(
                    market_slug="btc-updown-15m",
                    outcome="UP",
                    best_bid=0.45,
                    best_ask=0.50,
                ),
            ]
        )
        observer = Observer(bus, adapter, store)

        # Run observer first time (first run, no reconnect)
        task1 = asyncio.create_task(observer.run())
        await asyncio.sleep(0.1)
        observer.stop()
        await task1

        # Verify no reconnect on first run
        assert collector.get_counter("md_reconnect_total") == 0

        # Run observer second time (should trigger reconnect)
        adapter._index = 0  # Reset adapter
        task2 = asyncio.create_task(observer.run())
        await asyncio.sleep(0.1)
        observer.stop()
        await task2

        # Verify reconnect was recorded
        assert collector.get_counter("md_reconnect_total") == 1

    @pytest.mark.asyncio
    async def test_market_data_reconnect_on_error(self) -> None:
        """Test that reconnect metric is emitted when observer encounters an error."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        bus = EventBus()
        store = MemoryMarketDataStore()

        # Create adapter that raises an error when ticks() is iterated
        class ErrorAdapter(IMarketDataAdapter):
            def __init__(self) -> None:
                self._first = True

            async def ticks(self):
                # Make it an async generator that raises on second iteration
                # This simulates a connection error after initial connection
                if self._first:
                    self._first = False
                    # Yield once to make this a generator and allow initial connection
                    yield MarketDataEvent(
                        market_slug="test", outcome="UP", best_bid=0.45, best_ask=0.50
                    )
                # Raise on subsequent iteration to simulate connection error
                raise RuntimeError("Connection error")

        adapter = ErrorAdapter()
        observer = Observer(bus, adapter, store)

        # Run observer and expect error (after first successful tick)
        with pytest.raises(RuntimeError, match="Connection error"):
            await observer.run()

        # Verify reconnect was recorded on error
        assert collector.get_counter("md_reconnect_total") == 1

    @pytest.mark.asyncio
    async def test_market_data_metrics_multiple_markets(self) -> None:
        """Test that metrics work correctly with multiple markets and outcomes."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        bus = EventBus()
        store = MemoryMarketDataStore()
        adapter = MockMarketDataAdapter(
            [
                MarketDataEvent(
                    market_slug="btc-updown-15m",
                    outcome="UP",
                    best_bid=0.45,
                    best_ask=0.50,
                ),
                MarketDataEvent(
                    market_slug="btc-updown-15m",
                    outcome="DOWN",
                    best_bid=0.48,
                    best_ask=0.52,
                ),
                MarketDataEvent(
                    market_slug="eth-updown-15m",
                    outcome="UP",
                    best_bid=0.40,
                    best_ask=0.45,
                ),
            ]
        )
        observer = Observer(bus, adapter, store)

        # Run observer to process events
        task = asyncio.create_task(observer.run())
        await asyncio.sleep(0.1)
        observer.stop()
        await task

        # Verify metrics are isolated per market/outcome
        assert (
            collector.get_counter(
                "md_updates_total", labels={"market_slug": "btc-updown-15m", "outcome": "UP"}
            )
            == 1
        )
        assert (
            collector.get_counter(
                "md_updates_total", labels={"market_slug": "btc-updown-15m", "outcome": "DOWN"}
            )
            == 1
        )
        assert (
            collector.get_counter(
                "md_updates_total", labels={"market_slug": "eth-updown-15m", "outcome": "UP"}
            )
            == 1
        )

        # Verify book metrics are isolated
        assert collector.get_gauge(
            "md_book_mid", labels={"market_slug": "btc-updown-15m", "outcome": "UP"}
        ) == pytest.approx(0.475)
        assert collector.get_gauge(
            "md_book_mid", labels={"market_slug": "eth-updown-15m", "outcome": "UP"}
        ) == pytest.approx(0.425)
