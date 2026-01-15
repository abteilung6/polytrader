"""Integration tests for safety metrics in ops control.

Per Commit 11: Integrate safety metrics in ops control.
Per observability.mdc §4: Safety metrics are critical for operational monitoring.
"""

import pytest

from polytrader.events.bus import EventBus
from polytrader.events.store import MemoryEventStore
from polytrader.obs.metrics import (
    MemoryMetricsCollector,
    set_metrics_collector,
)
from polytrader.ops.control import CircuitBreaker, CircuitBreakerThresholds, ExecutionControl


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


class TestExecutionControlSafetyMetrics:
    """Tests for execution_enabled gauge in ExecutionControl."""

    def test_enable_emits_execution_enabled_gauge(
        self, execution_control: ExecutionControl, metrics_collector: MemoryMetricsCollector
    ) -> None:
        """Test that enable() emits execution_enabled gauge = 1.0."""
        # Initially disabled
        assert execution_control.execution_enabled is False
        assert metrics_collector.get_gauge("execution_enabled") == 0.0

        # Enable execution
        execution_control.enable()

        # Verify state
        assert execution_control.execution_enabled is True

        # Verify gauge was updated
        assert metrics_collector.get_gauge("execution_enabled") == 1.0

    def test_disable_emits_execution_enabled_gauge(
        self, execution_control: ExecutionControl, metrics_collector: MemoryMetricsCollector
    ) -> None:
        """Test that disable() emits execution_enabled gauge = 0.0."""
        # Enable first
        execution_control.enable()
        assert metrics_collector.get_gauge("execution_enabled") == 1.0

        # Disable execution
        execution_control.disable()

        # Verify state
        assert execution_control.execution_enabled is False

        # Verify gauge was updated
        assert metrics_collector.get_gauge("execution_enabled") == 0.0

    @pytest.mark.asyncio
    async def test_enable_with_permit_emits_execution_enabled_gauge(
        self,
        execution_control: ExecutionControl,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that enable_with_permit() emits execution_enabled gauge = 1.0."""
        # Initially disabled
        assert execution_control.execution_enabled is False
        assert metrics_collector.get_gauge("execution_enabled") == 0.0

        # Enable with permit
        await execution_control.enable_with_permit(
            permit_type="boot",
            reason="System boot complete",
            health_status={"status": "healthy"},
            issued_by="system",
        )

        # Verify state
        assert execution_control.execution_enabled is True

        # Verify gauge was updated
        assert metrics_collector.get_gauge("execution_enabled") == 1.0

    @pytest.mark.asyncio
    async def test_set_kill_switch_emits_execution_enabled_gauge_when_activated(
        self,
        execution_control: ExecutionControl,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that set_kill_switch(active=True) emits execution_enabled gauge = 0.0."""
        # Enable first
        execution_control.enable()
        assert metrics_collector.get_gauge("execution_enabled") == 1.0

        # Activate kill switch
        await execution_control.set_kill_switch(
            active=True, reason="Test kill switch", triggered_by="operator"
        )

        # Verify state
        assert execution_control.kill_switch_active is True
        assert execution_control.execution_enabled is False  # Disabled by kill switch

        # Verify gauges were updated
        assert metrics_collector.get_gauge("execution_enabled") == 0.0
        assert metrics_collector.get_gauge("kill_switch") == 1.0

    @pytest.mark.asyncio
    async def test_set_kill_switch_emits_kill_switch_gauge(
        self,
        execution_control: ExecutionControl,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that set_kill_switch() emits kill_switch gauge."""
        # Initially inactive
        assert execution_control.kill_switch_active is False
        assert metrics_collector.get_gauge("kill_switch") == 0.0

        # Activate kill switch
        await execution_control.set_kill_switch(
            active=True, reason="Test activation", triggered_by="operator"
        )

        # Verify gauge was updated
        assert metrics_collector.get_gauge("kill_switch") == 1.0

        # Deactivate kill switch
        await execution_control.set_kill_switch(
            active=False, reason="Test deactivation", triggered_by="operator"
        )

        # Verify gauge was updated
        assert metrics_collector.get_gauge("kill_switch") == 0.0

    def test_execution_enabled_gauge_updates_on_state_changes(
        self, execution_control: ExecutionControl, metrics_collector: MemoryMetricsCollector
    ) -> None:
        """Test that execution_enabled gauge updates correctly on all state changes."""
        # Initial state
        assert metrics_collector.get_gauge("execution_enabled") == 0.0

        # Enable
        execution_control.enable()
        assert metrics_collector.get_gauge("execution_enabled") == 1.0

        # Disable
        execution_control.disable()
        assert metrics_collector.get_gauge("execution_enabled") == 0.0

        # Enable again
        execution_control.enable()
        assert metrics_collector.get_gauge("execution_enabled") == 1.0


class TestCircuitBreakerSafetyMetrics:
    """Tests for circuit_breaker_total counter in CircuitBreaker."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_trigger_emits_metric(
        self,
        bus: EventBus,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that circuit breaker trigger emits circuit_breaker_total counter."""
        execution_control = ExecutionControl(bus=bus)
        thresholds = CircuitBreakerThresholds(
            max_phantom_orders=1,  # Low threshold for testing
            max_orphan_orders=1,
            max_fill_mismatches=1,
            require_error_severity=False,  # Don't require ERROR severity for test
        )
        circuit_breaker = CircuitBreaker(
            thresholds=thresholds, bus=bus, execution_control=execution_control
        )

        # Create reconcile events that will trigger circuit breaker
        from polytrader.events.types import ReconcileEvent

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

        # Trigger circuit breaker
        event = await circuit_breaker.check(reconcile_events)

        # Verify circuit breaker was triggered
        assert event is not None
        assert event.triggered is True

        # Verify metric was emitted
        assert (
            metrics_collector.get_counter(
                "circuit_breaker_total", labels={"type": "reconcile_divergence"}
            )
            == 1
        )

        # Verify execution was disabled
        assert execution_control.execution_enabled is False
        assert metrics_collector.get_gauge("execution_enabled") == 0.0

    @pytest.mark.asyncio
    async def test_circuit_breaker_reset_emits_metric(
        self,
        bus: EventBus,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that circuit breaker reset emits circuit_breaker_total counter."""
        execution_control = ExecutionControl(bus=bus)
        thresholds = CircuitBreakerThresholds(
            max_phantom_orders=1,
            require_error_severity=False,
        )
        circuit_breaker = CircuitBreaker(
            thresholds=thresholds, bus=bus, execution_control=execution_control
        )

        # Trigger circuit breaker first
        from polytrader.events.types import ReconcileEvent

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

        # Reset circuit breaker
        await circuit_breaker.reset()

        # Verify reset metric was emitted
        assert (
            metrics_collector.get_counter(
                "circuit_breaker_total", labels={"type": "reconcile_divergence_reset"}
            )
            == 1
        )

    @pytest.mark.asyncio
    async def test_circuit_breaker_multiple_triggers(
        self,
        bus: EventBus,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that multiple circuit breaker triggers are tracked separately."""
        execution_control = ExecutionControl(bus=bus)
        thresholds = CircuitBreakerThresholds(
            max_phantom_orders=1,
            require_error_severity=False,
        )
        circuit_breaker = CircuitBreaker(
            thresholds=thresholds, bus=bus, execution_control=execution_control
        )

        from polytrader.events.types import ReconcileEvent

        # Trigger first time
        reconcile_events1 = [
            ReconcileEvent(
                divergence_type="phantom_order",
                severity="WARNING",
                details={"order_id": "order-1"},
            ),
        ]
        await circuit_breaker.check(reconcile_events1)
        assert (
            metrics_collector.get_counter(
                "circuit_breaker_total", labels={"type": "reconcile_divergence"}
            )
            == 1
        )

        # Reset
        await circuit_breaker.reset()
        assert (
            metrics_collector.get_counter(
                "circuit_breaker_total", labels={"type": "reconcile_divergence_reset"}
            )
            == 1
        )

        # Trigger again (after reset, circuit breaker can trigger again)
        reconcile_events2 = [
            ReconcileEvent(
                divergence_type="phantom_order",
                severity="WARNING",
                details={"order_id": "order-2"},
            ),
        ]
        await circuit_breaker.check(reconcile_events2)

        # Verify metric was incremented
        assert (
            metrics_collector.get_counter(
                "circuit_breaker_total", labels={"type": "reconcile_divergence"}
            )
            == 2
        )
