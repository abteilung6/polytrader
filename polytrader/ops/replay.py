"""State reconstruction service for rebuilding projections from event log.

Per Phase 7: Rebuild OMS and position projections from event store on boot.
This service reads events from the event store and replays them to rebuild state.

Per flows.mdc §14: Replay / Backtest Mode (Same Core)
- Production behavior should be explainable by replay
- Rebuild projections from event log
"""

from polytrader.events.store import IEventStore
from polytrader.events.types import (
    FillEvent,
    OrderAckEvent,
    OrderCanceledEvent,
    OrderCreatedEvent,
    OrderRejectedEvent,
    OrderSubmittedEvent,
)
from polytrader.logging_config import logger
from polytrader.oms.store import IEventHandlingOrderStore
from polytrader.position_manager import IPositionManager

# Order-related event types for OMS reconstruction
ORDER_EVENT_TYPES = (
    OrderCreatedEvent,
    OrderSubmittedEvent,
    OrderAckEvent,
    OrderRejectedEvent,
    FillEvent,
    OrderCanceledEvent,
)


class StateReconstructionService:
    """Service for reconstructing state from event log.

    Per Phase 7: Rebuilds OMS and position projections from event store on boot.
    This service:
    1. Reads order-related events from event store
    2. Rebuilds OMS state by replaying events
    3. Rebuilds positions by replaying FillEvents
    4. Handles missing events gracefully

    Attributes:
        _event_store: Event store for reading events
        _oms_store: OMS order store for rebuilding order state
        _position_manager: Position manager for rebuilding positions (optional)
    """

    def __init__(
        self,
        event_store: IEventStore,
        oms_store: IEventHandlingOrderStore,
        position_manager: IPositionManager | None = None,
    ) -> None:
        """Initialize state reconstruction service.

        Args:
            event_store: Event store for reading events
            oms_store: OMS order store for rebuilding order state
            position_manager: Position manager for rebuilding positions (optional)
        """
        self._event_store = event_store
        self._oms_store = oms_store
        self._position_manager = position_manager

    async def reconstruct_oms(self) -> None:
        """Rebuild OMS state from event log.

        Per Phase 7: Read all order-related events from event store and
        call oms_store.rebuild_from_events(events).

        Events are filtered by type and sorted by ts_mono to ensure
        chronological replay.

        Note:
            This method clears existing OMS state and rebuilds from scratch.
            Missing events are handled gracefully (replay continues).
        """
        logger.info("Starting OMS state reconstruction from event log")

        # Collect all order-related events
        order_events: list[
            OrderCreatedEvent
            | OrderSubmittedEvent
            | OrderAckEvent
            | OrderRejectedEvent
            | FillEvent
            | OrderCanceledEvent
        ] = []

        # Read events for each order event type
        for event_type in ORDER_EVENT_TYPES:
            for event in self._event_store.replay(event_type=event_type):
                # Type narrowing: event is already filtered by event_type
                order_events.append(event)  # type: ignore[arg-type]

        # Sort by ts_mono to ensure chronological order
        # (replay() already sorts, but we're combining multiple types)
        order_events.sort(key=lambda e: e.ts_mono)

        logger.info(
            "Found {count} order-related events for OMS reconstruction",
            count=len(order_events),
        )

        if not order_events:
            logger.info("No order events found, OMS state remains empty")
            return

        # Rebuild OMS state from events
        try:
            # Convert to list[Event] for rebuild_from_events
            from polytrader.events.types import Event

            events: list[Event] = list(order_events)
            self._oms_store.rebuild_from_events(events)

            # Count reconstructed orders
            open_orders = self._oms_store.get_open_orders()
            logger.info(
                "OMS state reconstructed: {event_count} events replayed, "
                "{order_count} orders in store ({open_count} open)",
                event_count=len(order_events),
                order_count=len(self._oms_store.get_all_orders()),
                open_count=len(open_orders),
            )
        except Exception as e:
            logger.exception(
                "Error during OMS reconstruction: {error}",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    async def reconstruct_positions(self) -> None:
        """Rebuild positions from FillEvents.

        Per Phase 7: Read all FillEvents from event store and replay them
        to position manager.

        Note:
            This method only works with PaperPositionManager which has
            _handle_fill() method. For live PositionManager, positions
            are rebuilt via external API sync.

        Raises:
            ValueError: If position_manager is None or doesn't support fill replay
        """
        if self._position_manager is None:
            logger.info("No position manager provided, skipping position reconstruction")
            return

        logger.info("Starting position reconstruction from FillEvents")

        # Read all FillEvents from event store
        fill_events: list[FillEvent] = []
        for event in self._event_store.replay(event_type=FillEvent):
            if isinstance(event, FillEvent):
                fill_events.append(event)

        # Sort by ts_mono to ensure chronological order
        fill_events.sort(key=lambda e: e.ts_mono)

        logger.info(
            "Found {count} FillEvents for position reconstruction",
            count=len(fill_events),
        )

        if not fill_events:
            logger.info("No FillEvents found, positions remain empty")
            return

        # Replay fills to position manager
        # Check if position manager supports fill replay
        if not hasattr(self._position_manager, "_handle_fill"):
            logger.warning(
                "Position manager does not support fill replay (missing _handle_fill method). "
                "Positions will be rebuilt via external API sync instead."
            )
            return

        # Replay fills in chronological order
        replayed_count = 0
        error_count = 0

        for fill_event in fill_events:
            try:
                # Get order from OMS store to get order details
                order = None
                if fill_event.order_id:
                    order = self._oms_store.get_order(fill_event.order_id)

                if order is None:
                    logger.warning(
                        "FillEvent references unknown order_id: {order_id}, skipping",
                        order_id=fill_event.order_id,
                    )
                    error_count += 1
                    continue

                # Replay fill to position manager
                # PaperPositionManager has _handle_fill method
                await self._position_manager._handle_fill(fill_event)  # type: ignore[attr-defined]
                replayed_count += 1

            except Exception as e:
                logger.exception(
                    "Error replaying FillEvent {event_id}: {error}",
                    event_id=fill_event.event_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                error_count += 1
                # Continue with next fill (graceful handling)

        # Get final position count
        positions = self._position_manager.get_positions() or {}
        position_count = len(positions)

        logger.info(
            "Position reconstruction complete: {replayed} fills replayed, "
            "{errors} errors, {positions} positions",
            replayed=replayed_count,
            errors=error_count,
            positions=position_count,
        )

    async def reconstruct_all(self) -> None:
        """Rebuild both OMS and positions from event log.

        Per Phase 7: Reconstructs OMS first, then positions (since positions
        depend on order data from OMS).

        This is a convenience method that calls both reconstruct_oms() and
        reconstruct_positions() in the correct order.
        """
        logger.info("Starting full state reconstruction from event log")

        # Reconstruct OMS first (positions depend on order data)
        await self.reconstruct_oms()

        # Then reconstruct positions
        await self.reconstruct_positions()

        logger.info("Full state reconstruction complete")
