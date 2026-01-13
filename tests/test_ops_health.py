"""Tests for health service.

Per Phase 7 Commit 2: Test HealthService functionality including:
- Health evaluation with all checks passing
- Health evaluation with each gate failing
- Health gates with various thresholds
- Health service with missing optional components (paper trading)
"""

import time
from unittest.mock import MagicMock

import pytest

from polytrader.events.types import ReconcileEvent
from polytrader.ops.control import CircuitBreaker, CircuitBreakerThresholds, ExecutionControl
from polytrader.ops.health import HealthGateThresholds, HealthService, HealthStatus
from polytrader.store import IMarketDataStore, MarketDataEvent
from polytrader.types import Outcome


class FakeMarketDataStore(IMarketDataStore):
    """Fake market data store for testing."""

    def __init__(self, latest_event: MarketDataEvent | None = None) -> None:
        """Initialize fake store.

        Args:
            latest_event: Latest market data event to return (None if no data)
        """
        self._latest_event = latest_event

    def add(self, event: MarketDataEvent) -> None:
        """Add event (not used in tests)."""
        self._latest_event = event

    def latest(self, market_slug: str, outcome: Outcome) -> MarketDataEvent | None:
        """Get latest event."""
        return self._latest_event

    def history(self, market_slug: str, outcome: Outcome) -> list[MarketDataEvent]:
        """Get history (not used in tests)."""
        return [self._latest_event] if self._latest_event else []


class FakeUserStreamAdapter:
    """Fake user stream adapter for testing."""

    def __init__(self, connected: bool = True) -> None:
        """Initialize fake adapter.

        Args:
            connected: Whether adapter is connected
        """
        self._running = connected
        self._ws = MagicMock() if connected else None


class TestHealthStatus:
    """Tests for HealthStatus model."""

    def test_health_status_creation(self) -> None:
        """Test that HealthStatus can be created."""
        status = HealthStatus(
            market_data_fresh=True,
            market_data_staleness_seconds=5.0,
            user_stream_connected=True,
            reconciliation_healthy=True,
            reconciliation_divergence_count=0,
            error_rate_ok=True,
            error_rate=0.05,
            circuit_breaker_triggered=False,
            kill_switch_active=False,
        )

        assert status.market_data_fresh is True
        assert status.market_data_staleness_seconds == 5.0
        assert status.user_stream_connected is True
        assert status.reconciliation_healthy is True
        assert status.error_rate_ok is True
        assert status.error_rate == 0.05
        assert status.circuit_breaker_triggered is False
        assert status.kill_switch_active is False

    def test_health_status_defaults(self) -> None:
        """Test that HealthStatus has correct defaults."""
        status = HealthStatus(market_data_fresh=True)

        assert status.market_data_staleness_seconds is None
        assert status.user_stream_connected is False
        assert status.reconciliation_healthy is True
        assert status.reconciliation_divergence_count == 0
        assert status.error_rate_ok is True
        assert status.error_rate is None
        assert status.circuit_breaker_triggered is False
        assert status.kill_switch_active is False


class TestHealthGateThresholds:
    """Tests for HealthGateThresholds model."""

    def test_health_gate_thresholds_creation(self) -> None:
        """Test that HealthGateThresholds can be created."""
        thresholds = HealthGateThresholds(
            max_market_data_staleness_seconds=30.0,
            max_reconciliation_divergences=2,
            max_error_rate=0.15,
            require_user_stream=False,
        )

        assert thresholds.max_market_data_staleness_seconds == 30.0
        assert thresholds.max_reconciliation_divergences == 2
        assert thresholds.max_error_rate == 0.15
        assert thresholds.require_user_stream is False

    def test_health_gate_thresholds_defaults(self) -> None:
        """Test that HealthGateThresholds has correct defaults."""
        thresholds = HealthGateThresholds()

        assert thresholds.max_market_data_staleness_seconds == 60.0
        assert thresholds.max_reconciliation_divergences == 0
        assert thresholds.max_error_rate == 0.1
        assert thresholds.require_user_stream is True


