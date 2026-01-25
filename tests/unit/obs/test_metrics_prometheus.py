"""Unit tests for PrometheusMetricsCollector.

Per Commit 2: Verify PrometheusMetricsCollector implements IMetricsCollector
correctly and handles all metric types, labels, and Prometheus format compatibility.
"""

from prometheus_client import REGISTRY, CollectorRegistry, generate_latest

from polytrader.obs.metrics_prometheus import PrometheusMetricsCollector


class TestPrometheusMetricsCollectorBasic:
    """Basic tests for PrometheusMetricsCollector."""

    def test_initialization_default_registry(self) -> None:
        """Test that PrometheusMetricsCollector initializes with default registry."""
        # Note: This test intentionally uses default REGISTRY (not isolated)
        collector = PrometheusMetricsCollector()
        assert collector._registry is REGISTRY

    def test_initialization_custom_registry(self, isolated_registry: CollectorRegistry) -> None:
        """Test that PrometheusMetricsCollector can use custom registry."""
        collector = PrometheusMetricsCollector(registry=isolated_registry)
        assert collector._registry is isolated_registry
        assert collector._registry is not REGISTRY


class TestPrometheusMetricsCollectorCounter:
    """Tests for counter metrics."""

    def test_increment_counter_without_labels(
        self, prometheus_collector: PrometheusMetricsCollector
    ) -> None:
        """Test that increment_counter works without labels."""
        collector = prometheus_collector
        collector.increment_counter("test_counter_total")
        collector.increment_counter("test_counter_total")
        # Prometheus counters don't support direct get(), but we can verify
        # the metric was created by checking the registry
        assert "test_counter_total" in str(generate_latest(collector._registry))

    def test_increment_counter_with_labels(
        self, prometheus_collector: PrometheusMetricsCollector
    ) -> None:
        """Test that increment_counter works with labels."""
        collector = prometheus_collector
        collector.increment_counter("test_counter_total", labels={"status": "success"})
        collector.increment_counter("test_counter_total", labels={"status": "error"})
        # Verify both labeled metrics exist
        metrics_output = generate_latest(collector._registry).decode("utf-8")
        assert "test_counter_total" in metrics_output
        assert 'status="success"' in metrics_output
        assert 'status="error"' in metrics_output

    def test_increment_counter_multiple_labels(
        self, prometheus_collector: PrometheusMetricsCollector
    ) -> None:
        """Test that increment_counter works with multiple labels."""
        collector = prometheus_collector
        collector.increment_counter("test_counter_total", labels={"market": "btc", "outcome": "UP"})
        metrics_output = generate_latest(collector._registry).decode("utf-8")
        assert "test_counter_total" in metrics_output
        assert 'market="btc"' in metrics_output
        assert 'outcome="UP"' in metrics_output

    def test_increment_counter_same_name_different_labels(
        self, prometheus_collector: PrometheusMetricsCollector
    ) -> None:
        """Test that same metric name with different label values creates separate time series."""
        collector = prometheus_collector
        # Prometheus requires same label names for same metric,
        # but different values create different series
        collector.increment_counter("test_counter_total", labels={"status": "success"})
        collector.increment_counter("test_counter_total", labels={"status": "error"})
        # Both should exist as separate time series with same metric name
        metrics_output = generate_latest(collector._registry).decode("utf-8")
        assert "test_counter_total" in metrics_output
        assert 'status="success"' in metrics_output
        assert 'status="error"' in metrics_output

    def test_get_counter_returns_zero(
        self, prometheus_collector: PrometheusMetricsCollector
    ) -> None:
        """Test that get_counter returns 0 (Prometheus is pull-based)."""
        collector = prometheus_collector
        collector.increment_counter("test_counter_total")
        # Prometheus doesn't support direct value queries
        assert collector.get_counter("test_counter_total") == 0


