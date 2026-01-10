"""Tests for OMS FSM: State transition functions."""

import pytest

from polytrader.oms.fsm import (
    InvalidTransitionError,
    can_transition,
    get_valid_transitions,
    is_terminal_state,
    transition_order_state,
)
from polytrader.oms.models import Order, OrderState
from polytrader.types import OrderIntentEvent


def create_test_order(state: OrderState = OrderState.NEW) -> Order:
    """Create a test order with specified state."""
    intent = OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        target_price=0.6,
        limit_price=0.5,
        size=10.0,
        reason="Test order",
    )
    return Order(
        client_order_id="test-client-id",
        intent=intent,
        market_slug=intent.market_slug,
        outcome=intent.outcome,
        side=intent.side,
        size=intent.size,
        limit_price=intent.limit_price,
        correlation_id=intent.correlation_id,
        state=state,
    )


class TestCanTransition:
    """Tests for can_transition function."""

    def test_valid_transitions(self) -> None:
        """Test all valid transitions."""
        # Order creation flow
        assert can_transition(OrderState.NEW, OrderState.PENDING_SUBMIT)

        # Submission flow
        assert can_transition(OrderState.PENDING_SUBMIT, OrderState.SUBMITTED)
        assert can_transition(OrderState.PENDING_SUBMIT, OrderState.CANCELLED)

        # Venue response flow
        assert can_transition(OrderState.SUBMITTED, OrderState.ACKED)
        assert can_transition(OrderState.SUBMITTED, OrderState.REJECTED)

        # Fill flow
        assert can_transition(OrderState.ACKED, OrderState.PARTIALLY_FILLED)
        assert can_transition(OrderState.ACKED, OrderState.FILLED)
        assert can_transition(OrderState.PARTIALLY_FILLED, OrderState.FILLED)

        # Cancel flow
        assert can_transition(OrderState.ACKED, OrderState.CANCELLED)
        assert can_transition(OrderState.PARTIALLY_FILLED, OrderState.CANCELLED)

    def test_invalid_transitions(self) -> None:
        """Test invalid transitions."""
        # Cannot go backwards
        assert not can_transition(OrderState.PENDING_SUBMIT, OrderState.NEW)
        assert not can_transition(OrderState.ACKED, OrderState.SUBMITTED)

        # Cannot skip states
        assert not can_transition(OrderState.NEW, OrderState.ACKED)
        assert not can_transition(OrderState.NEW, OrderState.FILLED)

        # Terminal states cannot transition
        assert not can_transition(OrderState.FILLED, OrderState.CANCELLED)
        assert not can_transition(OrderState.CANCELLED, OrderState.FILLED)
        assert not can_transition(OrderState.REJECTED, OrderState.ACKED)

        # Invalid combinations
        assert not can_transition(OrderState.ACKED, OrderState.SUBMITTED)
        assert not can_transition(OrderState.PARTIALLY_FILLED, OrderState.ACKED)


class TestGetValidTransitions:
    """Tests for get_valid_transitions function."""

    def test_new_state_transitions(self) -> None:
        """Test valid transitions from NEW state."""
        valid = get_valid_transitions(OrderState.NEW)
        assert len(valid) == 1
        assert OrderState.PENDING_SUBMIT in valid

    def test_pending_submit_transitions(self) -> None:
        """Test valid transitions from PENDING_SUBMIT state."""
        valid = get_valid_transitions(OrderState.PENDING_SUBMIT)
        assert len(valid) == 2
        assert OrderState.SUBMITTED in valid
        assert OrderState.CANCELLED in valid

    def test_submitted_transitions(self) -> None:
        """Test valid transitions from SUBMITTED state."""
        valid = get_valid_transitions(OrderState.SUBMITTED)
        assert len(valid) == 2
        assert OrderState.ACKED in valid
        assert OrderState.REJECTED in valid

    def test_acked_transitions(self) -> None:
        """Test valid transitions from ACKED state."""
        valid = get_valid_transitions(OrderState.ACKED)
        assert len(valid) == 3
        assert OrderState.PARTIALLY_FILLED in valid
        assert OrderState.FILLED in valid
        assert OrderState.CANCELLED in valid

    def test_partially_filled_transitions(self) -> None:
        """Test valid transitions from PARTIALLY_FILLED state."""
        valid = get_valid_transitions(OrderState.PARTIALLY_FILLED)
        assert len(valid) == 2
        assert OrderState.FILLED in valid
        assert OrderState.CANCELLED in valid

    def test_terminal_state_transitions(self) -> None:
        """Test that terminal states have no valid transitions."""
        assert len(get_valid_transitions(OrderState.FILLED)) == 0
        assert len(get_valid_transitions(OrderState.CANCELLED)) == 0
        assert len(get_valid_transitions(OrderState.REJECTED)) == 0


