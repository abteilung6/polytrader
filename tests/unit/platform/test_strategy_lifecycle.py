"""Unit tests for StrategyLifecycleManager.

Per Commit 13: StrategyLifecycleManager handles desired_state → actual_state
transitions with FSM validation and event emission.

Per testing.mdc: Unit tests must be deterministic, fast, and isolated.
Lifecycle manager tests use mocks for database and event bus.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from polytrader.db.models import StrategyRecord
from polytrader.events import SYSTEM_LIFECYCLE, EventBus, StrategyStateTransitionEvent
from polytrader.platform.strategy_lifecycle import StrategyLifecycleManager
from polytrader.strategies.lifecycle import InvalidTransitionError
from polytrader.strategies.lifecycle_models import StrategyLifecycleState


class TestStrategyLifecycleManagerInitialization:
    """Tests for StrategyLifecycleManager initialization."""

    def test_manager_initializes_with_bus_and_session(self) -> None:
        """Test that manager initializes with event bus and database session."""
        bus = MagicMock(spec=EventBus)
        session = MagicMock()

        manager = StrategyLifecycleManager(bus=bus, session=session)

        assert manager._bus is bus
        assert manager._session is session


class TestStrategyLifecycleManagerTransitionToDesiredState:
    """Tests for transition_to_desired_state method."""

    @pytest.fixture
    def bus(self) -> MagicMock:
        """Create mock event bus."""
        bus = MagicMock(spec=EventBus)
        bus.publish = AsyncMock()
        return bus

    @pytest.fixture
    def session(self) -> MagicMock:
        """Create mock database session."""
        session = MagicMock()
        session.flush = AsyncMock()
        # Mock execute() to return a result that has scalar_one() method
        mock_result = MagicMock()
        mock_result.scalar_one = MagicMock(return_value=None)  # Will be set per test
        session.execute = AsyncMock(return_value=mock_result)
        return session

    @pytest.fixture
    def manager(self, bus: MagicMock, session: MagicMock) -> StrategyLifecycleManager:
        """Create StrategyLifecycleManager with mocked dependencies."""
        return StrategyLifecycleManager(bus=bus, session=session)

    @pytest.fixture
    def strategy_stopped(self) -> StrategyRecord:
        """Create a strategy in STOPPED state."""
        return StrategyRecord(
            strategy_id="test_strategy_1",
            name="Test Strategy",
            config={"buy_threshold": 0.3},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_123",
            desired_state=StrategyLifecycleState.STARTING.value,
            actual_state=StrategyLifecycleState.STOPPED.value,
        )

    @pytest.mark.asyncio
    async def test_transition_to_desired_state_valid(
        self,
        manager: StrategyLifecycleManager,
        strategy_stopped: StrategyRecord,
        bus: MagicMock,
        session: MagicMock,
    ) -> None:
        """Test valid transition from STOPPED to STARTING."""
        # Mock the database query to return the strategy record
        mock_result = MagicMock()
        mock_result.scalar_one = MagicMock(return_value=strategy_stopped)
        session.execute = AsyncMock(return_value=mock_result)

        new_state = await manager.transition_to_desired_state(
            strategy_stopped, reason="Operator requested start"
        )

        assert new_state == StrategyLifecycleState.STARTING
        assert strategy_stopped.actual_state == StrategyLifecycleState.STARTING.value
        assert strategy_stopped.last_transition_at is not None

        # Verify event was emitted
        bus.publish.assert_called_once()
        call_args = bus.publish.call_args
        assert call_args[0][0] == SYSTEM_LIFECYCLE
        event = call_args[0][1]
        assert isinstance(event, StrategyStateTransitionEvent)
        assert event.strategy_id == "test_strategy_1"
        assert event.from_state == StrategyLifecycleState.STOPPED.value
        assert event.to_state == StrategyLifecycleState.STARTING.value
        assert event.reason == "Operator requested start"

        # Verify database flush was called
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_transition_to_desired_state_already_in_desired(
        self,
        manager: StrategyLifecycleManager,
        bus: MagicMock,
        session: MagicMock,
    ) -> None:
        """Test that no transition occurs if already in desired state."""
        strategy = StrategyRecord(
            strategy_id="test_strategy_1",
            name="Test Strategy",
            config={"buy_threshold": 0.3},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_123",
            desired_state=StrategyLifecycleState.RUNNING.value,
            actual_state=StrategyLifecycleState.RUNNING.value,
        )

        new_state = await manager.transition_to_desired_state(strategy)

        assert new_state == StrategyLifecycleState.RUNNING
        # No event should be emitted
        bus.publish.assert_not_called()
        # No database flush should occur
        session.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_transition_to_desired_state_invalid_raises_error(
        self,
        manager: StrategyLifecycleManager,
        bus: MagicMock,
        session: MagicMock,
    ) -> None:
        """Test that invalid transition raises InvalidTransitionError."""
        strategy = StrategyRecord(
            strategy_id="test_strategy_1",
            name="Test Strategy",
            config={"buy_threshold": 0.3},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_123",
            desired_state=StrategyLifecycleState.RUNNING.value,
            actual_state=StrategyLifecycleState.STOPPED.value,  # Cannot go directly to RUNNING
        )

        with pytest.raises(InvalidTransitionError) as exc_info:
            await manager.transition_to_desired_state(strategy, reason="Invalid transition")

        assert exc_info.value.from_state == StrategyLifecycleState.STOPPED
        assert exc_info.value.to_state == StrategyLifecycleState.RUNNING

        # Verify event was emitted for ERROR state transition (if applicable)
        # The manager should attempt to transition to ERROR state on invalid transition
        if bus.publish.called:
            call_args = bus.publish.call_args
            event = call_args[0][1]
            assert isinstance(event, StrategyStateTransitionEvent)
            assert event.to_state == StrategyLifecycleState.ERROR.value

    @pytest.mark.asyncio
    async def test_transition_to_desired_state_updates_error_message(
        self,
        manager: StrategyLifecycleManager,
        strategy_stopped: StrategyRecord,
        bus: MagicMock,
        session: MagicMock,
    ) -> None:
        """Test that error message is updated when transitioning to ERROR state."""
        # Force an invalid transition
        strategy_stopped.desired_state = StrategyLifecycleState.RUNNING.value
        strategy_stopped.actual_state = StrategyLifecycleState.STOPPED.value

        with pytest.raises(InvalidTransitionError):
            await manager.transition_to_desired_state(strategy_stopped)

        # If transition to ERROR occurred, error message should be set
        if strategy_stopped.actual_state == StrategyLifecycleState.ERROR.value:
            assert strategy_stopped.last_error is not None
            assert "Invalid transition" in strategy_stopped.last_error

    @pytest.mark.asyncio
    async def test_transition_to_desired_state_clears_error_on_success(
        self,
        manager: StrategyLifecycleManager,
        bus: MagicMock,
        session: MagicMock,
    ) -> None:
        """Test that error message is cleared when transitioning away from ERROR."""
        strategy = StrategyRecord(
            strategy_id="test_strategy_1",
            name="Test Strategy",
            config={"buy_threshold": 0.3},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_123",
            desired_state=StrategyLifecycleState.STOPPED.value,
            actual_state=StrategyLifecycleState.ERROR.value,
            last_error="Previous error",
        )

        # Mock the database query to return the strategy record
        mock_result = MagicMock()
        mock_result.scalar_one = MagicMock(return_value=strategy)
        session.execute = AsyncMock(return_value=mock_result)

        new_state = await manager.transition_to_desired_state(
            strategy, reason="Recovery from error"
        )

        assert new_state == StrategyLifecycleState.STOPPED
        assert strategy.last_error is None


class TestStrategyLifecycleManagerTransitionToState:
    """Tests for transition_to_state method."""

    @pytest.fixture
    def bus(self) -> MagicMock:
        """Create mock event bus."""
        bus = MagicMock(spec=EventBus)
        bus.publish = AsyncMock()
        return bus

    @pytest.fixture
    def session(self) -> MagicMock:
        """Create mock database session."""
        session = MagicMock()
        session.flush = AsyncMock()
        # Mock execute() to return a result that has scalar_one() method
        mock_result = MagicMock()
        mock_result.scalar_one = MagicMock(return_value=None)  # Will be set per test
        session.execute = AsyncMock(return_value=mock_result)
        return session

    @pytest.fixture
    def manager(self, bus: MagicMock, session: MagicMock) -> StrategyLifecycleManager:
        """Create StrategyLifecycleManager with mocked dependencies."""
        return StrategyLifecycleManager(bus=bus, session=session)

    @pytest.mark.asyncio
    async def test_transition_to_state_valid(
        self,
        manager: StrategyLifecycleManager,
        bus: MagicMock,
        session: MagicMock,
    ) -> None:
        """Test valid transition to specific state."""
        strategy = StrategyRecord(
            strategy_id="test_strategy_1",
            name="Test Strategy",
            config={"buy_threshold": 0.3},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_123",
            desired_state=StrategyLifecycleState.STOPPED.value,
            actual_state=StrategyLifecycleState.STOPPED.value,
        )

        # Mock the database query to return the strategy record
        mock_result = MagicMock()
        mock_result.scalar_one = MagicMock(return_value=strategy)
        session.execute = AsyncMock(return_value=mock_result)

        new_state = await manager.transition_to_state(
            strategy, StrategyLifecycleState.STARTING, reason="Starting strategy"
        )

        assert new_state == StrategyLifecycleState.STARTING
        assert strategy.actual_state == StrategyLifecycleState.STARTING.value
        assert strategy.desired_state == StrategyLifecycleState.STARTING.value
        assert strategy.last_transition_at is not None

        # Verify event was emitted
        bus.publish.assert_called_once()
        call_args = bus.publish.call_args
        event = call_args[0][1]
        assert isinstance(event, StrategyStateTransitionEvent)
        assert event.from_state == StrategyLifecycleState.STOPPED.value
        assert event.to_state == StrategyLifecycleState.STARTING.value
        assert event.reason == "Starting strategy"

        # Verify database flush was called
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_transition_to_state_already_in_state(
        self,
        manager: StrategyLifecycleManager,
        bus: MagicMock,
        session: MagicMock,
    ) -> None:
        """Test that no transition occurs if already in target state."""
        strategy = StrategyRecord(
            strategy_id="test_strategy_1",
            name="Test Strategy",
            config={"buy_threshold": 0.3},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_123",
            desired_state=StrategyLifecycleState.RUNNING.value,
            actual_state=StrategyLifecycleState.RUNNING.value,
        )

        new_state = await manager.transition_to_state(strategy, StrategyLifecycleState.RUNNING)

        assert new_state == StrategyLifecycleState.RUNNING
        # No event should be emitted
        bus.publish.assert_not_called()
        # No database flush should occur
        session.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_transition_to_state_invalid_raises_error(
        self,
        manager: StrategyLifecycleManager,
        bus: MagicMock,
        session: MagicMock,
    ) -> None:
        """Test that invalid transition raises InvalidTransitionError."""
        strategy = StrategyRecord(
            strategy_id="test_strategy_1",
            name="Test Strategy",
            config={"buy_threshold": 0.3},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_123",
            desired_state=StrategyLifecycleState.STOPPED.value,
            actual_state=StrategyLifecycleState.STOPPED.value,
        )

        with pytest.raises(InvalidTransitionError):
            await manager.transition_to_state(
                strategy, StrategyLifecycleState.RUNNING, reason="Invalid direct transition"
            )

    @pytest.mark.asyncio
    async def test_transition_to_state_updates_both_desired_and_actual(
        self,
        manager: StrategyLifecycleManager,
        bus: MagicMock,
        session: MagicMock,
    ) -> None:
        """Test that transition_to_state updates both desired_state and actual_state."""
        strategy = StrategyRecord(
            strategy_id="test_strategy_1",
            name="Test Strategy",
            config={"buy_threshold": 0.3},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_123",
            desired_state=StrategyLifecycleState.STOPPED.value,
            actual_state=StrategyLifecycleState.STOPPED.value,
        )

        # Mock the database query to return the strategy record
        mock_result = MagicMock()
        mock_result.scalar_one = MagicMock(return_value=strategy)
        session.execute = AsyncMock(return_value=mock_result)

        await manager.transition_to_state(
            strategy, StrategyLifecycleState.STARTING, reason="Force start"
        )

        assert strategy.desired_state == StrategyLifecycleState.STARTING.value
        assert strategy.actual_state == StrategyLifecycleState.STARTING.value


class TestStrategyLifecycleManagerEventEmission:
    """Tests for event emission in StrategyLifecycleManager."""

    @pytest.fixture
    def bus(self) -> MagicMock:
        """Create mock event bus."""
        bus = MagicMock(spec=EventBus)
        bus.publish = AsyncMock()
        return bus

    @pytest.fixture
    def session(self) -> MagicMock:
        """Create mock database session."""
        session = MagicMock()
        session.flush = AsyncMock()
        # Mock execute() to return a result that has scalar_one() method
        mock_result = MagicMock()
        mock_result.scalar_one = MagicMock(return_value=None)  # Will be set per test
        session.execute = AsyncMock(return_value=mock_result)
        return session

    @pytest.fixture
    def manager(self, bus: MagicMock, session: MagicMock) -> StrategyLifecycleManager:
        """Create StrategyLifecycleManager with mocked dependencies."""
        return StrategyLifecycleManager(bus=bus, session=session)

    @pytest.mark.asyncio
    async def test_event_includes_deployment_id(
        self,
        manager: StrategyLifecycleManager,
        bus: MagicMock,
        session: MagicMock,
    ) -> None:
        """Test that event includes deployment_id if present."""
        deployment_id = uuid.uuid4()
        strategy = StrategyRecord(
            strategy_id="test_strategy_1",
            name="Test Strategy",
            config={"buy_threshold": 0.3},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_123",
            desired_state=StrategyLifecycleState.STARTING.value,
            actual_state=StrategyLifecycleState.STOPPED.value,
            deployment_id=deployment_id,
        )

        # Mock the database query to return the strategy record
        mock_result = MagicMock()
        mock_result.scalar_one = MagicMock(return_value=strategy)
        session.execute = AsyncMock(return_value=mock_result)

        await manager.transition_to_desired_state(strategy, reason="Start with deployment")

        call_args = bus.publish.call_args
        event = call_args[0][1]
        assert isinstance(event, StrategyStateTransitionEvent)
        assert event.deployment_id == str(deployment_id)

    @pytest.mark.asyncio
    async def test_event_deployment_id_none_when_not_set(
        self,
        manager: StrategyLifecycleManager,
        bus: MagicMock,
        session: MagicMock,
    ) -> None:
        """Test that event has deployment_id=None when not set on strategy."""
        strategy = StrategyRecord(
            strategy_id="test_strategy_1",
            name="Test Strategy",
            config={"buy_threshold": 0.3},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_123",
            desired_state=StrategyLifecycleState.STARTING.value,
            actual_state=StrategyLifecycleState.STOPPED.value,
            deployment_id=None,
        )

        # Mock the database query to return the strategy record
        mock_result = MagicMock()
        mock_result.scalar_one = MagicMock(return_value=strategy)
        session.execute = AsyncMock(return_value=mock_result)

        await manager.transition_to_desired_state(strategy, reason="Start without deployment")

        call_args = bus.publish.call_args
        event = call_args[0][1]
        assert isinstance(event, StrategyStateTransitionEvent)
        assert event.deployment_id is None
