"""Execution Router: Converts OMS commands to venue actions.

Per flows.mdc §8: Execution receives commands from OMS and routes to venue adapters.
"""

import asyncio
import time
from typing import TYPE_CHECKING

from polytrader.adapters.polymarket.models import VenueError
from polytrader.events import (
    CANCEL_ORDER_COMMANDS,
    EXECUTION_ERRORS,
    EXECUTION_REQUESTS,
    EXECUTION_RESPONSES,
    SUBMIT_ORDER_COMMANDS,
)
from polytrader.events.bus import EventBus
from polytrader.events.types import (
    ExecutionErrorEvent,
    ExecutionRequestEvent,
    ExecutionResponseEvent,
)
from polytrader.execution.adapter import IVenueAdapter
from polytrader.execution.tactics import ExecutionTactics

if TYPE_CHECKING:
    from polytrader.oms.commands import CancelOrderCommand, SubmitOrderCommand


class ExecutionRouter:
    """Execution router that converts OMS commands to venue actions.

    Per flows.mdc §8:
    - Subscribes to SUBMIT_ORDER_COMMANDS and CANCEL_ORDER_COMMANDS
    - Applies execution tactics (pricing, post-only, throttling)
    - Routes to venue adapter
    - Emits execution events (request/response/error)

    Attributes:
        _bus: Event bus for publishing events
        _adapter: Venue adapter (implements IVenueAdapter protocol)
        _tactics: Execution tactics engine
        _running: Flag to control async loop
    """

    def __init__(
        self,
        bus: EventBus,
        adapter: IVenueAdapter,
        tactics: ExecutionTactics | None = None,
    ) -> None:
        """Initialize execution router.

        Args:
            bus: Event bus for publishing events
            adapter: Venue adapter for order submission (implements IVenueAdapter)
            tactics: Execution tactics engine (defaults to new instance)
        """
        from polytrader.execution.tactics import ExecutionTactics

        self._bus = bus
        self._adapter = adapter
        self._tactics = tactics or ExecutionTactics()
        self._running = False

    async def run(self) -> None:
        """Start execution router async loop.

        Subscribes to SUBMIT_ORDER_COMMANDS and CANCEL_ORDER_COMMANDS.
        Processes commands from both queues concurrently.
        """
        from polytrader.logging_config import logger

        self._running = True
        submit_queue = self._bus.subscribe(SUBMIT_ORDER_COMMANDS)
        cancel_queue = self._bus.subscribe(CANCEL_ORDER_COMMANDS)

        async def process_submit_commands() -> None:
            """Process submit commands."""
            try:
                while self._running:
                    command = await submit_queue.get()
                    await self._handle_submit_command(command)
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Error in submit command processor")

        async def process_cancel_commands() -> None:
            """Process cancel commands."""
            try:
                while self._running:
                    command = await cancel_queue.get()
                    await self._handle_cancel_command(command)
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Error in cancel command processor")

        try:
            # Run both processors concurrently
            await asyncio.gather(
                process_submit_commands(),
                process_cancel_commands(),
            )
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False

    def stop(self) -> None:
        """Stop execution router async loop."""
        self._running = False

    async def _handle_submit_command(self, command: "SubmitOrderCommand") -> None:
        """Handle SubmitOrderCommand from OMS.

        Per flows.mdc §8:
        1. Apply execution tactics
        2. Emit ExecutionRequestEvent
        3. Call venue adapter
        4. Emit ExecutionResponseEvent or ExecutionErrorEvent
        5. Normalize venue response for OMS (emit venue ack/reject)

        Args:
            command: SubmitOrderCommand from OMS
        """
        from polytrader.logging_config import logger

        start_time = time.monotonic()

        try:
            # Emit ExecutionRequestEvent
            request_event = ExecutionRequestEvent(
                order_id=command.order_id,
                client_order_id=command.client_order_id,
                venue="polymarket",
                request_type="submit",
                correlation_id=command.correlation_id,
            )
            await self._bus.publish(EXECUTION_REQUESTS, request_event)

            # Apply tactics (pricing, throttling)
            # TODO: Get mid_price from market data (Phase 2: configurable)
            # For now, use intent.limit_price as mid_price approximation
            mid_price = command.intent.limit_price
            try:
                modified_intent = self._tactics.apply_tactics(
                    command.intent,
                    mid_price,
                    command.client_order_id,
                )
            except ValueError as e:
                # Throttled or other tactic failure
                error_event = ExecutionErrorEvent(
                    order_id=command.order_id,
                    client_order_id=command.client_order_id,
                    error_type="fatal",
                    error_message=str(e),
                    venue="polymarket",
                    correlation_id=command.correlation_id,
                )
                await self._bus.publish(EXECUTION_ERRORS, error_event)
                return

            # Call venue adapter
            venue_response = await self._adapter.submit_order(
                command.client_order_id,
                modified_intent,
            )

            # Calculate latency
            latency_ms = (time.monotonic() - start_time) * 1000.0

            # Emit ExecutionResponseEvent
            response_event = ExecutionResponseEvent(
                order_id=command.order_id,
                client_order_id=command.client_order_id,
                venue_order_id=venue_response.venue_order_id,
                latency_ms=latency_ms,
                success=True,
                correlation_id=command.correlation_id,
            )
            await self._bus.publish(EXECUTION_RESPONSES, response_event)

            # Publish FillEvent if order was filled
            # For paper trading, fills are immediate. For real trading, this comes from user stream.
            if venue_response.status == "FILLED":
                import uuid

                from polytrader.events import FILLS
                from polytrader.events.types import FillEvent

                # Extract fill information from venue response
                fill_price = venue_response.raw_response.get(
                    "fill_price", modified_intent.limit_price
                )
                fill_size = modified_intent.size  # Full size for immediate fills

                fill_event = FillEvent(
                    order_id=command.order_id,  # Use OMS order_id, not client_order_id
                    fill_id=str(uuid.uuid4()),
                    size=fill_size,
                    price=fill_price,
                    fee=0.0,  # Paper trading: no fees (real trading would extract from response)
                    venue_fill_id=venue_response.venue_order_id,
                    correlation_id=command.correlation_id,
                )
                await self._bus.publish(FILLS, fill_event)

            # Normalize venue response for OMS
            # OMS expects venue ack/reject, so we emit OrderAckEvent
            # TODO: This should come from user stream, but for now we emit it here
            # Future: Separate user stream adapter will handle this
            from polytrader.events import ORDER_ACKS
            from polytrader.events.types import OrderAckEvent

            ack_event = OrderAckEvent(
                order_id=command.order_id,
                venue_order_id=venue_response.venue_order_id,
                correlation_id=command.correlation_id,
            )
            await self._bus.publish(ORDER_ACKS, ack_event)

        except Exception as e:
            # Handle venue errors
            latency_ms = (time.monotonic() - start_time) * 1000.0

            # Classify error
            error_type = "fatal"
            if isinstance(e, VenueError):
                error_type = e.error_type
            elif hasattr(e, "error_type"):
                error_type = getattr(e, "error_type", "fatal")

            error_event = ExecutionErrorEvent(
                order_id=command.order_id,
                client_order_id=command.client_order_id,
                error_type=error_type,
                error_message=str(e),
                venue="polymarket",
                correlation_id=command.correlation_id,
            )
            await self._bus.publish(EXECUTION_ERRORS, error_event)

            # If fatal error, emit OrderRejectedEvent for OMS
            if error_type == "fatal":
                from polytrader.events import ORDER_REJECTS
                from polytrader.events.types import OrderRejectedEvent

                reject_event = OrderRejectedEvent(
                    order_id=command.order_id,
                    reason=str(e),
                    correlation_id=command.correlation_id,
                )
                await self._bus.publish(ORDER_REJECTS, reject_event)

            logger.exception("Execution error handling submit command")

    async def _handle_cancel_command(self, command: "CancelOrderCommand") -> None:
        """Handle CancelOrderCommand from OMS.

        Per flows.mdc §8:
        1. Check throttle
        2. Emit ExecutionRequestEvent
        3. Call venue adapter
        4. Emit ExecutionResponseEvent or ExecutionErrorEvent

        Args:
            command: CancelOrderCommand from OMS
        """
        from polytrader.logging_config import logger

        start_time = time.monotonic()

        try:
            # Check throttle
            if not self._tactics.throttle.check_cancel_throttle(command.client_order_id):
                raise ValueError(f"Cancel throttled: {command.client_order_id}")

            # Emit ExecutionRequestEvent
            request_event = ExecutionRequestEvent(
                order_id=command.order_id,
                client_order_id=command.client_order_id,
                venue="polymarket",
                request_type="cancel",
                correlation_id=command.correlation_id,
            )
            await self._bus.publish(EXECUTION_REQUESTS, request_event)

            # Call venue adapter
            venue_response = await self._adapter.cancel_order(
                command.client_order_id,
                command.venue_order_id or "",
            )

            # Calculate latency
            latency_ms = (time.monotonic() - start_time) * 1000.0

            # Emit ExecutionResponseEvent
            response_event = ExecutionResponseEvent(
                order_id=command.order_id,
                client_order_id=command.client_order_id,
                venue_order_id=venue_response.venue_order_id,
                latency_ms=latency_ms,
                success=True,
                correlation_id=command.correlation_id,
            )
            await self._bus.publish(EXECUTION_RESPONSES, response_event)

        except Exception as e:
            # Handle errors
            latency_ms = (time.monotonic() - start_time) * 1000.0

            error_type = "fatal"
            if isinstance(e, VenueError):
                error_type = e.error_type
            elif hasattr(e, "error_type"):
                error_type = getattr(e, "error_type", "fatal")

            error_event = ExecutionErrorEvent(
                order_id=command.order_id,
                client_order_id=command.client_order_id,
                error_type=error_type,
                error_message=str(e),
                venue="polymarket",
                correlation_id=command.correlation_id,
            )
            await self._bus.publish(EXECUTION_ERRORS, error_event)

            logger.exception("Execution error handling cancel command")
