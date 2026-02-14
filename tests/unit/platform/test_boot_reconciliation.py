"""Unit tests for boot reconciliation in ControlPlaneService.

Per investigation (2026-02-08): A state divergence bug was discovered where
the DB had execution_enabled=true from a previous session, but the in-memory
ExecutionControl defaulted to False on restart. The UI read from the DB
(showing ON) while the runtime rejected all orders (showing OFF).

Root cause: ControlPlaneService.start() did not reconcile DB state on boot.

These tests verify that:
1. On boot, DB execution state is reset to False (safety default)
2. In-memory state remains False regardless of DB state
3. Boot reconciliation is fail-safe (errors don't enable execution)
4. If DB was already disabled, no unnecessary update occurs

Per flows.mdc §2: "Default safe state is no trading."
Per testing.mdc: Unit tests must be deterministic, fast, and isolated.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from polytrader.events.bus import EventBus
from polytrader.ops.control import ExecutionControl
from polytrader.platform.control import (
    ControlCommandRepository,
    ExecutionControlRepository,
    LiveStrategyRepository,
)
from polytrader.platform.control_plane import ControlPlaneService
from polytrader.platform.registry import StrategyRegistry

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def bus() -> EventBus:
    """Create an EventBus for testing."""
    return EventBus()


@pytest.fixture
def execution_control(bus: EventBus) -> ExecutionControl:
    """Create ExecutionControl with default state (disabled)."""
    return ExecutionControl(bus=bus)


def _make_mock_db_record(
    execution_enabled: bool = False,
    version: int = 1,
    updated_by: str = "system",
    reason: str = "Initial state",
) -> MagicMock:
    """Create a mock ExecutionControlRecord."""
    record = MagicMock()
    record.execution_enabled = execution_enabled
    record.version = version
    record.updated_by = updated_by
    record.reason = reason
    record.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    return record


@pytest.fixture
def mock_execution_repo() -> MagicMock:
    """Create a mock ExecutionControlRepository."""
    repo = MagicMock(spec=ExecutionControlRepository)
    repo.get_control = AsyncMock(return_value=_make_mock_db_record())
    repo.update_control = AsyncMock(return_value=_make_mock_db_record())
    return repo


@pytest.fixture
def mock_command_repo() -> MagicMock:
    """Create a mock ControlCommandRepository."""
    repo = MagicMock(spec=ControlCommandRepository)
    repo.list_pending = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_live_repo() -> MagicMock:
    """Create a mock LiveStrategyRepository."""
    return MagicMock(spec=LiveStrategyRepository)


@pytest.fixture
def mock_strategy_registry() -> MagicMock:
    """Create a mock StrategyRegistry."""
    return MagicMock(spec=StrategyRegistry)


@pytest.fixture
def service(
    mock_command_repo: MagicMock,
    mock_execution_repo: MagicMock,
    mock_live_repo: MagicMock,
    mock_strategy_registry: MagicMock,
    execution_control: ExecutionControl,
    bus: EventBus,
) -> ControlPlaneService:
    """Create ControlPlaneService with mocked repositories."""
    return ControlPlaneService(
        command_repo=mock_command_repo,
        execution_repo=mock_execution_repo,
        live_repo=mock_live_repo,
        strategy_registry=mock_strategy_registry,
        execution_control=execution_control,
        bus=bus,
        poll_interval_s=60.0,  # Long interval — we stop immediately after start
    )


# ============================================================================
# Boot Reconciliation Tests
# ============================================================================


class TestBootReconciliation:
    """Tests for _reconcile_boot_state() behavior during start()."""

    @pytest.mark.asyncio
    async def test_resets_db_when_execution_was_enabled(
        self,
        service: ControlPlaneService,
        mock_execution_repo: MagicMock,
        execution_control: ExecutionControl,
    ) -> None:
        """DB execution_enabled=true is reset to false on boot.

        This is the exact bug scenario: DB was left enabled from a
        previous session, and the runtime defaults to disabled. The
        reconciliation must force DB to match the runtime.
        """
        # Simulate DB state from previous session: execution was enabled
        mock_execution_repo.get_control = AsyncMock(
            return_value=_make_mock_db_record(
                execution_enabled=True,
                version=5,
                updated_by="operator",
                reason="Test envelope structure",
            )
        )

        await service._reconcile_boot_state()

        # DB must be updated to disabled
        mock_execution_repo.update_control.assert_called_once_with(
            execution_enabled=False,
            updated_by="system",
            reason="Boot reconciliation: execution disabled on startup (safety default)",
        )

        # In-memory must be disabled
        assert execution_control.execution_enabled is False
        assert execution_control.kill_switch_active is False

    @pytest.mark.asyncio
    async def test_no_update_when_db_already_disabled(
        self,
        service: ControlPlaneService,
        mock_execution_repo: MagicMock,
        execution_control: ExecutionControl,
    ) -> None:
        """No DB write when execution_enabled is already false.

        Avoids unnecessary version increments when state is already correct.
        """
        mock_execution_repo.get_control = AsyncMock(
            return_value=_make_mock_db_record(execution_enabled=False, version=3)
        )

        await service._reconcile_boot_state()

        # No update_control call — DB was already correct
        mock_execution_repo.update_control.assert_not_called()

        # In-memory still disabled
        assert execution_control.execution_enabled is False

    @pytest.mark.asyncio
    async def test_in_memory_forced_disabled_regardless_of_db(
        self,
        service: ControlPlaneService,
        mock_execution_repo: MagicMock,
        execution_control: ExecutionControl,
    ) -> None:
        """In-memory state is explicitly set to disabled on boot.

        Even if someone tampered with the in-memory state before boot
        reconciliation, it must be forced to disabled.
        """
        # Simulate someone mutating in-memory state before reconciliation
        execution_control.execution_enabled = True
        execution_control.kill_switch_active = True

        mock_execution_repo.get_control = AsyncMock(
            return_value=_make_mock_db_record(execution_enabled=False)
        )

        await service._reconcile_boot_state()

        # In-memory must be forced to disabled
        assert execution_control.execution_enabled is False
        assert execution_control.kill_switch_active is False

    @pytest.mark.asyncio
    async def test_fail_safe_on_db_error(
        self,
        service: ControlPlaneService,
        mock_execution_repo: MagicMock,
        execution_control: ExecutionControl,
    ) -> None:
        """If DB read fails, in-memory execution remains disabled.

        Per troubleshooting_foundational.mdc §0: default-safe behavior.
        A failed reconciliation must not accidentally enable execution.
        """
        mock_execution_repo.get_control = AsyncMock(
            side_effect=RuntimeError("DB connection refused")
        )

        # Must not raise — fail-safe
        await service._reconcile_boot_state()

        # In-memory must be disabled
        assert execution_control.execution_enabled is False

    @pytest.mark.asyncio
    async def test_start_calls_reconciliation_before_polling(
        self,
        service: ControlPlaneService,
        mock_execution_repo: MagicMock,
    ) -> None:
        """start() calls _reconcile_boot_state() before starting the poll loop.

        This ensures the DB is always consistent before any commands are
        processed.
        """
        mock_execution_repo.get_control = AsyncMock(
            return_value=_make_mock_db_record(execution_enabled=True, version=5)
        )

        await service.start()
        # Stop immediately to avoid infinite loop
        await service.stop()

        # Reconciliation should have been called (DB update triggered)
        mock_execution_repo.update_control.assert_called_once()
        call_args = mock_execution_repo.update_control.call_args
        assert call_args.kwargs["execution_enabled"] is False
        assert call_args.kwargs["updated_by"] == "system"
