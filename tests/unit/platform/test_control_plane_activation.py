"""Unit tests: add/remove active strategy must not change lifecycle.

Per alpha_operating_model.mdc and frontend rules: Activation (add/remove from
active live strategies) controls Mode (Paper/Live). Lifecycle (Start/Stop)
controls whether the instance is running (paper tracking). These are
independent; conflating them causes "Remove from active" to stop the instance.

These tests verify:
- _add_active_strategy only calls live_repo.activate(); no desired_state/actual_state.
- _remove_active_strategy only calls live_repo.deactivate(); no desired_state/actual_state.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from polytrader.db.models import ControlCommandRecord
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
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def execution_control(bus: EventBus) -> ExecutionControl:
    return ExecutionControl(bus=bus)


@pytest.fixture
def mock_repos() -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
    """Mock command_repo, execution_repo, live_repo, strategy_registry."""
    command_repo = MagicMock(spec=ControlCommandRepository)
    execution_repo = MagicMock(spec=ExecutionControlRepository)
    live_repo = MagicMock(spec=LiveStrategyRepository)
    live_repo.activate = AsyncMock()
    live_repo.deactivate = AsyncMock()
    strategy_registry = MagicMock(spec=StrategyRegistry)
    strategy_registry.get_strategy = AsyncMock(return_value=None)
    strategy_registry.update_strategy = AsyncMock()
    return command_repo, execution_repo, live_repo, strategy_registry


@pytest.fixture
def service(
    mock_repos: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
    execution_control: ExecutionControl,
    bus: EventBus,
) -> ControlPlaneService:
    command_repo, execution_repo, live_repo, strategy_registry = mock_repos
    return ControlPlaneService(
        command_repo=command_repo,
        execution_repo=execution_repo,
        live_repo=live_repo,
        strategy_registry=strategy_registry,
        execution_control=execution_control,
        bus=bus,
        poll_interval_s=1.0,
    )


@pytest.fixture
def active_strategies() -> set[str]:
    """Mutable set for testing in-memory active_strategies updates."""
    return set()


@pytest.fixture
def service_with_active_strategies(
    mock_repos: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
    execution_control: ExecutionControl,
    bus: EventBus,
    active_strategies: set[str],
) -> ControlPlaneService:
    """ControlPlaneService with active_strategies set for testing."""
    command_repo, execution_repo, live_repo, strategy_registry = mock_repos
    return ControlPlaneService(
        command_repo=command_repo,
        execution_repo=execution_repo,
        live_repo=live_repo,
        strategy_registry=strategy_registry,
        execution_control=execution_control,
        bus=bus,
        poll_interval_s=1.0,
        active_strategies=active_strategies,
    )


class TestAddActiveStrategyDoesNotChangeLifecycle:
    """_add_active_strategy must only update live_repo, not desired_state/actual_state."""

    @pytest.mark.asyncio
    async def test_add_active_calls_live_repo_activate_only(
        self,
        service: ControlPlaneService,
        mock_repos: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
    ) -> None:
        _, _, live_repo, strategy_registry = mock_repos
        cmd = ControlCommandRecord(
            command_type="add_active_strategy",
            strategy_id="strat-1",
            reason="Add to active",
            issued_by="operator",
            client_request_id="req-1",
        )

        await service._add_active_strategy(cmd)

        live_repo.activate.assert_called_once()
        live_repo.activate.assert_awaited_once_with(
            strategy_id="strat-1",
            activated_by="operator",
            reason="Add to active",
        )
        strategy_registry.get_strategy.assert_not_called()
        strategy_registry.update_strategy.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_active_does_not_touch_strategy_registry_even_if_strategy_exists(
        self,
        service: ControlPlaneService,
        mock_repos: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
    ) -> None:
        _, _, live_repo, strategy_registry = mock_repos
        strategy_registry.get_strategy = AsyncMock(return_value=MagicMock())
        cmd = ControlCommandRecord(
            command_type="add_active_strategy",
            strategy_id="strat-1",
            reason="Add to active",
            issued_by="operator",
            client_request_id="req-1",
        )

        await service._add_active_strategy(cmd)

        live_repo.activate.assert_called_once()
        strategy_registry.update_strategy.assert_not_called()


class TestRemoveActiveStrategyDoesNotChangeLifecycle:
    """_remove_active_strategy must only update live_repo, not desired_state/actual_state."""

    @pytest.mark.asyncio
    async def test_remove_active_calls_live_repo_deactivate_only(
        self,
        service: ControlPlaneService,
        mock_repos: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
    ) -> None:
        _, _, live_repo, strategy_registry = mock_repos
        cmd = ControlCommandRecord(
            command_type="remove_active_strategy",
            strategy_id="strat-1",
            reason="Remove from active",
            issued_by="operator",
            client_request_id="req-2",
        )

        await service._remove_active_strategy(cmd)

        live_repo.deactivate.assert_called_once()
        live_repo.deactivate.assert_awaited_once_with(
            strategy_id="strat-1",
            activated_by="operator",
            reason="Remove from active",
        )
        strategy_registry.get_strategy.assert_not_called()
        strategy_registry.update_strategy.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_active_does_not_touch_strategy_registry_even_if_strategy_exists(
        self,
        service: ControlPlaneService,
        mock_repos: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
    ) -> None:
        _, _, live_repo, strategy_registry = mock_repos
        strategy_registry.get_strategy = AsyncMock(return_value=MagicMock())
        cmd = ControlCommandRecord(
            command_type="remove_active_strategy",
            strategy_id="strat-1",
            reason="Remove from active",
            issued_by="operator",
            client_request_id="req-2",
        )

        await service._remove_active_strategy(cmd)

        live_repo.deactivate.assert_called_once()
        strategy_registry.update_strategy.assert_not_called()


class TestControlPlaneUpdatesActiveStrategiesSet:
    """With active_strategies set, add/remove commands update the in-memory set."""

    @pytest.mark.asyncio
    async def test_add_active_strategy_adds_to_set(
        self,
        service_with_active_strategies: ControlPlaneService,
        active_strategies: set[str],
    ) -> None:
        """Process add_active_strategy → set contains strategy_id."""
        cmd = ControlCommandRecord(
            command_type="add_active_strategy",
            strategy_id="strat-1",
            reason="Add to active",
            issued_by="operator",
            client_request_id="req-1",
        )
        await service_with_active_strategies._add_active_strategy(cmd)
        assert "strat-1" in active_strategies

    @pytest.mark.asyncio
    async def test_remove_active_strategy_removes_from_set(
        self,
        service_with_active_strategies: ControlPlaneService,
        active_strategies: set[str],
    ) -> None:
        """Process remove_active_strategy → set no longer contains strategy_id."""
        active_strategies.add("strat-1")
        cmd = ControlCommandRecord(
            command_type="remove_active_strategy",
            strategy_id="strat-1",
            reason="Remove from active",
            issued_by="operator",
            client_request_id="req-2",
        )
        await service_with_active_strategies._remove_active_strategy(cmd)
        assert "strat-1" not in active_strategies
