"""Tests for circuit breaker.

Per Phase 6 Commit 6: Test CircuitBreaker functionality including:
- No trigger on minor divergences
- Trigger on multiple phantom orders
- Trigger on fill mismatch
- Reset circuit breaker
"""

import asyncio
from collections.abc import Generator

import pytest

from polytrader.events import CIRCUIT_BREAKER
from polytrader.events.bus import EventBus
from polytrader.events.types import ReconcileEvent
from polytrader.obs.metrics import MemoryMetricsCollector, set_metrics_collector
from polytrader.ops.control import CircuitBreaker, CircuitBreakerThresholds, ExecutionControl


@pytest.fixture
def metrics_collector() -> Generator[MemoryMetricsCollector, None, None]:
    """Create a memory metrics collector for testing.

    This prevents Prometheus metric duplication errors when multiple
    ExecutionControl instances are created in tests.
    """
    collector = MemoryMetricsCollector()
    set_metrics_collector(collector)
    yield collector
    # Cleanup: reset to None so next test gets fresh collector
    set_metrics_collector(None)


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def execution_control(metrics_collector: MemoryMetricsCollector) -> ExecutionControl:
    """Create ExecutionControl with metrics collector set up.

    Args:
        metrics_collector: Memory metrics collector fixture (ensures metrics are set up)
    """
    return ExecutionControl()


@pytest.fixture
def default_thresholds() -> CircuitBreakerThresholds:
    return CircuitBreakerThresholds()


