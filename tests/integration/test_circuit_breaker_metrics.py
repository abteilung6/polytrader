"""Integration tests for circuit breaker metrics in supervisor context.

Per Commit 12: Integrate circuit breaker metrics.
Per observability.mdc §4: Circuit breaker metrics are critical for operational monitoring.
"""

import pytest

from polytrader.events.bus import EventBus
from polytrader.events.store import MemoryEventStore
from polytrader.events.types import ReconcileEvent
from polytrader.obs.metrics import (
    MemoryMetricsCollector,
    set_metrics_collector,
)
from polytrader.ops.control import (
    CircuitBreaker,
    CircuitBreakerThresholds,
    ExecutionControl,
)


@pytest.fixture
def bus() -> EventBus:
    """Create an event bus for testing."""
    return EventBus(store=MemoryEventStore())


@pytest.fixture
def metrics_collector() -> MemoryMetricsCollector:
    """Create a metrics collector for testing."""
    collector = MemoryMetricsCollector()
    set_metrics_collector(collector)
    return collector


@pytest.fixture
def execution_control(bus: EventBus) -> ExecutionControl:
    """Create an execution control for testing."""
    return ExecutionControl(bus=bus)


@pytest.fixture
def circuit_breaker(bus: EventBus, execution_control: ExecutionControl) -> CircuitBreaker:
    """Create a circuit breaker for testing."""
    thresholds = CircuitBreakerThresholds(
        max_phantom_orders=1,  # Low threshold for testing
        max_orphan_orders=1,
        max_fill_mismatches=1,
        require_error_severity=False,  # Don't require ERROR severity for test
    )
    return CircuitBreaker(thresholds=thresholds, bus=bus, execution_control=execution_control)


