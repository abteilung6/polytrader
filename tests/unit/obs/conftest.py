"""Shared fixtures for observability unit tests.

Per unit_testing_techinical.mdc §5: Fixtures with function scope by default.
"""

import pytest
from prometheus_client import CollectorRegistry

from polytrader.obs.metrics_prometheus import PrometheusMetricsCollector


@pytest.fixture
def isolated_registry() -> CollectorRegistry:
    """Create an isolated Prometheus CollectorRegistry for testing.

    This fixture provides a fresh registry for each test to avoid
    metric name conflicts when running tests in parallel.

    Returns:
        CollectorRegistry instance (isolated from default REGISTRY)
    """
    return CollectorRegistry()


@pytest.fixture
def prometheus_collector(isolated_registry: CollectorRegistry) -> PrometheusMetricsCollector:
    """Create a PrometheusMetricsCollector with isolated registry.

    This fixture provides a fresh collector for each test with its own
    registry, preventing metric name conflicts in parallel test execution.

    Args:
        isolated_registry: Isolated CollectorRegistry fixture

    Returns:
        PrometheusMetricsCollector instance with isolated registry
    """
    return PrometheusMetricsCollector(registry=isolated_registry)
