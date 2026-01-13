"""OMS Core: Order creation and lifecycle management.

Per flows.mdc §7: OMS creates orders from approved intents and manages lifecycle.
Per flows.mdc §10: OMS handles venue updates from user stream.
"""

import asyncio
import time
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
    USER_STREAM_ACKS,
    USER_STREAM_CANCELS,
    USER_STREAM_FILLS,
    USER_STREAM_REJECTS,
)
from polytrader.events.bus import EventBus
from polytrader.events.types import (
    FillEvent,
    OrderAckEvent,
    OrderCanceledEvent,
    OrderRejectedEvent,
    OrderSubmittedEvent,
)
from polytrader.logging_config import logger
from polytrader.oms.fsm import transition_order_state
from polytrader.oms.idempotency import IdempotencyStore, generate_client_order_id
from polytrader.oms.metrics import (
    record_fill,
    record_idempotency_hit,
    record_order_acked,
    record_order_cancelled,
    record_order_created,
    record_order_lifetime,
    record_order_rejected,
    record_order_submitted,
    update_orders_live_gauge,
)
from polytrader.oms.models import Order, OrderState
from polytrader.oms.store import IEventHandlingOrderStore

if TYPE_CHECKING:
    from polytrader.adapters.polymarket.models import (
        CanonicalCancel,
        CanonicalFill,
        CanonicalOrderAck,
        CanonicalOrderReject,
    )

