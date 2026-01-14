"""Tests for market data metrics per observability.mdc §4.

Per Commit 1: Add market data metrics infrastructure.
"""

from polytrader.obs.metrics import (
    MemoryMetricsCollector,
    record_md_gap,
    record_md_reconnect,
    record_md_staleness,
    record_md_update,
    set_md_book_mid,
    set_md_spread,
    set_metrics_collector,
)


class TestMarketDataMetrics:
    """Tests for market data metrics functions per observability.mdc §4."""

    def test_record_md_update_without_labels(self) -> None:
        """Test that record_md_update records updates without labels."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_md_update()
        record_md_update()

        assert collector.get_counter("md_updates_total") == 2

    def test_record_md_update_with_labels(self) -> None:
        """Test that record_md_update records updates with labels."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_md_update(market_slug="btc-updown-15m", outcome="UP")
        record_md_update(market_slug="btc-updown-15m", outcome="UP")
        record_md_update(market_slug="btc-updown-15m", outcome="DOWN")

        assert (
            collector.get_counter(
                "md_updates_total", labels={"market_slug": "btc-updown-15m", "outcome": "UP"}
            )
            == 2
        )
        assert (
            collector.get_counter(
                "md_updates_total", labels={"market_slug": "btc-updown-15m", "outcome": "DOWN"}
            )
            == 1
        )

    def test_record_md_update_with_partial_labels(self) -> None:
        """Test that record_md_update works with partial labels."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_md_update(market_slug="btc-updown-15m")
        record_md_update(market_slug="eth-updown-15m")

        assert (
            collector.get_counter("md_updates_total", labels={"market_slug": "btc-updown-15m"}) == 1
        )
        assert (
            collector.get_counter("md_updates_total", labels={"market_slug": "eth-updown-15m"}) == 1
        )

    def test_record_md_staleness_without_labels(self) -> None:
        """Test that record_md_staleness records staleness without labels."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_md_staleness(staleness_seconds=5.0)
        assert collector.get_gauge("md_staleness_seconds") == 5.0

        record_md_staleness(staleness_seconds=10.5)
        assert collector.get_gauge("md_staleness_seconds") == 10.5

    def test_record_md_staleness_with_labels(self) -> None:
        """Test that record_md_staleness records staleness with labels."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_md_staleness(staleness_seconds=5.0, market_slug="btc-updown-15m")
        record_md_staleness(staleness_seconds=10.5, market_slug="eth-updown-15m")

        assert (
            collector.get_gauge("md_staleness_seconds", labels={"market_slug": "btc-updown-15m"})
            == 5.0
        )
        assert (
            collector.get_gauge("md_staleness_seconds", labels={"market_slug": "eth-updown-15m"})
            == 10.5
        )

    def test_record_md_gap_without_labels(self) -> None:
        """Test that record_md_gap records gaps without labels."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_md_gap()
        record_md_gap()

        assert collector.get_counter("md_gap_total") == 2

    def test_record_md_gap_with_labels(self) -> None:
        """Test that record_md_gap records gaps with labels."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_md_gap(market_slug="btc-updown-15m")
        record_md_gap(market_slug="btc-updown-15m")
        record_md_gap(market_slug="eth-updown-15m")

        assert collector.get_counter("md_gap_total", labels={"market_slug": "btc-updown-15m"}) == 2
        assert collector.get_counter("md_gap_total", labels={"market_slug": "eth-updown-15m"}) == 1

    def test_record_md_reconnect_without_labels(self) -> None:
        """Test that record_md_reconnect records reconnects without labels."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_md_reconnect()
        record_md_reconnect()

        assert collector.get_counter("md_reconnect_total") == 2

    def test_record_md_reconnect_with_labels(self) -> None:
        """Test that record_md_reconnect records reconnects with labels."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_md_reconnect(market_slug="btc-updown-15m")
        record_md_reconnect(market_slug="btc-updown-15m")
        record_md_reconnect(market_slug="eth-updown-15m")

        assert (
            collector.get_counter("md_reconnect_total", labels={"market_slug": "btc-updown-15m"})
            == 2
        )
        assert (
            collector.get_counter("md_reconnect_total", labels={"market_slug": "eth-updown-15m"})
            == 1
        )

    def test_set_md_book_mid(self) -> None:
        """Test that set_md_book_mid sets mid price gauge with labels."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        set_md_book_mid(mid=0.55, market_slug="btc-updown-15m", outcome="UP")
        set_md_book_mid(mid=0.60, market_slug="btc-updown-15m", outcome="DOWN")
        set_md_book_mid(mid=0.50, market_slug="eth-updown-15m", outcome="UP")

        assert (
            collector.get_gauge(
                "md_book_mid", labels={"market_slug": "btc-updown-15m", "outcome": "UP"}
            )
            == 0.55
        )
        assert (
            collector.get_gauge(
                "md_book_mid", labels={"market_slug": "btc-updown-15m", "outcome": "DOWN"}
            )
            == 0.60
        )
        assert (
            collector.get_gauge(
                "md_book_mid", labels={"market_slug": "eth-updown-15m", "outcome": "UP"}
            )
            == 0.50
        )

    def test_set_md_book_mid_updates_value(self) -> None:
        """Test that set_md_book_mid updates existing gauge value."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        set_md_book_mid(mid=0.55, market_slug="btc-updown-15m", outcome="UP")
        assert (
            collector.get_gauge(
                "md_book_mid", labels={"market_slug": "btc-updown-15m", "outcome": "UP"}
            )
            == 0.55
        )

        set_md_book_mid(mid=0.60, market_slug="btc-updown-15m", outcome="UP")
        assert (
            collector.get_gauge(
                "md_book_mid", labels={"market_slug": "btc-updown-15m", "outcome": "UP"}
            )
            == 0.60
        )

    def test_set_md_spread(self) -> None:
        """Test that set_md_spread sets spread gauge with labels."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        set_md_spread(spread=0.01, market_slug="btc-updown-15m", outcome="UP")
        set_md_spread(spread=0.02, market_slug="btc-updown-15m", outcome="DOWN")
        set_md_spread(spread=0.015, market_slug="eth-updown-15m", outcome="UP")

        assert (
            collector.get_gauge(
                "md_spread", labels={"market_slug": "btc-updown-15m", "outcome": "UP"}
            )
            == 0.01
        )
        assert (
            collector.get_gauge(
                "md_spread", labels={"market_slug": "btc-updown-15m", "outcome": "DOWN"}
            )
            == 0.02
        )
        assert (
            collector.get_gauge(
                "md_spread", labels={"market_slug": "eth-updown-15m", "outcome": "UP"}
            )
            == 0.015
        )

    def test_set_md_spread_updates_value(self) -> None:
        """Test that set_md_spread updates existing gauge value."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        set_md_spread(spread=0.01, market_slug="btc-updown-15m", outcome="UP")
        assert (
            collector.get_gauge(
                "md_spread", labels={"market_slug": "btc-updown-15m", "outcome": "UP"}
            )
            == 0.01
        )

        set_md_spread(spread=0.02, market_slug="btc-updown-15m", outcome="UP")
        assert (
            collector.get_gauge(
                "md_spread", labels={"market_slug": "btc-updown-15m", "outcome": "UP"}
            )
            == 0.02
        )

    def test_market_data_metrics_isolation(self) -> None:
        """Test that different market data metrics are isolated."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        # Record different metrics
        record_md_update(market_slug="btc-updown-15m")
        record_md_gap(market_slug="btc-updown-15m")
        record_md_reconnect(market_slug="btc-updown-15m")
        record_md_staleness(staleness_seconds=5.0, market_slug="btc-updown-15m")
        set_md_book_mid(mid=0.55, market_slug="btc-updown-15m", outcome="UP")
        set_md_spread(spread=0.01, market_slug="btc-updown-15m", outcome="UP")

        # Verify all metrics are recorded independently
        assert (
            collector.get_counter("md_updates_total", labels={"market_slug": "btc-updown-15m"}) == 1
        )
        assert collector.get_counter("md_gap_total", labels={"market_slug": "btc-updown-15m"}) == 1
        assert (
            collector.get_counter("md_reconnect_total", labels={"market_slug": "btc-updown-15m"})
            == 1
        )
        assert (
            collector.get_gauge("md_staleness_seconds", labels={"market_slug": "btc-updown-15m"})
            == 5.0
        )
        assert (
            collector.get_gauge(
                "md_book_mid", labels={"market_slug": "btc-updown-15m", "outcome": "UP"}
            )
            == 0.55
        )
        assert (
            collector.get_gauge(
                "md_spread", labels={"market_slug": "btc-updown-15m", "outcome": "UP"}
            )
            == 0.01
        )

    def test_market_data_metrics_multiple_markets(self) -> None:
        """Test that metrics work correctly with multiple markets."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        # Record metrics for different markets
        record_md_update(market_slug="btc-updown-15m")
        record_md_update(market_slug="eth-updown-15m")
        set_md_book_mid(mid=0.55, market_slug="btc-updown-15m", outcome="UP")
        set_md_book_mid(mid=0.50, market_slug="eth-updown-15m", outcome="UP")

        # Verify metrics are isolated per market
        assert (
            collector.get_counter("md_updates_total", labels={"market_slug": "btc-updown-15m"}) == 1
        )
        assert (
            collector.get_counter("md_updates_total", labels={"market_slug": "eth-updown-15m"}) == 1
        )
        assert (
            collector.get_gauge(
                "md_book_mid", labels={"market_slug": "btc-updown-15m", "outcome": "UP"}
            )
            == 0.55
        )
        assert (
            collector.get_gauge(
                "md_book_mid", labels={"market_slug": "eth-updown-15m", "outcome": "UP"}
            )
            == 0.50
        )
