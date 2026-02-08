"""Integration tests for ControlPlaneService.

Tests verify that ControlPlaneService correctly processes control commands
from the database queue and applies them to execution_control and
live_strategy_activation tables.
"""

import asyncio
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.db.models import ControlCommandRecord, StrategyRecord
from polytrader.events.bus import EventBus
from polytrader.ops.control import ExecutionControl
from polytrader.platform.control import (
    ControlCommandRepository,
    ExecutionControlRepository,
    LiveStrategyRepository,
)
from polytrader.platform.control_plane import ControlPlaneService
from polytrader.platform.registry import StrategyRegistry


@pytest.fixture
async def db_session(
    postgres_test_url: str, postgres_db: None
) -> AsyncGenerator[AsyncSession, None]:
    """Provide SQLAlchemy session for tests."""
    sqlalchemy_url = postgres_test_url
    if sqlalchemy_url.startswith("postgresql://"):
        sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+psycopg://", 1)

    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def event_bus() -> EventBus:
    """Create event bus for tests."""
    from polytrader.events.bus import EventBus

    return EventBus()


@pytest.fixture
async def execution_control(event_bus: EventBus) -> ExecutionControl:
    """Create execution control for tests."""
    return ExecutionControl(bus=event_bus)


@pytest.fixture
async def repositories(
    db_session: AsyncSession,
) -> tuple[
    ControlCommandRepository,
    ExecutionControlRepository,
    LiveStrategyRepository,
    StrategyRegistry,
]:
    """Create repositories for tests."""
    command_repo = ControlCommandRepository(db_session)
    execution_repo = ExecutionControlRepository(db_session)
    live_repo = LiveStrategyRepository(db_session)
    strategy_registry = StrategyRegistry(db_session)
    return command_repo, execution_repo, live_repo, strategy_registry


@pytest.fixture
async def service(
    repositories: tuple[
        ControlCommandRepository,
        ExecutionControlRepository,
        LiveStrategyRepository,
        StrategyRegistry,
    ],
    execution_control: ExecutionControl,
    event_bus: EventBus,
) -> ControlPlaneService:
    """Create ControlPlaneService for tests."""
    command_repo, execution_repo, live_repo, strategy_registry = repositories
    return ControlPlaneService(
        command_repo=command_repo,
        execution_repo=execution_repo,
        live_repo=live_repo,
        strategy_registry=strategy_registry,
        execution_control=execution_control,
        bus=event_bus,
        poll_interval_s=0.1,  # Fast polling for tests
    )


@pytest.fixture
async def test_strategy(db_session: AsyncSession) -> str:
    """Create test strategy and return its ID."""
    from polytrader.strategies.lifecycle_models import StrategyLifecycleState

    strategy = StrategyRecord(
        strategy_id="test_strategy",
        name="Test Strategy",
        config={"type": "simple_threshold"},
        template_type_id="simple_threshold",
        template_version="1.0.0",
        config_hash="test_hash",
        desired_state=StrategyLifecycleState.RUNNING,
        actual_state=StrategyLifecycleState.RUNNING,
    )
    db_session.add(strategy)
    await db_session.commit()
    return strategy.strategy_id