class TestIsTerminalState:
    """Tests for is_terminal_state function."""

    def test_terminal_states(self) -> None:
        """Test that terminal states are identified correctly."""
        assert is_terminal_state(OrderState.FILLED)
        assert is_terminal_state(OrderState.CANCELLED)
        assert is_terminal_state(OrderState.REJECTED)

    def test_non_terminal_states(self) -> None:
        """Test that non-terminal states are identified correctly."""
        assert not is_terminal_state(OrderState.NEW)
        assert not is_terminal_state(OrderState.PENDING_SUBMIT)
        assert not is_terminal_state(OrderState.SUBMITTED)
        assert not is_terminal_state(OrderState.ACKED)
        assert not is_terminal_state(OrderState.PARTIALLY_FILLED)


class TestTransitionOrderState:
    """Tests for transition_order_state function."""

    def test_valid_transition_new_to_pending_submit(self) -> None:
        """Test valid transition: NEW → PENDING_SUBMIT."""
        order = create_test_order(OrderState.NEW)
        new_order = transition_order_state(order, OrderState.PENDING_SUBMIT)

        assert new_order.state == OrderState.PENDING_SUBMIT
        assert new_order.order_id == order.order_id
        assert new_order.updated_at > order.updated_at

    def test_valid_transition_pending_submit_to_submitted(self) -> None:
        """Test valid transition: PENDING_SUBMIT → SUBMITTED."""
        order = create_test_order(OrderState.PENDING_SUBMIT)
        new_order = transition_order_state(order, OrderState.SUBMITTED)

        assert new_order.state == OrderState.SUBMITTED
        assert new_order.updated_at > order.updated_at

    def test_valid_transition_submitted_to_acked(self) -> None:
        """Test valid transition: SUBMITTED → ACKED."""
        order = create_test_order(OrderState.SUBMITTED)
        new_order = transition_order_state(order, OrderState.ACKED)

        assert new_order.state == OrderState.ACKED
        assert new_order.updated_at > order.updated_at

    def test_valid_transition_submitted_to_rejected(self) -> None:
        """Test valid transition: SUBMITTED → REJECTED with reason."""
        order = create_test_order(OrderState.SUBMITTED)
        reason = "Insufficient balance"
        new_order = transition_order_state(order, OrderState.REJECTED, reason=reason)

        assert new_order.state == OrderState.REJECTED
        assert new_order.reject_reason == reason
        assert new_order.updated_at > order.updated_at

    def test_valid_transition_acked_to_partially_filled(self) -> None:
        """Test valid transition: ACKED → PARTIALLY_FILLED."""
        order = create_test_order(OrderState.ACKED)
        new_order = transition_order_state(order, OrderState.PARTIALLY_FILLED)

        assert new_order.state == OrderState.PARTIALLY_FILLED
        assert new_order.updated_at > order.updated_at

    def test_valid_transition_acked_to_filled(self) -> None:
        """Test valid transition: ACKED → FILLED."""
        order = create_test_order(OrderState.ACKED)
        new_order = transition_order_state(order, OrderState.FILLED)

        assert new_order.state == OrderState.FILLED
        assert new_order.updated_at > order.updated_at

    def test_valid_transition_partially_filled_to_filled(self) -> None:
        """Test valid transition: PARTIALLY_FILLED → FILLED."""
        order = create_test_order(OrderState.PARTIALLY_FILLED)
        new_order = transition_order_state(order, OrderState.FILLED)

        assert new_order.state == OrderState.FILLED
        assert new_order.updated_at > order.updated_at

    def test_valid_transition_acked_to_cancelled(self) -> None:
        """Test valid transition: ACKED → CANCELLED."""
        order = create_test_order(OrderState.ACKED)
        new_order = transition_order_state(order, OrderState.CANCELLED)

        assert new_order.state == OrderState.CANCELLED
        assert new_order.updated_at > order.updated_at

    def test_valid_transition_partially_filled_to_cancelled(self) -> None:
        """Test valid transition: PARTIALLY_FILLED → CANCELLED."""
        order = create_test_order(OrderState.PARTIALLY_FILLED)
        new_order = transition_order_state(order, OrderState.CANCELLED)

        assert new_order.state == OrderState.CANCELLED
        assert new_order.updated_at > order.updated_at

    def test_valid_transition_pending_submit_to_cancelled(self) -> None:
        """Test valid transition: PENDING_SUBMIT → CANCELLED."""
        order = create_test_order(OrderState.PENDING_SUBMIT)
        new_order = transition_order_state(order, OrderState.CANCELLED)

        assert new_order.state == OrderState.CANCELLED
        assert new_order.updated_at > order.updated_at

    def test_invalid_transition_raises_error(self) -> None:
        """Test that invalid transitions raise InvalidTransitionError."""
        order = create_test_order(OrderState.NEW)

        with pytest.raises(InvalidTransitionError) as exc_info:
            transition_order_state(order, OrderState.FILLED)

        assert exc_info.value.from_state == OrderState.NEW
        assert exc_info.value.to_state == OrderState.FILLED

    def test_invalid_transition_from_terminal_state(self) -> None:
        """Test that transitions from terminal states raise error."""
        order = create_test_order(OrderState.FILLED)

        with pytest.raises(InvalidTransitionError):
            transition_order_state(order, OrderState.CANCELLED)

    def test_idempotent_transition(self) -> None:
        """Test that transitioning to the same state is idempotent."""
        order = create_test_order(OrderState.ACKED)
        original_updated_at = order.updated_at

        # Transition to same state
        new_order = transition_order_state(order, OrderState.ACKED)

        # Should return same order (idempotent)
        assert new_order.state == OrderState.ACKED
        # Note: updated_at will still be updated (by design)
        assert new_order.updated_at >= original_updated_at

    def test_reject_reason_only_set_on_reject(self) -> None:
        """Test that reject_reason is only set when transitioning to REJECTED."""
        order = create_test_order(OrderState.SUBMITTED)
        order.reject_reason = None

        # Transition to ACKED (should not set reject_reason)
        acked_order = transition_order_state(order, OrderState.ACKED)
        assert acked_order.reject_reason is None

        # Transition to REJECTED (should set reject_reason)
        rejected_order = transition_order_state(order, OrderState.REJECTED, reason="Test rejection")
        assert rejected_order.reject_reason == "Test rejection"

    def test_reject_reason_without_reason(self) -> None:
        """Test that reject_reason can be None if no reason provided."""
        order = create_test_order(OrderState.SUBMITTED)
        new_order = transition_order_state(order, OrderState.REJECTED)

        assert new_order.state == OrderState.REJECTED
        # reject_reason should be None if not provided
        assert new_order.reject_reason is None

    def test_transition_preserves_order_fields(self) -> None:
        """Test that transition preserves all order fields except state and updated_at."""
        order = create_test_order(OrderState.NEW)
        original_order_id = order.order_id
        original_client_order_id = order.client_order_id
        original_correlation_id = order.correlation_id

        new_order = transition_order_state(order, OrderState.PENDING_SUBMIT)

        assert new_order.order_id == original_order_id
        assert new_order.client_order_id == original_client_order_id
        assert new_order.correlation_id == original_correlation_id
        assert new_order.market_slug == order.market_slug
        assert new_order.outcome == order.outcome
        assert new_order.side == order.side
        assert new_order.size == order.size