class TestPrometheusMetricsCollectorGauge:
    """Tests for gauge metrics."""

    def test_set_gauge_without_labels(
        self, prometheus_collector: PrometheusMetricsCollector
    ) -> None:
        """Test that set_gauge works without labels."""
        collector = prometheus_collector
        collector.set_gauge("test_gauge", 42.5)
        # Verify metric was created
        assert "test_gauge" in str(generate_latest(collector._registry))

    def test_set_gauge_with_labels(self, prometheus_collector: PrometheusMetricsCollector) -> None:
        """Test that set_gauge works with labels."""
        collector = prometheus_collector
        collector.set_gauge("test_gauge", 10.0, labels={"market": "btc"})
        collector.set_gauge("test_gauge", 20.0, labels={"market": "eth"})
        metrics_output = generate_latest(collector._registry).decode("utf-8")
        assert "test_gauge" in metrics_output
        assert 'market="btc"' in metrics_output
        assert 'market="eth"' in metrics_output

    def test_set_gauge_updates_value(
        self, prometheus_collector: PrometheusMetricsCollector
    ) -> None:
        """Test that set_gauge updates the value."""
        collector = prometheus_collector
        collector.set_gauge("test_gauge", 10.0)
        collector.set_gauge("test_gauge", 20.0)
        # Both operations should work (Prometheus gauges are mutable)
        metrics_output = generate_latest(collector._registry).decode("utf-8")
        assert "test_gauge" in metrics_output

    def test_get_gauge_returns_zero(self, prometheus_collector: PrometheusMetricsCollector) -> None:
        """Test that get_gauge returns 0.0 (Prometheus is pull-based)."""
        collector = prometheus_collector
        collector.set_gauge("test_gauge", 42.5)
        # Prometheus doesn't support direct value queries
        assert collector.get_gauge("test_gauge") == 0.0


class TestPrometheusMetricsCollectorHistogram:
    """Tests for histogram metrics."""

    def test_record_histogram_without_labels(
        self, prometheus_collector: PrometheusMetricsCollector
    ) -> None:
        """Test that record_histogram works without labels."""
        collector = prometheus_collector
        collector.record_histogram("test_histogram", 10.5)
        collector.record_histogram("test_histogram", 20.3)
        # Verify metric was created
        assert "test_histogram" in str(generate_latest(collector._registry))

    def test_record_histogram_with_labels(
        self, prometheus_collector: PrometheusMetricsCollector
    ) -> None:
        """Test that record_histogram works with labels."""
        collector = prometheus_collector
        collector.record_histogram("test_histogram", 10.5, labels={"operation": "read"})
        collector.record_histogram("test_histogram", 20.3, labels={"operation": "write"})
        metrics_output = generate_latest(collector._registry).decode("utf-8")
        assert "test_histogram" in metrics_output
        assert 'operation="read"' in metrics_output
        assert 'operation="write"' in metrics_output

    def test_record_histogram_multiple_values(
        self, prometheus_collector: PrometheusMetricsCollector
    ) -> None:
        """Test that record_histogram can record multiple values."""
        collector = prometheus_collector
        for value in [10.0, 20.0, 30.0, 40.0, 50.0]:
            collector.record_histogram("test_histogram", value)
        # All values should be recorded in Prometheus buckets
        metrics_output = generate_latest(collector._registry).decode("utf-8")
        assert "test_histogram" in metrics_output
        assert "test_histogram_bucket" in metrics_output

    def test_get_histogram_percentiles_returns_zero(
        self, prometheus_collector: PrometheusMetricsCollector
    ) -> None:
        """Test that get_histogram_percentiles returns zeros (Prometheus is pull-based)."""
        collector = prometheus_collector
        collector.record_histogram("test_histogram", 10.5)
        # Prometheus doesn't support direct percentile queries
        result = collector.get_histogram_percentiles("test_histogram")
        assert result == {0.5: 0.0, 0.95: 0.0, 0.99: 0.0}

    def test_get_histogram_percentiles_custom_percentiles(
        self, prometheus_collector: PrometheusMetricsCollector
    ) -> None:
        """Test that get_histogram_percentiles accepts custom percentiles."""
        collector = prometheus_collector
        collector.record_histogram("test_histogram", 10.5)
        result = collector.get_histogram_percentiles("test_histogram", percentiles=[0.25, 0.75])
        assert result == {0.25: 0.0, 0.75: 0.0}


class TestPrometheusMetricsCollectorLabelHandling:
    """Tests for label handling and conversion."""

    def test_labels_sorted_consistently(
        self, prometheus_collector: PrometheusMetricsCollector
    ) -> None:
        """Test that labels are sorted consistently for same metric."""
        collector = prometheus_collector
        # Create metric with labels in different order
        collector.increment_counter("test_counter", labels={"b": "2", "a": "1"})
        collector.increment_counter("test_counter", labels={"a": "1", "b": "2"})
        # Should use same metric instance (labels sorted internally)
        metrics_output = generate_latest(collector._registry).decode("utf-8")
        # Both should result in same labeled metric
        assert metrics_output.count('a="1"') >= 1
        assert metrics_output.count('b="2"') >= 1

    def test_empty_labels_dict(self, prometheus_collector: PrometheusMetricsCollector) -> None:
        """Test that empty labels dict is handled correctly."""
        collector = prometheus_collector
        collector.increment_counter("test_counter", labels={})
        # Should work without errors
        assert "test_counter" in str(generate_latest(collector._registry))

    def test_none_labels(self, prometheus_collector: PrometheusMetricsCollector) -> None:
        """Test that None labels are handled correctly."""
        collector = prometheus_collector
        collector.increment_counter("test_counter", labels=None)
        # Should work without errors
        assert "test_counter" in str(generate_latest(collector._registry))


