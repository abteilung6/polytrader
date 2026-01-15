"""Tests for market data metrics per observability.mdc §4.

Per Commit 1: Add market data metrics infrastructure.
"""

from polytrader.obs.metrics import (
    MemoryMetricsCollector,
    record_adapter_error,
    record_circuit_breaker,
    record_md_gap,
    record_md_reconnect,
    record_md_staleness,
    record_md_update,
    record_order_intent,
    record_strategy_eval,
    record_strategy_eval_latency,
    set_execution_enabled,
    set_kill_switch,
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


class TestStrategyMetrics:
    """Tests for strategy metrics functions per observability.mdc §4."""

    def test_record_strategy_eval(self) -> None:
        """Test that record_strategy_eval records evaluations with strategy_id."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_strategy_eval(strategy_id="simple_threshold")
        record_strategy_eval(strategy_id="simple_threshold")
        record_strategy_eval(strategy_id="winner_threshold")

        assert (
            collector.get_counter("strategy_eval_total", labels={"strategy_id": "simple_threshold"})
            == 2
        )
        assert (
            collector.get_counter("strategy_eval_total", labels={"strategy_id": "winner_threshold"})
            == 1
        )

    def test_record_strategy_eval_latency(self) -> None:
        """Test that record_strategy_eval_latency records latency histogram."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_strategy_eval_latency(strategy_id="simple_threshold", latency_ms=10.5)
        record_strategy_eval_latency(strategy_id="simple_threshold", latency_ms=20.0)
        record_strategy_eval_latency(strategy_id="winner_threshold", latency_ms=15.0)

        # Verify histogram percentiles
        percentiles = collector.get_histogram_percentiles(
            "strategy_eval_latency_ms", labels={"strategy_id": "simple_threshold"}
        )
        assert 0.5 in percentiles
        assert 0.95 in percentiles
        assert 0.99 in percentiles
        # Median should be around 15.25 (average of 10.5 and 20.0)
        assert 10.0 <= percentiles[0.5] <= 20.0

        # Verify different strategy_id has separate histogram
        percentiles2 = collector.get_histogram_percentiles(
            "strategy_eval_latency_ms", labels={"strategy_id": "winner_threshold"}
        )
        assert percentiles2[0.5] == 15.0  # Only one value, so median is that value

    def test_record_order_intent(self) -> None:
        """Test that record_order_intent records intents with all labels."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_order_intent(
            strategy_id="simple_threshold",
            market_slug="btc-updown-15m",
            outcome="UP",
            side="BUY",
        )
        record_order_intent(
            strategy_id="simple_threshold",
            market_slug="btc-updown-15m",
            outcome="UP",
            side="BUY",
        )
        record_order_intent(
            strategy_id="simple_threshold",
            market_slug="btc-updown-15m",
            outcome="DOWN",
            side="SELL",
        )
        record_order_intent(
            strategy_id="winner_threshold",
            market_slug="eth-updown-15m",
            outcome="UP",
            side="BUY",
        )

        # Verify counter with all labels
        assert (
            collector.get_counter(
                "order_intents_total",
                labels={
                    "strategy_id": "simple_threshold",
                    "market_slug": "btc-updown-15m",
                    "outcome": "UP",
                    "side": "BUY",
                },
            )
            == 2
        )
        assert (
            collector.get_counter(
                "order_intents_total",
                labels={
                    "strategy_id": "simple_threshold",
                    "market_slug": "btc-updown-15m",
                    "outcome": "DOWN",
                    "side": "SELL",
                },
            )
            == 1
        )
        assert (
            collector.get_counter(
                "order_intents_total",
                labels={
                    "strategy_id": "winner_threshold",
                    "market_slug": "eth-updown-15m",
                    "outcome": "UP",
                    "side": "BUY",
                },
            )
            == 1
        )

    def test_strategy_metrics_isolation(self) -> None:
        """Test that different strategy metrics are isolated."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        # Record different metrics
        record_strategy_eval(strategy_id="simple_threshold")
        record_strategy_eval_latency(strategy_id="simple_threshold", latency_ms=10.0)
        record_order_intent(
            strategy_id="simple_threshold",
            market_slug="btc-updown-15m",
            outcome="UP",
            side="BUY",
        )

        # Verify all metrics are recorded independently
        assert (
            collector.get_counter("strategy_eval_total", labels={"strategy_id": "simple_threshold"})
            == 1
        )
        percentiles = collector.get_histogram_percentiles(
            "strategy_eval_latency_ms", labels={"strategy_id": "simple_threshold"}
        )
        assert percentiles[0.5] == 10.0
        assert (
            collector.get_counter(
                "order_intents_total",
                labels={
                    "strategy_id": "simple_threshold",
                    "market_slug": "btc-updown-15m",
                    "outcome": "UP",
                    "side": "BUY",
                },
            )
            == 1
        )

    def test_strategy_metrics_multiple_strategies(self) -> None:
        """Test that metrics work correctly with multiple strategies."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        # Record metrics for different strategies
        record_strategy_eval(strategy_id="simple_threshold")
        record_strategy_eval(strategy_id="winner_threshold")
        record_strategy_eval_latency(strategy_id="simple_threshold", latency_ms=10.0)
        record_strategy_eval_latency(strategy_id="winner_threshold", latency_ms=20.0)

        # Verify metrics are isolated per strategy
        assert (
            collector.get_counter("strategy_eval_total", labels={"strategy_id": "simple_threshold"})
            == 1
        )
        assert (
            collector.get_counter("strategy_eval_total", labels={"strategy_id": "winner_threshold"})
            == 1
        )
        simple_percentiles = collector.get_histogram_percentiles(
            "strategy_eval_latency_ms", labels={"strategy_id": "simple_threshold"}
        )
        winner_percentiles = collector.get_histogram_percentiles(
            "strategy_eval_latency_ms", labels={"strategy_id": "winner_threshold"}
        )
        assert simple_percentiles[0.5] == 10.0
        assert winner_percentiles[0.5] == 20.0


class TestSafetyMetrics:
    """Tests for safety metrics functions per observability.mdc §4."""

    def test_set_execution_enabled(self) -> None:
        """Test that set_execution_enabled sets gauge to 1 when enabled."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        set_execution_enabled(enabled=True)

        assert collector.get_gauge("execution_enabled") == 1.0

    def test_set_execution_enabled_disabled(self) -> None:
        """Test that set_execution_enabled sets gauge to 0 when disabled."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        set_execution_enabled(enabled=False)

        assert collector.get_gauge("execution_enabled") == 0.0

    def test_set_execution_enabled_updates(self) -> None:
        """Test that set_execution_enabled updates gauge value."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        set_execution_enabled(enabled=True)
        assert collector.get_gauge("execution_enabled") == 1.0

        set_execution_enabled(enabled=False)
        assert collector.get_gauge("execution_enabled") == 0.0

        set_execution_enabled(enabled=True)
        assert collector.get_gauge("execution_enabled") == 1.0

    def test_set_kill_switch(self) -> None:
        """Test that set_kill_switch sets gauge to 1 when active."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        set_kill_switch(active=True)

        assert collector.get_gauge("kill_switch") == 1.0

    def test_set_kill_switch_inactive(self) -> None:
        """Test that set_kill_switch sets gauge to 0 when inactive."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        set_kill_switch(active=False)

        assert collector.get_gauge("kill_switch") == 0.0

    def test_set_kill_switch_updates(self) -> None:
        """Test that set_kill_switch updates gauge value."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        set_kill_switch(active=True)
        assert collector.get_gauge("kill_switch") == 1.0

        set_kill_switch(active=False)
        assert collector.get_gauge("kill_switch") == 0.0

        set_kill_switch(active=True)
        assert collector.get_gauge("kill_switch") == 1.0

    def test_record_circuit_breaker(self) -> None:
        """Test that record_circuit_breaker increments counter with type label."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_circuit_breaker(circuit_type="reconcile_divergence")
        record_circuit_breaker(circuit_type="reconcile_divergence")
        record_circuit_breaker(circuit_type="data_stale")

        assert (
            collector.get_counter("circuit_breaker_total", labels={"type": "reconcile_divergence"})
            == 2
        )
        assert collector.get_counter("circuit_breaker_total", labels={"type": "data_stale"}) == 1

    def test_record_circuit_breaker_multiple_types(self) -> None:
        """Test that record_circuit_breaker tracks different types separately."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_circuit_breaker(circuit_type="reconcile_divergence")
        record_circuit_breaker(circuit_type="data_stale")
        record_circuit_breaker(circuit_type="error_rate")
        record_circuit_breaker(circuit_type="reconcile_divergence")

        assert (
            collector.get_counter("circuit_breaker_total", labels={"type": "reconcile_divergence"})
            == 2
        )
        assert collector.get_counter("circuit_breaker_total", labels={"type": "data_stale"}) == 1
        assert collector.get_counter("circuit_breaker_total", labels={"type": "error_rate"}) == 1

    def test_safety_metrics_isolation(self) -> None:
        """Test that different safety metrics are isolated."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        # Set different metrics
        set_execution_enabled(enabled=True)
        set_kill_switch(active=False)
        record_circuit_breaker(circuit_type="reconcile_divergence")

        # Verify all metrics are recorded independently
        assert collector.get_gauge("execution_enabled") == 1.0
        assert collector.get_gauge("kill_switch") == 0.0
        assert (
            collector.get_counter("circuit_breaker_total", labels={"type": "reconcile_divergence"})
            == 1
        )


class TestAdapterErrorMetrics:
    """Tests for adapter error metrics functions per observability.mdc §4."""

    def test_record_adapter_error(self) -> None:
        """Test that record_adapter_error increments counter with class label."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_adapter_error(error_class="fatal")
        record_adapter_error(error_class="fatal")
        record_adapter_error(error_class="retryable")

        assert collector.get_counter("adapter_errors_total", labels={"class": "fatal"}) == 2
        assert collector.get_counter("adapter_errors_total", labels={"class": "retryable"}) == 1

    def test_record_adapter_error_multiple_classes(self) -> None:
        """Test that record_adapter_error tracks different error classes separately."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_adapter_error(error_class="fatal")
        record_adapter_error(error_class="retryable")
        record_adapter_error(error_class="network")
        record_adapter_error(error_class="timeout")
        record_adapter_error(error_class="fatal")

        assert collector.get_counter("adapter_errors_total", labels={"class": "fatal"}) == 2
        assert collector.get_counter("adapter_errors_total", labels={"class": "retryable"}) == 1
        assert collector.get_counter("adapter_errors_total", labels={"class": "network"}) == 1
        assert collector.get_counter("adapter_errors_total", labels={"class": "timeout"}) == 1

    def test_record_adapter_error_isolation(self) -> None:
        """Test that adapter error metrics are isolated from other metrics."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_adapter_error(error_class="fatal")
        record_circuit_breaker(circuit_type="reconcile_divergence")

        assert collector.get_counter("adapter_errors_total", labels={"class": "fatal"}) == 1
        assert (
            collector.get_counter("circuit_breaker_total", labels={"type": "reconcile_divergence"})
            == 1
        )
