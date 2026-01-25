"""Pytest configuration and shared fixtures.

This file provides shared fixtures and utilities for all tests.
"""

import pytest

from polytrader.db.models import StrategyRecord
from polytrader.events.bus import EventBus
from polytrader.oms.idempotency import IdempotencyStore
from polytrader.oms.store import InMemoryOrderStore
from polytrader.strategies.lifecycle_models import StrategyLifecycleState


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


def create_strategy_record(
    strategy_id: str,
    name: str,
    config: dict,
    enabled: bool = True,
    template_type_id: str = "simple_threshold",
    template_version: str = "1.0.0",
    config_hash: str | None = None,
) -> StrategyRecord:
    """Helper function to create StrategyRecord with required fields.

    Args:
        strategy_id: Strategy identifier
        name: Strategy name
        config: Strategy configuration
        enabled: Whether strategy should be enabled (maps to RUNNING/STOPPED state)
        template_type_id: Template type identifier
        template_version: Template version
        config_hash: Config hash (auto-generated if None)

    Returns:
        StrategyRecord instance with all required fields
    """
    if config_hash is None:
        # Generate a simple hash from strategy_id for testing
        config_hash = f"hash_{strategy_id}"

    desired_state = StrategyLifecycleState.RUNNING if enabled else StrategyLifecycleState.STOPPED

    return StrategyRecord(
        strategy_id=strategy_id,
        name=name,
        config=config,
        template_type_id=template_type_id,
        template_version=template_version,
        config_hash=config_hash,
        desired_state=desired_state,
        actual_state=desired_state,
    )