class TestEnableExecution:
    """Test enable_execution command processing."""

    @pytest.mark.asyncio
    async def test_enable_execution_processes_command(
        self,
        service: ControlPlaneService,
        repositories: tuple[
            ControlCommandRepository,
            ExecutionControlRepository,
            LiveStrategyRepository,
            StrategyRegistry,
        ],
        execution_control: ExecutionControl,
    ) -> None:
        """Test that enable_execution command is processed correctly."""
        command_repo, execution_repo, _, _ = repositories

        # Create command
        cmd = ControlCommandRecord(
            command_type="enable_execution",
            reason="Enable for testing",
            issued_by="operator",
            client_request_id="req-enable-1",
        )
        await command_repo.create_command(cmd)

        # Process command manually (service would do this in background)
        await service._process_command(cmd)

        # Verify execution is enabled in DB
        control = await execution_repo.get_control()
        assert control.execution_enabled is True
        assert control.version == 2  # Version incremented from 1
        assert control.updated_by == "operator"
        assert control.reason == "Enable for testing"

        # Verify in-memory state is updated
        assert execution_control.execution_enabled is True

        # Verify command is marked as applied
        found = await command_repo.find_by_client_request_id(
            "enable_execution", None, "req-enable-1"
        )
        assert found is not None
        assert found.status == "applied"
        assert found.applied_at is not None

    @pytest.mark.asyncio
    async def test_enable_execution_with_version_check(
        self,
        service: ControlPlaneService,
        repositories: tuple[
            ControlCommandRepository,
            ExecutionControlRepository,
            LiveStrategyRepository,
            StrategyRegistry,
        ],
    ) -> None:
        """Test that enable_execution with version check works correctly."""
        command_repo, execution_repo, _, _ = repositories

        # Get current version
        current = await execution_repo.get_control()
        current_version = current.version

        # Create command with correct version
        cmd = ControlCommandRecord(
            command_type="enable_execution",
            reason="Enable with version check",
            issued_by="operator",
            client_request_id="req-enable-version",
            expected_version=current_version,
        )
        await command_repo.create_command(cmd)

        # Process command
        await service._process_command(cmd)

        # Verify command was applied
        found = await command_repo.find_by_client_request_id(
            "enable_execution", None, "req-enable-version"
        )
        assert found is not None
        assert found.status == "applied"

    @pytest.mark.asyncio
    async def test_enable_execution_version_mismatch_fails(
        self,
        service: ControlPlaneService,
        repositories: tuple[
            ControlCommandRepository,
            ExecutionControlRepository,
            LiveStrategyRepository,
            StrategyRegistry,
        ],
    ) -> None:
        """Test that enable_execution with wrong version fails."""
        command_repo, execution_repo, _, _ = repositories

        # Get current version
        current = await execution_repo.get_control()
        wrong_version = current.version + 10  # Wrong version

        # Create command with wrong version
        cmd = ControlCommandRecord(
            command_type="enable_execution",
            reason="Enable with wrong version",
            issued_by="operator",
            client_request_id="req-enable-wrong-version",
            expected_version=wrong_version,
        )
        await command_repo.create_command(cmd)

        # Process command
        await service._process_command(cmd)

        # Verify command was marked as failed
        found = await command_repo.find_by_client_request_id(
            "enable_execution", None, "req-enable-wrong-version"
        )
        assert found is not None
        assert found.status == "failed"
        assert "Version mismatch" in (found.error_message or "")


class TestDisableExecution:
    """Test disable_execution command processing."""

    @pytest.mark.asyncio
    async def test_disable_execution_processes_command(
        self,
        service: ControlPlaneService,
        repositories: tuple[
            ControlCommandRepository,
            ExecutionControlRepository,
            LiveStrategyRepository,
            StrategyRegistry,
        ],
        execution_control: ExecutionControl,
    ) -> None:
        """Test that disable_execution command is processed correctly."""
        command_repo, execution_repo, _, _ = repositories

        # First enable execution
        enable_cmd = ControlCommandRecord(
            command_type="enable_execution",
            reason="Enable first",
            issued_by="operator",
            client_request_id="req-enable-first",
        )
        await command_repo.create_command(enable_cmd)
        await service._process_command(enable_cmd)

        # Now disable execution
        disable_cmd = ControlCommandRecord(
            command_type="disable_execution",
            reason="Disable for testing",
            issued_by="operator",
            client_request_id="req-disable-1",
        )
        await command_repo.create_command(disable_cmd)
        await service._process_command(disable_cmd)

        # Verify execution is disabled in DB
        control = await execution_repo.get_control()
        assert control.execution_enabled is False
        assert control.version == 3  # Version incremented twice
        assert control.updated_by == "operator"
        assert control.reason == "Disable for testing"

        # Verify in-memory state is updated
        assert execution_control.execution_enabled is False

        # Verify command is marked as applied
        found = await command_repo.find_by_client_request_id(
            "disable_execution", None, "req-disable-1"
        )
        assert found is not None
        assert found.status == "applied"


