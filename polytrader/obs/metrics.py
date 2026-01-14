"""Metrics infrastructure for observability per observability.mdc §4.

This module provides a simple metrics interface for collecting
and querying metrics. In Phase 2, we use an in-memory implementation.
Future phases can add Prometheus/OpenTelemetry exporters.
"""

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


class MemoryMetricsCollector:
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


def get_metrics_collector() -> IMetricsCollector:
    """Get the global metrics collector instance.

    Returns:
        IMetricsCollector instance (singleton)
    """
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MemoryMetricsCollector()
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