class TestCircuitBreakerMetricsInSupervisorContext:
    """Tests for circuit breaker metrics when used by supervisor reconciliation loop."""

    @pytest.mark.asyncio
    async def test_supervisor_reconciliation_loop_emits_metrics_on_trigger(
        self,
        bus: EventBus,
        circuit_breaker: CircuitBreaker,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that supervisor reconciliation loop emits metrics when circuit breaker triggers."""
        # Create reconcile events that will trigger circuit breaker
        reconcile_events = [
            ReconcileEvent(
                divergence_type="phantom_order",
                severity="WARNING",
                details={"order_id": "order-123"},
            ),
            ReconcileEvent(
                divergence_type="orphan_order",
                severity="WARNING",
                details={"venue_order_id": "venue-123"},
            ),
        ]

        # Simulate supervisor reconciliation loop calling circuit breaker
        # (This is what happens in SystemSupervisor._start_reconciliation_task)
        event = await circuit_breaker.check(reconcile_events)

        # Verify circuit breaker was triggered
        assert event is not None
        assert event.triggered is True
        assert event.breaker_type == "reconcile_divergence"

        # Verify metric was emitted
        assert (
            metrics_collector.get_counter(
                "circuit_breaker_total", labels={"type": "reconcile_divergence"}
            )
            == 1
        )

    @pytest.mark.asyncio
    async def test_supervisor_reconciliation_loop_no_metrics_when_not_triggered(
        self,
        bus: EventBus,
        circuit_breaker: CircuitBreaker,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that supervisor reconciliation loop does not emit metrics when not triggered."""
        # Create reconcile events that will NOT trigger circuit breaker
        # (empty list or no divergences)
        reconcile_events: list[ReconcileEvent] = []

        # Simulate supervisor reconciliation loop calling circuit breaker
        event = await circuit_breaker.check(reconcile_events)

        # Verify circuit breaker was NOT triggered
        assert event is None

        # Verify NO metric was emitted
        assert (
            metrics_collector.get_counter(
                "circuit_breaker_total", labels={"type": "reconcile_divergence"}
            )
            == 0
        )

    @pytest.mark.asyncio
    async def test_supervisor_reconciliation_loop_multiple_checks(
        self,
        bus: EventBus,
        circuit_breaker: CircuitBreaker,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that supervisor reconciliation loop handles multiple checks correctly."""
        # First check: trigger circuit breaker
        reconcile_events1 = [
            ReconcileEvent(
                divergence_type="phantom_order",
                severity="WARNING",
                details={"order_id": "order-1"},
            ),
        ]
        event1 = await circuit_breaker.check(reconcile_events1)
        assert event1 is not None
        assert (
            metrics_collector.get_counter(
                "circuit_breaker_total", labels={"type": "reconcile_divergence"}
            )
            == 1
        )

        # Second check: circuit breaker already triggered, should not trigger again
        reconcile_events2 = [
            ReconcileEvent(
                divergence_type="phantom_order",
                severity="WARNING",
                details={"order_id": "order-2"},
            ),
        ]
        event2 = await circuit_breaker.check(reconcile_events2)
        assert event2 is None  # Already triggered, won't trigger again

        # Verify metric count did NOT increase
        assert (
            metrics_collector.get_counter(
                "circuit_breaker_total", labels={"type": "reconcile_divergence"}
            )
            == 1
        )

        # Reset circuit breaker
        await circuit_breaker.reset()
        assert (
            metrics_collector.get_counter(
                "circuit_breaker_total", labels={"type": "reconcile_divergence_reset"}
            )
            == 1
        )

        # Third check: After reset, should trigger again
        reconcile_events3 = [
            ReconcileEvent(
                divergence_type="phantom_order",
                severity="WARNING",
                details={"order_id": "order-3"},
            ),
        ]
        event3 = await circuit_breaker.check(reconcile_events3)
        assert event3 is not None

        # Verify metric count increased
        assert (
            metrics_collector.get_counter(
                "circuit_breaker_total", labels={"type": "reconcile_divergence"}
            )
            == 2
        )

    @pytest.mark.asyncio
    async def test_supervisor_reconciliation_loop_reset_emits_metric(
        self,
        bus: EventBus,
        circuit_breaker: CircuitBreaker,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that supervisor can reset circuit breaker and metrics are emitted."""
        # Trigger circuit breaker first
        reconcile_events = [
            ReconcileEvent(
                divergence_type="phantom_order",
                severity="WARNING",
                details={"order_id": "order-123"},
            ),
        ]
        await circuit_breaker.check(reconcile_events)

        # Verify initial metric
        assert (
            metrics_collector.get_counter(
                "circuit_breaker_total", labels={"type": "reconcile_divergence"}
            )
            == 1
        )

        # Reset circuit breaker (simulating operator action)
        await circuit_breaker.reset()

        # Verify reset metric was emitted
        assert (
            metrics_collector.get_counter(
                "circuit_breaker_total", labels={"type": "reconcile_divergence_reset"}
            )
            == 1
        )

    @pytest.mark.asyncio
    async def test_supervisor_reconciliation_loop_execution_disabled_on_trigger(
        self,
        bus: EventBus,
        circuit_breaker: CircuitBreaker,
        execution_control: ExecutionControl,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that supervisor reconciliation loop disables execution on trigger."""
        # Enable execution first
        execution_control.enable()
        assert execution_control.is_enabled()
        assert metrics_collector.get_gauge("execution_enabled") == 1.0

        # Trigger circuit breaker
        reconcile_events = [
            ReconcileEvent(
                divergence_type="phantom_order",
                severity="WARNING",
                details={"order_id": "order-123"},
            ),
        ]
        await circuit_breaker.check(reconcile_events)

        # Verify execution was disabled
        assert not execution_control.is_enabled()
        assert metrics_collector.get_gauge("execution_enabled") == 0.0

        # Verify circuit breaker metric was emitted
        assert (
            metrics_collector.get_counter(
                "circuit_breaker_total", labels={"type": "reconcile_divergence"}
            )
            == 1
        )
