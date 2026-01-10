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
    "transition_order_state",
]
