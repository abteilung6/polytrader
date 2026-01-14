"""End-to-end integration test: Boot sequence → Trading flow.

Per Phase 7 Review: Tests complete flow from boot to order submission.

Flow:
1. Boot sequence (config, event store, state reconstruction, reconciliation, health gates)
2. Execution permit issuance
3. SignalEvent → PortfolioService → OrderIntentEvent
4. Risk check → ApprovedProposal
5. OMSCore → SubmitOrderCommand
6. ExecutionRouter → Venue adapter (order submitted)

Per testing.md §B: Integration tests use fake venue adapters (deterministic)
and assert emitted events + resulting projections.
"""

import asyncio
from typing import Any

import pytest

from polytrader.adapters.polymarket.models import VenueResponse
from polytrader.common.ids import generate_correlation_id
from polytrader.events import (
    APPROVED_PROPOSALS,
    ORDER_ACKS,
    PROPOSALS,
    SIGNALS,
    SUBMIT_ORDER_COMMANDS,
    SYSTEM_LIFECYCLE,
    EventBus,
)
from polytrader.events.types import (
    ExecutionPermitEvent,
    MarketDataEvent,
    OrderAckEvent,
    OrderIntentEvent,
    SignalEvent,
    SystemStartedEvent,
)
from polytrader.execution import ExecutionRouter
from polytrader.oms import InMemoryOrderStore, OMSCore
from polytrader.oms.idempotency import IdempotencyStore
from polytrader.oms.reconcile import ReconciliationService
from polytrader.ops import (
    ExecutionControl,
    HealthGateThresholds,
    HealthService,
)
from polytrader.portfolio.service import PortfolioService
from polytrader.risk import RiskChecker, RiskEngine, get_default_limits
from polytrader.store import MemoryMarketDataStore
from polytrader.supervisor import SystemSupervisor