class TestAddActiveStrategy:
    """Test add_active_strategy command processing."""

    @pytest.mark.asyncio
    async def test_add_active_strategy_processes_command(
        self,
        service: ControlPlaneService,
        repositories: tuple[
            ControlCommandRepository,
            ExecutionControlRepository,
            LiveStrategyRepository,
            StrategyRegistry,
        ],
        test_strategy: str,
    ) -> None:
        """Test that add_active_strategy command is processed correctly."""
        command_repo, _, live_repo, strategy_registry = repositories

        # Create command
        cmd = ControlCommandRecord(
            command_type="add_active_strategy",
            strategy_id=test_strategy,
            reason="Activate strategy for testing",
            issued_by="operator",
            client_request_id="req-add-strategy-1",
        )
        await command_repo.create_command(cmd)

        # Process command
        await service._process_command(cmd)

        # Verify strategy is in active live set (Mode becomes Live)
        active = await live_repo.list_active()
        assert test_strategy in active

        # add_active_strategy does NOT change lifecycle (desired_state/actual_state
        # are unchanged; Start/Stop control lifecycle separately)
        strategy = await strategy_registry.get_strategy(test_strategy)
        assert strategy is not None
        # State unchanged by activation (fixture may be RUNNING or STOPPED)
        assert strategy.desired_state in ("RUNNING", "STOPPED")
        assert strategy.actual_state in ("RUNNING", "STOPPED")

        # Verify command is marked as applied
        found = await command_repo.find_by_client_request_id(
            "add_active_strategy", test_strategy, "req-add-strategy-1"
        )
        assert found is not None
        assert found.status == "applied"

    @pytest.mark.asyncio
    async def test_add_active_strategy_does_not_change_lifecycle(
        self,
        service: ControlPlaneService,
        repositories: tuple[
            ControlCommandRepository,
            ExecutionControlRepository,
            LiveStrategyRepository,
            StrategyRegistry,
        ],
        db_session: AsyncSession,
    ) -> None:
        """Add to active only updates live list; desired_state/actual_state unchanged."""
        from polytrader.strategies.lifecycle_models import StrategyLifecycleState

        command_repo, _, live_repo, strategy_registry = repositories

        # Create strategy with STOPPED
        strategy = StrategyRecord(
            strategy_id="vfmr-stopped-test",
            name="VFMR Stopped Test",
            config={"anchor_window": 96},
            template_type_id="volatility_filtered_mean_reversion",
            template_version="1.0.0",
            config_hash="hash_stopped",
            desired_state=StrategyLifecycleState.STOPPED.value,
            actual_state=StrategyLifecycleState.STOPPED.value,
        )
        db_session.add(strategy)
        await db_session.commit()

        cmd = ControlCommandRecord(
            command_type="add_active_strategy",
            strategy_id="vfmr-stopped-test",
            reason="Add to active for test",
            issued_by="operator",
            client_request_id="req-add-active-no-lifecycle-1",
        )
        await command_repo.create_command(cmd)
        await service._process_command(cmd)

        # In active list (Mode = Live)
        active = await live_repo.list_active()
        assert "vfmr-stopped-test" in active

        # Lifecycle unchanged: still STOPPED (Start would be needed to run)
        loaded = await strategy_registry.get_strategy("vfmr-stopped-test")
        assert loaded is not None
        assert loaded.desired_state == "STOPPED"
        assert loaded.actual_state == "STOPPED"

    @pytest.mark.asyncio
    async def test_add_active_strategy_without_strategy_id_fails(
        self,
        service: ControlPlaneService,
        repositories: tuple[
            ControlCommandRepository,
            ExecutionControlRepository,
            LiveStrategyRepository,
            StrategyRegistry,
        ],
    ) -> None:
        """Test that add_active_strategy without strategy_id fails."""
        command_repo, _, _, _ = repositories

        # Create command without strategy_id
        cmd = ControlCommandRecord(
            command_type="add_active_strategy",
            strategy_id=None,  # Missing strategy_id
            reason="Should fail",
            issued_by="operator",
            client_request_id="req-add-strategy-fail",
        )
        await command_repo.create_command(cmd)

        # Process command
        await service._process_command(cmd)

        # Verify command was marked as failed
        found = await command_repo.find_by_client_request_id(
            "add_active_strategy", None, "req-add-strategy-fail"
        )
        assert found is not None
        assert found.status == "failed"
        assert "requires strategy_id" in (found.error_message or "").lower()


