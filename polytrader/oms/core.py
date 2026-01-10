"""OMS Core: Order creation and lifecycle management.

Per flows.mdc §7: OMS creates orders from approved intents and manages lifecycle.
Per flows.mdc §10: OMS handles venue updates from user stream.
"""

import asyncio
import uuid
from typing import TYPE_CHECKING

from polytrader.events import (
    APPROVED_PROPOSALS,
    CANCEL_ORDER_COMMANDS,
    FILLS,
    ORDER_ACKS,
    ORDER_CANCELS,
    ORDER_REJECTS,
    ORDER_SUBMITTED,
    SUBMIT_ORDER_COMMANDS,
)
from polytrader.events.bus import EventBus
from polytrader.events.types import (
    FillEvent,
    OrderAckEvent,
    OrderCanceledEvent,
    OrderRejectedEvent,
    OrderSubmittedEvent,
)
from polytrader.oms.fsm import transition_order_state
from polytrader.oms.idempotency import IdempotencyStore, generate_client_order_id
from polytrader.oms.models import Order, OrderState
from polytrader.oms.store import IEventHandlingOrderStore

if TYPE_CHECKING:
    from polytrader.types import OrderIntentEvent


class OMSCore:
    """Core OMS component that manages order lifecycle.

    Per flows.mdc §7:
    - Creates orders from ApprovedOrderIntent (via APPROVED_PROPOSALS topic)
    - Emits OrderCreatedEvent
    - Sends SubmitOrderCommand to Execution
    - Handles user stream updates (ack/reject/fill/cancel)

    Per flows.mdc §10:
    - Matches venue updates to internal orders by client_order_id or venue_order_id
    - Applies FSM transitions
    - Emits lifecycle events

    Attributes:
        _bus: Event bus for publishing events and commands
        _store: Order store for maintaining projections
        _idempotency: Idempotency store for duplicate detection
        _running: Flag to control async loop
    """

    def __init__(
        self,
        bus: EventBus,
        store: IEventHandlingOrderStore,
        idempotency_store: IdempotencyStore,
    ) -> None:
        """Initialize OMS Core.

        Args:
            bus: Event bus for publishing events and commands
            store: Order store with event handling capabilities
            idempotency_store: Idempotency store for duplicate detection
        """
        self._bus = bus
        self._store = store
        self._idempotency = idempotency_store
        self._running = False

    async def run(self) -> None:
        """Start OMS Core async loop.

        Subscribes to APPROVED_PROPOSALS and processes order creation requests.
        Per flows.mdc §7: OMS receives approved intents from Risk layer.
        """
        self._running = True
        proposal_queue = self._bus.subscribe(APPROVED_PROPOSALS)

        try:
            while self._running:
                intent = await proposal_queue.get()
                await self.create_order(intent)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False

    def stop(self) -> None:
        """Stop OMS Core async loop."""
        self._running = False

    async def create_order(self, intent: "OrderIntentEvent") -> Order:
        """Create order from approved intent.

        Per flows.mdc §7:
        1. Generate client_order_id (deterministic from intent)
        2. Check idempotency (return existing if duplicate)
        3. Create Order in NEW state (via store)
        4. Transition to PENDING_SUBMIT
        5. Emit OrderCreatedEvent (via store)
        6. Send SubmitOrderCommand to Execution
        7. Transition to SUBMITTED
        8. Emit OrderSubmittedEvent

        Args:
            intent: Approved order intent (from Risk layer)

        Returns:
            Created or existing Order instance

        Raises:
            ValueError: If order creation fails
        """
        # Step 1: Generate client_order_id
        client_order_id = generate_client_order_id(intent)

        # Step 2: Check idempotency
        existing_order_id = self._idempotency.get_order_id(client_order_id)
        if existing_order_id:
            # Duplicate - return existing order
            existing_order = self._store.get_order(existing_order_id)
            if existing_order:
                return existing_order
            # Order ID exists but order not found - clear idempotency mapping
            # (shouldn't happen, but handle gracefully)
            # For now, we'll create a new order (this is a recovery scenario)

        # Step 3: Create Order in NEW state (via store)
        order = await self._store.create_order(intent, client_order_id)

        # Step 4: Record idempotency mapping
        self._idempotency.record_order(client_order_id, order.order_id)

        # Step 5: Transition to PENDING_SUBMIT
        order = transition_order_state(order, OrderState.PENDING_SUBMIT)
        self._store.update_order(order)

        # Step 6: Send SubmitOrderCommand to Execution
        from polytrader.oms.commands import SubmitOrderCommand

        command = SubmitOrderCommand(
            order_id=order.order_id,
            client_order_id=client_order_id,
            intent=intent,
            correlation_id=intent.correlation_id,
        )
        await self._bus.publish(SUBMIT_ORDER_COMMANDS, command)

        # Step 7: Transition to SUBMITTED and emit OrderSubmittedEvent
        order = transition_order_state(order, OrderState.SUBMITTED)
        self._store.update_order(order)

        submitted_event = OrderSubmittedEvent(
            order_id=order.order_id,
            client_order_id=client_order_id,
            correlation_id=intent.correlation_id,
        )
        await self._bus.publish(ORDER_SUBMITTED, submitted_event)
        # Store handler will update state if needed (idempotent)
        self._store.handle_order_submitted(submitted_event)

        return order

    async def handle_venue_ack(
        self,
        client_order_id: str,
        venue_order_id: str,
    ) -> None:
        """Handle venue acknowledgment.

        Per flows.mdc §10: OMS receives venue ack and updates order state.

        Flow:
        1. Find order by client_order_id
        2. Transition to ACKED
        3. Update venue_order_id
        4. Emit OrderAckEvent

        Args:
            client_order_id: Idempotency key to find order
            venue_order_id: Venue-assigned order ID

        Raises:
            ValueError: If order not found
        """
        order = self._store.get_order_by_client_id(client_order_id)
        if not order:
            raise ValueError(f"Order not found for client_order_id: {client_order_id}")

        # Transition to ACKED
        order = transition_order_state(order, OrderState.ACKED)
        # Update venue_order_id
        order = order.model_copy(update={"venue_order_id": venue_order_id})
        self._store.update_order(order)

        # Emit OrderAckEvent
        ack_event = OrderAckEvent(
            order_id=order.order_id,
            venue_order_id=venue_order_id,
            correlation_id=order.correlation_id,
        )
        await self._bus.publish(ORDER_ACKS, ack_event)
        # Store handler will update state if needed (idempotent)
        self._store.handle_order_ack(ack_event)

    async def handle_venue_reject(
        self,
        client_order_id: str,
        reason: str,
    ) -> None:
        """Handle venue rejection.

        Per flows.mdc §10: OMS receives venue reject and updates order state.

        Flow:
        1. Find order by client_order_id
        2. Transition to REJECTED
        3. Emit OrderRejectedEvent

        Args:
            client_order_id: Idempotency key to find order
            reason: Rejection reason from venue

        Raises:
            ValueError: If order not found
        """
        order = self._store.get_order_by_client_id(client_order_id)
        if not order:
            raise ValueError(f"Order not found for client_order_id: {client_order_id}")

        # Emit OrderRejectedEvent (store handles intermediate states)
        # Store will handle NEW → PENDING_SUBMIT → SUBMITTED → REJECTED if needed
        reject_event = OrderRejectedEvent(
            order_id=order.order_id,
            reason=reason,
            correlation_id=order.correlation_id,
        )
        await self._bus.publish(ORDER_REJECTS, reject_event)
        # Store handler will handle state transitions
        self._store.handle_order_rejected(reject_event)

    async def handle_fill(
        self,
        client_order_id: str,
        size: float,
        price: float,
        fee: float,
        venue_fill_id: str | None = None,
    ) -> None:
        """Handle fill from venue.

        Per flows.mdc §10: OMS receives fill and updates order state.

        Flow:
        1. Find order by client_order_id
        2. Generate fill_id
        3. Validate fill doesn't exceed order size
        4. Update filled_size, avg_fill_price (via store)
        5. Transition to PARTIALLY_FILLED or FILLED
        6. Emit FillEvent

        Args:
            client_order_id: Idempotency key to find order
            size: Fill size in USD
            price: Fill price
            fee: Fee amount
            venue_fill_id: Venue-assigned fill ID (if available)

        Raises:
            ValueError: If order not found or fill is invalid
        """
        order = self._store.get_order_by_client_id(client_order_id)
        if not order:
            raise ValueError(f"Order not found for client_order_id: {client_order_id}")

        # Validate fill doesn't exceed order size
        if order.filled_size + size > order.size:
            raise ValueError(
                f"Fill size {size} would exceed order size {order.size} "
                f"(current filled: {order.filled_size})"
            )

        # Generate fill_id
        fill_id = str(uuid.uuid4())

        # Emit FillEvent (store will handle state transition and calculations)
        fill_event = FillEvent(
            order_id=order.order_id,
            fill_id=fill_id,
            size=size,
            price=price,
            fee=fee,
            venue_fill_id=venue_fill_id,
            correlation_id=order.correlation_id,
        )
        await self._bus.publish(FILLS, fill_event)
        # Store handler will handle state transitions and calculations
        self._store.handle_fill(fill_event)

    async def handle_cancel(
        self,
        client_order_id: str,
        reason: str | None = None,
    ) -> None:
        """Handle order cancellation.

        Per flows.mdc §7, §10: OMS cancels order and updates state.

        Flow:
        1. Find order by client_order_id
        2. Check if order can be cancelled (not terminal)
        3. Send CancelOrderCommand to Execution
        4. Transition to CANCELLED
        5. Emit OrderCanceledEvent

        Args:
            client_order_id: Idempotency key to find order
            reason: Optional cancellation reason

        Raises:
            ValueError: If order not found or already terminal
        """
        order = self._store.get_order_by_client_id(client_order_id)
        if not order:
            raise ValueError(f"Order not found for client_order_id: {client_order_id}")

        # Check if order can be cancelled
        if order.is_terminal:
            raise ValueError(f"Order {order.order_id} is already in terminal state: {order.state}")

        # Send CancelOrderCommand to Execution
        from polytrader.oms.commands import CancelOrderCommand

        cancel_command = CancelOrderCommand(
            order_id=order.order_id,
            client_order_id=client_order_id,
            venue_order_id=order.venue_order_id,
            reason=reason,
            correlation_id=order.correlation_id,
        )
        await self._bus.publish(CANCEL_ORDER_COMMANDS, cancel_command)

        # Emit OrderCanceledEvent (store will handle state transition)
        cancel_event = OrderCanceledEvent(
            order_id=order.order_id,
            reason=reason,
            correlation_id=order.correlation_id,
        )
        await self._bus.publish(ORDER_CANCELS, cancel_event)
        # Store handler will handle state transition
        self._store.handle_order_canceled(cancel_event)
