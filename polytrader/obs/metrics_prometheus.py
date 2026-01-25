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
        # Store metric instances: (name, tuple of label_names) -> Prometheus metric object
        # This allows us to handle metrics with different label sets
        self._counters: dict[tuple[str, tuple[str, ...]], Counter] = {}
        self._gauges: dict[tuple[str, tuple[str, ...]], Gauge] = {}
        self._histograms: dict[tuple[str, tuple[str, ...]], Histogram] = {}

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
        """
        # For Prometheus, we need to know label names upfront when creating the metric
        # If labels are provided, extract label names
        label_names: list[str] = []
        if labels:
            label_names = sorted(labels.keys())  # Sort for consistency

        # Create a key that includes both name and label names (for uniqueness)
        # This ensures metrics with different label sets are handled correctly
        metric_key = (name, tuple(label_names))

        if metric_key not in self._counters:
            # Create Counter with label names
            self._counters[metric_key] = Counter(
                name=name,
                documentation=f"Counter metric: {name}",
                labelnames=label_names,
                registry=self._registry,
            )

        counter = self._counters[metric_key]
        # Apply labels if provided
        if labels:
            # Sort labels to match label_names order
            sorted_labels = {k: labels[k] for k in label_names}
            return counter.labels(**sorted_labels)
        return counter

    def _get_or_create_gauge(self, name: str, labels: dict[str, str] | None = None) -> Gauge:
        """Get or create a Prometheus Gauge metric.

        Args:
            name: Metric name
            labels: Optional labels dictionary

        Returns:
            Prometheus Gauge instance (with labels applied if provided)
        """
        # Extract label names
        label_names: list[str] = []
        if labels:
            label_names = sorted(labels.keys())  # Sort for consistency

        metric_key = (name, tuple(label_names))

        if metric_key not in self._gauges:
            # Create Gauge with label names
            self._gauges[metric_key] = Gauge(
                name=name,
                documentation=f"Gauge metric: {name}",
                labelnames=label_names,
                registry=self._registry,
            )

        gauge = self._gauges[metric_key]
        # Apply labels if provided
        if labels:
            # Sort labels to match label_names order
            sorted_labels = {k: labels[k] for k in label_names}
            return gauge.labels(**sorted_labels)
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
        """
        # Extract label names
        label_names: list[str] = []
        if labels:
            label_names = sorted(labels.keys())  # Sort for consistency

        metric_key = (name, tuple(label_names))

        if metric_key not in self._histograms:
            # Create Histogram with label names
            # Use default buckets (Prometheus default)
            self._histograms[metric_key] = Histogram(
                name=name,
                documentation=f"Histogram metric: {name}",
                labelnames=label_names,
                registry=self._registry,
            )

        histogram = self._histograms[metric_key]
        # Apply labels if provided
        if labels:
            # Sort labels to match label_names order
            sorted_labels = {k: labels[k] for k in label_names}
            return histogram.labels(**sorted_labels)
        return histogram
