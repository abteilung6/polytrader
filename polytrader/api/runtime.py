"""Runtime state registry for API access to live services.

This module provides a minimal, explicit bridge between the running
platform services (orchestrator/position manager/event store) and the
control API for read-only observability endpoints.
"""

from dataclasses import dataclass

from polytrader.events.store import IEventStore
from polytrader.position_manager import IPositionManager
from polytrader.store import IMarketDataStore


@dataclass(frozen=True)
class RuntimeState:
    """References to live in-process services for API reads."""

    market_data_store: IMarketDataStore
    event_store: IEventStore
    position_manager: IPositionManager | None


_runtime_state: RuntimeState | None = None


def set_runtime_state(state: RuntimeState | None) -> None:
    """Set the global runtime state (used by API endpoints)."""

    global _runtime_state
    _runtime_state = state


def get_runtime_state() -> RuntimeState | None:
    """Get the current runtime state (or None if not initialized)."""

    return _runtime_state
