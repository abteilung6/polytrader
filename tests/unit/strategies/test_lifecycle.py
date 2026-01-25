"""Unit tests for strategy lifecycle state machine.

Per testing.mdc: Unit tests must be deterministic, fast, and isolated.
All FSM functions are pure (no side effects, no I/O).
"""

import pytest

from polytrader.strategies.lifecycle import (
    InvalidTransitionError,
    can_transition,
    is_terminal_state,
    transition_strategy_state,
)
from polytrader.strategies.lifecycle_models import StrategyLifecycleState


class TestStrategyLifecycleState:
    """Tests for StrategyLifecycleState enum."""

    def test_all_states_defined(self) -> None:
        """Test that all required states are defined."""
        assert StrategyLifecycleState.STOPPED == "STOPPED"
        assert StrategyLifecycleState.STARTING == "STARTING"
        assert StrategyLifecycleState.RUNNING == "RUNNING"
        assert StrategyLifecycleState.PAUSED == "PAUSED"
        assert StrategyLifecycleState.DRAINING == "DRAINING"
        assert StrategyLifecycleState.STOPPING == "STOPPING"
        assert StrategyLifecycleState.ERROR == "ERROR"

    def test_state_values_are_strings(self) -> None:
        """Test that all state values are strings."""
        for state in StrategyLifecycleState:
            assert isinstance(state.value, str)


class TestCanTransition:
    """Tests for can_transition function."""

    def test_valid_startup_flow(self) -> None:
        """Test valid startup flow transitions."""
        # STOPPED → STARTING
        assert can_transition(StrategyLifecycleState.STOPPED, StrategyLifecycleState.STARTING)

        # STARTING → RUNNING
        assert can_transition(StrategyLifecycleState.STARTING, StrategyLifecycleState.RUNNING)

    def test_valid_startup_failure(self) -> None:
        """Test valid startup failure transition."""
        # STARTING → ERROR
        assert can_transition(StrategyLifecycleState.STARTING, StrategyLifecycleState.ERROR)

    def test_valid_normal_operation(self) -> None:
        """Test valid normal operation transitions."""
        # RUNNING → PAUSED
        assert can_transition(StrategyLifecycleState.RUNNING, StrategyLifecycleState.PAUSED)

        # PAUSED → RUNNING
        assert can_transition(StrategyLifecycleState.PAUSED, StrategyLifecycleState.RUNNING)

    def test_valid_graceful_shutdown(self) -> None:
        """Test valid graceful shutdown transitions."""
        # RUNNING → DRAINING
        assert can_transition(StrategyLifecycleState.RUNNING, StrategyLifecycleState.DRAINING)

        # DRAINING → STOPPING
        assert can_transition(StrategyLifecycleState.DRAINING, StrategyLifecycleState.STOPPING)

        # STOPPING → STOPPED
        assert can_transition(StrategyLifecycleState.STOPPING, StrategyLifecycleState.STOPPED)

    def test_valid_error_handling(self) -> None:
        """Test valid error handling transitions."""
        # RUNNING → ERROR
        assert can_transition(StrategyLifecycleState.RUNNING, StrategyLifecycleState.ERROR)

        # PAUSED → ERROR
        assert can_transition(StrategyLifecycleState.PAUSED, StrategyLifecycleState.ERROR)

        # ERROR → STOPPED
        assert can_transition(StrategyLifecycleState.ERROR, StrategyLifecycleState.STOPPED)

    def test_valid_emergency_stop(self) -> None:
        """Test valid emergency stop transitions."""
        # RUNNING → STOPPING
        assert can_transition(StrategyLifecycleState.RUNNING, StrategyLifecycleState.STOPPING)

        # PAUSED → STOPPING
        assert can_transition(StrategyLifecycleState.PAUSED, StrategyLifecycleState.STOPPING)

        # DRAINING → STOPPING
        assert can_transition(StrategyLifecycleState.DRAINING, StrategyLifecycleState.STOPPING)

    def test_invalid_transitions(self) -> None:
        """Test invalid transitions."""
        # STOPPED → RUNNING (must go through STARTING)
        assert not can_transition(StrategyLifecycleState.STOPPED, StrategyLifecycleState.RUNNING)

        # RUNNING → STARTING (cannot go backwards)
        assert not can_transition(StrategyLifecycleState.RUNNING, StrategyLifecycleState.STARTING)

        # STOPPED → ERROR (must go through STARTING first)
        assert not can_transition(StrategyLifecycleState.STOPPED, StrategyLifecycleState.ERROR)

        # DRAINING → RUNNING (cannot resume from draining)
        assert not can_transition(StrategyLifecycleState.DRAINING, StrategyLifecycleState.RUNNING)

        # ERROR → RUNNING (must go through STOPPED first)
        assert not can_transition(StrategyLifecycleState.ERROR, StrategyLifecycleState.RUNNING)

    def test_idempotent_transitions(self) -> None:
        """Test that same state → same state is valid (idempotent)."""
        for state in StrategyLifecycleState:
            assert can_transition(state, state)


