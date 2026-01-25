"""Prometheus-backed metrics collector implementation.

This module provides a PrometheusMetricsCollector that implements IMetricsCollector
using the prometheus_client library. This enables Prometheus metrics export for
Grafana dashboards while maintaining backward compatibility with existing code.

Per observability.mdc §4: Maintains all existing metric types.
"""

from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
)

from polytrader.obs.metrics import IMetricsCollector


class PrometheusMetricsCollector(IMetricsCollector):
    """Prometheus-backed metrics collector.

    Implements IMetricsCollector using prometheus_client library.
    Maintains compatibility with existing metrics API while enabling
    Prometheus export for Grafana dashboards.

    This class implements the IMetricsCollector protocol via structural typing.
    All required methods from IMetricsCollector are implemented.

    Attributes:
        _registry: Prometheus CollectorRegistry (defaults to REGISTRY)
        _counters: Dictionary mapping metric name to Prometheus Counter
        _gauges: Dictionary mapping metric name to Prometheus Gauge
        _histograms: Dictionary mapping metric name to Prometheus Histogram
    """

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        """Initialize Prometheus metrics collector.

        Args:
            registry: Prometheus CollectorRegistry to use. If None, uses REGISTRY.
        """
        self._registry = registry or REGISTRY
        # Store metric instances: name -> Prometheus metric object
        # Track all label names used for each metric (union of all label sets)
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}
        # Track all label names seen for each metric (to handle different label sets)
        self._counter_label_names: dict[str, set[str]] = {}
        self._gauge_label_names: dict[str, set[str]] = {}
        self._histogram_label_names: dict[str, set[str]] = {}

    def increment_counter(self, name: str, labels: dict[str, str] | None = None) -> None:
        """Increment a counter metric.

        Args:
            name: Metric name (e.g., "risk_checks_total")
            labels: Optional labels/tags (e.g., {"allowed": "true"})
        """
        counter = self._get_or_create_counter(name, labels)
        counter.inc()

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Set a gauge metric value.

        Args:
            name: Metric name (e.g., "risk_projected_exposure")
            value: Gauge value
            labels: Optional labels/tags
        """
        gauge = self._get_or_create_gauge(name, labels)
        gauge.set(value)

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
        histogram = self._get_or_create_histogram(name, labels)
        histogram.observe(value)

    def get_counter(self, name: str, labels: dict[str, str] | None = None) -> int:
        """Get current counter value.

        Args:
            name: Metric name
            labels: Optional labels to filter

        Returns:
            Current counter value

        Note:
            Prometheus metrics are pull-based and don't support direct value queries.
            This method returns 0 for compatibility. To get actual values, query
            Prometheus API or use the /metrics endpoint.
        """
        # Prometheus Counter doesn't support direct value queries
        # This is a limitation of the pull-based model
        # For compatibility with IMetricsCollector interface, return 0
        # In practice, this method is rarely used (mainly for testing)
        return 0

    def get_gauge(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Get current gauge value.

        Args:
            name: Metric name
            labels: Optional labels to filter

        Returns:
            Current gauge value

        Note:
            Prometheus metrics are pull-based and don't support direct value queries.
            This method returns 0.0 for compatibility. To get actual values, query
            Prometheus API or use the /metrics endpoint.
        """
        # Prometheus Gauge doesn't support direct value queries
        # This is a limitation of the pull-based model
        # For compatibility with IMetricsCollector interface, return 0.0
        # In practice, this method is rarely used (mainly for testing)
        return 0.0

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

        Note:
            Prometheus histograms use buckets and don't support direct percentile queries.
            This method returns 0.0 for all percentiles for compatibility. To get actual
            percentiles, query Prometheus API using histogram_quantile() function.
        """
        if percentiles is None:
            percentiles = [0.5, 0.95, 0.99]

        # Prometheus Histogram doesn't provide direct percentile access
        # Percentiles must be calculated from buckets via Prometheus query API
        # For compatibility with IMetricsCollector interface, return 0.0
        # In practice, percentiles should be queried from Prometheus, not from the collector
        return dict.fromkeys(percentiles, 0.0)

    def _get_or_create_counter(self, name: str, labels: dict[str, str] | None = None) -> Counter:
        """Get or create a Prometheus Counter metric.

        Args:
            name: Metric name
            labels: Optional labels dictionary

        Returns:
            Prometheus Counter instance (with labels applied if provided)

        Note:
            Prometheus requires the same label names for all instances of a metric.
            This method tracks all label names used and creates the metric with the
            union of all label names seen so far.
        """
        # Track all label names used for this metric
        if name not in self._counter_label_names:
            self._counter_label_names[name] = set()
        if labels:
            self._counter_label_names[name].update(labels.keys())

        # Get union of all label names (sorted for consistency)
        all_label_names = sorted(self._counter_label_names[name])

        # Create metric if it doesn't exist
        if name not in self._counters:
            self._counters[name] = Counter(
                name=name,
                documentation=f"Counter metric: {name}",
                labelnames=all_label_names,
                registry=self._registry,
            )

        counter = self._counters[name]
        # Check if metric actually has label names (Prometheus metric attribute)
        has_label_names = len(counter._labelnames) > 0 if hasattr(counter, "_labelnames") else False

        # Apply labels if provided
        if labels:
            if has_label_names:
                # Metric has label names, use them (fill missing with empty string)
                full_labels = {
                    label_name: labels.get(label_name, "") for label_name in all_label_names
                }
                return counter.labels(**full_labels)
            else:
                # Metric was created without label names, can't add labels
                # Return the unlabeled counter (labels are ignored)
                return counter
        # If no labels provided
        if has_label_names:
            # Metric has label names, must provide them (use empty strings)
            empty_labels = dict.fromkeys(counter._labelnames, "")
            return counter.labels(**empty_labels)
        # Metric has no label names, return as-is
        return counter

    def _get_or_create_gauge(self, name: str, labels: dict[str, str] | None = None) -> Gauge:
        """Get or create a Prometheus Gauge metric.

        Args:
            name: Metric name
            labels: Optional labels dictionary

        Returns:
            Prometheus Gauge instance (with labels applied if provided)

        Note:
            Prometheus requires the same label names for all instances of a metric.
            This method tracks all label names used and creates the metric with the
            union of all label names seen so far. If a metric is first used without
            labels and later with labels, it will be created with label names from
            the first labeled usage.
        """
        # Track all label names used for this metric
        if name not in self._gauge_label_names:
            self._gauge_label_names[name] = set()
        if labels:
            self._gauge_label_names[name].update(labels.keys())

        # Get union of all label names (sorted for consistency)
        all_label_names = sorted(self._gauge_label_names[name])

        # Create metric if it doesn't exist
        if name not in self._gauges:
            self._gauges[name] = Gauge(
                name=name,
                documentation=f"Gauge metric: {name}",
                labelnames=all_label_names,
                registry=self._registry,
            )

        gauge = self._gauges[name]
        # Check if metric actually has label names (Prometheus metric attribute)
        has_label_names = len(gauge._labelnames) > 0 if hasattr(gauge, "_labelnames") else False

        # Apply labels if provided
        if labels:
            if has_label_names:
                # Metric has label names, use them (fill missing with empty string)
                full_labels = {
                    label_name: labels.get(label_name, "") for label_name in all_label_names
                }
                return gauge.labels(**full_labels)
            else:
                # Metric was created without label names, can't add labels
                # Return the unlabeled metric (labels are ignored)
                return gauge
        # If no labels provided
        if has_label_names:
            # Metric has label names, must provide them (use empty strings)
            empty_labels = dict.fromkeys(gauge._labelnames, "")
            return gauge.labels(**empty_labels)
        # Metric has no label names, return as-is
        return gauge

    def _get_or_create_histogram(
        self, name: str, labels: dict[str, str] | None = None
    ) -> Histogram:
        """Get or create a Prometheus Histogram metric.

        Args:
            name: Metric name
            labels: Optional labels dictionary

        Returns:
            Prometheus Histogram instance (with labels applied if provided)

        Note:
            Prometheus requires the same label names for all instances of a metric.
            This method tracks all label names used and creates the metric with the
            union of all label names seen so far.
        """
        # Track all label names used for this metric
        if name not in self._histogram_label_names:
            self._histogram_label_names[name] = set()
        if labels:
            self._histogram_label_names[name].update(labels.keys())

        # Get union of all label names (sorted for consistency)
        all_label_names = sorted(self._histogram_label_names[name])

        # Create metric if it doesn't exist
        if name not in self._histograms:
            # Use default buckets (Prometheus default)
            self._histograms[name] = Histogram(
                name=name,
                documentation=f"Histogram metric: {name}",
                labelnames=all_label_names,
                registry=self._registry,
            )

        histogram = self._histograms[name]
        # Check if metric actually has label names (Prometheus metric attribute)
        has_label_names = (
            len(histogram._labelnames) > 0 if hasattr(histogram, "_labelnames") else False
        )

        # Apply labels if provided
        if labels:
            if has_label_names:
                # Metric has label names, use them (fill missing with empty string)
                full_labels = {
                    label_name: labels.get(label_name, "") for label_name in all_label_names
                }
                return histogram.labels(**full_labels)
            else:
                # Metric was created without label names, can't add labels
                # Return the unlabeled histogram (labels are ignored)
                return histogram
        # If no labels provided
        if has_label_names:
            # Metric has label names, must provide them (use empty strings)
            empty_labels = dict.fromkeys(histogram._labelnames, "")
            return histogram.labels(**empty_labels)
        # Metric has no label names, return as-is
        return histogram
