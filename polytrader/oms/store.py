"""OMS Store: Event-backed order projection.

Per flows.mdc §7: OMS maintains order state via event-sourced projections.
This module provides an in-memory order store that maintains order projections
from OMS events, enabling event replay and state reconstruction.
"""

from typing import TYPE_CHECKING, Protocol

from polytrader.events.bus import EventBus
from polytrader.events.types import Event
from polytrader.oms.fsm import transition_order_state
from polytrader.oms.models import Order, OrderState

if TYPE_CHECKING:
    from polytrader.events.types import (
        FillEvent,
        OrderAckEvent,
        OrderCanceledEvent,
        OrderCreatedEvent,
        OrderIntentEvent,
        OrderRejectedEvent,
        OrderSubmittedEvent,
    )


class IOrderStore(Protocol):
    """Interface for order storage and querying.

    Per flows.mdc §7: OMS store provides query surface for current orders.
    """

    async def create_order(self, intent: "OrderIntentEvent", client_order_id: str) -> Order:
        """Create new order, emit OrderCreatedEvent.

        Args:
            intent: Approved order intent
            client_order_id: Idempotency key

        Returns:
            Created Order instance in NEW state
        """
        ...

    def get_order(self, order_id: str) -> Order | None:
        """Get order by order_id.

        Args:
            order_id: Internal order UUID

        Returns:
            Order if found, None otherwise
        """
        ...

    def get_order_by_client_id(self, client_order_id: str) -> Order | None:
        """Get order by client_order_id.

        Args:
            client_order_id: Idempotency key

        Returns:
            Order if found, None otherwise
        """
        ...

    def get_order_by_venue_id(self, venue_order_id: str) -> Order | None:
        """Get order by venue_order_id.

        Args:
            venue_order_id: Venue-assigned order ID

        Returns:
            Order if found, None otherwise
        """
        ...

    def get_open_orders(self) -> list[Order]:
        """Get all non-terminal orders.

        Returns:
            List of orders that are not in terminal state (FILLED, CANCELLED, REJECTED)
        """
        ...

    def get_order_history(self, order_id: str) -> list[Event]:
        """Get event history for an order (for debugging).

        Args:
            order_id: Internal order UUID

        Returns:
            List of events for this order, in chronological order
        """
        ...

    def update_order(self, order: Order) -> None:
        """Update order in store (with FSM validation).

        This method allows OMS Core to update order state after FSM transitions.
        The store validates the transition is valid before updating.

        Args:
            order: Updated Order instance

        Raises:
            ValueError: If order not found or transition is invalid
        """
        ...


class IEventHandlingOrderStore(IOrderStore):
    """Interface for order stores that can handle OMS events.

    This protocol extends IOrderStore with event handler methods.
    Stores that implement this protocol can be used by OMSCore to handle
    OMS lifecycle events (ack, reject, fill, cancel, etc.).

    Per flows.mdc §7: OMS store maintains order state from OMS events.
    """

    def handle_order_submitted(self, event: "OrderSubmittedEvent") -> None:
        """Handle OrderSubmittedEvent - transition to SUBMITTED.

        Args:
            event: OrderSubmittedEvent from OMS
        """
        ...

    def handle_order_ack(self, event: "OrderAckEvent") -> None:
        """Handle OrderAckEvent - update venue_order_id, transition to ACKED.

        Args:
            event: OrderAckEvent from venue
        """
        ...

    def handle_order_rejected(self, event: "OrderRejectedEvent") -> None:
        """Handle OrderRejectedEvent - transition to REJECTED.

        Args:
            event: OrderRejectedEvent from venue
        """
        ...

    def handle_fill(self, event: "FillEvent") -> None:
        """Handle FillEvent - update filled_size, avg_fill_price, transition state.

        Args:
            event: FillEvent from venue
        """
        ...

    def handle_order_canceled(self, event: "OrderCanceledEvent") -> None:
        """Handle OrderCanceledEvent - transition to CANCELLED.

        Args:
            event: OrderCanceledEvent from OMS
        """
        ...


