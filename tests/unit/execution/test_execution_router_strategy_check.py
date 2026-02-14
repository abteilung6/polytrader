"""Unit tests for ExecutionRouter strategy activation backstop.

Per Platform_Proposal.md §2.4: Tests verify that ExecutionRouter rejects
inactive strategies in live mode and always allows in paper mode.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from polytrader.adapters.polymarket.models import VenueResponse
from polytrader.events import (
    CANCEL_ORDER_COMMANDS_PAPER,
    ORDER_REJECTS,
    SUBMIT_ORDER_COMMANDS_PAPER,
    EventBus,
)
from polytrader.events.types import OrderIntentEvent, OrderRejectedEvent
from polytrader.execution.router import ExecutionRouter
from polytrader.execution.tactics import ExecutionTactics
from polytrader.oms.commands import SubmitOrderCommand
from tests.factories.events import create_order_intent_event


class FakeAdapter:
    """Fake venue adapter for testing.

    Implements IVenueAdapter protocol (structural typing).
    """

    async def submit_order(self, client_order_id: str, intent: OrderIntentEvent) -> VenueResponse:
        """Submit order to venue."""
        return VenueResponse(
            venue_order_id=f"venue-{client_order_id}",
            status="ACKED",
            raw_response={"order_id": f"venue-{client_order_id}"},
        )

    async def cancel_order(self, client_order_id: str, venue_order_id: str) -> VenueResponse:
        """Cancel order."""
        return VenueResponse(
            venue_order_id=venue_order_id,
            status="CANCELLED",
            raw_response={"order_id": venue_order_id},
        )

    async def get_open_orders(
        self, market_slug: str | None = None, token_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get open orders."""
        return []


def create_submit_order_command(
    strategy_id: str = "test_strategy",
    order_id: str | None = None,
    client_order_id: str | None = None,
) -> SubmitOrderCommand:
    """Create a test SubmitOrderCommand with deterministic defaults.

    Args:
        strategy_id: Strategy ID for the order intent
        order_id: Order ID (default: generated)
        client_order_id: Client order ID (default: generated)

    Returns:
        SubmitOrderCommand with specified parameters
    """
    import uuid

    intent = create_order_intent_event(strategy_id=strategy_id)
    return SubmitOrderCommand(
        order_id=order_id or str(uuid.uuid4()),
        client_order_id=client_order_id or str(uuid.uuid4()),
        intent=intent,
        correlation_id=intent.correlation_id,
    )


class EventCapture:
    """Capture events for testing."""

    def __init__(self) -> None:
        """Initialize event capture."""
        self.events: list[OrderRejectedEvent] = []

    async def add(self, event: OrderRejectedEvent) -> None:
        """Add event to capture."""
        self.events.append(event)


@pytest.fixture
def bus() -> EventBus:
    """Create event bus for tests."""
    return EventBus()


@pytest.fixture
def fake_adapter() -> FakeAdapter:
    """Create fake adapter for tests."""
    return FakeAdapter()


@pytest.fixture
def tactics() -> ExecutionTactics:
    """Create execution tactics for tests."""
    from polytrader.execution.throttle import ExecutionThrottle

    return ExecutionTactics(throttle=ExecutionThrottle())