if TYPE_CHECKING:
    from polytrader.events.types import OrderIntentEvent


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
        # Track order timestamps for latency calculation
        # order_id -> {"created": ts, "submitted": ts, "acked": ts, "first_fill": ts}
        self._order_timestamps: dict[str, dict[str, float]] = {}

    async def run(self) -> None:
        """Start OMS Core async loop.

        Subscribes to APPROVED_PROPOSALS and processes order creation requests.
        Also subscribes to user stream events and converts them to OMS events.
        Per flows.mdc §7: OMS receives approved intents from Risk layer.
        Per flows.mdc §10: OMS handles user stream updates.
        """
        self._running = True
        proposal_queue = self._bus.subscribe(APPROVED_PROPOSALS)

        # Subscribe to user stream topics
        user_stream_acks_queue = self._bus.subscribe(USER_STREAM_ACKS)
        user_stream_rejects_queue = self._bus.subscribe(USER_STREAM_REJECTS)
        user_stream_fills_queue = self._bus.subscribe(USER_STREAM_FILLS)
        user_stream_cancels_queue = self._bus.subscribe(USER_STREAM_CANCELS)

        # Periodic queue depth and orders_live gauge update
        async def update_gauges():
            while self._running:
                try:
                    queue_size = proposal_queue.qsize()
                    from polytrader.obs.metrics import get_metrics_collector

                    metrics = get_metrics_collector()
                    metrics.set_gauge("queue_depth", queue_size)
                    update_orders_live_gauge(self._store)
                    await asyncio.sleep(1.0)  # Update every second
                except asyncio.CancelledError:
                    break
                except Exception:
                    # Don't let gauge updates crash the main loop
                    logger.exception("Error updating OMS gauges")
                    await asyncio.sleep(1.0)

        gauge_task = asyncio.create_task(update_gauges())

        # Process each queue separately
        async def process_user_stream_acks():
            """Process user stream acks."""
            while self._running:
                try:
                    canonical_ack = await asyncio.wait_for(
                        user_stream_acks_queue.get(), timeout=0.1
                    )
                    await self._handle_canonical_ack(canonical_ack)
                except TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.exception("Error handling canonical ack", error=str(e))

        async def process_user_stream_rejects():
            """Process user stream rejects."""
            while self._running:
                try:
                    canonical_reject = await asyncio.wait_for(
                        user_stream_rejects_queue.get(), timeout=0.1
                    )
                    await self._handle_canonical_reject(canonical_reject)
                except TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.exception("Error handling canonical reject", error=str(e))

        async def process_user_stream_fills():
            """Process user stream fills."""
            while self._running:
                try:
                    canonical_fill = await asyncio.wait_for(
                        user_stream_fills_queue.get(), timeout=0.1
                    )
                    await self._handle_canonical_fill(canonical_fill)
                except TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.exception("Error handling canonical fill", error=str(e))

        async def process_user_stream_cancels():
            """Process user stream cancels."""
            while self._running:
                try:
                    canonical_cancel = await asyncio.wait_for(
                        user_stream_cancels_queue.get(), timeout=0.1
                    )
                    await self._handle_canonical_cancel(canonical_cancel)
                except TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.exception("Error handling canonical cancel", error=str(e))

        # Start user stream handlers
        user_stream_tasks = [
            asyncio.create_task(process_user_stream_acks()),
            asyncio.create_task(process_user_stream_rejects()),
            asyncio.create_task(process_user_stream_fills()),
            asyncio.create_task(process_user_stream_cancels()),
        ]

        try:
            while self._running:
                intent = await proposal_queue.get()
                await self.create_order(intent)
        except asyncio.CancelledError:
            pass
        finally:
            gauge_task.cancel()
            for task in user_stream_tasks:
                task.cancel()
            try:
                await gauge_task
            except asyncio.CancelledError:
                pass
            for task in user_stream_tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
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
        start_time = time.monotonic()
        # Step 1: Generate client_order_id
        client_order_id = generate_client_order_id(intent)

        # Step 2: Check idempotency
        existing_order_id = self._idempotency.get_order_id(client_order_id)
        if existing_order_id:
            # Duplicate - return existing order
            existing_order = self._store.get_order(existing_order_id)
            if existing_order:
                record_idempotency_hit(client_order_id)
                logger.bind(
                    correlation_id=intent.correlation_id,
                    order_id=existing_order.order_id,
                    client_order_id=client_order_id,
                    market_slug=intent.market_slug,
                    outcome=intent.outcome,
                    side=intent.side,
                ).debug("Duplicate order detected, returning existing order")
                return existing_order
            # Order ID exists but order not found - clear idempotency mapping
            # (shouldn't happen, but handle gracefully)
            # For now, we'll create a new order (this is a recovery scenario)

        # Step 3: Create Order in NEW state (via store)
        order = await self._store.create_order(intent, client_order_id)

        # Record creation timestamp
        created_time = time.monotonic()
        self._order_timestamps[order.order_id] = {"created": created_time}

        # Record order created metric
        record_order_created(order)

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

        # Record submission timestamp and calculate latency
        submitted_time = time.monotonic()
        self._order_timestamps[order.order_id]["submitted"] = submitted_time
        submit_latency_ms = (submitted_time - created_time) * 1000
        record_order_submitted(order, submit_latency_ms)

        submitted_event = OrderSubmittedEvent(
            order_id=order.order_id,
            client_order_id=client_order_id,
            correlation_id=intent.correlation_id,
        )
        await self._bus.publish(ORDER_SUBMITTED, submitted_event)
        # Store handler will update state if needed (idempotent)
        self._store.handle_order_submitted(submitted_event)

        # Structured logging
        total_latency_ms = (time.monotonic() - start_time) * 1000
        logger.bind(
            correlation_id=intent.correlation_id,
            order_id=order.order_id,
            client_order_id=client_order_id,
            market_slug=order.market_slug,
            outcome=order.outcome,
            side=order.side,
            size=order.size,
            limit_price=order.limit_price,
            latency_ms=total_latency_ms,
        ).info(
            "Order created: {order_id} for {market_slug}/{outcome} "
            "side={side} size={size} price={limit_price}",
            order_id=order.order_id,
            market_slug=order.market_slug,
            outcome=order.outcome,
            side=order.side,
            size=order.size,
            limit_price=order.limit_price,
        )

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
        start_time = time.monotonic()
        order = self._store.get_order_by_client_id(client_order_id)
        if not order:
            logger.bind(
                client_order_id=client_order_id,
                error_class="ValueError",
            ).error(
                "Order not found for client_order_id: {client_order_id}",
                client_order_id=client_order_id,
            )
            raise ValueError(f"Order not found for client_order_id: {client_order_id}")

        # Record ack timestamp and calculate latency
        acked_time = time.monotonic()
        if order.order_id in self._order_timestamps:
            self._order_timestamps[order.order_id]["acked"] = acked_time
            if "submitted" in self._order_timestamps[order.order_id]:
                ack_latency_ms = (
                    acked_time - self._order_timestamps[order.order_id]["submitted"]
                ) * 1000
                record_order_acked(order, ack_latency_ms)

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

        # Structured logging
        latency_ms = (time.monotonic() - start_time) * 1000
        logger.bind(
            correlation_id=order.correlation_id,
            order_id=order.order_id,
            client_order_id=client_order_id,
            venue_order_id=venue_order_id,
            market_slug=order.market_slug,
            outcome=order.outcome,
            side=order.side,
            latency_ms=latency_ms,
        ).info(
            "Order acknowledged: {order_id} venue_order_id={venue_order_id}",
            order_id=order.order_id,
            venue_order_id=venue_order_id,
        )

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
        start_time = time.monotonic()
        order = self._store.get_order_by_client_id(client_order_id)
        if not order:
            logger.bind(
                client_order_id=client_order_id,
                error_class="ValueError",
            ).error(
                "Order not found for client_order_id: {client_order_id}",
                client_order_id=client_order_id,
            )
            raise ValueError(f"Order not found for client_order_id: {client_order_id}")

        # Record rejection metric
        record_order_rejected(order, reason)

        # Clean up timestamps if order reaches terminal state
        if order.order_id in self._order_timestamps:
            if "created" in self._order_timestamps[order.order_id]:
                lifetime_ms = (
                    time.monotonic() - self._order_timestamps[order.order_id]["created"]
                ) * 1000
                # Order will be REJECTED after this, so record lifetime
                # We'll update the order state after the event is processed
                # For now, record with current state
                record_order_lifetime(order, lifetime_ms)
            del self._order_timestamps[order.order_id]

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

        # Structured logging
        latency_ms = (time.monotonic() - start_time) * 1000
        logger.bind(
            correlation_id=order.correlation_id,
            order_id=order.order_id,
            client_order_id=client_order_id,
            venue_order_id=order.venue_order_id,
            market_slug=order.market_slug,
            outcome=order.outcome,
            side=order.side,
            reason=reason,
            latency_ms=latency_ms,
            error_class="rejection",
        ).warning(
            "Order rejected: {order_id} reason={reason}",
            order_id=order.order_id,
            reason=reason,
        )

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
        start_time = time.monotonic()
        order = self._store.get_order_by_client_id(client_order_id)
        if not order:
            logger.bind(
                client_order_id=client_order_id,
                error_class="ValueError",
            ).error(
                "Order not found for client_order_id: {client_order_id}",
                client_order_id=client_order_id,
            )
            raise ValueError(f"Order not found for client_order_id: {client_order_id}")

        # Validate fill doesn't exceed order size
        if order.filled_size + size > order.size:
            error_msg = (
                f"Fill size {size} would exceed order size {order.size} "
                f"(current filled: {order.filled_size})"
            )
            logger.bind(
                correlation_id=order.correlation_id,
                order_id=order.order_id,
                client_order_id=client_order_id,
                fill_size=size,
                order_size=order.size,
                current_filled=order.filled_size,
                error_class="ValueError",
            ).error(error_msg)
            raise ValueError(error_msg)

        # Record first fill timestamp and calculate latency
        fill_latency_ms = None
        if order.order_id in self._order_timestamps:
            if "first_fill" not in self._order_timestamps[order.order_id]:
                self._order_timestamps[order.order_id]["first_fill"] = time.monotonic()
                if "acked" in self._order_timestamps[order.order_id]:
                    fill_latency_ms = (
                        self._order_timestamps[order.order_id]["first_fill"]
                        - self._order_timestamps[order.order_id]["acked"]
                    ) * 1000

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

        # Get updated order to check if it's terminal
        updated_order = self._store.get_order(order.order_id)
        if updated_order:
            # Record fill metric
            record_fill(updated_order, fill_latency_ms)

            # If order is terminal, record lifetime and clean up timestamps
            if updated_order.is_terminal and updated_order.order_id in self._order_timestamps:
                if "created" in self._order_timestamps[updated_order.order_id]:
                    lifetime_ms = (
                        time.monotonic() - self._order_timestamps[updated_order.order_id]["created"]
                    ) * 1000
                    record_order_lifetime(updated_order, lifetime_ms)
                del self._order_timestamps[updated_order.order_id]

        # Structured logging
        latency_ms = (time.monotonic() - start_time) * 1000
        logger.bind(
            correlation_id=order.correlation_id,
            order_id=order.order_id,
            client_order_id=client_order_id,
            venue_order_id=order.venue_order_id,
            venue_fill_id=venue_fill_id,
            market_slug=order.market_slug,
            outcome=order.outcome,
            side=order.side,
            fill_size=size,
            fill_price=price,
            fee=fee,
            latency_ms=latency_ms,
        ).info(
            "Order filled: {order_id} size={fill_size} price={fill_price} fee={fee}",
            order_id=order.order_id,
            fill_size=size,
            fill_price=price,
            fee=fee,
        )

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
        start_time = time.monotonic()
        order = self._store.get_order_by_client_id(client_order_id)
        if not order:
            logger.bind(
                client_order_id=client_order_id,
                error_class="ValueError",
            ).error(
                "Order not found for client_order_id: {client_order_id}",
                client_order_id=client_order_id,
            )
            raise ValueError(f"Order not found for client_order_id: {client_order_id}")

        # Check if order can be cancelled
        if order.is_terminal:
            error_msg = f"Order {order.order_id} is already in terminal state: {order.state}"
            logger.bind(
                correlation_id=order.correlation_id,
                order_id=order.order_id,
                client_order_id=client_order_id,
                state=order.state.value,
                error_class="ValueError",
            ).warning(error_msg)
            raise ValueError(error_msg)

        # Record cancellation metric
        record_order_cancelled(order, reason)

        # Clean up timestamps if order reaches terminal state
        if order.order_id in self._order_timestamps:
            if "created" in self._order_timestamps[order.order_id]:
                lifetime_ms = (
                    time.monotonic() - self._order_timestamps[order.order_id]["created"]
                ) * 1000
                # Order will be CANCELLED after this, so record lifetime
                # We'll update the order state after the event is processed
                # For now, record with current state
                record_order_lifetime(order, lifetime_ms)
            del self._order_timestamps[order.order_id]

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

        # Structured logging
        latency_ms = (time.monotonic() - start_time) * 1000
        logger.bind(
            correlation_id=order.correlation_id,
            order_id=order.order_id,
            client_order_id=client_order_id,
            venue_order_id=order.venue_order_id,
            market_slug=order.market_slug,
            outcome=order.outcome,
            side=order.side,
            reason=reason,
            latency_ms=latency_ms,
        ).info(
            "Order cancelled: {order_id} reason={reason}",
            order_id=order.order_id,
            reason=reason or "unknown",
        )

    async def _handle_canonical_ack(self, canonical_ack: "CanonicalOrderAck") -> None:
        """Handle canonical order ack from user stream.

        Per flows.mdc §10: Convert canonical ack to OMS ack event.

        Args:
            canonical_ack: Canonical order ack from user stream adapter
        """
        # Find order by venue_order_id (or client_order_id if available)
        order = None
        if canonical_ack.client_order_id:
            order = self._store.get_order_by_client_id(canonical_ack.client_order_id)
        if not order and canonical_ack.venue_order_id:
            order = self._store.get_order_by_venue_id(canonical_ack.venue_order_id)

        if not order:
            logger.bind(
                client_order_id=canonical_ack.client_order_id or "",
                venue_order_id=canonical_ack.venue_order_id,
            ).warning(
                "Order not found for canonical ack (venue_order_id={venue_order_id})",
                venue_order_id=canonical_ack.venue_order_id,
            )
            return

        # Convert to OMS ack
        await self.handle_venue_ack(
            client_order_id=order.client_order_id,
            venue_order_id=canonical_ack.venue_order_id,
        )

    async def _handle_canonical_reject(self, canonical_reject: "CanonicalOrderReject") -> None:
        """Handle canonical order reject from user stream.

        Per flows.mdc §10: Convert canonical reject to OMS reject event.

        Args:
            canonical_reject: Canonical order reject from user stream adapter
        """
        # Find order by client_order_id (CanonicalOrderReject doesn't have venue_order_id)
        order = None
        if canonical_reject.client_order_id:
            order = self._store.get_order_by_client_id(canonical_reject.client_order_id)

        if not order:
            logger.bind(
                client_order_id=canonical_reject.client_order_id or "",
            ).warning(
                "Order not found for canonical reject (client_order_id={client_order_id})",
                client_order_id=canonical_reject.client_order_id or "",
            )
            return

        # Convert to OMS reject
        await self.handle_venue_reject(
            client_order_id=order.client_order_id,
            reason=canonical_reject.reason,
        )

    async def _handle_canonical_fill(self, canonical_fill: "CanonicalFill") -> None:
        """Handle canonical fill from user stream.

        Per flows.mdc §10: Convert canonical fill to OMS fill event.

        Args:
            canonical_fill: Canonical fill from user stream adapter
        """
        # Find order by venue_order_id (or client_order_id if available)
        order = None
        if canonical_fill.client_order_id:
            order = self._store.get_order_by_client_id(canonical_fill.client_order_id)
        if not order and canonical_fill.venue_order_id:
            order = self._store.get_order_by_venue_id(canonical_fill.venue_order_id)

        if not order:
            logger.bind(
                client_order_id=canonical_fill.client_order_id or "",
                venue_order_id=canonical_fill.venue_order_id or "",
                fill_id=canonical_fill.fill_id,
            ).warning(
                (
                    "Order not found for canonical fill "
                    "(venue_order_id={venue_order_id}, fill_id={fill_id})"
                ),
                venue_order_id=canonical_fill.venue_order_id or "",
                fill_id=canonical_fill.fill_id,
            )
            return

        # Convert to OMS fill
        await self.handle_fill(
            client_order_id=order.client_order_id,
            size=canonical_fill.size,
            price=canonical_fill.price,
            fee=canonical_fill.fee,
            venue_fill_id=canonical_fill.fill_id,
        )

    async def _handle_canonical_cancel(self, canonical_cancel: "CanonicalCancel") -> None:
        """Handle canonical cancel from user stream.

        Per flows.mdc §10: Convert canonical cancel to OMS cancel event.

        Args:
            canonical_cancel: Canonical cancel from user stream adapter
        """
        # Find order by venue_order_id (or client_order_id if available)
        order = None
        if canonical_cancel.client_order_id:
            order = self._store.get_order_by_client_id(canonical_cancel.client_order_id)
        if not order and canonical_cancel.venue_order_id:
            order = self._store.get_order_by_venue_id(canonical_cancel.venue_order_id)

        if not order:
            logger.bind(
                client_order_id=canonical_cancel.client_order_id or "",
                venue_order_id=canonical_cancel.venue_order_id,
            ).warning(
                "Order not found for canonical cancel (venue_order_id={venue_order_id})",
                venue_order_id=canonical_cancel.venue_order_id,
            )
            return

        # Convert to OMS cancel
        reason = f"Order cancelled on venue (venue_order_id: {canonical_cancel.venue_order_id})"
        await self.handle_cancel(
            client_order_id=order.client_order_id,
            reason=reason,
        )
