"""Unit tests for metrics collector factory.

Per Commit 3: Verify create_metrics_collector() factory function works correctly
with both prometheus and memory backends, defaults to prometheus, and handles
configuration properly.
"""

import pytest

from polytrader.config import MetricsConfig
from polytrader.obs.metrics import (
    MemoryMetricsCollector,
    create_metrics_collector,
    get_metrics_collector,
    set_metrics_collector,
)


class TestCreateMetricsCollector:
    """Tests for create_metrics_collector() factory function."""

    def test_create_metrics_collector_defaults_to_prometheus(self) -> None:
        """Test that create_metrics_collector defaults to prometheus."""
        collector = create_metrics_collector()
        # Should be PrometheusMetricsCollector
        from polytrader.obs.metrics_prometheus import PrometheusMetricsCollector

        assert isinstance(collector, PrometheusMetricsCollector)

    def test_create_metrics_collector_with_prometheus_backend(self) -> None:
        """Test that create_metrics_collector works with 'prometheus' backend."""
        collector = create_metrics_collector(backend="prometheus")
        from polytrader.obs.metrics_prometheus import PrometheusMetricsCollector

        assert isinstance(collector, PrometheusMetricsCollector)

    def test_create_metrics_collector_with_memory_backend(self) -> None:
        """Test that create_metrics_collector works with 'memory' backend."""
        collector = create_metrics_collector(backend="memory")
        assert isinstance(collector, MemoryMetricsCollector)

    def test_create_metrics_collector_reads_config(self) -> None:
        """Test that create_metrics_collector reads MetricsConfig."""
        # Use model_construct to bypass env file reading for explicit test values
        config = MetricsConfig.model_construct(metrics_backend="memory")
        collector = create_metrics_collector(config=config)
        assert isinstance(collector, MemoryMetricsCollector)

        config = MetricsConfig.model_construct(metrics_backend="prometheus")
        collector = create_metrics_collector(config=config)
        from polytrader.obs.metrics_prometheus import PrometheusMetricsCollector

        assert isinstance(collector, PrometheusMetricsCollector)

    def test_create_metrics_collector_config_overrides_default(self) -> None:
        """Test that MetricsConfig overrides default."""
        # Use model_construct to bypass env file reading for explicit test values
        config = MetricsConfig.model_construct(metrics_backend="memory")
        collector = create_metrics_collector(config=config)
        assert isinstance(collector, MemoryMetricsCollector)

    def test_create_metrics_collector_explicit_backend_overrides_config(self) -> None:
        """Test that explicit backend parameter overrides config."""
        # Use model_construct to bypass env file reading for explicit test values
        config = MetricsConfig.model_construct(metrics_backend="memory")
        collector = create_metrics_collector(backend="prometheus", config=config)
        from polytrader.obs.metrics_prometheus import PrometheusMetricsCollector

        assert isinstance(collector, PrometheusMetricsCollector)

    def test_create_metrics_collector_invalid_backend_raises_error(self) -> None:
        """Test that invalid backend raises ValueError."""
        with pytest.raises(ValueError, match="Unknown metrics backend"):
            create_metrics_collector(backend="invalid")

    def test_create_metrics_collector_creates_new_instances(self) -> None:
        """Test that create_metrics_collector creates new instances each time."""
        collector1 = create_metrics_collector(backend="memory")
        collector2 = create_metrics_collector(backend="memory")
        # Should be different instances
        assert collector1 is not collector2


class TestGetMetricsCollectorUsesFactory:
    """Tests for get_metrics_collector() using factory."""

    def test_get_metrics_collector_defaults_to_prometheus(self) -> None:
        """Test that get_metrics_collector defaults to prometheus via factory."""
        # Reset to None to test default
        set_metrics_collector(None)
        collector = get_metrics_collector()
        from polytrader.obs.metrics_prometheus import PrometheusMetricsCollector

        assert isinstance(collector, PrometheusMetricsCollector)

    def test_get_metrics_collector_uses_default_config(self) -> None:
        """Test that get_metrics_collector uses default MetricsConfig."""
        set_metrics_collector(None)
        # Default config should use prometheus backend
        collector = get_metrics_collector()
        from polytrader.obs.metrics_prometheus import PrometheusMetricsCollector

        assert isinstance(collector, PrometheusMetricsCollector)

    def test_get_metrics_collector_returns_singleton(self) -> None:
        """Test that get_metrics_collector returns singleton instance."""
        set_metrics_collector(None)
        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()
        assert collector1 is collector2

    def test_get_metrics_collector_uses_factory_on_first_call(self) -> None:
        """Test that get_metrics_collector uses factory to create collector."""
        set_metrics_collector(None)
        # First call should create via factory
        collector = get_metrics_collector()
        assert collector is not None
        # Should be PrometheusMetricsCollector by default
        from polytrader.obs.metrics_prometheus import PrometheusMetricsCollector

        assert isinstance(collector, PrometheusMetricsCollector)
