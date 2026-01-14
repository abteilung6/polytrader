"""Health service for evaluating system health gates.

Per flows.mdc §2: Health gates must pass before enabling execution.
This service evaluates all health checks and determines if execution can be enabled.

Per architecture.mdc §H: Ops Control Plane provides health evaluation.
"""

import time
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from polytrader.store import IMarketDataStore
from polytrader.types import Outcome

if TYPE_CHECKING:
    from polytrader.adapters.polymarket.user_stream import UserStreamAdapter  # noqa: F401
    from polytrader.ops.control import CircuitBreaker, ExecutionControl


class HealthStatus(BaseModel):
    """Health status snapshot.

    Per flows.mdc §2: Health gates evaluate multiple system components.
    This model captures the current state of all health checks.

    Attributes:
        market_data_fresh: Whether market data is fresh (within threshold)
        market_data_staleness_seconds: Age of latest market data in seconds (None if no data)
        user_stream_connected: Whether user stream WebSocket is connected
        reconciliation_healthy: Whether reconciliation shows no severe divergences
        reconciliation_divergence_count: Number of reconciliation divergences
        error_rate_ok: Whether error rate is below threshold
        error_rate: Current error rate (0-1, None if not tracked)
        circuit_breaker_triggered: Whether circuit breaker is triggered
        kill_switch_active: Whether kill switch is active
    """

    market_data_fresh: bool = Field(description="Whether market data is fresh")
    market_data_staleness_seconds: float | None = Field(
        default=None, description="Age of latest market data in seconds"
    )
    user_stream_connected: bool = Field(
        default=False, description="Whether user stream WebSocket is connected"
    )
    reconciliation_healthy: bool = Field(
        default=True, description="Whether reconciliation shows no severe divergences"
    )
    reconciliation_divergence_count: int = Field(
        default=0, description="Number of reconciliation divergences"
    )
    error_rate_ok: bool = Field(default=True, description="Whether error rate is below threshold")
    error_rate: float | None = Field(
        default=None, description="Current error rate (0-1, None if not tracked)"
    )
    circuit_breaker_triggered: bool = Field(
        default=False, description="Whether circuit breaker is triggered"
    )
    kill_switch_active: bool = Field(default=False, description="Whether kill switch is active")


class HealthGateThresholds(BaseModel):
    """Configuration for health gate thresholds.

    Per flows.mdc §2: Health gates have configurable thresholds.
    These thresholds determine when health checks pass or fail.

    Attributes:
        max_market_data_staleness_seconds: Maximum age of market data before considered stale
        max_reconciliation_divergences: Maximum number of divergences before unhealthy
        max_error_rate: Maximum error rate (0-1) before considered unhealthy
        require_user_stream: Whether user stream connection is required (True for live trading)
    """

    max_market_data_staleness_seconds: float = Field(
        default=60.0,
        ge=0.0,
        description="Maximum age of market data before considered stale (seconds)",
    )
    max_reconciliation_divergences: int = Field(
        default=0,
        ge=0,
        description="Maximum number of reconciliation divergences before unhealthy",
    )
    max_error_rate: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Maximum error rate (0-1) before considered unhealthy",
    )
    require_user_stream: bool = Field(
        default=True,
        description="Whether user stream connection is required (True for live trading)",
    )


