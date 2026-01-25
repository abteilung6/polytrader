"""Strategy lifecycle state models.

Per institutional best practices: Lifecycle is a state machine, not a boolean.
States enable safe restarts, drain, warm-up, and reproducible incident debugging.
"""

from __future__ import annotations

from enum import Enum


class StrategyLifecycleState(str, Enum):
    """Strategy lifecycle state machine.

    Per institutional best practices: Lifecycle is a state machine, not a boolean.
    States enable safe restarts, drain, warm-up, and reproducible incident debugging.

    State Flow:
        STOPPED → STARTING → RUNNING
        STARTING → ERROR (startup failure)
        RUNNING → PAUSED → RUNNING (resume)
        RUNNING → DRAINING → STOPPING → STOPPED (graceful shutdown)
        RUNNING → STOPPING → STOPPED (emergency stop)
        RUNNING → ERROR → STOPPED (error recovery)
        PAUSED → ERROR → STOPPED (error recovery)
    """

    STOPPED = "STOPPED"  # Not running (initial state)
    STARTING = "STARTING"  # Transitioning to RUNNING
    RUNNING = "RUNNING"  # Active and processing market data
    PAUSED = "PAUSED"  # Temporarily paused (can resume)
    DRAINING = "DRAINING"  # Gracefully shutting down (finish current work)
    STOPPING = "STOPPING"  # Transitioning to STOPPED
    ERROR = "ERROR"  # Error state (requires operator intervention)