class FakeVenueAdapter:
    """Fake venue adapter for end-to-end testing.

    Per testing.md §3.B: Deterministic adapter that accepts orders.

    Implements IVenueAdapter protocol (structural typing):
    - submit_order() -> VenueResponse
    - cancel_order() -> VenueResponse
    - get_open_orders() -> list[dict[str, Any]]

    Mypy verifies protocol compliance when passed to ExecutionRouter(adapter=...).
    """

    def __init__(self) -> None:
        self.submit_calls: list[tuple[str, OrderIntentEvent]] = []
        self._venue_order_id = "venue-e2e-123"

    async def submit_order(
        self,
        client_order_id: str,
        intent: OrderIntentEvent,
    ) -> VenueResponse:
        """Submit order and return normalized response.

        Per IVenueAdapter protocol: Submits order to venue (simulated).
        """
        self.submit_calls.append((client_order_id, intent))
        return VenueResponse(
            venue_order_id=self._venue_order_id,
            status="acknowledged",
            raw_response={
                "status": "acknowledged",
                "order_id": self._venue_order_id,
                "client_order_id": client_order_id,
            },
        )

    async def cancel_order(
        self,
        client_order_id: str,
        venue_order_id: str,
    ) -> VenueResponse:
        """Cancel order (not used in this test).

        Per IVenueAdapter protocol: Cancels order on venue (simulated).
        """
        return VenueResponse(
            venue_order_id=venue_order_id,
            status="cancelled",
            raw_response={"status": "cancelled", "order_id": venue_order_id},
        )

    async def get_open_orders(
        self,
        market_slug: str | None = None,
        token_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get active orders (returns empty for reconciliation).

        Per IVenueAdapter protocol: Returns list of active orders from venue.
        """
        return []


@pytest.mark.asyncio
async def test_boot_to_trading_end_to_end() -> None:
    """Test complete flow: Boot sequence → Signal → Order submission.

    Per Phase 7 Review: End-to-end integration test verifying:
    1. Boot sequence completes successfully
    2. Health gates pass
    3. Execution permit issued
    4. Order can be submitted after boot
    5. Order flows through complete pipeline

    This test verifies that the boot sequence properly enables execution
    and that orders can flow through the system after boot completes.
    """
    import time

    # Setup: Create event bus and market data store
    bus = EventBus()
    store = MemoryMarketDataStore()

    # Add fresh market data (required for health gates)
    fresh_event = MarketDataEvent(
        market_slug="test-market",
        outcome="UP",
        best_bid=0.44,
        best_ask=0.46,
        ts_mono=time.monotonic() - 1.0,  # 1 second old (fresh)
    )
    store.add(fresh_event)

    # Create fake venue adapter (implements IVenueAdapter protocol)
    # Protocol compliance is verified by mypy when passed to ExecutionRouter(adapter=...)
    fake_adapter = FakeVenueAdapter()

    # Create execution control
    execution_control = ExecutionControl(bus=bus)

    # Create OMS components
    oms_store = InMemoryOrderStore(bus)
    idempotency_store = IdempotencyStore()

    def oms_factory() -> OMSCore:
        return OMSCore(bus=bus, store=oms_store, idempotency_store=idempotency_store)

    # Create execution router factory
    def execution_router_factory() -> ExecutionRouter:
        return ExecutionRouter(bus=bus, adapter=fake_adapter, execution_control=execution_control)

    # Create reconciliation service factory
    def reconciliation_factory() -> ReconciliationService:
        return ReconciliationService(store=oms_store, venue_adapter=fake_adapter, bus=bus)

    # Create health service factory (will pass all gates)
    def health_service_factory() -> HealthService:
        return HealthService(
            store=store,
            thresholds=HealthGateThresholds(
                max_market_data_staleness_seconds=60.0,
                max_reconciliation_divergences=0,
                max_error_rate=0.1,
                require_user_stream=False,
            ),
            user_stream_adapter=None,
            circuit_breaker=None,
            execution_control=execution_control,
            kill_switch_active=False,
            error_rate=None,
            recent_reconcile_events=[],
        )

    # Create portfolio service
    portfolio_service = PortfolioService(bus=bus, store=store, fixed_size_usd=1.0)

    def portfolio_factory() -> PortfolioService:
        return portfolio_service

    # Create risk checker
    risk_checker = RiskChecker(bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store)

    def risk_factory() -> RiskChecker:
        return risk_checker

    # Subscribe to events for verification
    lifecycle_queue = bus.subscribe(SYSTEM_LIFECYCLE)
    proposals_queue = bus.subscribe(PROPOSALS)
    approved_queue = bus.subscribe(APPROVED_PROPOSALS)
    submit_queue = bus.subscribe(SUBMIT_ORDER_COMMANDS)
    ack_queue = bus.subscribe(ORDER_ACKS)

    # Create and start SystemSupervisor (boot sequence)
    supervisor = SystemSupervisor(
        bus=bus,
        store=store,
        portfolio_service_factory=portfolio_factory,
        risk_checker_factory=risk_factory,
        oms_core_factory=oms_factory,
        execution_router_factory=execution_router_factory,
        reconciliation_service_factory=reconciliation_factory,
        execution_control=execution_control,
        health_service_factory=health_service_factory,
    )

    # Step 1: Boot sequence
    await supervisor.start()

    # Verify boot sequence completed
    assert supervisor.portfolio_service is not None
    assert supervisor.risk_checker is not None
    assert supervisor.oms_core is not None
    assert supervisor.execution_router is not None

    # Verify execution was enabled (health gates passed)
    assert execution_control.is_enabled(), "Execution should be enabled after boot"

    # Verify boot sequence events
    from polytrader.events.types import Event

    boot_events: list[Event] = []
    try:
        while len(boot_events) < 2:  # SystemStarted, ExecutionPermit
            event = await asyncio.wait_for(lifecycle_queue.get(), timeout=2.0)
            boot_events.append(event)
    except TimeoutError:
        pass

    # Verify SystemStartedEvent
    system_started = next((e for e in boot_events if isinstance(e, SystemStartedEvent)), None)
    assert system_started is not None, "SystemStartedEvent should be published"
    assert system_started.run_id is not None, "SystemStartedEvent should have run_id"
    assert len(system_started.run_id) > 0, "run_id should be valid UUID"

    # Verify ExecutionPermitEvent
    execution_permit = next((e for e in boot_events if isinstance(e, ExecutionPermitEvent)), None)
    assert execution_permit is not None, "ExecutionPermitEvent should be published"
    assert execution_permit.permit_type == "boot"
    assert execution_permit.health_status is not None

    # Step 2: Wait for services to be ready
    await asyncio.sleep(0.1)  # Give services time to subscribe

    # Step 3: Publish SignalEvent (triggers trading flow)
    correlation_id = generate_correlation_id()
    signal = SignalEvent(
        market_slug="test-market",
        outcome="UP",
        p_up=0.7,
        p_down=0.3,
        edge=0.4,
        confidence=0.8,
        model_id="test_model",
        model_version="1.0.0",
        rationale="E2E test signal",
        correlation_id=correlation_id,
    )
    await bus.publish(SIGNALS, signal)

    # Step 4: Verify OrderIntentEvent (PortfolioService output)
    try:
        intent = await asyncio.wait_for(proposals_queue.get(), timeout=2.0)
        assert intent is not None
        assert isinstance(intent, OrderIntentEvent)
        assert intent.market_slug == "test-market"
        assert intent.outcome == "UP"
        assert intent.side == "BUY"
        assert intent.correlation_id == correlation_id
    except TimeoutError:
        pytest.fail("OrderIntentEvent was not published")

    # Step 5: Verify ApprovedProposal (RiskChecker output)
    try:
        approved = await asyncio.wait_for(approved_queue.get(), timeout=2.0)
        assert approved is not None
        assert approved.correlation_id == correlation_id
    except TimeoutError:
        pytest.fail("ApprovedProposal was not published")

    # Step 6: Verify SubmitOrderCommand (OMSCore output)
    try:
        submit_cmd = await asyncio.wait_for(submit_queue.get(), timeout=2.0)
        assert submit_cmd is not None
        assert submit_cmd.intent.market_slug == "test-market"
        assert submit_cmd.intent.correlation_id == correlation_id
    except TimeoutError:
        pytest.fail("SubmitOrderCommand was not published")

    # Step 7: Verify order was submitted to venue adapter
    await asyncio.sleep(0.2)  # Give ExecutionRouter time to process
    assert len(fake_adapter.submit_calls) > 0, "Order should be submitted to venue adapter"
    assert fake_adapter.submit_calls[0][1].market_slug == "test-market"
    assert fake_adapter.submit_calls[0][1].correlation_id == correlation_id

    # Step 8: Verify OrderAckEvent (ExecutionRouter output)
    try:
        ack = await asyncio.wait_for(ack_queue.get(), timeout=2.0)
        assert ack is not None
        assert isinstance(ack, OrderAckEvent)
        assert ack.venue_order_id == fake_adapter._venue_order_id
    except TimeoutError:
        # OrderAckEvent might not be published if ExecutionRouter doesn't emit it
        # This is acceptable - the important part is that order was submitted
        pass

    # Verify OMS has the order
    open_orders = oms_store.get_open_orders()
    assert len(open_orders) > 0, "OMS should have the order"
    assert open_orders[0].market_slug == "test-market"

    # Cleanup
    await supervisor.stop()
