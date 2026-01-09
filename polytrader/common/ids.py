"""ID generation utilities for events and correlation tracking."""

import uuid

# Global run_id (set once at process start)
_run_id: str | None = None


def get_run_id() -> str:
    """Get or generate the process run_id (singleton per process).

    The run_id is generated once when first called and remains constant
    for the lifetime of the process. This allows correlating all events
    from a single process run.

    Returns:
        A UUID string representing the process run ID.
    """
    global _run_id
    if _run_id is None:
        _run_id = str(uuid.uuid4())
    return _run_id


def generate_correlation_id() -> str:
    """Generate a new correlation ID for tracing decision → actions.

    Correlation IDs are used to trace a single decision through the
    trading pipeline: from market data → signal → intent → order → fill.
    Each decision gets a unique correlation_id that propagates through
    all related events.

    Returns:
        A UUID string representing the correlation ID.
    """
    return str(uuid.uuid4())


def reset_run_id() -> None:
    """Reset run_id (for testing only).

    This function should only be used in tests to reset the global
    run_id state between test runs.
    """
    global _run_id
    _run_id = None
