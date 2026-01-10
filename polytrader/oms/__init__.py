"""Order Management System (OMS) module.

Per flows.mdc §7: OMS is the authoritative owner of order state.
OMS manages the order lifecycle via explicit finite state machine.
"""

from polytrader.oms.fsm import (
    InvalidTransitionError,
    can_transition,
    get_valid_transitions,
    is_terminal_state,
    transition_order_state,
)
from polytrader.oms.idempotency import IdempotencyStore, generate_client_order_id
from polytrader.oms.models import Fill, Order, OrderState
from polytrader.oms.store import IOrderStore, InMemoryOrderStore

__all__ = [
    "Fill",
    "IOrderStore",
    "IdempotencyStore",
    "InMemoryOrderStore",
    "InvalidTransitionError",
    "Order",
    "OrderState",
    "can_transition",
    "generate_client_order_id",
    "get_valid_transitions",
    "is_terminal_state",
    "transition_order_state",
]