@pytest.fixture
def circuit_breaker(
    default_thresholds: CircuitBreakerThresholds,
    bus: EventBus,
    execution_control: ExecutionControl,
) -> CircuitBreaker:
    return CircuitBreaker(
        thresholds=default_thresholds,
        bus=bus,
        execution_control=execution_control,
    )


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_circuit_breaker_no_trigger_no_divergences(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Test that circuit breaker doesn't trigger with no divergences."""
        reconcile_events: list[ReconcileEvent] = []

        result = await circuit_breaker.check(reconcile_events)

        assert result is None
        assert not circuit_breaker.is_triggered()
        assert not circuit_breaker._execution_control.is_enabled()

    @pytest.mark.asyncio
    async def test_circuit_breaker_no_trigger_minor_divergences(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Test that circuit breaker doesn't trigger on minor divergences."""
        # Create minor divergences (below thresholds)
        reconcile_events = [
            ReconcileEvent(
                divergence_type="phantom_order",
                order_id="order-1",
                venue_order_id="venue-1",
                severity="WARNING",
                details={},
            ),
            ReconcileEvent(
                divergence_type="orphan_order",
                venue_order_id="venue-2",
                severity="WARNING",
                details={},
            ),
        ]

        result = await circuit_breaker.check(reconcile_events)

        # Should not trigger (only 1 phantom, 1 orphan, below thresholds of 3)
        assert result is None
        assert not circuit_breaker.is_triggered()

    @pytest.mark.asyncio
    async def test_circuit_breaker_trigger_phantom_orders(
        self, bus: EventBus, execution_control: ExecutionControl
    ) -> None:
        """Test that circuit breaker triggers on multiple phantom orders."""
        # Create circuit breaker with require_error_severity=False for this test
        circuit_breaker = CircuitBreaker(
            thresholds=CircuitBreakerThresholds(require_error_severity=False),
            bus=bus,
            execution_control=execution_control,
        )
        # Create enough phantom orders to exceed threshold (default: 3)
        reconcile_events = [
            ReconcileEvent(
                divergence_type="phantom_order",
                order_id=f"order-{i}",
                venue_order_id=f"venue-{i}",
                severity="WARNING",
                details={},
            )
            for i in range(4)  # 4 > threshold of 3
        ]

        circuit_breaker_queue = bus.subscribe(CIRCUIT_BREAKER)
        result = await circuit_breaker.check(reconcile_events)

        # Should trigger
        assert result is not None
        assert result.breaker_type == "reconcile_divergence"
        assert result.triggered is True
        assert "phantom orders" in result.reason.lower()
        assert result.details["phantom_count"] == 4
        assert circuit_breaker.is_triggered()
        assert not circuit_breaker._execution_control.is_enabled()

        # Check that event was published
        published_event = await asyncio.wait_for(circuit_breaker_queue.get(), timeout=1.0)
        assert published_event == result

    @pytest.mark.asyncio
    async def test_circuit_breaker_trigger_orphan_orders(
        self, bus: EventBus, execution_control: ExecutionControl
    ) -> None:
        """Test that circuit breaker triggers on multiple orphan orders."""
        # Create circuit breaker with require_error_severity=False for this test
        circuit_breaker = CircuitBreaker(
            thresholds=CircuitBreakerThresholds(require_error_severity=False),
            bus=bus,
            execution_control=execution_control,
        )
        # Create enough orphan orders to exceed threshold (default: 3)
        reconcile_events = [
            ReconcileEvent(
                divergence_type="orphan_order",
                venue_order_id=f"venue-{i}",
                severity="WARNING",
                details={},
            )
            for i in range(4)  # 4 > threshold of 3
        ]

        result = await circuit_breaker.check(reconcile_events)

        # Should trigger
        assert result is not None
        assert result.triggered is True
        assert "orphan orders" in result.reason.lower()
        assert result.details["orphan_count"] == 4
        assert circuit_breaker.is_triggered()

    @pytest.mark.asyncio
    async def test_circuit_breaker_trigger_fill_mismatch(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Test that circuit breaker triggers on fill mismatch."""
        # Create fill mismatch (threshold is 1, so 1 is enough)
        reconcile_events = [
            ReconcileEvent(
                divergence_type="fill_mismatch",
                order_id="order-1",
                venue_order_id="venue-1",
                severity="ERROR",
                details={},
            )
        ]

        result = await circuit_breaker.check(reconcile_events)

        # Should trigger (1 fill mismatch >= threshold of 1)
        assert result is not None
        assert result.triggered is True
        assert "fill mismatch" in result.reason.lower()
        assert result.details["fill_mismatch_count"] == 1
        assert circuit_breaker.is_triggered()

    @pytest.mark.asyncio
    async def test_circuit_breaker_require_error_severity(
        self, bus: EventBus, execution_control: ExecutionControl
    ) -> None:
        """Test that circuit breaker respects require_error_severity flag."""
        # Create thresholds that require ERROR severity
        thresholds = CircuitBreakerThresholds(
            max_phantom_orders=2,
            require_error_severity=True,
        )
        circuit_breaker = CircuitBreaker(
            thresholds=thresholds,
            bus=bus,
            execution_control=execution_control,
        )

        # Create WARNING severity phantom orders (should not trigger)
        reconcile_events = [
            ReconcileEvent(
                divergence_type="phantom_order",
                order_id=f"order-{i}",
                venue_order_id=f"venue-{i}",
                severity="WARNING",  # Not ERROR
                details={},
            )
            for i in range(3)  # 3 > threshold of 2, but all WARNING
        ]

        result = await circuit_breaker.check(reconcile_events)

        # Should not trigger (no ERROR severity)
        assert result is None
        assert not circuit_breaker.is_triggered()

        # Now create ERROR severity (should trigger)
        reconcile_events_error = [
            ReconcileEvent(
                divergence_type="phantom_order",
                order_id="order-1",
                venue_order_id="venue-1",
                severity="ERROR",  # ERROR severity
                details={},
            ),
            ReconcileEvent(
                divergence_type="phantom_order",
                order_id="order-2",
                venue_order_id="venue-2",
                severity="ERROR",  # ERROR severity
                details={},
            ),
            ReconcileEvent(
                divergence_type="phantom_order",
                order_id="order-3",
                venue_order_id="venue-3",
                severity="ERROR",  # ERROR severity
                details={},
            ),
        ]

        result = await circuit_breaker.check(reconcile_events_error)

        # Should trigger (3 ERROR severity > threshold of 2)
        assert result is not None
        assert result.triggered is True
        assert result.details["error_severity_count"] == 3

    @pytest.mark.asyncio
    async def test_circuit_breaker_multiple_divergence_types(
        self, bus: EventBus, execution_control: ExecutionControl
    ) -> None:
        """Test that circuit breaker triggers on multiple divergence types."""
        # Create circuit breaker with require_error_severity=False for this test
        circuit_breaker = CircuitBreaker(
            thresholds=CircuitBreakerThresholds(require_error_severity=False),
            bus=bus,
            execution_control=execution_control,
        )
        # Create mix of divergences that together exceed thresholds
        reconcile_events = [
            ReconcileEvent(
                divergence_type="phantom_order",
                order_id="order-1",
                venue_order_id="venue-1",
                severity="WARNING",
                details={},
            ),
            ReconcileEvent(
                divergence_type="orphan_order",
                venue_order_id="venue-2",
                severity="WARNING",
                details={},
            ),
            ReconcileEvent(
                divergence_type="fill_mismatch",
                order_id="order-3",
                venue_order_id="venue-3",
                severity="ERROR",
                details={},
            ),
            ReconcileEvent(
                divergence_type="phantom_order",
                order_id="order-4",
                venue_order_id="venue-4",
                severity="WARNING",
                details={},
            ),
        ]

        result = await circuit_breaker.check(reconcile_events)

        # Should trigger (multiple types, fill mismatch alone would trigger)
        assert result is not None
        assert result.triggered is True
        assert result.details["phantom_count"] == 2
        assert result.details["orphan_count"] == 1
        assert result.details["fill_mismatch_count"] == 1
        assert result.details["error_severity_count"] == 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_reset(
        self, bus: EventBus, execution_control: ExecutionControl
    ) -> None:
        """Test that circuit breaker can be reset."""
        # Create circuit breaker with require_error_severity=False for this test
        circuit_breaker = CircuitBreaker(
            thresholds=CircuitBreakerThresholds(require_error_severity=False),
            bus=bus,
            execution_control=execution_control,
        )
        circuit_breaker_queue = bus.subscribe(CIRCUIT_BREAKER)

        # First trigger it
        reconcile_events = [
            ReconcileEvent(
                divergence_type="fill_mismatch",
                order_id="order-1",
                venue_order_id="venue-1",
                severity="ERROR",
                details={},
            )
        ]

        trigger_result = await circuit_breaker.check(reconcile_events)
        assert trigger_result is not None
        assert circuit_breaker.is_triggered()

        # Check that trigger event was published
        trigger_event = await asyncio.wait_for(circuit_breaker_queue.get(), timeout=1.0)
        assert trigger_event == trigger_result

        # Reset it
        reset_result = await circuit_breaker.reset()

        assert reset_result.breaker_type == "reconcile_divergence"
        assert reset_result.triggered is False
        assert "reset" in reset_result.reason.lower()
        assert not circuit_breaker.is_triggered()

        # Check that reset event was published
        reset_event = await asyncio.wait_for(circuit_breaker_queue.get(), timeout=1.0)
        assert reset_event == reset_result

    @pytest.mark.asyncio
    async def test_circuit_breaker_disables_execution(
        self, bus: EventBus, execution_control: ExecutionControl
    ) -> None:
        """Test that circuit breaker disables execution when triggered."""
        # Create circuit breaker with require_error_severity=False for this test
        circuit_breaker = CircuitBreaker(
            thresholds=CircuitBreakerThresholds(require_error_severity=False),
            bus=bus,
            execution_control=execution_control,
        )
        # Enable execution first
        execution_control.enable()
        assert execution_control.is_enabled()

        # Trigger circuit breaker
        reconcile_events = [
            ReconcileEvent(
                divergence_type="fill_mismatch",
                order_id="order-1",
                venue_order_id="venue-1",
                severity="ERROR",
                details={},
            )
        ]

        await circuit_breaker.check(reconcile_events)

        # Execution should be disabled
        assert not execution_control.is_enabled()

    @pytest.mark.asyncio
    async def test_circuit_breaker_custom_thresholds(
        self, bus: EventBus, execution_control: ExecutionControl
    ) -> None:
        """Test that circuit breaker respects custom thresholds."""
        # Create custom thresholds
        thresholds = CircuitBreakerThresholds(
            max_phantom_orders=5,
            max_orphan_orders=5,
            max_fill_mismatches=2,
            require_error_severity=False,
        )
        circuit_breaker = CircuitBreaker(
            thresholds=thresholds,
            bus=bus,
            execution_control=execution_control,
        )

        # Create 4 phantom orders (below threshold of 5)
        reconcile_events = [
            ReconcileEvent(
                divergence_type="phantom_order",
                order_id=f"order-{i}",
                venue_order_id=f"venue-{i}",
                severity="WARNING",
                details={},
            )
            for i in range(4)
        ]

        result = await circuit_breaker.check(reconcile_events)

        # Should not trigger (4 < threshold of 5)
        assert result is None

        # Add one more (5 >= threshold of 5)
        reconcile_events.append(
            ReconcileEvent(
                divergence_type="phantom_order",
                order_id="order-5",
                venue_order_id="venue-5",
                severity="WARNING",
                details={},
            )
        )

        result = await circuit_breaker.check(reconcile_events)

        # Should trigger (5 >= threshold of 5)
        assert result is not None
        assert result.triggered is True
