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

        return {"counters": counters, "gauges": gauges}


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
