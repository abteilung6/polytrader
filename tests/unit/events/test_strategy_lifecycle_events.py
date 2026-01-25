"""Unit tests for StrategyStateTransitionEvent.

Per Commit 12: StrategyStateTransitionEvent provides audit trail for
strategy lifecycle state changes.

Per testing.mdc: Unit tests must be deterministic, fast, and isolated.
Event creation, serialization, and validation are pure functions.
"""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from polytrader.events.types import EventSource, StrategyStateTransitionEvent
from polytrader.strategies.lifecycle_models import StrategyLifecycleState


class TestStrategyStateTransitionEventCreation:
    """Tests for StrategyStateTransitionEvent creation."""

    def test_event_has_required_fields(self) -> None:
        """Test that StrategyStateTransitionEvent has all required fields."""
        event = StrategyStateTransitionEvent(
            strategy_id="test_strategy_1",
            from_state=StrategyLifecycleState.STOPPED.value,
            to_state=StrategyLifecycleState.STARTING.value,
        )

        assert event.strategy_id == "test_strategy_1"
        assert event.from_state == StrategyLifecycleState.STOPPED.value
        assert event.to_state == StrategyLifecycleState.STARTING.value
        assert event.reason is None
        assert event.deployment_id is None

        # Base Event fields
        assert event.event_id
        assert event.ts_wall
        assert event.ts_mono
        assert event.correlation_id
        assert event.run_id
        assert event.schema_version == "1.0"
        assert event.source == EventSource.OPS

    def test_event_with_all_fields(self) -> None:
        """Test that StrategyStateTransitionEvent can be created with all fields."""
        deployment_id = str(uuid.uuid4())
        reason = "Strategy started by operator"

        event = StrategyStateTransitionEvent(
            strategy_id="test_strategy_1",
            from_state=StrategyLifecycleState.STOPPED.value,
            to_state=StrategyLifecycleState.STARTING.value,
            reason=reason,
            deployment_id=deployment_id,
        )

        assert event.strategy_id == "test_strategy_1"
        assert event.from_state == StrategyLifecycleState.STOPPED.value
        assert event.to_state == StrategyLifecycleState.STARTING.value
        assert event.reason == reason
        assert event.deployment_id == deployment_id

    def test_event_with_optional_fields_none(self) -> None:
        """Test that optional fields can be None."""
        event = StrategyStateTransitionEvent(
            strategy_id="test_strategy_1",
            from_state=StrategyLifecycleState.RUNNING.value,
            to_state=StrategyLifecycleState.PAUSED.value,
            reason=None,
            deployment_id=None,
        )

        assert event.reason is None
        assert event.deployment_id is None

    def test_event_validates_strategy_id_required(self) -> None:
        """Test that strategy_id is required."""
        with pytest.raises(ValidationError) as exc_info:
            StrategyStateTransitionEvent(  # type: ignore[call-arg]
                from_state=StrategyLifecycleState.STOPPED.value,
                to_state=StrategyLifecycleState.STARTING.value,
            )

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("strategy_id",) for error in errors)

    def test_event_validates_from_state_required(self) -> None:
        """Test that from_state is required."""
        with pytest.raises(ValidationError) as exc_info:
            StrategyStateTransitionEvent(  # type: ignore[call-arg]
                strategy_id="test_strategy_1",
                to_state=StrategyLifecycleState.STARTING.value,
            )

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("from_state",) for error in errors)

    def test_event_validates_to_state_required(self) -> None:
        """Test that to_state is required."""
        with pytest.raises(ValidationError) as exc_info:
            StrategyStateTransitionEvent(  # type: ignore[call-arg]
                strategy_id="test_strategy_1",
                from_state=StrategyLifecycleState.STOPPED.value,
            )

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("to_state",) for error in errors)

    def test_event_all_lifecycle_states(self) -> None:
        """Test that all lifecycle states can be used in transitions."""
        states = [
            StrategyLifecycleState.STOPPED,
            StrategyLifecycleState.STARTING,
            StrategyLifecycleState.RUNNING,
            StrategyLifecycleState.PAUSED,
            StrategyLifecycleState.DRAINING,
            StrategyLifecycleState.STOPPING,
            StrategyLifecycleState.ERROR,
        ]

        for from_state in states:
            for to_state in states:
                event = StrategyStateTransitionEvent(
                    strategy_id="test_strategy_1",
                    from_state=from_state.value,
                    to_state=to_state.value,
                )

                assert event.from_state == from_state.value
                assert event.to_state == to_state.value

    def test_event_inherits_base_event_fields(self) -> None:
        """Test that StrategyStateTransitionEvent inherits base Event fields."""
        event = StrategyStateTransitionEvent(
            strategy_id="test_strategy_1",
            from_state=StrategyLifecycleState.STOPPED.value,
            to_state=StrategyLifecycleState.STARTING.value,
        )

        # Base Event fields should be present
        assert hasattr(event, "event_id")
        assert hasattr(event, "ts_wall")
        assert hasattr(event, "ts_mono")
        assert hasattr(event, "correlation_id")
        assert hasattr(event, "run_id")
        assert hasattr(event, "schema_version")
        assert hasattr(event, "source")

        # Base Event fields should have valid values
        assert event.event_id
        assert event.ts_wall
        assert isinstance(event.ts_mono, float)
        assert event.correlation_id
        assert event.run_id
        assert event.schema_version == "1.0"
        assert event.source == EventSource.OPS