class TestTransitionStrategyState:
    """Tests for transition_strategy_state function."""

    def test_valid_transition_returns_new_state(self) -> None:
        """Test that valid transition returns new state."""
        new_state = transition_strategy_state(
            StrategyLifecycleState.STOPPED, StrategyLifecycleState.STARTING
        )
        assert new_state == StrategyLifecycleState.STARTING

    def test_invalid_transition_raises_error(self) -> None:
        """Test that invalid transition raises InvalidTransitionError."""
        with pytest.raises(InvalidTransitionError) as exc_info:
            transition_strategy_state(
                StrategyLifecycleState.STOPPED, StrategyLifecycleState.RUNNING
            )

        assert exc_info.value.from_state == StrategyLifecycleState.STOPPED
        assert exc_info.value.to_state == StrategyLifecycleState.RUNNING
        assert "not allowed by FSM" in str(exc_info.value)

    def test_invalid_transition_with_reason(self) -> None:
        """Test that invalid transition includes reason in error."""
        with pytest.raises(InvalidTransitionError) as exc_info:
            transition_strategy_state(
                StrategyLifecycleState.STOPPED,
                StrategyLifecycleState.RUNNING,
                reason="Test reason",
            )

        assert "Test reason" in str(exc_info.value)

    def test_idempotent_transition(self) -> None:
        """Test that same state → same state is idempotent."""
        for state in StrategyLifecycleState:
            result = transition_strategy_state(state, state)
            assert result == state

    def test_all_valid_transitions(self) -> None:
        """Test all valid transitions from proposal."""
        valid_transitions = [
            # Normal startup flow
            (StrategyLifecycleState.STOPPED, StrategyLifecycleState.STARTING),
            (StrategyLifecycleState.STARTING, StrategyLifecycleState.RUNNING),
            (StrategyLifecycleState.STARTING, StrategyLifecycleState.ERROR),
            # Normal operation
            (StrategyLifecycleState.RUNNING, StrategyLifecycleState.PAUSED),
            (StrategyLifecycleState.PAUSED, StrategyLifecycleState.RUNNING),
            # Graceful shutdown
            (StrategyLifecycleState.RUNNING, StrategyLifecycleState.DRAINING),
            (StrategyLifecycleState.DRAINING, StrategyLifecycleState.STOPPING),
            (StrategyLifecycleState.STOPPING, StrategyLifecycleState.STOPPED),
            # Error handling
            (StrategyLifecycleState.RUNNING, StrategyLifecycleState.ERROR),
            (StrategyLifecycleState.PAUSED, StrategyLifecycleState.ERROR),
            (StrategyLifecycleState.ERROR, StrategyLifecycleState.STOPPED),
            # Emergency stop
            (StrategyLifecycleState.RUNNING, StrategyLifecycleState.STOPPING),
            (StrategyLifecycleState.PAUSED, StrategyLifecycleState.STOPPING),
            (StrategyLifecycleState.DRAINING, StrategyLifecycleState.STOPPING),
        ]

        for from_state, to_state in valid_transitions:
            result = transition_strategy_state(from_state, to_state)
            assert result == to_state


class TestInvalidTransitionError:
    """Tests for InvalidTransitionError exception."""

    def test_error_message_includes_states(self) -> None:
        """Test that error message includes from and to states."""
        error = InvalidTransitionError(
            from_state=StrategyLifecycleState.STOPPED,
            to_state=StrategyLifecycleState.RUNNING,
        )

        assert "STOPPED" in str(error)
        assert "RUNNING" in str(error)
        assert "→" in str(error)

    def test_error_message_includes_reason(self) -> None:
        """Test that error message includes reason if provided."""
        error = InvalidTransitionError(
            from_state=StrategyLifecycleState.STOPPED,
            to_state=StrategyLifecycleState.RUNNING,
            reason="Test reason",
        )

        assert "Test reason" in str(error)


class TestIsTerminalState:
    """Tests for is_terminal_state function."""

    def test_stopped_is_terminal(self) -> None:
        """Test that STOPPED is a terminal state."""
        assert is_terminal_state(StrategyLifecycleState.STOPPED)

    def test_error_is_terminal(self) -> None:
        """Test that ERROR is a terminal state."""
        assert is_terminal_state(StrategyLifecycleState.ERROR)

    def test_non_terminal_states(self) -> None:
        """Test that non-terminal states return False."""
        assert not is_terminal_state(StrategyLifecycleState.STARTING)
        assert not is_terminal_state(StrategyLifecycleState.RUNNING)
        assert not is_terminal_state(StrategyLifecycleState.PAUSED)
        assert not is_terminal_state(StrategyLifecycleState.DRAINING)
        assert not is_terminal_state(StrategyLifecycleState.STOPPING)
