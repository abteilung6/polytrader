"""Shared fixtures for all tests.

Per unit_testing_techinical.mdc §5: Fixtures with function scope by default.
"""

from unittest.mock import MagicMock

import pytest

from polytrader.events.bus import EventBus
from polytrader.events.types import OrderIntentEvent
from polytrader.oms.core import OMSCore
from polytrader.oms.idempotency import IdempotencyStore
from polytrader.oms.store import InMemoryOrderStore


# Core infrastructure fixtures
@pytest.fixture
def bus() -> EventBus:
    """Create EventBus for testing."""
    return EventBus()


@pytest.fixture
def order_store(bus: EventBus) -> InMemoryOrderStore:
    """Create InMemoryOrderStore for testing."""
    return InMemoryOrderStore(bus)


@pytest.fixture
def idempotency_store() -> IdempotencyStore:
    """Create IdempotencyStore for testing."""
    return IdempotencyStore()


@pytest.fixture
def oms_core(
    bus: EventBus, order_store: InMemoryOrderStore, idempotency_store: IdempotencyStore
) -> OMSCore:
    """Create OMSCore for testing."""
    return OMSCore(bus=bus, store=order_store, idempotency_store=idempotency_store)


@pytest.fixture
def sample_intent() -> OrderIntentEvent:
    """Create sample order intent for testing."""
    from tests.factories.events import create_order_intent_event

    return create_order_intent_event()


# Clock fixtures (deterministic)
@pytest.fixture
def mock_clock() -> MagicMock:
    """Create mock clock for deterministic time-based tests."""
    clock = MagicMock()
    clock.monotonic.return_value = 1000.0  # Fixed base time
    return clock


@pytest.fixture
def fixed_clock():
    """Create FixedClock for deterministic time-based tests."""
    from tests.factories.clocks import create_fixed_clock

    return create_fixed_clock(base_monotonic=1000.0)