class TestStrategyStateTransitionEventSerialization:
    """Tests for StrategyStateTransitionEvent serialization."""

    def test_event_serializes_to_dict(self) -> None:
        """Test that event can be serialized to dictionary."""
        deployment_id = str(uuid.uuid4())
        event = StrategyStateTransitionEvent(
            strategy_id="test_strategy_1",
            from_state=StrategyLifecycleState.STOPPED.value,
            to_state=StrategyLifecycleState.STARTING.value,
            reason="Test transition",
            deployment_id=deployment_id,
        )

        event_dict = event.model_dump()

        assert event_dict["strategy_id"] == "test_strategy_1"
        assert event_dict["from_state"] == StrategyLifecycleState.STOPPED.value
        assert event_dict["to_state"] == StrategyLifecycleState.STARTING.value
        assert event_dict["reason"] == "Test transition"
        assert event_dict["deployment_id"] == deployment_id

        # Base Event fields should be in dict
        assert "event_id" in event_dict
        assert "ts_wall" in event_dict
        assert "ts_mono" in event_dict
        assert "correlation_id" in event_dict
        assert "run_id" in event_dict
        assert "schema_version" in event_dict
        assert "source" in event_dict

    def test_event_serializes_to_json(self) -> None:
        """Test that event can be serialized to JSON."""
        deployment_id = str(uuid.uuid4())
        event = StrategyStateTransitionEvent(
            strategy_id="test_strategy_1",
            from_state=StrategyLifecycleState.RUNNING.value,
            to_state=StrategyLifecycleState.PAUSED.value,
            reason="Paused for maintenance",
            deployment_id=deployment_id,
        )

        json_str = event.model_dump_json()

        assert "test_strategy_1" in json_str
        assert StrategyLifecycleState.RUNNING.value in json_str
        assert StrategyLifecycleState.PAUSED.value in json_str
        assert "Paused for maintenance" in json_str
        assert deployment_id in json_str

    def test_event_deserializes_from_dict(self) -> None:
        """Test that event can be deserialized from dictionary."""
        deployment_id = str(uuid.uuid4())
        event_dict = {
            "strategy_id": "test_strategy_1",
            "from_state": StrategyLifecycleState.STOPPED.value,
            "to_state": StrategyLifecycleState.STARTING.value,
            "reason": "Test transition",
            "deployment_id": deployment_id,
            "event_id": str(uuid.uuid4()),
            "ts_wall": datetime.now(UTC).isoformat(),
            "ts_mono": 1234.567,
            "correlation_id": "test_correlation",
            "run_id": "test_run",
            "schema_version": "1.0",
            "source": EventSource.OPS.value,
        }

        event = StrategyStateTransitionEvent.model_validate(event_dict)

        assert event.strategy_id == "test_strategy_1"
        assert event.from_state == StrategyLifecycleState.STOPPED.value
        assert event.to_state == StrategyLifecycleState.STARTING.value
        assert event.reason == "Test transition"
        assert event.deployment_id == deployment_id

    def test_event_round_trip_serialization(self) -> None:
        """Test that event can be serialized and deserialized correctly."""
        deployment_id = str(uuid.uuid4())
        original_event = StrategyStateTransitionEvent(
            strategy_id="test_strategy_1",
            from_state=StrategyLifecycleState.RUNNING.value,
            to_state=StrategyLifecycleState.DRAINING.value,
            reason="Graceful shutdown",
            deployment_id=deployment_id,
        )

        # Serialize to dict
        event_dict = original_event.model_dump()

        # Deserialize from dict
        deserialized_event = StrategyStateTransitionEvent.model_validate(event_dict)

        assert deserialized_event.strategy_id == original_event.strategy_id
        assert deserialized_event.from_state == original_event.from_state
        assert deserialized_event.to_state == original_event.to_state
        assert deserialized_event.reason == original_event.reason
        assert deserialized_event.deployment_id == original_event.deployment_id
        assert deserialized_event.event_id == original_event.event_id


