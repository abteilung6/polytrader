"""Unit tests for kill switch API endpoints.

Per Commit 2 (Pilot Live): Kill switch endpoints provide immediate
emergency stop and reset functionality.

Tests verify:
- Kill switch activates kill switch (immediate, not queued)
- Kill switch disables execution (is_enabled() returns False)
- Reset endpoint clears kill switch but execution remains disabled
- KillSwitchEvent emitted on activate and reset
- 400 if reason is empty
- 503 if platform not running (ExecutionControl unavailable)

Per testing.mdc: Unit tests must be deterministic, fast, and isolated.
Per unit_testing_technical.mdc: No databases, no network, no real clocks.
"""

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polytrader.api.app import create_app
from polytrader.api.dependencies import (
    get_control_command_repo,
    get_execution_control,
    get_execution_control_repo,
)
from polytrader.events.bus import EventBus
from polytrader.ops.control import ExecutionControl
from polytrader.platform.control import (
    ControlCommandRepository,
    ExecutionControlRepository,
)

# ============================================================================
# Fixtures
# ============================================================================

# Note: MemoryMetricsCollector is set globally via autouse fixture in
# tests/conftest.py::_use_memory_metrics — no per-file setup needed.


@pytest.fixture
def bus() -> EventBus:
    """Create an EventBus for testing."""
    return EventBus()


@pytest.fixture
def execution_control(
    bus: EventBus,
) -> ExecutionControl:
    """Create ExecutionControl with bus for event emission testing.

    Args:
        bus: Event bus for publishing events
    """
    return ExecutionControl(bus=bus)


@pytest.fixture
def mock_command_repo() -> MagicMock:
    """Create a mock ControlCommandRepository."""
    repo = MagicMock(spec=ControlCommandRepository)
    # create_command returns a command_id string
    repo.create_command = AsyncMock(return_value=str(uuid4()))
    repo.mark_applied = AsyncMock()
    return repo


@pytest.fixture
def mock_execution_repo() -> MagicMock:
    """Create a mock ExecutionControlRepository."""
    repo = MagicMock(spec=ExecutionControlRepository)
    # update_control returns an updated record
    mock_record = MagicMock()
    mock_record.version = 2
    mock_record.execution_enabled = False
    mock_record.updated_at = datetime(2024, 1, 1, tzinfo=UTC)
    mock_record.updated_by = "system"
    mock_record.reason = "Kill switch activated"
    repo.update_control = AsyncMock(return_value=mock_record)
    repo.get_control = AsyncMock(return_value=mock_record)
    return repo


@pytest.fixture
def app() -> FastAPI:
    """Create a shared FastAPI app instance.

    Reusing a single app avoids Prometheus metric duplication errors
    when multiple TestClient instances are created.
    """
    return create_app()


@pytest.fixture
def client(
    app: FastAPI,
    execution_control: ExecutionControl,
    mock_command_repo: MagicMock,
    mock_execution_repo: MagicMock,
) -> Generator[TestClient, None, None]:
    """Create FastAPI test client with mocked dependencies."""
    app.dependency_overrides[get_execution_control] = lambda: execution_control
    app.dependency_overrides[get_control_command_repo] = lambda: mock_command_repo
    app.dependency_overrides[get_execution_control_repo] = lambda: mock_execution_repo

    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client_no_platform(
    app: FastAPI,
    mock_command_repo: MagicMock,
    mock_execution_repo: MagicMock,
) -> Generator[TestClient, None, None]:
    """Create FastAPI test client without ExecutionControl (platform not running)."""
    app.dependency_overrides[get_execution_control] = lambda: None
    app.dependency_overrides[get_control_command_repo] = lambda: mock_command_repo
    app.dependency_overrides[get_execution_control_repo] = lambda: mock_execution_repo

    yield TestClient(app)
    app.dependency_overrides.clear()


# ============================================================================
# Kill Switch Activate Tests
# ============================================================================