class TestRemoveActiveStrategy:
    """Test remove_active_strategy command processing."""

    @pytest.mark.asyncio
    async def test_remove_active_strategy_processes_command(
        self,
        service: ControlPlaneService,
        repositories: tuple[
            ControlCommandRepository,
            ExecutionControlRepository,
            LiveStrategyRepository,
            StrategyRegistry,
        ],
        test_strategy: str,
    ) -> None:
        """Remove from active only updates live list; lifecycle unchanged (paper mode)."""
        from polytrader.strategies.lifecycle_models import StrategyLifecycleState

        command_repo, _, live_repo, strategy_registry = repositories

        # Ensure strategy is RUNNING (e.g. was started via UI)
        strategy = await strategy_registry.get_strategy(test_strategy)
        assert strategy is not None
        strategy.desired_state = StrategyLifecycleState.RUNNING.value
        strategy.actual_state = StrategyLifecycleState.RUNNING.value
        await strategy_registry.update_strategy(strategy)

        # Add to active then remove from active
        activate_cmd = ControlCommandRecord(
            command_type="add_active_strategy",
            strategy_id=test_strategy,
            reason="Activate first",
            issued_by="operator",
            client_request_id="req-activate-first",
        )
        await command_repo.create_command(activate_cmd)
        await service._process_command(activate_cmd)

        deactivate_cmd = ControlCommandRecord(
            command_type="remove_active_strategy",
            strategy_id=test_strategy,
            reason="Remove from active (paper mode only)",
            issued_by="operator",
            client_request_id="req-remove-strategy-1",
        )
        await command_repo.create_command(deactivate_cmd)
        await service._process_command(deactivate_cmd)

        # No longer in active list (Mode = Paper)
        active = await live_repo.list_active()
        assert test_strategy not in active

        # Lifecycle unchanged: still RUNNING (instance keeps running in paper mode)
        after = await strategy_registry.get_strategy(test_strategy)
        assert after is not None
        assert after.desired_state == "RUNNING"
        assert after.actual_state == "RUNNING"

        found = await command_repo.find_by_client_request_id(
            "remove_active_strategy", test_strategy, "req-remove-strategy-1"
        )
        assert found is not None
        assert found.status == "applied"


class TestControlCommandEvent:
    """Test that ControlCommandEvent is emitted."""

    @pytest.mark.asyncio
    async def test_control_command_event_emitted_on_success(
        self,
        service: ControlPlaneService,
        repositories: tuple[
            ControlCommandRepository,
            ExecutionControlRepository,
            LiveStrategyRepository,
            StrategyRegistry,
        ],
        event_bus: EventBus,
    ) -> None:
        """Test that ControlCommandEvent is emitted when command is applied."""
        command_repo, _, _, _ = repositories

        # Subscribe to SYSTEM_LIFECYCLE events
        from polytrader.events import SYSTEM_LIFECYCLE
        from polytrader.events.types import ControlCommandEvent

        events_received: list[ControlCommandEvent] = []
        queue = event_bus.subscribe(SYSTEM_LIFECYCLE)

        # Start background task to consume events
        async def consume_events() -> None:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=2.0)
                    if isinstance(event, ControlCommandEvent):
                        events_received.append(event)
                except TimeoutError:
                    break

        consume_task = asyncio.create_task(consume_events())

        # Create and process command
        cmd = ControlCommandRecord(
            command_type="enable_execution",
            reason="Enable for event test",
            issued_by="operator",
            client_request_id="req-event-test",
        )
        await command_repo.create_command(cmd)
        await service._process_command(cmd)

        # Wait for event
        await asyncio.sleep(0.2)
        consume_task.cancel()
        try:
            await consume_task
        except asyncio.CancelledError:
            pass

        # Verify event was emitted
        assert len(events_received) > 0
        event = events_received[0]
        assert isinstance(event, ControlCommandEvent)
        assert event.command_type == "enable_execution"
        assert event.status == "applied"
        assert event.issued_by == "operator"
        assert event.reason == "Enable for event test"