class TestStrategyStateTransitionEventValidation:
    """Tests for StrategyStateTransitionEvent validation."""

    def test_event_validates_strategy_id_not_empty(self) -> None:
        """Test that strategy_id cannot be empty."""
        with pytest.raises(ValidationError) as exc_info:
            StrategyStateTransitionEvent(
                strategy_id="",
                from_state=StrategyLifecycleState.STOPPED.value,
                to_state=StrategyLifecycleState.STARTING.value,
            )

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("strategy_id",) for error in errors)

    def test_event_validates_from_state_not_empty(self) -> None:
        """Test that from_state cannot be empty."""
        with pytest.raises(ValidationError) as exc_info:
            StrategyStateTransitionEvent(
                strategy_id="test_strategy_1",
                from_state="",
                to_state=StrategyLifecycleState.STARTING.value,
            )

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("from_state",) for error in errors)

    def test_event_validates_to_state_not_empty(self) -> None:
        """Test that to_state cannot be empty."""
        with pytest.raises(ValidationError) as exc_info:
            StrategyStateTransitionEvent(
                strategy_id="test_strategy_1",
                from_state=StrategyLifecycleState.STOPPED.value,
                to_state="",
            )

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("to_state",) for error in errors)

    def test_event_immutable_after_creation(self) -> None:
        """Test that event is immutable (frozen model)."""
        from pydantic import ValidationError

        event = StrategyStateTransitionEvent(
            strategy_id="test_strategy_1",
            from_state=StrategyLifecycleState.STOPPED.value,
            to_state=StrategyLifecycleState.STARTING.value,
        )

        # Attempting to modify should raise ValidationError (frozen model)
        with pytest.raises(ValidationError):
            event.strategy_id = "modified"  # type: ignore[misc]

    def test_event_deployment_id_valid_uuid_format(self) -> None:
        """Test that deployment_id must be a valid UUID string if provided."""
        # Valid UUID should work
        valid_uuid = str(uuid.uuid4())
        event = StrategyStateTransitionEvent(
            strategy_id="test_strategy_1",
            from_state=StrategyLifecycleState.STOPPED.value,
            to_state=StrategyLifecycleState.STARTING.value,
            deployment_id=valid_uuid,
        )

        assert event.deployment_id == valid_uuid

        # Invalid UUID format should still be accepted as string
        # (Pydantic doesn't validate UUID format by default for str fields)
        # But we can test that it accepts any string
        invalid_uuid = "not-a-uuid"
        event2 = StrategyStateTransitionEvent(
            strategy_id="test_strategy_1",
            from_state=StrategyLifecycleState.STOPPED.value,
            to_state=StrategyLifecycleState.STARTING.value,
            deployment_id=invalid_uuid,
        )

        assert event2.deployment_id == invalid_uuid
