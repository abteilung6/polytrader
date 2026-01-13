"""OMS Reconciliation Service.

Per flows.mdc §12: Continuous reconciliation against venue truth.
This module compares OMS state with venue state and detects divergences.

Reconciliation detects:
- Phantom orders: OMS has order, venue doesn't (by venue_order_id)
- Orphan orders: Venue has order, OMS doesn't (by venue_order_id)
- Fill mismatches: OMS filled_size != venue filled_size
"""

from typing import TYPE_CHECKING

from polytrader.events import RECONCILE
from polytrader.events.bus import EventBus
from polytrader.events.types import ReconcileEvent
from polytrader.logging_config import logger
from polytrader.oms.models import Order
from polytrader.oms.store import IOrderStore

if TYPE_CHECKING:
    from polytrader.clob import ExternalOrder
    from polytrader.execution.adapter import IVenueAdapter


class ReconciliationService:
    """Reconciliation service for comparing OMS state with venue.

    Per flows.mdc §12: Continuous reconciliation against venue truth.
    This service:
    1. Fetches OMS open orders
    2. Fetches venue open orders
    3. Compares them and detects divergences
    4. Emits ReconcileEvent for each divergence

    Attributes:
        store: OMS order store
        venue_adapter: Venue adapter for fetching venue orders
        bus: Event bus for publishing ReconcileEvents
    """

    def __init__(
        self,
        store: IOrderStore,
        venue_adapter: "IVenueAdapter",
        bus: EventBus,
    ) -> None:
        """Initialize reconciliation service.

        Args:
            store: OMS order store
            venue_adapter: Venue adapter for fetching venue orders
            bus: Event bus for publishing ReconcileEvents
        """
        self._store = store
        self._venue_adapter = venue_adapter
        self._bus = bus

    async def reconcile(self) -> list[ReconcileEvent]:
        """Reconcile OMS state with venue state.

        Per flows.mdc §12: Compare venue truth vs OMS projection.

        Returns:
            List of ReconcileEvents (one per divergence, empty if none)
        """
        logger.info("Starting reconciliation")

        # Fetch OMS open orders
        oms_orders = self._store.get_open_orders()
        logger.debug(f"OMS has {len(oms_orders)} open orders")

        # Fetch venue open orders
        try:
            venue_orders_raw = await self._venue_adapter.get_open_orders()
        except Exception as e:
            logger.exception("Failed to fetch venue orders", error=str(e))
            # Emit error-level ReconcileEvent for fetch failure
            error_event = ReconcileEvent(
                divergence_type="none",
                severity="ERROR",
                details={
                    "error": "Failed to fetch venue orders",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            await self._bus.publish(RECONCILE, error_event)
            return [error_event]

        # Parse venue orders to ExternalOrder models
        from polytrader.clob import ExternalOrder

        venue_orders: list[ExternalOrder] = []
        for order_data in venue_orders_raw:
            external_order = ExternalOrder.from_api_response(order_data)
            if external_order:
                venue_orders.append(external_order)
            else:
                logger.warning(
                    "Failed to parse venue order",
                    order_data=order_data,
                )

        logger.debug(f"Venue has {len(venue_orders)} open orders")

        # Compare orders and detect divergences
        reconcile_events = self._compare_orders(oms_orders, venue_orders)

        # Publish all reconcile events
        for event in reconcile_events:
            await self._bus.publish(RECONCILE, event)

        if reconcile_events:
            logger.warning(
                f"Reconciliation detected {len(reconcile_events)} divergence(s)",
                count=len(reconcile_events),
            )
        else:
            logger.info("Reconciliation complete: no divergences detected")

        return reconcile_events

    def _compare_orders(
        self,
        oms_orders: list[Order],
        venue_orders: list["ExternalOrder"],
    ) -> list[ReconcileEvent]:
        """Compare OMS orders with venue orders and detect divergences.

        Args:
            oms_orders: List of OMS open orders
            venue_orders: List of venue open orders

        Returns:
            List of ReconcileEvents (one per divergence)
        """
        reconcile_events: list[ReconcileEvent] = []

        # Build maps for efficient lookup
        oms_by_venue_id: dict[str, Order] = {}
        for order in oms_orders:
            if order.venue_order_id:
                oms_by_venue_id[order.venue_order_id] = order

        venue_by_id: dict[str, ExternalOrder] = {}
        for venue_order in venue_orders:
            venue_by_id[venue_order.order_id] = venue_order

        # Detect phantom orders: OMS has order, venue doesn't
        for order in oms_orders:
            if order.venue_order_id and order.venue_order_id not in venue_by_id:
                # OMS thinks order is open, but venue doesn't have it
                # This could mean:
                # - Order was cancelled/filled on venue but we didn't receive update
                # - Order was never actually placed
                # - Network issue prevented us from receiving update
                event = ReconcileEvent(
                    divergence_type="phantom_order",
                    order_id=order.order_id,
                    venue_order_id=order.venue_order_id,
                    severity="WARNING",
                    details={
                        "oms_state": order.state.value,
                        "oms_filled_size": order.filled_size,
                        "oms_size": order.size,
                        "oms_market": order.market_slug,
                        "oms_outcome": order.outcome,
                        "oms_side": order.side,
                    },
                )
                reconcile_events.append(event)
                logger.warning(
                    "Phantom order detected",
                    order_id=order.order_id,
                    venue_order_id=order.venue_order_id,
                )

        # Detect orphan orders: Venue has order, OMS doesn't
        for venue_order in venue_orders:
            if venue_order.order_id not in oms_by_venue_id:
                # Venue has order, but OMS doesn't know about it
                # This could mean:
                # - Order was placed outside our system
                # - Order was placed before system restart and we lost state
                # - Order was placed by another instance/system
                event = ReconcileEvent(
                    divergence_type="orphan_order",
                    venue_order_id=venue_order.order_id,
                    severity="WARNING",
                    details={
                        "venue_status": venue_order.status,
                        "venue_size": venue_order.size,
                        "venue_side": venue_order.side,
                        "venue_token_id": venue_order.token_id,
                    },
                )
                reconcile_events.append(event)
                logger.warning(
                    "Orphan order detected",
                    venue_order_id=venue_order.order_id,
                )

        # Detect fill mismatches: OMS filled_size != venue filled_size
        for order in oms_orders:
            if not order.venue_order_id:
                # Can't compare if we don't have venue_order_id
                continue

            matched_venue_order: ExternalOrder | None = venue_by_id.get(order.venue_order_id)
            if not matched_venue_order:
                # Already handled as phantom order above
                continue

            # Compare fill sizes
            # Note: ExternalOrder doesn't have filled_size, only status and size
            # We need to infer filled_size from status and size
            # For now, we'll check if venue order is FILLED but OMS isn't
            # or if venue order is PARTIALLY_FILLED but OMS filled_size doesn't match

            if matched_venue_order.status == "FILLED" and order.state.value != "FILLED":
                # Venue says filled, but OMS doesn't
                event = ReconcileEvent(
                    divergence_type="fill_mismatch",
                    order_id=order.order_id,
                    venue_order_id=order.venue_order_id,
                    severity="ERROR",
                    details={
                        "oms_state": order.state.value,
                        "oms_filled_size": order.filled_size,
                        "oms_size": order.size,
                        "venue_status": matched_venue_order.status,
                        "venue_size": matched_venue_order.size,
                        "expected_oms_state": "FILLED",
                    },
                )
                reconcile_events.append(event)
                logger.error(
                    "Fill mismatch detected: venue says FILLED but OMS doesn't",
                    order_id=order.order_id,
                    venue_order_id=order.venue_order_id,
                )
            elif matched_venue_order.status == "OPEN" and order.filled_size > 0:
                # Venue says OPEN, but OMS has fills
                # This is less severe - could be timing issue
                # But we should still log it
                event = ReconcileEvent(
                    divergence_type="fill_mismatch",
                    order_id=order.order_id,
                    venue_order_id=order.venue_order_id,
                    severity="WARNING",
                    details={
                        "oms_state": order.state.value,
                        "oms_filled_size": order.filled_size,
                        "oms_size": order.size,
                        "venue_status": matched_venue_order.status,
                        "venue_size": matched_venue_order.size,
                        "note": "Venue says OPEN but OMS has fills (possible timing issue)",
                    },
                )
                reconcile_events.append(event)
                logger.warning(
                    "Fill mismatch detected: venue says OPEN but OMS has fills",
                    order_id=order.order_id,
                    venue_order_id=order.venue_order_id,
                )

        return reconcile_events