class InMemoryOrderStore(IEventHandlingOrderStore):
    """In-memory order store with event-sourced projections.

    Per flows.mdc §7: Maintains order state from OMS events.
    This store:
    - Maintains order projections from events
    - Provides methods to handle OMS events (called by OMS core)
    - Supports event replay for state reconstruction

    Attributes:
        _orders: Dictionary mapping order_id → Order
        _client_order_ids: Dictionary mapping client_order_id → order_id
        _order_events: Dictionary mapping order_id → list of events
        _bus: Event bus for publishing events
    """

    def __init__(self, bus: EventBus) -> None:
        """Initialize the in-memory order store.

        Args:
            bus: Event bus for publishing OrderCreatedEvent
        """
        self._bus = bus
        self._orders: dict[str, Order] = {}
        self._client_order_ids: dict[str, str] = {}  # client_order_id → order_id
        self._venue_order_ids: dict[str, str] = {}  # venue_order_id → order_id
        self._order_events: dict[str, list[Event]] = {}

    async def create_order(self, intent: "OrderIntentEvent", client_order_id: str) -> Order:
        """Create new order, emit OrderCreatedEvent.

        Args:
            intent: Approved order intent
            client_order_id: Idempotency key

        Returns:
            Created Order instance in NEW state
        """
        from polytrader.events import ORDER_CREATED
        from polytrader.events.types import OrderCreatedEvent

        # Create order in NEW state
        order = Order(
            client_order_id=client_order_id,
            intent=intent,
            market_slug=intent.market_slug,
            outcome=intent.outcome,
            side=intent.side,
            size=intent.size,
            limit_price=intent.limit_price,
            correlation_id=intent.correlation_id,
            state=OrderState.NEW,
        )

        # Store order
        self._orders[order.order_id] = order
        self._client_order_ids[client_order_id] = order.order_id
        self._order_events[order.order_id] = []

        # Emit OrderCreatedEvent and handle it immediately
        event = OrderCreatedEvent(
            order_id=order.order_id,
            client_order_id=client_order_id,
            intent=intent,
            correlation_id=intent.correlation_id,
        )
        await self._bus.publish(ORDER_CREATED, event)
        # Handle the event to record it in history
        self._handle_order_created(event)

        return order

    def get_order(self, order_id: str) -> Order | None:
        """Get order by order_id.

        Args:
            order_id: Internal order UUID

        Returns:
            Order if found, None otherwise
        """
        return self._orders.get(order_id)

    def get_order_by_client_id(self, client_order_id: str) -> Order | None:
        """Get order by client_order_id.

        Args:
            client_order_id: Idempotency key

        Returns:
            Order if found, None otherwise
        """
        order_id = self._client_order_ids.get(client_order_id)
        if order_id:
            return self._orders.get(order_id)
        return None

    def get_order_by_venue_id(self, venue_order_id: str) -> Order | None:
        """Get order by venue_order_id.

        Args:
            venue_order_id: Venue-assigned order ID

        Returns:
            Order if found, None otherwise
        """
        order_id = self._venue_order_ids.get(venue_order_id)
        if order_id:
            return self._orders.get(order_id)
        return None

    def get_open_orders(self) -> list[Order]:
        """Get all non-terminal orders.

        Returns:
            List of orders that are not in terminal state (FILLED, CANCELLED, REJECTED)
        """
        return [order for order in self._orders.values() if not order.is_terminal]

    def get_order_history(self, order_id: str) -> list[Event]:
        """Get event history for an order (for debugging).

        Args:
            order_id: Internal order UUID

        Returns:
            List of events for this order, in chronological order
        """
        events = self._order_events.get(order_id, [])
        return sorted(events, key=lambda e: e.ts_mono)

    def update_order(self, order: Order) -> None:
        """Update order in store (with FSM validation).

        This method allows OMS Core to update order state after FSM transitions.
        The store validates the transition is valid before updating.

        Args:
            order: Updated Order instance

        Raises:
            ValueError: If order not found or transition is invalid
        """
        if order.order_id not in self._orders:
            raise ValueError(f"Order {order.order_id} not found in store")

        # Validate transition (if state changed)
        existing_order = self._orders[order.order_id]
        if existing_order.state != order.state:
            from polytrader.oms.fsm import can_transition

            if not can_transition(existing_order.state, order.state):
                raise ValueError(f"Invalid transition: {existing_order.state} → {order.state}")

        # Update order
        self._orders[order.order_id] = order
        # Update client_order_id mapping if changed
        if order.client_order_id != existing_order.client_order_id:
            # Remove old mapping
            if existing_order.client_order_id in self._client_order_ids:
                del self._client_order_ids[existing_order.client_order_id]
            # Add new mapping
            self._client_order_ids[order.client_order_id] = order.order_id
        # Update venue_order_id mapping if changed
        if order.venue_order_id != existing_order.venue_order_id:
            # Remove old mapping
            if (
                existing_order.venue_order_id
                and existing_order.venue_order_id in self._venue_order_ids
            ):
                del self._venue_order_ids[existing_order.venue_order_id]
            # Add new mapping
            if order.venue_order_id:
                self._venue_order_ids[order.venue_order_id] = order.order_id

    def rebuild_from_events(self, events: list[Event]) -> None:
        """Rebuild order state from event log.

        Per flows.mdc §7: Used on restart to reconstruct order state.

        Args:
            events: List of events to replay (should be sorted by ts_mono)
        """
        from polytrader.events.types import (
            FillEvent,
            OrderAckEvent,
            OrderCanceledEvent,
            OrderCreatedEvent,
            OrderRejectedEvent,
            OrderSubmittedEvent,
        )

        # Clear existing state
        self._orders.clear()
        self._client_order_ids.clear()
        self._order_events.clear()

        # Replay events in order
        for event in events:
            if isinstance(event, OrderCreatedEvent):
                self._handle_order_created(event)
            elif isinstance(event, OrderSubmittedEvent):
                self.handle_order_submitted(event)
            elif isinstance(event, OrderAckEvent):
                self.handle_order_ack(event)
            elif isinstance(event, OrderRejectedEvent):
                self.handle_order_rejected(event)
            elif isinstance(event, FillEvent):
                self.handle_fill(event)
            elif isinstance(event, OrderCanceledEvent):
                self.handle_order_canceled(event)

    def _handle_order_created(self, event: "OrderCreatedEvent") -> None:
        """Handle OrderCreatedEvent - create order in NEW state."""
        # Order should already be created by create_order(), but handle for replay
        if event.order_id not in self._orders:
            order = Order(
                order_id=event.order_id,
                client_order_id=event.client_order_id,
                intent=event.intent,
                market_slug=event.intent.market_slug,
                outcome=event.intent.outcome,
                side=event.intent.side,
                size=event.intent.size,
                limit_price=event.intent.limit_price,
                correlation_id=event.intent.correlation_id,
                state=OrderState.NEW,
            )
            self._orders[order.order_id] = order
            self._client_order_ids[event.client_order_id] = order.order_id
            self._order_events[order.order_id] = []

        # Record event
        self._order_events[event.order_id].append(event)

    def handle_order_submitted(self, event: "OrderSubmittedEvent") -> None:
        """Handle OrderSubmittedEvent - transition to SUBMITTED."""
        order = self._orders.get(event.order_id)
        if order:
            # If order is NEW, transition through PENDING_SUBMIT first
            if order.state == OrderState.NEW:
                order = transition_order_state(order, OrderState.PENDING_SUBMIT)
            # Then transition to SUBMITTED
            order = transition_order_state(order, OrderState.SUBMITTED)
            self._orders[event.order_id] = order
            self._order_events[event.order_id].append(event)

    def handle_order_ack(self, event: "OrderAckEvent") -> None:
        """Handle OrderAckEvent - update venue_order_id, transition to ACKED."""
        order = self._orders.get(event.order_id)
        if order:
            order = transition_order_state(order, OrderState.ACKED)
            # Update venue_order_id using model_copy (Order is immutable)
            order = order.model_copy(update={"venue_order_id": event.venue_order_id})
            self._orders[event.order_id] = order
            # Update venue_order_id mapping
            if event.venue_order_id:
                self._venue_order_ids[event.venue_order_id] = event.order_id
            self._order_events[event.order_id].append(event)

    def handle_order_rejected(self, event: "OrderRejectedEvent") -> None:
        """Handle OrderRejectedEvent - transition to REJECTED."""
        order = self._orders.get(event.order_id)
        if order:
            # REJECTED can only come from SUBMITTED
            # If order is NEW or PENDING_SUBMIT, transition through SUBMITTED first
            if order.state == OrderState.NEW:
                order = transition_order_state(order, OrderState.PENDING_SUBMIT)
                self._orders[event.order_id] = order  # Update after each transition
            if order.state == OrderState.PENDING_SUBMIT:
                order = transition_order_state(order, OrderState.SUBMITTED)
                self._orders[event.order_id] = order  # Update after each transition
            # Then transition to REJECTED
            order = transition_order_state(order, OrderState.REJECTED, reason=event.reason)
            self._orders[event.order_id] = order
            self._order_events[event.order_id].append(event)

    def handle_fill(self, event: "FillEvent") -> None:
        """Handle FillEvent - update filled_size, avg_fill_price, transition state."""
        order = self._orders.get(event.order_id)
        if order:
            # Update filled size
            new_filled_size = order.filled_size + event.size

            # Update average fill price
            if order.avg_fill_price is None:
                new_avg_fill_price = event.price
            else:
                # Weighted average: (old_avg * old_size + new_price * new_size) / total_size
                total_size = order.filled_size + event.size
                new_avg_fill_price = (
                    order.avg_fill_price * order.filled_size + event.price * event.size
                ) / total_size

            # Update order
            order = order.model_copy(
                update={
                    "filled_size": new_filled_size,
                    "avg_fill_price": new_avg_fill_price,
                }
            )

            # Transition state based on fill completion
            if new_filled_size >= order.size:
                # Fully filled
                order = transition_order_state(order, OrderState.FILLED)
            elif order.state == OrderState.ACKED:
                # First fill
                order = transition_order_state(order, OrderState.PARTIALLY_FILLED)
            # If already PARTIALLY_FILLED, stay in that state until FILLED

            self._orders[event.order_id] = order
            self._order_events[event.order_id].append(event)

    def handle_order_canceled(self, event: "OrderCanceledEvent") -> None:
        """Handle OrderCanceledEvent - transition to CANCELLED."""
        order = self._orders.get(event.order_id)
        if order:
            order = transition_order_state(order, OrderState.CANCELLED, reason=event.reason)
            self._orders[event.order_id] = order
            self._order_events[event.order_id].append(event)