class TestInvalidTransitionError:
    """Tests for InvalidTransitionError exception."""

    def test_error_message(self) -> None:
        """Test that error message includes states."""
        error = InvalidTransitionError(OrderState.NEW, OrderState.FILLED, reason="Test reason")

        assert "NEW" in str(error)
        assert "FILLED" in str(error)
        assert "Test reason" in str(error)

    def test_error_attributes(self) -> None:
        """Test that error has correct attributes."""
        error = InvalidTransitionError(OrderState.NEW, OrderState.FILLED, reason="Test reason")

        assert error.from_state == OrderState.NEW
        assert error.to_state == OrderState.FILLED
        assert error.reason == "Test reason"

    def test_error_without_reason(self) -> None:
        """Test error without reason."""
        error = InvalidTransitionError(OrderState.NEW, OrderState.FILLED)

        assert error.from_state == OrderState.NEW
        assert error.to_state == OrderState.FILLED
        assert error.reason is None
        assert "NEW" in str(error)
        assert "FILLED" in str(error)


class TestFSMEdgeCases:
    """Tests for FSM edge cases."""

    def test_complete_order_lifecycle(self) -> None:
        """Test a complete order lifecycle through all states."""
        order = create_test_order(OrderState.NEW)

        # NEW → PENDING_SUBMIT
        order = transition_order_state(order, OrderState.PENDING_SUBMIT)
        assert order.state == OrderState.PENDING_SUBMIT

        # PENDING_SUBMIT → SUBMITTED
        order = transition_order_state(order, OrderState.SUBMITTED)
        assert order.state == OrderState.SUBMITTED

        # SUBMITTED → ACKED
        order = transition_order_state(order, OrderState.ACKED)
        assert order.state == OrderState.ACKED

        # ACKED → PARTIALLY_FILLED
        order = transition_order_state(order, OrderState.PARTIALLY_FILLED)
        assert order.state == OrderState.PARTIALLY_FILLED

        # PARTIALLY_FILLED → FILLED
        order = transition_order_state(order, OrderState.FILLED)
        assert order.state == OrderState.FILLED
        assert order.is_terminal

    def test_rejected_order_lifecycle(self) -> None:
        """Test order lifecycle ending in rejection."""
        order = create_test_order(OrderState.NEW)

        # NEW → PENDING_SUBMIT
        order = transition_order_state(order, OrderState.PENDING_SUBMIT)

        # PENDING_SUBMIT → SUBMITTED
        order = transition_order_state(order, OrderState.SUBMITTED)

        # SUBMITTED → REJECTED
        order = transition_order_state(order, OrderState.REJECTED, reason="Insufficient balance")
        assert order.state == OrderState.REJECTED
        assert order.reject_reason == "Insufficient balance"
        assert order.is_terminal

    def test_cancelled_order_lifecycle(self) -> None:
        """Test order lifecycle ending in cancellation."""
        order = create_test_order(OrderState.NEW)

        # NEW → PENDING_SUBMIT
        order = transition_order_state(order, OrderState.PENDING_SUBMIT)

        # PENDING_SUBMIT → SUBMITTED
        order = transition_order_state(order, OrderState.SUBMITTED)

        # SUBMITTED → ACKED
        order = transition_order_state(order, OrderState.ACKED)

        # ACKED → CANCELLED
        order = transition_order_state(order, OrderState.CANCELLED)
        assert order.state == OrderState.CANCELLED
        assert order.is_terminal

    def test_cancel_before_submit(self) -> None:
        """Test cancelling order before submission."""
        order = create_test_order(OrderState.NEW)

        # NEW → PENDING_SUBMIT
        order = transition_order_state(order, OrderState.PENDING_SUBMIT)

        # PENDING_SUBMIT → CANCELLED (before SUBMITTED)
        order = transition_order_state(order, OrderState.CANCELLED)
        assert order.state == OrderState.CANCELLED
        assert order.is_terminal
