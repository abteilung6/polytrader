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
from polytrader.obs.logging import bind_correlation_context
from polytrader.obs.metrics import record_adapter_error

if TYPE_CHECKING:
    from polytrader.oms.commands import CancelOrderCommand, SubmitOrderCommand
    from polytrader.ops.control import ExecutionControl


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
        execution_control: "ExecutionControl | None" = None,
        active_strategies: set[str] | None = None,
        is_paper_mode: bool = True,
    ) -> None:
        """Initialize execution router.

        Args:
            bus: Event bus for publishing events
            adapter: Venue adapter for order submission (implements IVenueAdapter)
            tactics: Execution tactics engine (defaults to new instance)
            execution_control: Execution control for checking execution_enabled (optional)
            active_strategies: Set of active strategy IDs for live trading (optional)
            is_paper_mode: Whether system is in paper mode (default: True)
        """
        from polytrader.execution.tactics import ExecutionTactics

        self._bus = bus
        self._adapter = adapter
        self._tactics = tactics or ExecutionTactics()
        self._execution_control = execution_control
        self._active_strategies = active_strategies or set()
        self._is_paper_mode = is_paper_mode
        self._running = False

    def get_adapter(self) -> IVenueAdapter:
        """Get the venue adapter (for reconciliation).

        Returns:
            Venue adapter instance
        """
        return self._adapter

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
                bind_correlation_context(
                    logger,
                    correlation_id="",
                    event_type="ExecutionSubmitProcessorError",
                    error_class="system",
                ).exception("Error in submit command processor")

        async def process_cancel_commands() -> None:
            """Process cancel commands."""
            try:
                while self._running:
                    command = await cancel_queue.get()
                    await self._handle_cancel_command(command)
            except asyncio.CancelledError:
                pass
            except Exception:
                bind_correlation_context(
                    logger,
                    correlation_id="",
                    event_type="ExecutionCancelProcessorError",
                    error_class="system",
                ).exception("Error in cancel command processor")

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

        # Check if execution is enabled (Phase 7: execution gating)
        if self._execution_control is not None and not self._execution_control.is_enabled():
            bind_correlation_context(
                logger,
                correlation_id=command.correlation_id,
                order_id=command.order_id,
                client_order_id=command.client_order_id,
                market_slug=command.intent.market_slug,
                outcome=command.intent.outcome,
                side=command.intent.side,
                event_type="ExecutionDisabled",
                error_class="system",
            ).warning("Order submission rejected: execution is disabled")

            # Emit OrderRejectedEvent
            from polytrader.events import ORDER_REJECTS
            from polytrader.events.types import OrderRejectedEvent

            reject_event = OrderRejectedEvent(
                order_id=command.order_id,
                venue_order_id=None,
                reason="Execution disabled",
                correlation_id=command.correlation_id,
            )
            await self._bus.publish(ORDER_REJECTS, reject_event)
            return

        # Check strategy activation (backstop - should not reach here if Risk works)
        # Paper mode: always allow (skip check)
        if not self._is_paper_mode:
            strategy_id = command.intent.strategy_id
            if strategy_id not in self._active_strategies:
                bind_correlation_context(
                    logger,
                    correlation_id=command.correlation_id,
                    order_id=command.order_id,
                    client_order_id=command.client_order_id,
                    market_slug=command.intent.market_slug,
                    outcome=command.intent.outcome,
                    side=command.intent.side,
                    strategy_id=strategy_id,
                    event_type="StrategyNotActive",
                    error_class="system",
                ).warning(
                    "Order submission rejected: strategy not active for live trading",
                    strategy_id=strategy_id,
                )

                # Emit OrderRejectedEvent
                from polytrader.events import ORDER_REJECTS
                from polytrader.events.types import OrderRejectedEvent

                reject_event = OrderRejectedEvent(
                    order_id=command.order_id,
                    venue_order_id=None,
                    reason="Strategy not active for live trading",
                    correlation_id=command.correlation_id,
                )
                await self._bus.publish(ORDER_REJECTS, reject_event)
                return

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
                latency_ms = (time.monotonic() - start_time) * 1000.0
                error_event = ExecutionErrorEvent(
                    order_id=command.order_id,
                    client_order_id=command.client_order_id,
                    error_type="fatal",
                    error_message=str(e),
                    venue="polymarket",
                    correlation_id=command.correlation_id,
                )
                await self._bus.publish(EXECUTION_ERRORS, error_event)

                # Emit adapter error metric per observability.mdc §4
                record_adapter_error(error_class="fatal")

                # Structured logging for tactic failure
                bind_correlation_context(
                    logger,
                    correlation_id=command.correlation_id,
                    order_id=command.order_id,
                    client_order_id=command.client_order_id,
                    market_slug=command.intent.market_slug,
                    outcome=command.intent.outcome,
                    side=command.intent.side,
                    event_type="ExecutionTacticFailure",
                    error_class="fatal",
                    latency_ms=latency_ms,
                ).error(
                    "Execution tactic failure: {error_message}",
                    error_message=str(e),
                )
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

            # Structured logging for successful submission
            bind_correlation_context(
                logger,
                correlation_id=command.correlation_id,
                order_id=command.order_id,
                client_order_id=command.client_order_id,
                venue_order_id=venue_response.venue_order_id,
                market_slug=command.intent.market_slug,
                outcome=command.intent.outcome,
                side=command.intent.side,
                event_type="ExecutionSubmitSuccess",
                latency_ms=latency_ms,
            ).info(
                "Order submitted successfully: {order_id} venue_order_id={venue_order_id}",
                order_id=command.order_id,
                venue_order_id=venue_response.venue_order_id,
            )

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

            # Emit adapter error metric per observability.mdc §4
            # Map error_type to error_class (retryable/fatal)
            error_class = "retryable" if error_type == "retryable" else "fatal"
            record_adapter_error(error_class=error_class)

            bind_correlation_context(
                logger,
                correlation_id=command.correlation_id,
                order_id=command.order_id,
                client_order_id=command.client_order_id,
                market_slug=command.intent.market_slug,
                outcome=command.intent.outcome,
                side=command.intent.side,
                event_type="ExecutionSubmitError",
                error_class=error_type,
                latency_ms=latency_ms,
            ).exception("Execution error handling submit command")

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

            # Structured logging for successful cancellation
            bind_correlation_context(
                logger,
                correlation_id=command.correlation_id,
                order_id=command.order_id,
                client_order_id=command.client_order_id,
                venue_order_id=command.venue_order_id,
                event_type="ExecutionCancelSuccess",
                latency_ms=latency_ms,
            ).info(
                "Order cancelled successfully: {order_id}",
                order_id=command.order_id,
            )

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

            # Emit adapter error metric per observability.mdc §4
            # Map error_type to error_class (retryable/fatal)
            error_class = "retryable" if error_type == "retryable" else "fatal"
            record_adapter_error(error_class=error_class)

            bind_correlation_context(
                logger,
                correlation_id=command.correlation_id,
                order_id=command.order_id,
                client_order_id=command.client_order_id,
                venue_order_id=command.venue_order_id,
                event_type="ExecutionCancelError",
                error_class=error_type,
                latency_ms=latency_ms,
            ).exception("Execution error handling cancel command")
