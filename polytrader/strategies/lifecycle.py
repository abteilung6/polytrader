"""Strategy lifecycle state machine (pure FSM functions).

Per flows.mdc: State transitions must be validated and deterministic.
This module provides pure, deterministic functions for strategy lifecycle transitions.
All transitions are validated to ensure they follow the legal state machine.
"""

from __future__ import annotations

from polytrader.strategies.lifecycle_models import StrategyLifecycleState


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted.

    Attributes:
        from_state: Current strategy lifecycle state
        to_state: Attempted new state
        reason: Optional reason for the invalid transition
    """

    def __init__(
        self,
        from_state: StrategyLifecycleState,
        to_state: StrategyLifecycleState,
        reason: str | None = None,
    ) -> None:
        """Initialize InvalidTransitionError.

        Args:
            from_state: Current strategy lifecycle state
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


def _get_valid_transitions() -> set[tuple[StrategyLifecycleState, StrategyLifecycleState]]:
    """Get set of valid state transitions.

    Returns:
        Set of (from_state, to_state) tuples representing valid transitions

    Per proposal §7.2: Valid transitions include:
    - Normal startup flow: STOPPED → STARTING → RUNNING
    - Startup failure: STARTING → ERROR
    - Normal operation: RUNNING ↔ PAUSED
    - Graceful shutdown: RUNNING → DRAINING → STOPPING → STOPPED
    - Error handling: RUNNING/PAUSED → ERROR → STOPPED
    - Emergency stop: RUNNING/PAUSED/DRAINING → STOPPING → STOPPED
    """
    return {
        # Normal startup flow
        (StrategyLifecycleState.STOPPED, StrategyLifecycleState.STARTING),
        (StrategyLifecycleState.STARTING, StrategyLifecycleState.RUNNING),
        (StrategyLifecycleState.STARTING, StrategyLifecycleState.ERROR),  # Startup failure
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
        (StrategyLifecycleState.ERROR, StrategyLifecycleState.STOPPED),  # Manual recovery
        # Emergency stop
        (StrategyLifecycleState.RUNNING, StrategyLifecycleState.STOPPING),
        (StrategyLifecycleState.PAUSED, StrategyLifecycleState.STOPPING),
        (StrategyLifecycleState.DRAINING, StrategyLifecycleState.STOPPING),
    }


def can_transition(
    from_state: StrategyLifecycleState,
    to_state: StrategyLifecycleState,
) -> bool:
    """Check if state transition is valid.

    Args:
        from_state: Current strategy lifecycle state
        to_state: Target state to transition to

    Returns:
        True if transition is valid, False otherwise

    Note:
        This is a pure function (no side effects, deterministic).
        Same state → same state is considered valid (idempotent).
    """
    # Same state → same state is always valid (idempotent)
    if from_state == to_state:
        return True

    return (from_state, to_state) in _get_valid_transitions()


def transition_strategy_state(
    current_state: StrategyLifecycleState,
    new_state: StrategyLifecycleState,
    reason: str | None = None,
) -> StrategyLifecycleState:
    """Transition strategy to new state (pure function).

    Per flows.mdc: All state transitions must be validated.
    This function returns the new state if transition is valid.

    Args:
        current_state: Current lifecycle state
        new_state: Target state
        reason: Optional reason for transition

    Returns:
        New state (if transition valid)

    Raises:
        InvalidTransitionError: If transition is not valid

    Note:
        This is a pure function (no side effects, deterministic).
        Same state → same state is idempotent (returns same state).
    """
    # Same state → same state is idempotent
    if current_state == new_state:
        return new_state

    # Check if transition is valid
    if not can_transition(current_state, new_state):
        raise InvalidTransitionError(
            from_state=current_state,
            to_state=new_state,
            reason=reason or "Transition not allowed by FSM",
        )

    return new_state


def is_terminal_state(state: StrategyLifecycleState) -> bool:
    """Check if state is terminal (cannot transition to another state).

    Args:
        state: Strategy lifecycle state to check

    Returns:
        True if state is terminal, False otherwise

    Note:
        Terminal states: STOPPED, ERROR
        Non-terminal states can transition to other states.
    """
    return state in (StrategyLifecycleState.STOPPED, StrategyLifecycleState.ERROR)
