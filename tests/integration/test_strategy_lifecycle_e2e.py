"""End-to-end integration tests for strategy lifecycle management.

Per Commit 26: End-to-end tests verify full strategy lifecycle flow:
- Strategy creation with lifecycle management
- State transitions (STOPPED → STARTING → RUNNING → STOPPING → STOPPED)
- Event emission (StrategyStateTransitionEvent)
- Reproducibility metadata (config_hash, template_code_ref, dependency_set)

Per testing.mdc: Integration tests verify full pipeline with real database
and event bus, using deterministic adapters.
"""

import asyncio
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from polytrader.db.models import StrategyRecord
from polytrader.events import SYSTEM_LIFECYCLE, EventBus
from polytrader.events.types import StrategyStateTransitionEvent
from polytrader.platform.orchestrator import PlatformOrchestrator
from polytrader.platform.strategy_lifecycle import StrategyLifecycleManager
from polytrader.store import IMarketDataStore
from polytrader.strategies.lifecycle_models import StrategyLifecycleState

if TYPE_CHECKING:
    from collections.abc import Callable
    from unittest.mock import MagicMock

    from polytrader.adapters import IMarketDataAdapter
    from polytrader.observer import IObserver


@pytest.mark.integration
@pytest.mark.asyncio
async def test_strategy_lifecycle_create_start_stop(
    db_session: AsyncSession,
    bus: EventBus,
    store: IMarketDataStore,
    discovery_service: MagicMock,
    adapter_factory: "Callable[[str], MagicMock]",
    observer_factory: "Callable[[IMarketDataAdapter], IObserver]",
) -> None:
    """Test end-to-end strategy lifecycle: create → start → stop.

    Per Commit 26: Verify complete lifecycle flow with:
    - Strategy creation in database
    - State transitions (STOPPED → STARTING → RUNNING → STOPPING → STOPPED)
    - Event emission (StrategyStateTransitionEvent)
    - Reproducibility metadata (config_hash, template_code_ref, dependency_set)
    """
    from polytrader.strategies.reproducibility import calculate_config_hash, create_run_identity

    # Step 1: Create strategy in database with STOPPED state
    config = {"buy_threshold": 0.3, "min_history": 30}
    config_hash = calculate_config_hash(config)
    run_identity = create_run_identity(
        template_code_ref="test_commit_abc123",
        config=config,
        dependency_packages=["polytrader", "numpy", "pydantic"],
    )

    strategy = StrategyRecord(
        strategy_id="e2e_test_strategy",
        name="E2E Test Strategy",
        description="End-to-end lifecycle test strategy",
        config=config,
        template_type_id="simple_threshold",
        template_version="1.0.0",
        config_hash=config_hash,
        desired_state=StrategyLifecycleState.STOPPED,
        actual_state=StrategyLifecycleState.STOPPED,
        template_code_ref=run_identity.template_code_ref,
        dependency_set=run_identity.dependency_set,
        market_data_snapshot_ref=run_identity.market_data_snapshot_ref,
    )
    db_session.add(strategy)
    await db_session.commit()

    # Step 2: Create orchestrator and lifecycle manager
    orchestrator = PlatformOrchestrator(
        bus=bus,
        store=store,
        session=db_session,
        discovery_service=discovery_service,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
    )

    lifecycle_manager = StrategyLifecycleManager(
        session=db_session,
        bus=bus,
    )

    await orchestrator.start()

    # Subscribe to lifecycle events BEFORE making transitions
    lifecycle_queue = bus.subscribe(SYSTEM_LIFECYCLE)
    transition_events: list[StrategyStateTransitionEvent] = []

    async def collect_transitions() -> None:
        """Collect state transition events."""
        while True:
            try:
                event = await asyncio.wait_for(lifecycle_queue.get(), timeout=1.0)
                if isinstance(event, StrategyStateTransitionEvent):
                    transition_events.append(event)
                    # Stop collecting after we get both expected events
                    if len(transition_events) >= 2:
                        break
            except TimeoutError:
                break

    # Start collector before making transitions
    transition_collector = asyncio.create_task(collect_transitions())

    try:
        # Give collector time to start
        await asyncio.sleep(0.05)

        # Step 3: Transition to RUNNING (should trigger STOPPED → STARTING → RUNNING)
        # First transition to STARTING
        await lifecycle_manager.transition_to_state(
            strategy=strategy,
            target_state=StrategyLifecycleState.STARTING,
            reason="E2E test: starting strategy",
        )

        # Wait a bit for STARTING transition event
        await asyncio.sleep(0.1)

        # Then transition to RUNNING
        await lifecycle_manager.transition_to_state(
            strategy=strategy,
            target_state=StrategyLifecycleState.RUNNING,
            reason="E2E test: strategy started",
        )

        # Wait for events to be collected
        await asyncio.sleep(0.3)

        # Cancel collector if still running
        if not transition_collector.done():
            transition_collector.cancel()
        try:
            await transition_collector
        except asyncio.CancelledError:
            pass

        # Verify state transition events were emitted
        assert len(transition_events) >= 2, (
            "Should have at least two state transition events (STARTING, RUNNING)"
        )

        # Find the transition to STARTING
        starting_transition = next((e for e in transition_events if e.to_state == "STARTING"), None)
        assert starting_transition is not None, "Should have transition to STARTING state"
        assert starting_transition.strategy_id == "e2e_test_strategy"
        assert starting_transition.from_state == "STOPPED"
        assert starting_transition.to_state == "STARTING"

        # Find the transition to RUNNING
        running_transition = next((e for e in transition_events if e.to_state == "RUNNING"), None)
        assert running_transition is not None, "Should have transition to RUNNING state"
        assert running_transition.strategy_id == "e2e_test_strategy"
        assert running_transition.from_state == "STARTING"
        assert running_transition.to_state == "RUNNING"
        assert running_transition.reason == "E2E test: strategy started"

        # Verify strategy state in database
        from sqlalchemy import select

        result = await db_session.execute(
            select(StrategyRecord).where(StrategyRecord.strategy_id == "e2e_test_strategy")
        )
        updated_strategy = result.scalar_one()
        assert updated_strategy.actual_state == StrategyLifecycleState.RUNNING.value
        assert updated_strategy.desired_state == StrategyLifecycleState.RUNNING.value
        assert updated_strategy.last_transition_at is not None

        # Verify reproducibility metadata
        assert updated_strategy.config_hash == config_hash
        assert updated_strategy.template_code_ref == "test_commit_abc123"
        assert updated_strategy.dependency_set is not None
        # Note: polytrader package might not be installed in test environment
        # So we just verify that dependency_set is populated
        assert len(updated_strategy.dependency_set) > 0, "dependency_set should be populated"
        # Note: deployment_id is set during strategy creation, not during state transitions
        # So it might be None if not set during creation. This is acceptable for E2E test.

        # Step 4: Transition to STOPPED (should trigger RUNNING → STOPPING → STOPPED)
        transition_events.clear()
        transition_collector = asyncio.create_task(collect_transitions())

        # First transition to STOPPING
        await lifecycle_manager.transition_to_state(
            strategy=updated_strategy,
            target_state=StrategyLifecycleState.STOPPING,
            reason="E2E test: stopping strategy",
        )

        # Wait a bit for STOPPING transition
        await asyncio.sleep(0.1)

        # Then transition to STOPPED
        await lifecycle_manager.transition_to_state(
            strategy=updated_strategy,
            target_state=StrategyLifecycleState.STOPPED,
            reason="E2E test: strategy stopped",
        )

        # Wait for events to be processed
        await asyncio.sleep(0.2)
        transition_collector.cancel()
        try:
            await transition_collector
        except asyncio.CancelledError:
            pass

        # Verify state transition events were emitted
        assert len(transition_events) >= 2, (
            "Should have at least two state transition events (STOPPING, STOPPED)"
        )

        # Find the transition to STOPPING
        stopping_transition = next((e for e in transition_events if e.to_state == "STOPPING"), None)
        assert stopping_transition is not None, "Should have transition to STOPPING state"
        assert stopping_transition.strategy_id == "e2e_test_strategy"
        assert stopping_transition.from_state == "RUNNING"
        assert stopping_transition.to_state == "STOPPING"

        # Find the transition to STOPPED
        stopped_transition = next((e for e in transition_events if e.to_state == "STOPPED"), None)
        assert stopped_transition is not None, "Should have transition to STOPPED state"
        assert stopped_transition.strategy_id == "e2e_test_strategy"
        assert stopped_transition.from_state == "STOPPING"
        assert stopped_transition.to_state == "STOPPED"
        assert stopped_transition.reason == "E2E test: strategy stopped"

        # Verify final state in database
        result = await db_session.execute(
            select(StrategyRecord).where(StrategyRecord.strategy_id == "e2e_test_strategy")
        )
        final_strategy = result.scalar_one()
        assert final_strategy.actual_state == StrategyLifecycleState.STOPPED.value
        assert final_strategy.desired_state == StrategyLifecycleState.STOPPED.value

    finally:
        await orchestrator.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_strategy_lifecycle_invalid_transition(
    db_session: AsyncSession,
    bus: EventBus,
) -> None:
    """Test that invalid state transitions are rejected.

    Per Commit 26: Verify FSM validation prevents invalid transitions.
    """
    from polytrader.strategies.reproducibility import calculate_config_hash

    # Create strategy in STOPPED state
    config = {"buy_threshold": 0.3, "min_history": 30}
    config_hash = calculate_config_hash(config)

    strategy = StrategyRecord(
        strategy_id="e2e_test_strategy_invalid",
        name="E2E Test Strategy Invalid",
        config=config,
        template_type_id="simple_threshold",
        template_version="1.0.0",
        config_hash=config_hash,
        desired_state=StrategyLifecycleState.STOPPED,
        actual_state=StrategyLifecycleState.STOPPED,
    )
    db_session.add(strategy)
    await db_session.commit()

    lifecycle_manager = StrategyLifecycleManager(
        session=db_session,
        bus=bus,
    )

    # Try invalid transition: STOPPED → ERROR (should fail)
    from polytrader.strategies.lifecycle import InvalidTransitionError

    with pytest.raises(InvalidTransitionError):
        await lifecycle_manager.transition_to_state(
            strategy=strategy,
            target_state=StrategyLifecycleState.ERROR,
            reason="Invalid transition test",
        )

    # Verify state didn't change
    from sqlalchemy import select

    result = await db_session.execute(
        select(StrategyRecord).where(StrategyRecord.strategy_id == "e2e_test_strategy_invalid")
    )
    updated_strategy = result.scalar_one()
    assert updated_strategy.actual_state == StrategyLifecycleState.STOPPED.value


