"""Shared fixtures for OMS unit tests."""

import pytest

from polytrader.oms.core import OMSCore


@pytest.fixture
def oms_core(
    bus,  # From root conftest
    order_store,  # From root conftest
    idempotency_store,  # From root conftest
) -> OMSCore:
    """Create OMSCore for testing."""
    return OMSCore(bus=bus, store=order_store, idempotency_store=idempotency_store)


@pytest.fixture
def sample_intent():
    """Create sample order intent for testing."""
    from tests.factories.events import create_order_intent_event

    return create_order_intent_event()
