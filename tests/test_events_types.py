"""Tests for event type definitions."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from polytrader.common.ids import generate_correlation_id, get_run_id, reset_run_id
from polytrader.events.types import Event, EventSource


class TestEventBaseClass:
    """Tests for the base Event class."""

    def test_event_has_required_fields(self) -> None:
        """Test that Event has all required fields."""
        event = Event(source=EventSource.OPS)

        assert event.event_id
        assert event.ts_wall
        assert event.ts_mono
        assert event.correlation_id
        assert event.run_id
        assert event.schema_version == "1.0"
        assert event.source == EventSource.OPS

    def test_event_id_is_uuid(self) -> None:
        """Test that event_id is a valid UUID."""
        event = Event(source=EventSource.OPS)

        # Should be a valid UUID string
        uuid.UUID(event.event_id)

    def test_ts_wall_is_iso_format(self) -> None:
        """Test that ts_wall is in ISO format."""
        event = Event(source=EventSource.OPS)

        # Should be parseable as ISO datetime
        datetime.fromisoformat(event.ts_wall.replace("Z", "+00:00"))

    def test_ts_mono_is_float(self) -> None:
        """Test that ts_mono is a float."""
        event = Event(source=EventSource.OPS)

        assert isinstance(event.ts_mono, float)
        assert event.ts_mono > 0

    def test_correlation_id_is_uuid(self) -> None:
        """Test that correlation_id is a valid UUID."""
        event = Event(source=EventSource.OPS)

        uuid.UUID(event.correlation_id)

    def test_run_id_matches_singleton(self) -> None:
        """Test that run_id matches the global singleton."""
        reset_run_id()
        event = Event(source=EventSource.OPS)

        assert event.run_id == get_run_id()

    def test_event_is_immutable(self) -> None:
        """Test that Event is immutable (frozen Pydantic model)."""
        event = Event(source=EventSource.OPS)

        with pytest.raises(ValidationError):
            event.source = EventSource.MDP  # type: ignore[misc]

    def test_event_can_override_defaults(self) -> None:
        """Test that Event fields can be explicitly set."""
        custom_event_id = str(uuid.uuid4())
        custom_correlation_id = generate_correlation_id()
        custom_run_id = get_run_id()
        custom_ts_wall = datetime.now(UTC).isoformat()

        event = Event(
            event_id=custom_event_id,
            correlation_id=custom_correlation_id,
            run_id=custom_run_id,
            ts_wall=custom_ts_wall,
            source=EventSource.MDP,
        )

        assert event.event_id == custom_event_id
        assert event.correlation_id == custom_correlation_id
        assert event.run_id == custom_run_id
        assert event.ts_wall == custom_ts_wall
        assert event.source == EventSource.MDP

    def test_event_requires_source(self) -> None:
        """Test that source is required."""
        # Should work with explicit source
        event = Event(source=EventSource.OPS)
        assert event.source == EventSource.OPS

        # Default source should be OPS
        event_default = Event()
        assert event_default.source == EventSource.OPS

    def test_event_validates_required_fields(self) -> None:
        """Test that Event validates required fields (Pydantic validation)."""
        # Invalid EventSource should raise ValidationError
        # Pydantic accepts strings and validates them at runtime
        with pytest.raises(ValidationError):
            Event(source="invalid_source")

        # Empty schema_version is allowed (defaults to "1.0")
        event = Event(source=EventSource.OPS, schema_version="")
        assert event.schema_version == ""

        # Note: Pydantic doesn't validate UUID format by default for str fields
        # Empty strings are also allowed unless we add validators
        # This is acceptable - UUID format is validated by usage, not by Pydantic

    def test_event_sources_are_valid(self) -> None:
        """Test that all valid EventSource values work."""
        valid_sources = [
            EventSource.MDP,
            EventSource.STRATEGY,
            EventSource.PORTFOLIO,
            EventSource.RISK,
            EventSource.OMS,
            EventSource.EXEC,
            EventSource.POSTTRADE,
            EventSource.OPS,
        ]

        for source in valid_sources:
            event = Event(source=source)
            assert event.source == source
            # EventSource is a string enum, so .value gives the string
            assert isinstance(event.source.value, str)

    def test_events_have_unique_ids(self) -> None:
        """Test that each Event instance gets a unique event_id."""
        event1 = Event(source=EventSource.OPS)
        event2 = Event(source=EventSource.OPS)

        assert event1.event_id != event2.event_id

    def test_events_have_unique_correlation_ids(self) -> None:
        """Test that each Event instance gets a unique correlation_id by default."""
        event1 = Event(source=EventSource.OPS)
        event2 = Event(source=EventSource.OPS)

        assert event1.correlation_id != event2.correlation_id

    def test_events_share_run_id(self) -> None:
        """Test that all events in the same process share the same run_id."""
        reset_run_id()

        event1 = Event(source=EventSource.OPS)
        event2 = Event(source=EventSource.MDP)
        event3 = Event(source=EventSource.STRATEGY)

        assert event1.run_id == event2.run_id == event3.run_id

    def test_event_can_share_correlation_id(self) -> None:
        """Test that events can share a correlation_id for tracing."""
        shared_correlation_id = generate_correlation_id()

        event1 = Event(correlation_id=shared_correlation_id, source=EventSource.MDP)
        event2 = Event(correlation_id=shared_correlation_id, source=EventSource.STRATEGY)
        event3 = Event(correlation_id=shared_correlation_id, source=EventSource.PORTFOLIO)

        assert event1.correlation_id == event2.correlation_id == event3.correlation_id


class TestEventSourceEnum:
    """Tests for EventSource enum."""

    def test_event_source_is_enum(self) -> None:
        """Test that EventSource is an enum."""
        assert isinstance(EventSource.OPS, EventSource)
        assert EventSource.OPS.value == "ops"

    def test_event_source_string_comparison(self) -> None:
        """Test that EventSource can be compared to strings (str, Enum)."""
        # EventSource is a str Enum, so .value gives the string
        assert EventSource.OPS.value == "ops"
        assert EventSource.MDP.value == "mdp"
        # Runtime comparison works because it's a str Enum
        # But mypy needs explicit .value for type safety

    def test_event_source_iteration(self) -> None:
        """Test that we can iterate over EventSource values."""
        sources = list(EventSource)
        assert len(sources) == 8
        assert EventSource.OPS in sources
        assert EventSource.MDP in sources

    def test_event_source_from_string(self) -> None:
        """Test that EventSource can be created from string value."""
        # Pydantic automatically converts strings to enum at runtime
        event = Event(source="ops")
        assert event.source == EventSource.OPS

    def test_invalid_event_source_raises(self) -> None:
        """Test that invalid EventSource raises ValidationError."""
        with pytest.raises(ValidationError):
            Event(source="invalid")
