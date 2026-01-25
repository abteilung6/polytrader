"""Shared fixtures for OMS unit tests."""

from collections.abc import Generator

import pytest

from polytrader.obs.metrics import MemoryMetricsCollector, set_metrics_collector
from polytrader.oms.core import OMSCore


@pytest.fixture(autouse=True)
def metrics_collector() -> Generator[MemoryMetricsCollector, None, None]:
    """Use MemoryMetricsCollector for all OMS tests to prevent Prometheus metric duplication.

    Per testing.mdc: Unit tests must be isolated. This fixture ensures each test
    gets a fresh metrics collector, preventing "Duplicated timeseries" errors.

    Yields:
        MemoryMetricsCollector instance
    """
    collector = MemoryMetricsCollector()
    set_metrics_collector(collector)
    yield collector
    # Cleanup: reset to None so next test gets fresh collector
    set_metrics_collector(None)


@pytest.fixture
def oms_core(
    bus,  # From root conftest
    order_store,  # From root conftest
    idempotency_store,  # From root conftest
) -> OMSCore:
    """Create OMSCore for testing."""
    return OMSCore(bus=bus, store=order_store, idempotency_store=idempotency_store)


@pytest.fixture
def sample_intent():
    """Create sample order intent for testing."""
    from tests.factories.events import create_order_intent_event

    return create_order_intent_event()