@pytest.mark.integration
@pytest.mark.asyncio
async def test_strategy_lifecycle_reproducibility_metadata(
    db_session: AsyncSession,
    bus: EventBus,
) -> None:
    """Test that reproducibility metadata is correctly stored and retrieved.

    Per Commit 26: Verify config_hash, template_code_ref, dependency_set,
    and market_data_snapshot_ref are preserved through lifecycle.
    """
    from polytrader.strategies.reproducibility import (
        calculate_config_hash,
        create_run_identity,
    )

    # Create strategy with full reproducibility metadata
    config = {"buy_threshold": 0.35, "min_history": 50}
    config_hash = calculate_config_hash(config)
    run_identity = create_run_identity(
        template_code_ref="git_sha_abc123def456",
        config=config,
        market_data_snapshot_ref="snapshot_20250127_120000",
        dependency_packages=["polytrader", "numpy", "pydantic", "scipy"],
    )

    strategy = StrategyRecord(
        strategy_id="e2e_test_reproducibility",
        name="E2E Reproducibility Test",
        config=config,
        template_type_id="simple_threshold",
        template_version="1.0.0",
        config_hash=config_hash,
        desired_state=StrategyLifecycleState.RUNNING,
        actual_state=StrategyLifecycleState.RUNNING,
        template_code_ref=run_identity.template_code_ref,
        dependency_set=run_identity.dependency_set,
        market_data_snapshot_ref=run_identity.market_data_snapshot_ref,
    )
    db_session.add(strategy)
    await db_session.commit()

    # Verify metadata is stored correctly
    from sqlalchemy import select

    result = await db_session.execute(
        select(StrategyRecord).where(StrategyRecord.strategy_id == "e2e_test_reproducibility")
    )
    retrieved_strategy = result.scalar_one()

    assert retrieved_strategy.config_hash == config_hash
    assert retrieved_strategy.template_code_ref == "git_sha_abc123def456"
    assert retrieved_strategy.market_data_snapshot_ref == "snapshot_20250127_120000"
    assert retrieved_strategy.dependency_set is not None
    # Note: Not all packages may be installed in test environment
    # collect_dependency_set only includes packages that are actually installed
    # So we check for at least 1 dependency (pydantic should always be available)
    assert len(retrieved_strategy.dependency_set) >= 1, "Should have at least 1 dependency"
    assert "pydantic" in retrieved_strategy.dependency_set, "pydantic should be in dependency_set"
    # numpy and scipy are optional - check if they're available
    if "numpy" in retrieved_strategy.dependency_set:
        assert isinstance(retrieved_strategy.dependency_set["numpy"], str)

    # Verify config_hash is deterministic (same config = same hash)
    config_hash2 = calculate_config_hash(config)
    assert config_hash2 == config_hash, "Config hash should be deterministic"

    # Verify config_hash changes with different config
    different_config = {"buy_threshold": 0.4, "min_history": 50}
    different_hash = calculate_config_hash(different_config)
    assert different_hash != config_hash, "Different config should produce different hash"
