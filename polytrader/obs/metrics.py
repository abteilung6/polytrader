"""Metrics infrastructure for observability per observability.mdc §4.

This module provides a simple metrics interface for collecting
and querying metrics. Defaults to PrometheusMetricsCollector for
operator visibility via Grafana dashboards.
"""

import os
from collections import defaultdict
from typing import Any, Protocol


class IMetricsCollector(Protocol):
    """Protocol for metrics collection per observability.mdc §4."""

    def increment_counter(self, name: str, labels: dict[str, str] | None = None) -> None:
        """Increment a counter metric.

        Args:
            name: Metric name (e.g., "risk_checks_total")
            labels: Optional labels/tags (e.g., {"allowed": "true"})
        """
        ...

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Set a gauge metric value.

        Args:
            name: Metric name (e.g., "risk_projected_exposure")
            value: Gauge value
            labels: Optional labels/tags
        """
        ...

    def record_histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a histogram value.

        Args:
            name: Metric name (e.g., "submit_latency_ms")
            value: Value to record
            labels: Optional labels/tags
        """
        ...

    def get_counter(self, name: str, labels: dict[str, str] | None = None) -> int:
        """Get current counter value.

        Args:
            name: Metric name
            labels: Optional labels to filter

        Returns:
            Current counter value
        """
        ...

    def get_gauge(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Get current gauge value.

        Args:
            name: Metric name
            labels: Optional labels to filter

        Returns:
            Current gauge value
        """
        ...

    def get_histogram_percentiles(
        self,
        name: str,
        percentiles: list[float] | None = None,
        labels: dict[str, str] | None = None,
    ) -> dict[float, float]:
        """Get histogram percentiles.

        Args:
            name: Metric name
            percentiles: List of percentiles (0.0 to 1.0), defaults to [0.5, 0.95, 0.99]
            labels: Optional labels to filter

        Returns:
            Dictionary mapping percentile to value
        """
        ...


class MemoryMetricsCollector(IMetricsCollector):
    """In-memory metrics collector for Phase 2.

    Simple implementation that stores metrics in memory.
    Suitable for single-process deployment. Future phases
    can add Prometheus/OpenTelemetry exporters.

    Per observability.mdc §4: Metrics are required for monitoring.
    """

    def __init__(self) -> None:
        """Initialize the metrics collector."""
        # Counters: name -> labels_key -> count
        # labels_key is tuple of (key, value) pairs for hashability
        self._counters: dict[str, dict[tuple[tuple[str, str], ...], int]] = defaultdict(
            lambda: defaultdict(int)
        )
        # Gauges: name -> labels_key -> value
        self._gauges: dict[str, dict[tuple[tuple[str, str], ...], float]] = defaultdict(
            lambda: defaultdict(float)
        )
        # Histograms: name -> labels_key -> list of values
        # Keep only last 1000 values per metric to prevent memory growth
        self._histograms: dict[str, dict[tuple[tuple[str, str], ...], list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._histogram_max_size = 1000

    def increment_counter(self, name: str, labels: dict[str, str] | None = None) -> None:
        """Increment a counter metric.

        Args:
            name: Metric name
            labels: Optional labels/tags
        """
        key = self._labels_to_key(labels)
        self._counters[name][key] += 1

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Set a gauge metric value.

        Args:
            name: Metric name
            value: Gauge value
            labels: Optional labels/tags
        """
        key = self._labels_to_key(labels)
        self._gauges[name][key] = value

    def get_counter(self, name: str, labels: dict[str, str] | None = None) -> int:
        """Get current counter value.

        Args:
            name: Metric name
            labels: Optional labels to filter

        Returns:
            Current counter value
        """
        key = self._labels_to_key(labels)
        return self._counters[name][key]

    def get_gauge(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Get current gauge value.

        Args:
            name: Metric name
            labels: Optional labels to filter

        Returns:
            Current gauge value
        """
        key = self._labels_to_key(labels)
        return self._gauges[name][key]

    def record_histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record histogram value.

        Args:
            name: Metric name
            value: Value to record
            labels: Optional labels/tags
        """
        key = self._labels_to_key(labels)
        self._histograms[name][key].append(value)

        # Keep only last N values to prevent memory growth
        if len(self._histograms[name][key]) > self._histogram_max_size:
            self._histograms[name][key] = self._histograms[name][key][-self._histogram_max_size :]

    def get_histogram_percentiles(
        self,
        name: str,
        percentiles: list[float] | None = None,
        labels: dict[str, str] | None = None,
    ) -> dict[float, float]:
        """Get histogram percentiles.

        Args:
            name: Metric name
            percentiles: List of percentiles (0.0 to 1.0), defaults to [0.5, 0.95, 0.99]
            labels: Optional labels to filter

        Returns:
            Dictionary mapping percentile to value
        """
        if percentiles is None:
            percentiles = [0.5, 0.95, 0.99]

        key = self._labels_to_key(labels)
        values = sorted(self._histograms[name][key])
        if not values:
            return dict.fromkeys(percentiles, 0.0)

        result = {}
        for p in percentiles:
            index = int(len(values) * p)
            result[p] = values[min(index, len(values) - 1)]
        return result

    def _labels_to_key(self, labels: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
        """Convert labels dict to immutable key for storage.

        Args:
            labels: Labels dictionary

        Returns:
            Immutable tuple key for storage (tuple of (key, value) pairs)
        """
        if labels is None:
            return ()
        # Sort items for consistent ordering
        return tuple(sorted(labels.items()))

    def get_all_metrics(self) -> dict[str, Any]:
        """Get all metrics (for debugging/export).

        Returns:
            Dictionary with all counter and gauge values.
            Labels are returned as dictionaries in a list format.
        """
        counters: dict[str, list[dict[str, Any]]] = {}
        for name, key_dict in self._counters.items():
            counters[name] = []
            for key, count in key_dict.items():
                # Convert tuple key back to dict
                labels_dict: dict[str, str] = dict(key) if key else {}
                counters[name].append({"labels": labels_dict, "value": count})

        gauges: dict[str, list[dict[str, Any]]] = {}
        for name, gauge_key_dict in self._gauges.items():
            gauges[name] = []
            for key, value in gauge_key_dict.items():
                # Convert tuple key back to dict
                gauge_labels_dict: dict[str, str] = dict(key) if key else {}
                gauges[name].append({"labels": gauge_labels_dict, "value": value})

        histograms: dict[str, list[dict[str, Any]]] = {}
        for name, hist_key_dict in self._histograms.items():
            histograms[name] = []
            for key, values in hist_key_dict.items():
                # Convert tuple key back to dict
                hist_labels_dict: dict[str, str] = dict(key) if key else {}
                # Calculate percentiles
                sorted_values = sorted(values)
                percentiles = {}
                if sorted_values:
                    for p in [0.5, 0.95, 0.99]:
                        index = int(len(sorted_values) * p)
                        percentiles[p] = sorted_values[min(index, len(sorted_values) - 1)]
                histograms[name].append(
                    {
                        "labels": hist_labels_dict,
                        "count": len(values),
                        "percentiles": percentiles,
                    }
                )

        return {"counters": counters, "gauges": gauges, "histograms": histograms}


# Global metrics collector instance (singleton)
_metrics_collector: IMetricsCollector | None = None


def create_metrics_collector(backend: str | None = None) -> IMetricsCollector:
    """Create metrics collector based on backend.

    Args:
        backend: Backend type ('prometheus' or 'memory'), or None to read from env

    Returns:
        IMetricsCollector instance

    Raises:
        ValueError: If backend is not 'prometheus' or 'memory'
    """
    if backend is None:
        backend = os.getenv("METRICS_BACKEND", "prometheus")  # Default to prometheus

    if backend == "prometheus":
        from polytrader.obs.metrics_prometheus import PrometheusMetricsCollector

        return PrometheusMetricsCollector()
    elif backend == "memory":
        return MemoryMetricsCollector()
    else:
        raise ValueError(f"Unknown metrics backend: {backend}. Must be 'prometheus' or 'memory'")


def get_metrics_collector() -> IMetricsCollector:
    """Get the global metrics collector instance.

    Returns:
        IMetricsCollector instance (singleton, defaults to Prometheus)
    """
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = create_metrics_collector()  # Uses factory, defaults to prometheus
    return _metrics_collector


def set_metrics_collector(collector: IMetricsCollector | None) -> None:
    """Set the global metrics collector (for testing).

    Args:
        collector: Metrics collector instance, or None to reset to default
    """
    global _metrics_collector
    _metrics_collector = collector


# Risk metrics functions per observability.mdc §4


def record_risk_check(allowed: bool) -> None:
    """Record a risk check per observability.mdc §4.

    Args:
        allowed: Whether the order was allowed
    """
    collector = get_metrics_collector()
    collector.increment_counter("risk_checks_total", labels={"allowed": str(allowed).lower()})


def record_risk_denial(reason: str) -> None:
    """Record a risk denial per observability.mdc §4.

    Args:
        reason: Denial reason code (e.g., "RISK_MAX_POSITION")
    """
    collector = get_metrics_collector()
    collector.increment_counter("risk_denials_total", labels={"reason": reason})


def record_projected_exposure(exposure: float) -> None:
    """Record projected exposure per observability.mdc §4.

    Args:
        exposure: Projected exposure value (USD)
    """
    collector = get_metrics_collector()
    collector.set_gauge("risk_projected_exposure", exposure)


# Market Data metrics functions per observability.mdc §4


def record_md_update(market_slug: str | None = None, outcome: str | None = None) -> None:
    """Record a market data update per observability.mdc §4.

    Args:
        market_slug: Optional market slug label
        outcome: Optional outcome label (UP/DOWN)
    """
    collector = get_metrics_collector()
    labels: dict[str, str] = {}
    if market_slug:
        labels["market_slug"] = market_slug
    if outcome:
        labels["outcome"] = outcome
    collector.increment_counter("md_updates_total", labels=labels if labels else None)


def record_md_staleness(staleness_seconds: float, market_slug: str | None = None) -> None:
    """Record market data staleness per observability.mdc §4.

    Args:
        staleness_seconds: Staleness in seconds (time since last update)
        market_slug: Optional market slug label
    """
    collector = get_metrics_collector()
    labels: dict[str, str] = {}
    if market_slug:
        labels["market_slug"] = market_slug
    collector.set_gauge(
        "md_staleness_seconds", staleness_seconds, labels=labels if labels else None
    )


def record_md_gap(market_slug: str | None = None) -> None:
    """Record a market data gap per observability.mdc §4.

    Args:
        market_slug: Optional market slug label
    """
    collector = get_metrics_collector()
    labels: dict[str, str] = {}
    if market_slug:
        labels["market_slug"] = market_slug
    collector.increment_counter("md_gap_total", labels=labels if labels else None)


def record_md_reconnect(market_slug: str | None = None) -> None:
    """Record a market data reconnect per observability.mdc §4.

    Args:
        market_slug: Optional market slug label
    """
    collector = get_metrics_collector()
    labels: dict[str, str] = {}
    if market_slug:
        labels["market_slug"] = market_slug
    collector.increment_counter("md_reconnect_total", labels=labels if labels else None)


def set_md_book_mid(mid: float, market_slug: str, outcome: str) -> None:
    """Set market data book mid price per observability.mdc §4.

    Args:
        mid: Mid price (average of bid and ask)
        market_slug: Market slug label
        outcome: Outcome label (UP/DOWN)
    """
    collector = get_metrics_collector()
    collector.set_gauge("md_book_mid", mid, labels={"market_slug": market_slug, "outcome": outcome})


def set_md_spread(spread: float, market_slug: str, outcome: str) -> None:
    """Set market data spread per observability.mdc §4.

    Args:
        spread: Spread (ask - bid)
        market_slug: Market slug label
        outcome: Outcome label (UP/DOWN)
    """
    collector = get_metrics_collector()
    collector.set_gauge(
        "md_spread", spread, labels={"market_slug": market_slug, "outcome": outcome}
    )


# Tick Storage metrics functions per observability.mdc §4


def record_tick_write_latency_ms(latency_ms: float) -> None:
    """Record tick write latency (time to buffer) per observability.mdc §4.

    Args:
        latency_ms: Write latency in milliseconds
    """
    collector = get_metrics_collector()
    collector.record_histogram("tick_write_latency_ms", latency_ms)


def record_tick_flush(count: int, latency_ms: float) -> None:
    """Record tick flush operation (counter + latency) per observability.mdc §4.

    Args:
        count: Number of ticks flushed
        latency_ms: Flush latency in milliseconds
    """
    collector = get_metrics_collector()
    collector.increment_counter("tick_flushes_total")
    collector.record_histogram("tick_flush_latency_ms", latency_ms)


def set_tick_buffer_size(size: int) -> None:
    """Set current tick buffer size per observability.mdc §4.

    Args:
        size: Current buffer size (number of ticks)
    """
    collector = get_metrics_collector()
    collector.set_gauge("tick_buffer_size", float(size))


def set_tick_buffer_capacity(capacity: int) -> None:
    """Set tick buffer capacity per observability.mdc §4.

    Args:
        capacity: Buffer capacity (batch_size)
    """
    collector = get_metrics_collector()
    collector.set_gauge("tick_buffer_capacity", float(capacity))


def increment_tick_write_errors(error_class: str) -> None:
    """Increment tick write error counter per observability.mdc §4.

    Args:
        error_class: Error classification (retryable/fatal/unknown)
    """
    collector = get_metrics_collector()
    collector.increment_counter("tick_write_errors_total", labels={"class": error_class})


def increment_tick_flush_errors(error_class: str) -> None:
    """Increment tick flush error counter per observability.mdc §4.

    Args:
        error_class: Error classification (retryable/fatal/unknown)
    """
    collector = get_metrics_collector()
    collector.increment_counter("tick_flush_errors_total", labels={"class": error_class})


def record_tick_db_read(operation: str, latency_ms: float) -> None:
    """Record database read operation per observability.mdc §4.

    Args:
        operation: Operation type (latest/history/markets)
        latency_ms: Read latency in milliseconds
    """
    collector = get_metrics_collector()
    collector.increment_counter("tick_db_reads_total", labels={"operation": operation})
    collector.record_histogram(
        "tick_db_read_latency_ms", latency_ms, labels={"operation": operation}
    )


def record_tick_db_read_error(operation: str, error_class: str) -> None:
    """Record database read error per observability.mdc §4.

    Args:
        operation: Operation type (latest/history/markets)
        error_class: Error classification (retryable/fatal/unknown)
    """
    collector = get_metrics_collector()
    collector.increment_counter(
        "tick_db_read_errors_total",
        labels={"operation": operation, "class": error_class},
    )


def set_tick_store_health(state: str) -> None:
    """Set tick store health state per observability.mdc §4.

    Args:
        state: Health state (open/closed)
    """
    collector = get_metrics_collector()
    collector.set_gauge(
        "tick_store_health", 1.0 if state == "open" else 0.0, labels={"state": state}
    )


# Strategy metrics functions per observability.mdc §4


def record_strategy_eval(strategy_id: str) -> None:
    """Record a strategy evaluation per observability.mdc §4.

    Args:
        strategy_id: Strategy identifier (e.g., "simple_threshold")
    """
    collector = get_metrics_collector()
    collector.increment_counter("strategy_eval_total", labels={"strategy_id": strategy_id})


def record_strategy_eval_latency(strategy_id: str, latency_ms: float) -> None:
    """Record strategy evaluation latency per observability.mdc §4.

    Args:
        strategy_id: Strategy identifier (e.g., "simple_threshold")
        latency_ms: Evaluation latency in milliseconds
    """
    collector = get_metrics_collector()
    collector.record_histogram(
        "strategy_eval_latency_ms", latency_ms, labels={"strategy_id": strategy_id}
    )


def record_order_intent(strategy_id: str, market_slug: str, outcome: str, side: str) -> None:
    """Record an order intent per observability.mdc §4.

    Args:
        strategy_id: Strategy identifier (e.g., "simple_threshold")
        market_slug: Market slug label
        outcome: Outcome label (UP/DOWN)
        side: Trade side label (BUY/SELL)
    """
    collector = get_metrics_collector()
    collector.increment_counter(
        "order_intents_total",
        labels={
            "strategy_id": strategy_id,
            "market_slug": market_slug,
            "outcome": outcome,
            "side": side,
        },
    )


# Safety metrics functions per observability.mdc §4


def set_execution_enabled(enabled: bool) -> None:
    """Set execution enabled gauge per observability.mdc §4.

    Args:
        enabled: Whether execution is enabled (True = 1, False = 0)
    """
    collector = get_metrics_collector()
    collector.set_gauge("execution_enabled", 1.0 if enabled else 0.0)


def set_kill_switch(active: bool) -> None:
    """Set kill switch gauge per observability.mdc §4.

    Args:
        active: Whether kill switch is active (True = 1, False = 0)
    """
    collector = get_metrics_collector()
    collector.set_gauge("kill_switch", 1.0 if active else 0.0)


def record_circuit_breaker(circuit_type: str) -> None:
    """Record a circuit breaker trigger per observability.mdc §4.

    Args:
        circuit_type: Circuit breaker type (e.g., "reconcile_divergence",
            "data_stale", "error_rate")
    """
    collector = get_metrics_collector()
    collector.increment_counter("circuit_breaker_total", labels={"type": circuit_type})


def record_adapter_error(error_class: str) -> None:
    """Record an adapter error per observability.mdc §4.

    Args:
        error_class: Error classification (e.g., "fatal", "retryable",
            "network", "timeout")
    """
    collector = get_metrics_collector()
    collector.increment_counter("adapter_errors_total", labels={"class": error_class})


# Posttrade metrics functions per observability.mdc §4


def set_position_net(
    market_slug: str,
    outcome: str,
    net_position: float,
    strategy_id: str | None = None,
) -> None:
    """Set position net gauge per observability.mdc §4.

    Args:
        market_slug: Market identifier
        outcome: Market outcome (UP/DOWN)
        net_position: Net position size (positive for long, negative for short)
        strategy_id: Optional strategy identifier for per-strategy tracking
    """
    collector = get_metrics_collector()
    labels: dict[str, str] = {"market": market_slug, "outcome": outcome}
    if strategy_id:
        labels["strategy_id"] = strategy_id
    collector.set_gauge("position_net", net_position, labels=labels)


def set_pnl_unrealized(unrealized_pnl: float, strategy_id: str | None = None) -> None:
    """Set unrealized PnL gauge per observability.mdc §4.

    Args:
        unrealized_pnl: Total unrealized profit/loss across all open positions
        strategy_id: Optional strategy identifier for per-strategy tracking
    """
    collector = get_metrics_collector()
    labels: dict[str, str] | None = None
    if strategy_id:
        labels = {"strategy_id": strategy_id}
    collector.set_gauge("pnl_unrealized", unrealized_pnl, labels=labels)


def record_pnl_realized(pnl: float, strategy_id: str | None = None) -> None:
    """Record realized PnL per observability.mdc §4.

    Args:
        pnl: Realized profit/loss from a closed position
        strategy_id: Optional strategy identifier for per-strategy tracking
    """
    collector = get_metrics_collector()
    labels: dict[str, str] | None = None
    if strategy_id:
        labels = {"strategy_id": strategy_id}
    # Use gauge to track cumulative realized PnL
    # Get current value and add to it
    current = collector.get_gauge("pnl_realized", labels=labels)
    collector.set_gauge("pnl_realized", current + pnl, labels=labels)