class HealthService:
    """Health service for evaluating system health gates.

    Per flows.mdc §2: Evaluates all health gates before enabling execution.
    This service checks:
    - Market data freshness
    - User stream connection (if required)
    - Reconciliation health
    - Error rate
    - Circuit breaker status
    - Kill switch status

    Attributes:
        _store: Market data store (for freshness check)
        _user_stream_adapter: User stream adapter (optional, for connection check)
        _circuit_breaker: Circuit breaker (optional, for status check)
        _execution_control: Execution control (optional, for kill switch check)
        _thresholds: Health gate thresholds
        _recent_reconcile_events: Recent reconciliation events (for divergence count)
        _error_tracker: Error rate tracker (optional, for error rate calculation)
    """

    def __init__(
        self,
        store: IMarketDataStore,
        thresholds: HealthGateThresholds,
        user_stream_adapter: Any | None = None,  # UserStreamAdapter | None, but allow duck typing
        circuit_breaker: "CircuitBreaker | None" = None,
        execution_control: "ExecutionControl | None" = None,
        kill_switch_active: bool = False,
        error_rate: float | None = None,
        recent_reconcile_events: list[Any] | None = None,
    ) -> None:
        """Initialize health service.

        Args:
            store: Market data store (required, for freshness check)
            thresholds: Health gate thresholds
            user_stream_adapter: User stream adapter (optional, for live trading)
            circuit_breaker: Circuit breaker (optional, for live trading)
            execution_control: Execution control (optional, for kill switch check)
            kill_switch_active: Whether kill switch is active (default: False)
            error_rate: Current error rate (optional, 0-1)
            recent_reconcile_events: Recent reconciliation events (optional, for divergence count)
        """
        self._store = store
        self._thresholds = thresholds
        self._user_stream_adapter = user_stream_adapter
        self._circuit_breaker = circuit_breaker
        self._execution_control = execution_control
        self._kill_switch_active = kill_switch_active
        self._error_rate = error_rate
        self._recent_reconcile_events = recent_reconcile_events or []

    async def evaluate(
        self, market_slug: str | None = None, outcome: Outcome | None = None
    ) -> HealthStatus:
        """Evaluate all health checks.

        Per flows.mdc §2: Check all health gates before enabling execution.

        Args:
            market_slug: Market slug to check (optional, checks all if None)
            outcome: Market outcome to check (optional, checks all if None)

        Returns:
            HealthStatus with all health check results
        """
        # 1. Check market data freshness
        market_data_fresh, staleness_seconds = self._check_market_data_freshness(
            market_slug, outcome
        )

        # 2. Check user stream connection
        user_stream_connected = self._check_user_stream_connection()

        # 3. Check reconciliation health
        reconciliation_healthy, divergence_count = self._check_reconciliation_health()

        # 4. Check error rate
        error_rate_ok = self._check_error_rate()

        # 5. Check circuit breaker status
        circuit_breaker_triggered = self._check_circuit_breaker()

        # 6. Check kill switch status
        kill_switch_active = self._check_kill_switch()

        return HealthStatus(
            market_data_fresh=market_data_fresh,
            market_data_staleness_seconds=staleness_seconds,
            user_stream_connected=user_stream_connected,
            reconciliation_healthy=reconciliation_healthy,
            reconciliation_divergence_count=divergence_count,
            error_rate_ok=error_rate_ok,
            error_rate=self._error_rate,
            circuit_breaker_triggered=circuit_breaker_triggered,
            kill_switch_active=kill_switch_active,
        )

    def check_gates(self, health_status: HealthStatus) -> tuple[bool, list[str]]:
        """Check if all health gates pass.

        Per flows.mdc §2: All gates must pass before enabling execution.

        Args:
            health_status: Health status to check

        Returns:
            Tuple of (all_passed, failed_gates)
            - all_passed: True if all gates pass, False otherwise
            - failed_gates: List of failed gate names
        """
        failed_gates: list[str] = []

        # Check market data freshness
        if not health_status.market_data_fresh:
            failed_gates.append("market_data_freshness")
            if health_status.market_data_staleness_seconds is not None:
                failed_gates.append(
                    f"market_data_stale_{health_status.market_data_staleness_seconds:.1f}s"
                )

        # Check user stream connection (if required)
        if self._thresholds.require_user_stream and not health_status.user_stream_connected:
            failed_gates.append("user_stream_disconnected")

        # Check reconciliation health
        if not health_status.reconciliation_healthy:
            failed_gates.append("reconciliation_unhealthy")
        if (
            health_status.reconciliation_divergence_count
            > self._thresholds.max_reconciliation_divergences
        ):
            failed_gates.append(
                f"reconciliation_divergences_{health_status.reconciliation_divergence_count}"
            )

        # Check error rate
        if not health_status.error_rate_ok:
            failed_gates.append("error_rate_high")
            if health_status.error_rate is not None:
                failed_gates.append(f"error_rate_{health_status.error_rate:.2%}")

        # Check circuit breaker
        if health_status.circuit_breaker_triggered:
            failed_gates.append("circuit_breaker_triggered")

        # Check kill switch
        if health_status.kill_switch_active:
            failed_gates.append("kill_switch_active")

        all_passed = len(failed_gates) == 0
        return (all_passed, failed_gates)

    def _check_market_data_freshness(
        self, market_slug: str | None, outcome: Outcome | None
    ) -> tuple[bool, float | None]:
        """Check market data freshness.

        Args:
            market_slug: Market slug to check (optional, checks all if None)
            outcome: Market outcome to check (optional, checks all if None)

        Returns:
            Tuple of (is_fresh, staleness_seconds). If checking multiple markets,
            returns False if ANY market is stale, and the maximum staleness_seconds.
        """
        # If no specific market specified, check all markets in the store
        if market_slug is None or outcome is None:
            # Get all markets from store
            try:
                all_markets = self._store.get_all_markets()
            except AttributeError:
                # Store doesn't implement get_all_markets - can't check
                # Return False (not fresh) to be safe
                return (False, None)

            if not all_markets:
                # No market data available at all
                return (False, None)

            # Check all markets - fail if ANY is stale
            current_time = time.monotonic()
            max_staleness_seconds: float | None = None
            all_fresh = True

            for ms, oc in all_markets:
                latest = self._store.latest(ms, oc)
                if latest is None:
                    # Missing data for this market - consider stale
                    all_fresh = False
                    continue

                staleness = current_time - latest.ts_mono
                if max_staleness_seconds is None or staleness > max_staleness_seconds:
                    max_staleness_seconds = staleness

                if staleness > self._thresholds.max_market_data_staleness_seconds:
                    all_fresh = False

            return (all_fresh, max_staleness_seconds)

        # Check specific market
        latest = self._store.latest(market_slug, outcome)
        if latest is None:
            # No market data available
            return (False, None)

        current_time = time.monotonic()
        staleness_seconds = current_time - latest.ts_mono

        is_fresh = staleness_seconds <= self._thresholds.max_market_data_staleness_seconds
        return (is_fresh, staleness_seconds)

    def _check_user_stream_connection(self) -> bool:
        """Check user stream connection status.

        Returns:
            True if connected, False otherwise
        """
        if self._user_stream_adapter is None:
            # No user stream adapter (paper trading) - return True (not required)
            return True

        # Check if adapter is running and has active connection
        # UserStreamAdapter has _running flag and _ws connection
        if not self._user_stream_adapter._running:
            return False

        # Check if WebSocket connection exists
        if self._user_stream_adapter._ws is None:
            return False

        # Connection is active
        return True

    def _check_reconciliation_health(self) -> tuple[bool, int]:
        """Check reconciliation health.

        Returns:
            Tuple of (is_healthy, divergence_count)
        """
        # Count divergences from recent reconcile events
        # Filter out "none" divergence type (no divergence)
        actual_divergences = [
            event
            for event in self._recent_reconcile_events
            if getattr(event, "divergence_type", None) != "none"
        ]
        divergence_count = len(actual_divergences)

        # Check if any divergences are ERROR severity
        has_error_severity = any(
            getattr(event, "severity", None) == "ERROR" for event in actual_divergences
        )

        # Reconciliation is unhealthy if:
        # - Divergence count exceeds threshold, OR
        # - Any ERROR severity divergences exist
        is_healthy = (
            divergence_count <= self._thresholds.max_reconciliation_divergences
            and not has_error_severity
        )

        return (is_healthy, divergence_count)

    def _check_error_rate(self) -> bool:
        """Check error rate.

        Returns:
            True if error rate is OK, False otherwise
        """
        if self._error_rate is None:
            # Error rate not tracked - assume OK
            return True

        return self._error_rate <= self._thresholds.max_error_rate

    def _check_circuit_breaker(self) -> bool:
        """Check circuit breaker status.

        Returns:
            True if triggered, False otherwise
        """
        if self._circuit_breaker is None:
            # No circuit breaker (paper trading) - return False (not triggered)
            return False

        return self._circuit_breaker.is_triggered()

    def _check_kill_switch(self) -> bool:
        """Check kill switch status.

        Returns:
            True if active, False otherwise
        """
        # Kill switch is a separate flag (not execution_enabled)
        # Execution can be disabled for other reasons (circuit breaker, etc.)
        return self._kill_switch_active