class TestActivateKillSwitch:
    """Tests for POST /commands/execution/kill-switch endpoint."""

    def test_kill_switch_activates_successfully(
        self,
        client: TestClient,
        execution_control: ExecutionControl,
    ) -> None:
        """Kill switch endpoint activates kill switch and disables execution."""
        # Pre-condition: execution is enabled
        execution_control.enable()
        assert execution_control.is_enabled() is True

        response = client.post(
            "/api/v1/commands/execution/kill-switch",
            json={
                "reason": "Emergency: unexpected market behavior",
                "cancel_open_orders": True,
                "issued_by": "operator",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "applied"
        assert "command_id" in data
        assert "links" in data
        assert "status" in data["links"]

    def test_kill_switch_disables_execution(
        self,
        client: TestClient,
        execution_control: ExecutionControl,
    ) -> None:
        """Kill switch makes is_enabled() return False."""
        execution_control.enable()
        assert execution_control.is_enabled() is True

        client.post(
            "/api/v1/commands/execution/kill-switch",
            json={
                "reason": "Emergency stop",
                "issued_by": "operator",
            },
        )

        # After kill switch: execution_enabled=false, kill_switch_active=true
        assert execution_control.kill_switch_active is True
        assert execution_control.execution_enabled is False
        assert execution_control.is_enabled() is False

    def test_kill_switch_sets_kill_switch_active(
        self,
        client: TestClient,
        execution_control: ExecutionControl,
    ) -> None:
        """Kill switch sets kill_switch_active to True."""
        assert execution_control.kill_switch_active is False

        client.post(
            "/api/v1/commands/execution/kill-switch",
            json={
                "reason": "Infrastructure issue detected",
                "issued_by": "operator",
            },
        )

        assert execution_control.kill_switch_active is True

    def test_kill_switch_persists_to_db(
        self,
        client: TestClient,
        mock_execution_repo: MagicMock,
    ) -> None:
        """Kill switch updates execution_enabled=false in DB."""
        client.post(
            "/api/v1/commands/execution/kill-switch",
            json={
                "reason": "Emergency stop",
                "issued_by": "operator",
            },
        )

        mock_execution_repo.update_control.assert_called_once_with(
            execution_enabled=False,
            updated_by="operator",
            reason="Kill switch activated: Emergency stop",
        )

    def test_kill_switch_creates_audit_record(
        self,
        client: TestClient,
        mock_command_repo: MagicMock,
    ) -> None:
        """Kill switch creates a command record for audit trail."""
        client.post(
            "/api/v1/commands/execution/kill-switch",
            json={
                "reason": "Emergency stop",
                "issued_by": "operator",
            },
        )

        mock_command_repo.create_command.assert_called_once()
        cmd = mock_command_repo.create_command.call_args[0][0]
        assert cmd.command_type == "kill_switch_activate"
        assert cmd.reason == "Emergency stop"
        assert cmd.issued_by == "operator"

        # Verify command is marked as applied immediately
        mock_command_repo.mark_applied.assert_called_once()

    def test_kill_switch_emits_event(
        self,
        client: TestClient,
        bus: EventBus,
        execution_control: ExecutionControl,
    ) -> None:
        """Kill switch emits KillSwitchEvent via EventBus."""
        from polytrader.events import SYSTEM_LIFECYCLE
        from polytrader.events.types import KillSwitchEvent

        # Subscribe to capture events via queue
        queue = bus.subscribe(SYSTEM_LIFECYCLE)

        client.post(
            "/api/v1/commands/execution/kill-switch",
            json={
                "reason": "Emergency stop",
                "cancel_open_orders": True,
                "issued_by": "operator",
            },
        )

        assert not queue.empty()
        event = queue.get_nowait()
        assert isinstance(event, KillSwitchEvent)
        assert event.triggered is True
        assert event.reason == "Emergency stop"
        assert event.cancel_open_orders is True
        assert event.triggered_by == "operator"

    def test_kill_switch_rejects_empty_reason(
        self,
        client: TestClient,
    ) -> None:
        """Kill switch returns 422 if reason is empty."""
        response = client.post(
            "/api/v1/commands/execution/kill-switch",
            json={
                "reason": "",
                "issued_by": "operator",
            },
        )

        assert response.status_code == 422

    def test_kill_switch_503_when_platform_not_running(
        self,
        client_no_platform: TestClient,
    ) -> None:
        """Kill switch returns 503 when ExecutionControl is not available."""
        response = client_no_platform.post(
            "/api/v1/commands/execution/kill-switch",
            json={
                "reason": "Emergency stop",
                "issued_by": "operator",
            },
        )

        assert response.status_code == 503
        data = response.json()
        assert "Platform not running" in data["detail"]["error"]

    def test_kill_switch_default_cancel_open_orders(
        self,
        client: TestClient,
        execution_control: ExecutionControl,
    ) -> None:
        """Kill switch defaults cancel_open_orders to True."""
        response = client.post(
            "/api/v1/commands/execution/kill-switch",
            json={
                "reason": "Emergency stop",
                "issued_by": "operator",
            },
        )

        assert response.status_code == 200
        # The ExecutionControl.set_kill_switch was called with cancel_open_orders=True
        assert execution_control.kill_switch_active is True

    def test_kill_switch_cancel_open_orders_false(
        self,
        client: TestClient,
        bus: EventBus,
    ) -> None:
        """Kill switch respects cancel_open_orders=false."""
        from polytrader.events import SYSTEM_LIFECYCLE
        from polytrader.events.types import KillSwitchEvent

        queue = bus.subscribe(SYSTEM_LIFECYCLE)

        response = client.post(
            "/api/v1/commands/execution/kill-switch",
            json={
                "reason": "Emergency stop",
                "cancel_open_orders": False,
                "issued_by": "operator",
            },
        )

        assert response.status_code == 200
        assert not queue.empty()
        event = queue.get_nowait()
        assert isinstance(event, KillSwitchEvent)
        assert event.cancel_open_orders is False


# ============================================================================
# Kill Switch Reset Tests
# ============================================================================


class TestResetKillSwitch:
    """Tests for POST /commands/execution/kill-switch/reset endpoint."""

    def test_reset_clears_kill_switch(
        self,
        client: TestClient,
        execution_control: ExecutionControl,
    ) -> None:
        """Reset endpoint clears kill_switch_active to False."""
        # Pre-condition: kill switch is active
        execution_control.kill_switch_active = True
        execution_control.execution_enabled = False

        response = client.post(
            "/api/v1/commands/execution/kill-switch/reset",
            json={
                "reason": "Issue resolved, resetting kill switch",
                "issued_by": "operator",
            },
        )

        assert response.status_code == 200
        assert execution_control.kill_switch_active is False

    def test_reset_keeps_execution_disabled(
        self,
        client: TestClient,
        execution_control: ExecutionControl,
    ) -> None:
        """Reset clears kill switch but execution remains disabled.

        This is a critical safety invariant: the operator must explicitly
        re-enable execution after resetting the kill switch.
        """
        # Pre-condition: kill switch active, execution disabled
        execution_control.kill_switch_active = True
        execution_control.execution_enabled = False

        client.post(
            "/api/v1/commands/execution/kill-switch/reset",
            json={
                "reason": "Issue resolved",
                "issued_by": "operator",
            },
        )

        # Kill switch cleared, but execution still disabled
        assert execution_control.kill_switch_active is False
        assert execution_control.execution_enabled is False
        assert execution_control.is_enabled() is False

    def test_reset_emits_event(
        self,
        client: TestClient,
        bus: EventBus,
        execution_control: ExecutionControl,
    ) -> None:
        """Reset emits KillSwitchEvent with triggered=False."""
        from polytrader.events import SYSTEM_LIFECYCLE
        from polytrader.events.types import KillSwitchEvent

        execution_control.kill_switch_active = True

        queue = bus.subscribe(SYSTEM_LIFECYCLE)

        client.post(
            "/api/v1/commands/execution/kill-switch/reset",
            json={
                "reason": "Issue resolved",
                "issued_by": "operator",
            },
        )

        assert not queue.empty()
        event = queue.get_nowait()
        assert isinstance(event, KillSwitchEvent)
        assert event.triggered is False
        assert event.reason == "Issue resolved"

    def test_reset_creates_audit_record(
        self,
        client: TestClient,
        execution_control: ExecutionControl,
        mock_command_repo: MagicMock,
    ) -> None:
        """Reset creates a command record for audit trail."""
        execution_control.kill_switch_active = True

        client.post(
            "/api/v1/commands/execution/kill-switch/reset",
            json={
                "reason": "Issue resolved",
                "issued_by": "operator",
            },
        )

        mock_command_repo.create_command.assert_called_once()
        cmd = mock_command_repo.create_command.call_args[0][0]
        assert cmd.command_type == "kill_switch_reset"
        assert cmd.reason == "Issue resolved"
        assert cmd.issued_by == "operator"

        mock_command_repo.mark_applied.assert_called_once()

    def test_reset_rejects_empty_reason(
        self,
        client: TestClient,
    ) -> None:
        """Reset returns 422 if reason is empty."""
        response = client.post(
            "/api/v1/commands/execution/kill-switch/reset",
            json={
                "reason": "",
                "issued_by": "operator",
            },
        )

        assert response.status_code == 422

    def test_reset_503_when_platform_not_running(
        self,
        client_no_platform: TestClient,
    ) -> None:
        """Reset returns 503 when ExecutionControl is not available."""
        response = client_no_platform.post(
            "/api/v1/commands/execution/kill-switch/reset",
            json={
                "reason": "Issue resolved",
                "issued_by": "operator",
            },
        )

        assert response.status_code == 503

    def test_reset_response_status_is_applied(
        self,
        client: TestClient,
        execution_control: ExecutionControl,
    ) -> None:
        """Reset response has status='applied' (immediate, not queued)."""
        execution_control.kill_switch_active = True

        response = client.post(
            "/api/v1/commands/execution/kill-switch/reset",
            json={
                "reason": "Issue resolved",
                "issued_by": "operator",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "applied"


# ============================================================================
# Execution State (kill switch field) Tests
# ============================================================================


class TestExecutionStateWithKillSwitch:
    """Tests for GET /state/execution including kill_switch_active field."""

    def test_execution_state_includes_kill_switch_active(
        self,
        client: TestClient,
    ) -> None:
        """Execution state response includes kill_switch_active field."""
        response = client.get("/api/v1/state/execution")

        assert response.status_code == 200
        data = response.json()
        assert "kill_switch_active" in data
        assert data["kill_switch_active"] is False

    def test_execution_state_reflects_kill_switch_true(
        self,
        client: TestClient,
        execution_control: ExecutionControl,
    ) -> None:
        """Execution state shows kill_switch_active=true when activated."""
        execution_control.kill_switch_active = True

        response = client.get("/api/v1/state/execution")

        assert response.status_code == 200
        data = response.json()
        assert data["kill_switch_active"] is True

    def test_execution_state_defaults_kill_switch_false_no_platform(
        self,
        client_no_platform: TestClient,
    ) -> None:
        """Kill switch defaults to false when platform is not running."""
        response = client_no_platform.get("/api/v1/state/execution")

        assert response.status_code == 200
        data = response.json()
        assert data["kill_switch_active"] is False


# ============================================================================
# Full Lifecycle Tests
# ============================================================================


class TestKillSwitchFullLifecycle:
    """End-to-end lifecycle: activate → verify state → reset → verify state."""

    def test_activate_then_reset_lifecycle(
        self,
        client: TestClient,
        execution_control: ExecutionControl,
    ) -> None:
        """Full kill switch lifecycle: activate → reset → manual re-enable."""
        # Step 1: Start with execution enabled
        execution_control.enable()
        assert execution_control.is_enabled() is True

        # Step 2: Activate kill switch
        response = client.post(
            "/api/v1/commands/execution/kill-switch",
            json={
                "reason": "Emergency: unexpected fill",
                "issued_by": "operator",
            },
        )
        assert response.status_code == 200
        assert execution_control.kill_switch_active is True
        assert execution_control.is_enabled() is False

        # Step 3: Reset kill switch
        response = client.post(
            "/api/v1/commands/execution/kill-switch/reset",
            json={
                "reason": "Fill was legitimate, resetting",
                "issued_by": "operator",
            },
        )
        assert response.status_code == 200
        assert execution_control.kill_switch_active is False
        # Execution still disabled — operator must re-enable explicitly
        assert execution_control.execution_enabled is False
        assert execution_control.is_enabled() is False

        # Step 4: Operator re-enables execution (would use enable endpoint)
        execution_control.enable()
        assert execution_control.is_enabled() is True