class TestHealthService:
    """Tests for HealthService."""

    @pytest.fixture
    def store(self) -> FakeMarketDataStore:
        """Create fake market data store."""
        # Create fresh market data (1 second old)
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
            ts_mono=time.monotonic() - 1.0,
        )
        return FakeMarketDataStore(latest_event=event)

    @pytest.fixture
    def thresholds(self) -> HealthGateThresholds:
        """Create health gate thresholds."""
        return HealthGateThresholds(
            max_market_data_staleness_seconds=60.0,
            max_reconciliation_divergences=0,
            max_error_rate=0.1,
            require_user_stream=True,
        )

    @pytest.fixture
    def user_stream_adapter(self) -> FakeUserStreamAdapter:
        """Create fake user stream adapter."""
        return FakeUserStreamAdapter(connected=True)

    @pytest.fixture
    def circuit_breaker(self) -> CircuitBreaker:
        """Create circuit breaker."""
        from polytrader.events.bus import EventBus

        thresholds = CircuitBreakerThresholds()
        bus = EventBus()
        execution_control = ExecutionControl()
        return CircuitBreaker(thresholds=thresholds, bus=bus, execution_control=execution_control)

    @pytest.fixture
    def execution_control(self) -> ExecutionControl:
        """Create execution control."""
        return ExecutionControl()

    @pytest.mark.asyncio
    async def test_health_evaluation_all_checks_passing(
        self,
        store: FakeMarketDataStore,
        thresholds: HealthGateThresholds,
        user_stream_adapter: FakeUserStreamAdapter,
        circuit_breaker: CircuitBreaker,
        execution_control: ExecutionControl,
    ) -> None:
        """Test health evaluation with all checks passing."""
        service = HealthService(
            store=store,
            thresholds=thresholds,
            user_stream_adapter=user_stream_adapter,
            circuit_breaker=circuit_breaker,
            execution_control=execution_control,
            kill_switch_active=False,
            error_rate=0.05,
            recent_reconcile_events=[],
        )

        status = await service.evaluate(market_slug="test-market", outcome="UP")

        assert status.market_data_fresh is True
        assert status.market_data_staleness_seconds is not None
        assert status.market_data_staleness_seconds <= 5.0  # Should be around 1-2 seconds
        assert status.user_stream_connected is True
        assert status.reconciliation_healthy is True
        assert status.reconciliation_divergence_count == 0
        assert status.error_rate_ok is True
        assert status.error_rate == 0.05
        assert status.circuit_breaker_triggered is False
        assert status.kill_switch_active is False

        # Check gates
        all_passed, failed_gates = service.check_gates(status)
        assert all_passed is True
        assert len(failed_gates) == 0

    @pytest.mark.asyncio
    async def test_health_evaluation_market_data_stale(
        self,
        store: FakeMarketDataStore,
        thresholds: HealthGateThresholds,
    ) -> None:
        """Test health evaluation with stale market data."""
        # Create stale market data (100 seconds old)
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
            ts_mono=time.monotonic() - 100.0,
        )
        stale_store = FakeMarketDataStore(latest_event=event)

        service = HealthService(
            store=stale_store,
            thresholds=thresholds,
            error_rate=0.05,
        )

        status = await service.evaluate(market_slug="test-market", outcome="UP")

        assert status.market_data_fresh is False
        assert status.market_data_staleness_seconds is not None
        assert status.market_data_staleness_seconds >= 95.0  # Should be around 100 seconds

        # Check gates
        all_passed, failed_gates = service.check_gates(status)
        assert all_passed is False
        assert "market_data_freshness" in failed_gates

    @pytest.mark.asyncio
    async def test_health_evaluation_no_market_data(
        self,
        thresholds: HealthGateThresholds,
    ) -> None:
        """Test health evaluation with no market data."""
        empty_store = FakeMarketDataStore(latest_event=None)

        service = HealthService(
            store=empty_store,
            thresholds=thresholds,
            error_rate=0.05,
        )

        status = await service.evaluate(market_slug="test-market", outcome="UP")

        assert status.market_data_fresh is False
        assert status.market_data_staleness_seconds is None

        # Check gates
        all_passed, failed_gates = service.check_gates(status)
        assert all_passed is False
        assert "market_data_freshness" in failed_gates

    @pytest.mark.asyncio
    async def test_health_evaluation_user_stream_disconnected(
        self,
        store: FakeMarketDataStore,
        thresholds: HealthGateThresholds,
    ) -> None:
        """Test health evaluation with user stream disconnected."""
        disconnected_adapter = FakeUserStreamAdapter(connected=False)

        service = HealthService(
            store=store,
            thresholds=thresholds,
            user_stream_adapter=disconnected_adapter,
            error_rate=0.05,
        )

        status = await service.evaluate(market_slug="test-market", outcome="UP")

        assert status.user_stream_connected is False

        # Check gates
        all_passed, failed_gates = service.check_gates(status)
        assert all_passed is False
        assert "user_stream_disconnected" in failed_gates

    @pytest.mark.asyncio
    async def test_health_evaluation_reconciliation_unhealthy(
        self,
        store: FakeMarketDataStore,
        thresholds: HealthGateThresholds,
    ) -> None:
        """Test health evaluation with reconciliation divergences."""
        # Create reconcile events with divergences
        reconcile_events = [
            ReconcileEvent(
                divergence_type="phantom_order",
                order_id="order-123",
                severity="ERROR",
            ),
            ReconcileEvent(
                divergence_type="orphan_order",
                venue_order_id="venue-456",
                severity="WARNING",
            ),
        ]

        service = HealthService(
            store=store,
            thresholds=thresholds,
            error_rate=0.05,
            recent_reconcile_events=reconcile_events,
        )

        status = await service.evaluate(market_slug="test-market", outcome="UP")

        assert status.reconciliation_healthy is False
        assert status.reconciliation_divergence_count == 2

        # Check gates
        all_passed, failed_gates = service.check_gates(status)
        assert all_passed is False
        assert "reconciliation_unhealthy" in failed_gates

    @pytest.mark.asyncio
    async def test_health_evaluation_error_rate_high(
        self,
        store: FakeMarketDataStore,
        thresholds: HealthGateThresholds,
    ) -> None:
        """Test health evaluation with high error rate."""
        service = HealthService(
            store=store,
            thresholds=thresholds,
            error_rate=0.15,  # Above threshold of 0.1
        )

        status = await service.evaluate(market_slug="test-market", outcome="UP")

        assert status.error_rate_ok is False
        assert status.error_rate == 0.15

        # Check gates
        all_passed, failed_gates = service.check_gates(status)
        assert all_passed is False
        assert "error_rate_high" in failed_gates

    @pytest.mark.asyncio
    async def test_health_evaluation_circuit_breaker_triggered(
        self,
        store: FakeMarketDataStore,
        thresholds: HealthGateThresholds,
        circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test health evaluation with circuit breaker triggered."""
        # Manually trigger circuit breaker
        circuit_breaker._triggered = True

        service = HealthService(
            store=store,
            thresholds=thresholds,
            circuit_breaker=circuit_breaker,
            error_rate=0.05,
        )

        status = await service.evaluate(market_slug="test-market", outcome="UP")

        assert status.circuit_breaker_triggered is True

        # Check gates
        all_passed, failed_gates = service.check_gates(status)
        assert all_passed is False
        assert "circuit_breaker_triggered" in failed_gates

    @pytest.mark.asyncio
    async def test_health_evaluation_kill_switch_active(
        self,
        store: FakeMarketDataStore,
        thresholds: HealthGateThresholds,
    ) -> None:
        """Test health evaluation with kill switch active."""
        service = HealthService(
            store=store,
            thresholds=thresholds,
            kill_switch_active=True,
            error_rate=0.05,
        )

        status = await service.evaluate(market_slug="test-market", outcome="UP")

        assert status.kill_switch_active is True

        # Check gates
        all_passed, failed_gates = service.check_gates(status)
        assert all_passed is False
        assert "kill_switch_active" in failed_gates

    @pytest.mark.asyncio
    async def test_health_gates_various_thresholds(
        self,
        store: FakeMarketDataStore,
    ) -> None:
        """Test health gates with various thresholds."""
        # Test with strict thresholds
        strict_thresholds = HealthGateThresholds(
            max_market_data_staleness_seconds=10.0,  # Very strict
            max_reconciliation_divergences=0,  # No divergences allowed
            max_error_rate=0.05,  # Very low error rate
            require_user_stream=True,
        )

        service = HealthService(
            store=store,
            thresholds=strict_thresholds,
            error_rate=0.03,
        )

        status = await service.evaluate(market_slug="test-market", outcome="UP")
        all_passed, failed_gates = service.check_gates(status)

        # Should pass with fresh data and low error rate
        assert all_passed is True

        # Test with lenient thresholds
        lenient_thresholds = HealthGateThresholds(
            max_market_data_staleness_seconds=300.0,  # 5 minutes
            max_reconciliation_divergences=5,  # Allow some divergences
            max_error_rate=0.2,  # Higher error rate allowed
            require_user_stream=False,  # Don't require user stream
        )

        service_lenient = HealthService(
            store=store,
            thresholds=lenient_thresholds,
            error_rate=0.15,
        )

        status_lenient = await service_lenient.evaluate(market_slug="test-market", outcome="UP")
        all_passed_lenient, failed_gates_lenient = service_lenient.check_gates(status_lenient)

        # Should pass with lenient thresholds
        assert all_passed_lenient is True

    @pytest.mark.asyncio
    async def test_health_service_missing_optional_components(
        self,
        store: FakeMarketDataStore,
    ) -> None:
        """Test health service with missing optional components (paper trading)."""
        # Paper trading: no user stream, no circuit breaker, no execution control
        thresholds = HealthGateThresholds(
            require_user_stream=False,  # Paper trading doesn't require user stream
        )

        service = HealthService(
            store=store,
            thresholds=thresholds,
            user_stream_adapter=None,  # No user stream
            circuit_breaker=None,  # No circuit breaker
            execution_control=None,  # No execution control
            error_rate=0.05,
        )

        status = await service.evaluate(market_slug="test-market", outcome="UP")

        # Should work without optional components
        assert status.market_data_fresh is True
        assert status.user_stream_connected is True  # Returns True when adapter is None
        assert status.circuit_breaker_triggered is False  # Returns False when breaker is None
        assert status.kill_switch_active is False

        # Check gates
        all_passed, failed_gates = service.check_gates(status)
        assert all_passed is True

    @pytest.mark.asyncio
    async def test_health_evaluation_multiple_failed_gates(
        self,
        store: FakeMarketDataStore,
        thresholds: HealthGateThresholds,
    ) -> None:
        """Test health evaluation with multiple gates failing."""
        # Create stale data
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
            ts_mono=time.monotonic() - 100.0,
        )
        stale_store = FakeMarketDataStore(latest_event=event)

        disconnected_adapter = FakeUserStreamAdapter(connected=False)

        reconcile_events = [
            ReconcileEvent(
                divergence_type="phantom_order",
                order_id="order-123",
                severity="ERROR",
            ),
        ]

        service = HealthService(
            store=stale_store,
            thresholds=thresholds,
            user_stream_adapter=disconnected_adapter,
            error_rate=0.15,  # High error rate
            recent_reconcile_events=reconcile_events,
            kill_switch_active=True,
        )

        status = await service.evaluate(market_slug="test-market", outcome="UP")

        # Check gates
        all_passed, failed_gates = service.check_gates(status)
        assert all_passed is False
        assert len(failed_gates) >= 4  # Multiple gates should fail
        assert "market_data_freshness" in failed_gates
        assert "user_stream_disconnected" in failed_gates
        assert "reconciliation_unhealthy" in failed_gates
        assert "error_rate_high" in failed_gates
        assert "kill_switch_active" in failed_gates

    @pytest.mark.asyncio
    async def test_health_evaluation_reconciliation_divergence_count_threshold(
        self,
        store: FakeMarketDataStore,
    ) -> None:
        """Test health gates with reconciliation divergence count threshold."""
        thresholds = HealthGateThresholds(
            max_reconciliation_divergences=2,  # Allow up to 2 divergences
        )

        # Create 3 divergences (exceeds threshold)
        reconcile_events = [
            ReconcileEvent(divergence_type="phantom_order", severity="WARNING"),
            ReconcileEvent(divergence_type="orphan_order", severity="WARNING"),
            ReconcileEvent(divergence_type="fill_mismatch", severity="WARNING"),
        ]

        service = HealthService(
            store=store,
            thresholds=thresholds,
            error_rate=0.05,
            recent_reconcile_events=reconcile_events,
        )

        status = await service.evaluate(market_slug="test-market", outcome="UP")

        assert status.reconciliation_divergence_count == 3

        # Check gates
        all_passed, failed_gates = service.check_gates(status)
        assert all_passed is False
        assert any("reconciliation_divergences_3" in gate for gate in failed_gates)

    @pytest.mark.asyncio
    async def test_health_evaluation_reconciliation_none_divergence_ignored(
        self,
        store: FakeMarketDataStore,
        thresholds: HealthGateThresholds,
    ) -> None:
        """Test that 'none' divergence type is ignored in reconciliation count."""
        # Create events with 'none' divergence type (no actual divergence)
        reconcile_events = [
            ReconcileEvent(divergence_type="none", severity="INFO"),
            ReconcileEvent(divergence_type="none", severity="INFO"),
        ]

        service = HealthService(
            store=store,
            thresholds=thresholds,
            error_rate=0.05,
            recent_reconcile_events=reconcile_events,
        )

        status = await service.evaluate(market_slug="test-market", outcome="UP")

        # 'none' divergences should not be counted
        assert status.reconciliation_divergence_count == 0
        assert status.reconciliation_healthy is True

        # Check gates
        all_passed, failed_gates = service.check_gates(status)
        assert all_passed is True
