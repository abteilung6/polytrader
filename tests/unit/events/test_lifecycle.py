"""Tests for system lifecycle events."""

import pytest
from pydantic import ValidationError

from polytrader.common.ids import reset_run_id
from polytrader.events.types import (
    ConfigLoadedEvent,
    EventSource,
    SystemStartedEvent,
    SystemStoppedEvent,
)


class TestSystemStartedEvent:
    """Tests for SystemStartedEvent."""

    def test_system_started_has_required_fields(self) -> None:
        """Test that SystemStartedEvent has all required Event fields."""
        event = SystemStartedEvent()

        assert event.event_id
        assert event.ts_wall
        assert event.ts_mono > 0
        assert event.correlation_id
        assert event.run_id
        assert event.schema_version == "1.0"
        assert event.source == EventSource.OPS

    def test_system_started_is_immutable(self) -> None:
        """Test that SystemStartedEvent is immutable."""
        event = SystemStartedEvent()

        with pytest.raises((ValidationError, TypeError)):
            event.source = EventSource.MDP  # type: ignore[misc]

    def test_system_started_has_default_source(self) -> None:
        """Test that SystemStartedEvent defaults to OPS source."""
        event = SystemStartedEvent()
        assert event.source == EventSource.OPS

    def test_system_started_events_have_unique_ids(self) -> None:
        """Test that each SystemStartedEvent gets a unique event_id."""
        event1 = SystemStartedEvent()
        event2 = SystemStartedEvent()

        assert event1.event_id != event2.event_id

    def test_system_started_events_share_run_id(self) -> None:
        """Test that SystemStartedEvents in same process share run_id."""
        reset_run_id()

        event1 = SystemStartedEvent()
        event2 = SystemStartedEvent()

        assert event1.run_id == event2.run_id

    def test_system_started_event_with_explicit_run_id(self) -> None:
        """Test that SystemStartedEvent can be created with explicit run_id.

        Per flows.mdc §2: SystemStartedEvent should include run_id for correlation.
        This test verifies that run_id can be explicitly set during boot.
        """
        explicit_run_id = "test-run-id-12345"
        event = SystemStartedEvent(run_id=explicit_run_id)

        assert event.run_id == explicit_run_id
        assert event.source == EventSource.OPS
        assert event.event_id  # Should still have unique event_id


class TestConfigLoadedEvent:
    """Tests for ConfigLoadedEvent."""

    def test_config_loaded_has_required_fields(self) -> None:
        """Test that ConfigLoadedEvent has all required fields."""
        event = ConfigLoadedEvent(config_hash="abc123")

        assert event.event_id
        assert event.ts_wall
        assert event.ts_mono > 0
        assert event.correlation_id
        assert event.run_id
        assert event.schema_version == "1.0"
        assert event.source == EventSource.OPS
        assert event.config_hash == "abc123"
        assert event.config_version is None

    def test_config_loaded_with_version(self) -> None:
        """Test ConfigLoadedEvent with version."""
        event = ConfigLoadedEvent(config_hash="abc123", config_version="1.2.3")

        assert event.config_hash == "abc123"
        assert event.config_version == "1.2.3"

    def test_config_loaded_is_immutable(self) -> None:
        """Test that ConfigLoadedEvent is immutable."""
        event = ConfigLoadedEvent(config_hash="abc123")

        with pytest.raises((ValidationError, TypeError)):
            event.config_hash = "new_hash"  # type: ignore[misc]

    def test_config_loaded_requires_config_hash(self) -> None:
        """Test that ConfigLoadedEvent requires config_hash."""
        with pytest.raises(ValidationError):
            ConfigLoadedEvent()  # type: ignore[call-arg]


class TestSystemStoppedEvent:
    """Tests for SystemStoppedEvent."""

    def test_system_stopped_has_required_fields(self) -> None:
        """Test that SystemStoppedEvent has all required Event fields."""
        event = SystemStoppedEvent()

        assert event.event_id
        assert event.ts_wall
        assert event.ts_mono > 0
        assert event.correlation_id
        assert event.run_id
        assert event.schema_version == "1.0"
        assert event.source == EventSource.OPS
        assert event.reason is None

    def test_system_stopped_with_reason(self) -> None:
        """Test SystemStoppedEvent with reason."""
        event = SystemStoppedEvent(reason="KeyboardInterrupt")

        assert event.reason == "KeyboardInterrupt"

    def test_system_stopped_is_immutable(self) -> None:
        """Test that SystemStoppedEvent is immutable."""
        event = SystemStoppedEvent()

        with pytest.raises((ValidationError, TypeError)):
            event.reason = "new_reason"  # type: ignore[misc]

    def test_system_stopped_events_have_unique_ids(self) -> None:
        """Test that each SystemStoppedEvent gets a unique event_id."""
        event1 = SystemStoppedEvent()
        event2 = SystemStoppedEvent()

        assert event1.event_id != event2.event_id
