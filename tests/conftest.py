"""Pytest configuration and shared fixtures.

This file provides shared fixtures and utilities for all tests.
"""

from collections.abc import Generator

import pytest

from polytrader.db.models import StrategyRecord
from polytrader.events.bus import EventBus
from polytrader.obs.metrics import MemoryMetricsCollector, set_metrics_collector
from polytrader.oms.idempotency import IdempotencyStore
from polytrader.oms.store import InMemoryOrderStore
from polytrader.strategies.lifecycle_models import StrategyLifecycleState


@pytest.fixture(autouse=True)
def _use_memory_metrics() -> Generator[None, None, None]:
    """Set MemoryMetricsCollector as global metrics backend for all tests.

    This prevents Prometheus CollectorRegistry duplication errors when
    multiple create_app() or ExecutionControl instances are created
    across tests. The ObservabilityMiddleware and all metrics helper
    functions (set_execution_enabled, set_kill_switch, etc.) call
    get_metrics_collector() which would otherwise create a singleton
    PrometheusMetricsCollector that registers in the global registry.

    By setting MemoryMetricsCollector here, we ensure:
    - No Prometheus registry conflicts across test files
    - No side effects from metric registration in production code
    - Each test gets a clean metrics state

    Tests that specifically need Prometheus (e.g. tests/unit/obs/) can
    override by using the isolated_registry fixture from their conftest.

    Per unit_testing_technical.mdc: Unit tests must be isolated and
    free of external I/O.
    """
    collector = MemoryMetricsCollector()
    set_metrics_collector(collector)
    yield
    set_metrics_collector(None)


@pytest.fixture
def bus() -> EventBus:
    """Create EventBus for testing."""
    return EventBus()


@pytest.fixture
def order_store(bus: EventBus) -> InMemoryOrderStore:
    """Create InMemoryOrderStore for testing."""
    return InMemoryOrderStore(bus)


@pytest.fixture
def idempotency_store() -> IdempotencyStore:
    """Create IdempotencyStore for testing."""
    return IdempotencyStore()


def create_strategy_record(
    strategy_id: str,
    name: str,
    config: dict,
    enabled: bool = True,
    template_type_id: str = "simple_threshold",
    template_version: str = "1.0.0",
    config_hash: str | None = None,
) -> StrategyRecord:
    """Helper function to create StrategyRecord with required fields.

    Args:
        strategy_id: Strategy identifier
        name: Strategy name
        config: Strategy configuration
        enabled: Whether strategy should be enabled (maps to RUNNING/STOPPED state)
        template_type_id: Template type identifier
        template_version: Template version
        config_hash: Config hash (auto-generated if None)

    Returns:
        StrategyRecord instance with all required fields
    """
    if config_hash is None:
        # Generate a simple hash from strategy_id for testing
        config_hash = f"hash_{strategy_id}"

    desired_state = StrategyLifecycleState.RUNNING if enabled else StrategyLifecycleState.STOPPED

    return StrategyRecord(
        strategy_id=strategy_id,
        name=name,
        config=config,
        template_type_id=template_type_id,
        template_version=template_version,
        config_hash=config_hash,
        desired_state=desired_state,
        actual_state=desired_state,
    )
