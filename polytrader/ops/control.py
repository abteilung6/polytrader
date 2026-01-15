"""Operational controls: circuit breakers, execution control.

Per flows.mdc §13: Circuit breakers trigger on severe divergence or system issues.
Per architecture.mdc §H: Ops Control Plane provides execution_enabled flag.

This module provides:
- CircuitBreaker: Monitors reconciliation and triggers on severe divergence
- ExecutionControl: Manages execution_enabled flag
- CircuitBreakerThresholds: Configuration for circuit breaker thresholds
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from polytrader.events import CIRCUIT_BREAKER, SYSTEM_LIFECYCLE
from polytrader.events.bus import EventBus
from polytrader.events.types import (
    CircuitBreakerEvent,
    ExecutionPermitEvent,
    KillSwitchEvent,
    ReconcileEvent,
)
from polytrader.logging_config import logger
from polytrader.obs.metrics import record_circuit_breaker, set_execution_enabled, set_kill_switch


class CircuitBreakerThresholds(BaseModel):
    """Configuration for circuit breaker thresholds.

    Per flows.mdc §13: Circuit breakers trigger on severe divergence.
    These thresholds determine when the circuit breaker should trigger.

    Attributes:
        max_phantom_orders: Maximum number of phantom orders before trigger (default: 3)
        max_orphan_orders: Maximum number of orphan orders before trigger (default: 3)
        max_fill_mismatches: Maximum number of fill mismatches before trigger (default: 1)
        require_error_severity: If True, only trigger on ERROR severity divergences (default: True)
    """

    max_phantom_orders: int = Field(
        default=3,
        ge=0,
        description="Maximum number of phantom orders before trigger",
    )
    max_orphan_orders: int = Field(
        default=3,
        ge=0,
        description="Maximum number of orphan orders before trigger",
    )
    max_fill_mismatches: int = Field(
        default=1,
        ge=0,
        description="Maximum number of fill mismatches before trigger",
    )
    require_error_severity: bool = Field(
        default=True,
        description="If True, only trigger on ERROR severity divergences",
    )


class ExecutionControl:
    """Execution control: manages execution_enabled flag.

    Per flows.mdc §2: Default safe state is no trading.
    This class provides a simple flag to enable/disable execution.

    Attributes:
        execution_enabled: Whether execution is enabled (default: False)
        kill_switch_active: Whether kill switch is active (default: False)
        bus: Event bus for publishing ExecutionPermitEvent and KillSwitchEvent (optional)
    """

    def __init__(self, bus: EventBus | None = None) -> None:
        """Initialize execution control.

        Args:
            bus: Event bus for publishing events (optional)
        """
        self.execution_enabled: bool = False
        self.kill_switch_active: bool = False
        self._bus = bus

    def enable(self) -> None:
        """Enable execution (simple enable without permit event)."""
        self.execution_enabled = True
        set_execution_enabled(enabled=True)
        logger.info("Execution enabled")

    async def enable_with_permit(
        self,
        permit_type: Literal["boot", "manual", "health_reset"],
        reason: str,
        health_status: dict[str, Any],
        issued_by: Literal["system", "operator"] = "system",
    ) -> None:
        """Enable execution with permit event.

        Per Phase 7: Emits ExecutionPermitEvent when execution is enabled.

        Args:
            permit_type: Type of permit ("boot", "manual", "health_reset")
            reason: Human-readable reason for enabling execution
            health_status: Snapshot of health status at permit time
            issued_by: Who issued the permit ("system" | "operator")
        """
        self.execution_enabled = True
        set_execution_enabled(enabled=True)
        logger.info(
            "Execution enabled with permit: {permit_type} - {reason}",
            permit_type=permit_type,
            reason=reason,
        )

        # Emit ExecutionPermitEvent if bus is available
        if self._bus is not None:
            permit_event = ExecutionPermitEvent(
                permit_type=permit_type,
                reason=reason,
                health_status=health_status,
                issued_by=issued_by,
            )
            await self._bus.publish(SYSTEM_LIFECYCLE, permit_event)

    def disable(self) -> None:
        """Disable execution."""
        self.execution_enabled = False
        set_execution_enabled(enabled=False)
        logger.warning("Execution disabled")

    async def set_kill_switch(
        self,
        active: bool,
        reason: str,
        cancel_open_orders: bool = True,
        triggered_by: Literal["system", "operator", "circuit_breaker"] = "operator",
    ) -> None:
        """Set kill switch state.

        Per flows.mdc §13: Kill switch provides immediate stop-trading policy.

        Args:
            active: True to activate kill switch, False to deactivate
            reason: Human-readable reason for trigger/reset
            cancel_open_orders: Whether to cancel open orders when triggered (default: True)
            triggered_by: Who triggered the kill switch ("system" | "operator" | "circuit_breaker")
        """
        self.kill_switch_active = active
        set_kill_switch(active=active)

        if active:
            # Disable execution when kill switch is activated
            self.execution_enabled = False
            set_execution_enabled(enabled=False)
            logger.error(
                "Kill switch activated: {reason}",
                reason=reason,
                triggered_by=triggered_by,
                cancel_open_orders=cancel_open_orders,
            )
        else:
            logger.info("Kill switch deactivated: {reason}", reason=reason)

        # Emit KillSwitchEvent if bus is available
        if self._bus is not None:
            kill_switch_event = KillSwitchEvent(
                triggered=active,
                reason=reason,
                cancel_open_orders=cancel_open_orders,
                triggered_by=triggered_by,
            )
            await self._bus.publish(SYSTEM_LIFECYCLE, kill_switch_event)

    def is_enabled(self) -> bool:
        """Check if execution is enabled.

        Per flows.mdc §2: Execution is disabled if kill switch is active.

        Returns:
            True if execution is enabled and kill switch is not active, False otherwise
        """
        return self.execution_enabled and not self.kill_switch_active


class CircuitBreaker:
    """Circuit breaker for reconciliation divergences.

    Per flows.mdc §13: Circuit breakers trigger on severe divergence.
    This circuit breaker monitors reconciliation events and triggers when
    thresholds are exceeded.

    Attributes:
        thresholds: Circuit breaker thresholds
        bus: Event bus for publishing CircuitBreakerEvent
        execution_control: Execution control for disabling execution
        triggered: Whether circuit breaker is currently triggered
    """

    def __init__(
        self,
        thresholds: CircuitBreakerThresholds,
        bus: EventBus,
        execution_control: ExecutionControl,
    ) -> None:
        """Initialize circuit breaker.

        Args:
            thresholds: Circuit breaker thresholds
            bus: Event bus for publishing CircuitBreakerEvent
            execution_control: Execution control for disabling execution
        """
        self._thresholds = thresholds
        self._bus = bus
        self._execution_control = execution_control
        self._triggered = False

    async def check(self, reconcile_events: list[ReconcileEvent]) -> CircuitBreakerEvent | None:
        """Check if circuit breaker should trigger.

        Per flows.mdc §13: Trigger on severe divergence.

        Args:
            reconcile_events: List of reconciliation events

        Returns:
            CircuitBreakerEvent if triggered, None otherwise
        """
        if self._triggered:
            # Already triggered, don't trigger again
            return None

        if not reconcile_events:
            # No divergences, circuit breaker should not trigger
            return None

        # Count divergences by type and severity
        phantom_count = 0
        orphan_count = 0
        fill_mismatch_count = 0
        error_severity_count = 0

        for reconcile_event in reconcile_events:
            if reconcile_event.divergence_type == "phantom_order":
                phantom_count += 1
            elif reconcile_event.divergence_type == "orphan_order":
                orphan_count += 1
            elif reconcile_event.divergence_type == "fill_mismatch":
                fill_mismatch_count += 1

            if reconcile_event.severity == "ERROR":
                error_severity_count += 1

        # Check if we should trigger
        should_trigger = False
        reason_parts: list[str] = []

        if phantom_count >= self._thresholds.max_phantom_orders:
            should_trigger = True
            reason_parts.append(
                f"{phantom_count} phantom orders (threshold: {self._thresholds.max_phantom_orders})"
            )

        if orphan_count >= self._thresholds.max_orphan_orders:
            should_trigger = True
            reason_parts.append(
                f"{orphan_count} orphan orders (threshold: {self._thresholds.max_orphan_orders})"
            )

        if fill_mismatch_count >= self._thresholds.max_fill_mismatches:
            should_trigger = True
            reason_parts.append(
                f"{fill_mismatch_count} fill mismatches "
                f"(threshold: {self._thresholds.max_fill_mismatches})"
            )

        # If require_error_severity is True, only trigger if there are ERROR severity divergences
        if self._thresholds.require_error_severity and error_severity_count == 0:
            should_trigger = False
            reason_parts.append("(no ERROR severity divergences, threshold requires ERROR)")

        if not should_trigger:
            return None

        # Trigger circuit breaker
        reason = "; ".join(reason_parts) if reason_parts else "Severe divergence detected"
        event = CircuitBreakerEvent(
            breaker_type="reconcile_divergence",
            triggered=True,
            reason=reason,
            details={
                "phantom_count": phantom_count,
                "orphan_count": orphan_count,
                "fill_mismatch_count": fill_mismatch_count,
                "error_severity_count": error_severity_count,
                "total_divergences": len(reconcile_events),
                "thresholds": {
                    "max_phantom_orders": self._thresholds.max_phantom_orders,
                    "max_orphan_orders": self._thresholds.max_orphan_orders,
                    "max_fill_mismatches": self._thresholds.max_fill_mismatches,
                    "require_error_severity": self._thresholds.require_error_severity,
                },
            },
        )

        # Disable execution
        self._execution_control.disable()
        self._triggered = True

        # Emit circuit breaker metric per observability.mdc §4
        record_circuit_breaker(circuit_type=event.breaker_type)

        # Publish circuit breaker event
        await self._bus.publish(CIRCUIT_BREAKER, event)

        logger.error(
            "Circuit breaker triggered: {reason}",
            reason=reason,
            phantom_count=phantom_count,
            orphan_count=orphan_count,
            fill_mismatch_count=fill_mismatch_count,
        )

        return event

    async def reset(self) -> CircuitBreakerEvent:
        """Reset circuit breaker (manual operator action).

        Per flows.mdc §13: Require manual/health reset to re-enable.

        Returns:
            CircuitBreakerEvent (triggered=False)
        """
        self._triggered = False

        event = CircuitBreakerEvent(
            breaker_type="reconcile_divergence",
            triggered=False,
            reason="Circuit breaker reset by operator",
            details={},
        )

        # Emit circuit breaker reset metric per observability.mdc §4
        # Note: We still record it as a circuit breaker event, but with a reset type
        record_circuit_breaker(circuit_type=f"{event.breaker_type}_reset")

        # Publish reset event
        await self._bus.publish(CIRCUIT_BREAKER, event)

        logger.info("Circuit breaker reset by operator")

        return event

    def is_triggered(self) -> bool:
        """Check if circuit breaker is currently triggered.

        Returns:
            True if triggered, False otherwise
        """
        return self._triggered