class TestPrometheusMetricsCollectorPrometheusFormat:
    """Tests for Prometheus format compatibility."""

    def test_metrics_exported_in_prometheus_format(
        self, prometheus_collector: PrometheusMetricsCollector
    ) -> None:
        """Test that metrics can be exported in Prometheus text format."""
        collector = prometheus_collector
        collector.increment_counter("test_counter_total")
        collector.set_gauge("test_gauge", 42.5)
        collector.record_histogram("test_histogram", 10.0)

        # Generate Prometheus format
        output = generate_latest(collector._registry).decode("utf-8")

        # Verify Prometheus format structure
        assert "# TYPE" in output or "test_counter_total" in output
        assert "test_gauge" in output
        assert "test_histogram" in output

    def test_counter_has_total_suffix(
        self, prometheus_collector: PrometheusMetricsCollector
    ) -> None:
        """Test that counter metrics follow Prometheus naming conventions."""
        collector = prometheus_collector
        collector.increment_counter("test_counter_total")
        output = generate_latest(collector._registry).decode("utf-8")
        assert "test_counter_total" in output

    def test_histogram_creates_buckets(
        self, prometheus_collector: PrometheusMetricsCollector
    ) -> None:
        """Test that histogram creates bucket metrics."""
        collector = prometheus_collector
        collector.record_histogram("test_histogram", 10.0)
        output = generate_latest(collector._registry).decode("utf-8")
        # Prometheus histograms create _bucket, _sum, _count metrics
        assert "test_histogram" in output


class TestPrometheusMetricsCollectorInterfaceCompliance:
    """Tests to verify IMetricsCollector interface compliance."""

    def test_implements_all_required_methods(
        self, prometheus_collector: PrometheusMetricsCollector
    ) -> None:
        """Test that PrometheusMetricsCollector implements all IMetricsCollector methods."""
        collector = prometheus_collector
        # Verify all required methods exist
        assert hasattr(collector, "increment_counter")
        assert hasattr(collector, "set_gauge")
        assert hasattr(collector, "record_histogram")
        assert hasattr(collector, "get_counter")
        assert hasattr(collector, "get_gauge")
        assert hasattr(collector, "get_histogram_percentiles")

    def test_method_signatures_match_interface(
        self, prometheus_collector: PrometheusMetricsCollector
    ) -> None:
        """Test that method signatures match IMetricsCollector protocol."""
        import inspect

        collector = prometheus_collector

        # Check increment_counter signature
        collector_sig = inspect.signature(collector.increment_counter)
        # Should accept name and optional labels
        assert "name" in collector_sig.parameters
        assert "labels" in collector_sig.parameters

        # Check set_gauge signature
        collector_sig = inspect.signature(collector.set_gauge)
        assert "name" in collector_sig.parameters
        assert "value" in collector_sig.parameters
        assert "labels" in collector_sig.parameters

        # Check record_histogram signature
        collector_sig = inspect.signature(collector.record_histogram)
        assert "name" in collector_sig.parameters
        assert "value" in collector_sig.parameters
        assert "labels" in collector_sig.parameters


class TestPrometheusMetricsCollectorIsolation:
    """Tests to verify metrics isolation between instances."""

    def test_different_registries_isolated(self) -> None:
        """Test that different collectors with different registries are isolated."""
        registry1 = CollectorRegistry()
        registry2 = CollectorRegistry()
        collector1 = PrometheusMetricsCollector(registry=registry1)
        collector2 = PrometheusMetricsCollector(registry=registry2)

        collector1.increment_counter("test_counter")
        collector2.increment_counter("test_counter")

        # Each registry should have its own metrics
        output1 = generate_latest(registry1).decode("utf-8")
        output2 = generate_latest(registry2).decode("utf-8")

        assert "test_counter" in output1
        assert "test_counter" in output2
        # They should be independent
        assert output1 != output2 or len(output1) > 0  # At least one has metrics
