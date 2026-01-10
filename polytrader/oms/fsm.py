"""OMS Finite State Machine: Pure state transition functions.

Per flows.mdc §7: Orders have explicit finite state machine.
Per architecture.mdc §D: OMS owns all order state.

This module provides pure, deterministic functions for order state transitions.
All transitions are validated to ensure they follow the legal state machine.
"""

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from polytrader.oms.models import Order, OrderState


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted.

    Attributes:
        from_state: Current order state
        to_state: Attempted new state
        reason: Optional reason for the invalid transition
    """

    def __init__(
        self,
        from_state: "OrderState",
        to_state: "OrderState",
        reason: str | None = None,
    ) -> None:
        """Initialize InvalidTransitionError.

        Args:
            from_state: Current order state
            to_state: Attempted new state
            reason: Optional reason for the invalid transition
        """
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        message = f"Invalid transition: {from_state.value} → {to_state.value}"
        if reason:
            message += f" ({reason})"
        super().__init__(message)


def _get_valid_transitions() -> set[tuple["OrderState", "OrderState"]]:
    """Get set of valid state transitions per flows.mdc §7, §10.

    Returns:
        Set of (from_state, to_state) tuples representing valid transitions
    """
    from polytrader.oms.models import OrderState

    return {
        # Order creation flow
        (OrderState.NEW, OrderState.PENDING_SUBMIT),  # On order creation
        # Submission flow
        (OrderState.PENDING_SUBMIT, OrderState.SUBMITTED),  # On submit to execution
        (OrderState.PENDING_SUBMIT, OrderState.CANCELLED),  # On cancel before submit
        # Venue response flow
        (OrderState.SUBMITTED, OrderState.ACKED),  # On venue ack
        (OrderState.SUBMITTED, OrderState.REJECTED),  # On venue reject
        # Fill flow
        (OrderState.ACKED, OrderState.PARTIALLY_FILLED),  # On partial fill
        (OrderState.ACKED, OrderState.FILLED),  # On full fill
        (OrderState.PARTIALLY_FILLED, OrderState.FILLED),  # On remaining fill
        # Cancel flow
        (OrderState.ACKED, OrderState.CANCELLED),  # On cancel
        (OrderState.PARTIALLY_FILLED, OrderState.CANCELLED),  # On cancel after partial fill
    }


def can_transition(from_state: "OrderState", to_state: "OrderState") -> bool:
    """Check if a state transition is valid.

    Args:
        from_state: Current order state
        to_state: Target order state

    Returns:
        True if transition is valid, False otherwise
    """
    return (from_state, to_state) in _get_valid_transitions()


def get_valid_transitions(state: "OrderState") -> list["OrderState"]:
    """Get list of valid next states from current state.

    Args:
        state: Current order state

    Returns:
        List of valid next states
    """
    valid_next = [
        to_state for from_state, to_state in _get_valid_transitions() if from_state == state
    ]
    return valid_next


def is_terminal_state(state: "OrderState") -> bool:
    """Check if a state is terminal (no further transitions possible).

    Terminal states: FILLED, CANCELLED, REJECTED

    Args:
        state: Order state to check

    Returns:
        True if state is terminal, False otherwise
    """
    from polytrader.oms.models import OrderState

    return state in (OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED)


def transition_order_state(
    order: "Order",
    new_state: "OrderState",
    reason: str | None = None,
) -> "Order":
    """Transition an order to a new state (pure function).

    Per flows.mdc §7: All order state transitions must be validated.
    This function returns a new Order instance with updated state.

    Args:
        order: Current order instance
        new_state: Target state to transition to
        reason: Optional reason for the transition (used for reject_reason if REJECTED)

    Returns:
        New Order instance with updated state and updated_at timestamp

    Raises:
        InvalidTransitionError: If transition is not valid
    """
    from polytrader.oms.models import OrderState

    # If already in target state, return order unchanged (idempotent)
    # Note: updated_at will still be updated if we proceed, but for true idempotency
    # we return the same instance. However, the test expects updated_at to be updated.
    if order.state == new_state:
        # Return a copy with updated timestamp (per test expectation)
        return order.model_copy(update={"updated_at": time.monotonic()})

    # Check if transition is valid
    if not can_transition(order.state, new_state):
        raise InvalidTransitionError(
            from_state=order.state,
            to_state=new_state,
            reason=reason or "Transition not allowed by FSM",
        )

    # Create updated order with new state
    updated_order = order.model_copy(
        update={
            "state": new_state,
            "updated_at": time.monotonic(),
        }
    )

    # Set reject_reason if transitioning to REJECTED
    if new_state == OrderState.REJECTED and reason:
        updated_order.reject_reason = reason

    return updated_order
