"""Order Management System (OMS) module.

Per flows.mdc §7: OMS is the authoritative owner of order state.
OMS manages the order lifecycle via explicit finite state machine.
"""

from polytrader.oms.commands import CancelOrderCommand, SubmitOrderCommand
from polytrader.oms.core import OMSCore
from polytrader.oms.fsm import (
    InvalidTransitionError,
    can_transition,
    get_valid_transitions,
    is_terminal_state,
    transition_order_state,
)
from polytrader.oms.idempotency import IdempotencyStore, generate_client_order_id
from polytrader.oms.metrics import (
    record_fill,
    record_idempotency_hit,
    record_invalid_transition,
    record_order_acked,
    record_order_cancelled,
    record_order_created,
    record_order_lifetime,
    record_order_rejected,
    record_order_submitted,
    update_orders_live_gauge,
)
from polytrader.oms.models import Fill, Order, OrderState
from polytrader.oms.store import (
    IEventHandlingOrderStore,
    InMemoryOrderStore,
    IOrderStore,
)

__all__ = [
    "CancelOrderCommand",
    "Fill",
    "IEventHandlingOrderStore",
    "IOrderStore",
    "IdempotencyStore",
    "InMemoryOrderStore",
    "InvalidTransitionError",
    "OMSCore",
    "Order",
    "OrderState",
    "SubmitOrderCommand",
    "can_transition",
    "generate_client_order_id",
    "get_valid_transitions",
    "is_terminal_state",
    "record_fill",
    "record_idempotency_hit",
    "record_invalid_transition",
    "record_order_acked",
    "record_order_cancelled",
    "record_order_created",
    "record_order_lifetime",
    "record_order_rejected",
    "record_order_submitted",
    "transition_order_state",
    "update_orders_live_gauge",
]