class TestExecutionRouterStrategyCheck:
    """Tests for ExecutionRouter strategy activation backstop."""

    @pytest.mark.asyncio
    async def test_rejects_inactive_strategy_live_mode(
        self, bus: EventBus, fake_adapter: FakeAdapter, tactics: ExecutionTactics
    ) -> None:
        """Test _handle_submit_command() rejects inactive strategy (live mode)."""
        router = ExecutionRouter(
            bus=bus,
            adapter=fake_adapter,
            tactics=tactics,
            active_strategies={"active_strategy"},
            is_paper_mode=False,
        )

        command = create_submit_order_command(strategy_id="inactive_strategy")

        # Capture OrderRejectedEvent
        reject_queue = bus.subscribe(ORDER_REJECTS)

        # Process command
        await router._handle_submit_command(command)

        # Check if OrderRejectedEvent was emitted
        rejected_events = []
        try:
            while True:
                event = await asyncio.wait_for(reject_queue.get(), timeout=0.1)
                rejected_events.append(event)
        except TimeoutError:
            pass

        # Should have rejected event
        assert len(rejected_events) == 1
        assert isinstance(rejected_events[0], OrderRejectedEvent)
        assert rejected_events[0].order_id == command.order_id
        assert "Strategy not active" in rejected_events[0].reason

        # Adapter should not have been called
        # Note: We can't easily verify this with FakeAdapter, but the rejection
        # happening means adapter wasn't called (since we return early)

    @pytest.mark.asyncio
    async def test_allows_active_strategy_live_mode(
        self, bus: EventBus, fake_adapter: FakeAdapter, tactics: ExecutionTactics
    ) -> None:
        """Test _handle_submit_command() allows active strategy (live mode)."""
        # Use AsyncMock to track adapter calls
        mock_adapter = AsyncMock(spec=FakeAdapter)
        from polytrader.adapters.polymarket.models import VenueResponse

        mock_adapter.submit_order.return_value = VenueResponse(
            venue_order_id="venue-test",
            status="ACKED",
            raw_response={"order_id": "venue-test"},
        )

        router = ExecutionRouter(
            bus=bus,
            adapter=mock_adapter,
            tactics=tactics,
            active_strategies={"active_strategy"},
            is_paper_mode=False,
        )

        command = create_submit_order_command(strategy_id="active_strategy")

        # Process command
        await router._handle_submit_command(command)

        # Adapter should have been called
        mock_adapter.submit_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_always_allows_paper_mode(
        self, bus: EventBus, fake_adapter: FakeAdapter, tactics: ExecutionTactics
    ) -> None:
        """Test _handle_submit_command() always allows in paper mode (no check)."""
        # Use AsyncMock to track adapter calls
        mock_adapter = AsyncMock(spec=FakeAdapter)
        from polytrader.adapters.polymarket.models import VenueResponse

        mock_adapter.submit_order.return_value = VenueResponse(
            venue_order_id="venue-test",
            status="ACKED",
            raw_response={"order_id": "venue-test"},
        )

        router = ExecutionRouter(
            bus=bus,
            adapter=mock_adapter,
            tactics=tactics,
            active_strategies=set(),  # Empty set (inactive)
            is_paper_mode=True,  # Paper mode
        )

        command = create_submit_order_command(strategy_id="inactive_strategy")

        # Process command
        await router._handle_submit_command(command)

        # Adapter should have been called (paper mode allows all)
        mock_adapter.submit_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejection_emits_order_rejected_event(
        self, bus: EventBus, fake_adapter: FakeAdapter, tactics: ExecutionTactics
    ) -> None:
        """Test rejection emits OrderRejectedEvent with reason."""
        router = ExecutionRouter(
            bus=bus,
            adapter=fake_adapter,
            tactics=tactics,
            active_strategies={"active_strategy"},
            is_paper_mode=False,
        )

        command = create_submit_order_command(strategy_id="inactive_strategy")

        # Capture OrderRejectedEvent
        reject_queue = bus.subscribe(ORDER_REJECTS)

        # Process command
        await router._handle_submit_command(command)

        # Check if OrderRejectedEvent was emitted
        rejected_events = []
        try:
            while True:
                event = await asyncio.wait_for(reject_queue.get(), timeout=0.1)
                rejected_events.append(event)
        except TimeoutError:
            pass

        assert len(rejected_events) == 1
        assert isinstance(rejected_events[0], OrderRejectedEvent)
        assert rejected_events[0].order_id == command.order_id
        assert rejected_events[0].correlation_id == command.correlation_id
        assert "Strategy not active" in rejected_events[0].reason

    @pytest.mark.asyncio
    async def test_rejection_does_not_call_venue_adapter(
        self, bus: EventBus, tactics: ExecutionTactics
    ) -> None:
        """Test rejection does not call venue adapter."""
        # Use AsyncMock to track adapter calls
        mock_adapter = AsyncMock()

        router = ExecutionRouter(
            bus=bus,
            adapter=mock_adapter,
            tactics=tactics,
            active_strategies={"active_strategy"},
            is_paper_mode=False,
        )

        command = create_submit_order_command(strategy_id="inactive_strategy")

        # Process command
        await router._handle_submit_command(command)

        # Adapter should not have been called
        mock_adapter.submit_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscribes_to_injected_lane_topics(
        self, bus: EventBus, tactics: ExecutionTactics
    ) -> None:
        """With lane topic overrides, router receives commands from injected topic."""
        from polytrader.adapters.polymarket.models import VenueResponse

        submitted: asyncio.Event = asyncio.Event()
        response = VenueResponse(
            venue_order_id="venue-test",
            status="ACKED",
            raw_response={"order_id": "venue-test"},
        )
        mock_adapter = AsyncMock()
        mock_adapter.submit_order.return_value = response

        async def set_submitted(*args: object, **kwargs: object) -> VenueResponse:
            submitted.set()
            return response

        mock_adapter.submit_order.side_effect = set_submitted
        mock_adapter.cancel_order = AsyncMock(
            return_value=VenueResponse(
                venue_order_id="v1",
                status="CANCELLED",
                raw_response={},
            )
        )
        mock_adapter.get_open_orders = AsyncMock(return_value=[])

        router = ExecutionRouter(
            bus=bus,
            adapter=mock_adapter,
            tactics=tactics,
            is_paper_mode=True,
            submit_commands_topic=SUBMIT_ORDER_COMMANDS_PAPER,
            cancel_commands_topic=CANCEL_ORDER_COMMANDS_PAPER,
        )
        router_task = asyncio.create_task(router.run())
        await asyncio.sleep(0)  # Yield so router reaches submit_queue.get()
        command = create_submit_order_command()
        await bus.publish(SUBMIT_ORDER_COMMANDS_PAPER, command)
        await asyncio.wait_for(submitted.wait(), timeout=2.0)
        router_task.cancel()
        try:
            await router_task
        except asyncio.CancelledError:
            pass
        mock_adapter.submit_order.assert_called_once()
