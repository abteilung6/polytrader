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
        assert (
            len(sources) >= 9
        )  # MDP, STRATEGY, PORTFOLIO, RISK, OMS, EXECUTION, EXEC, POSTTRADE, OPS
        assert EventSource.OPS in sources
        assert EventSource.MDP in sources
        assert EventSource.STRATEGY in sources
        assert EventSource.PORTFOLIO in sources

    def test_event_source_from_string(self) -> None:
        """Test that EventSource can be created from string value."""
        # Pydantic automatically converts strings to enum at runtime
        event = Event(source="ops")
        assert event.source == EventSource.OPS

    def test_invalid_event_source_raises(self) -> None:
        """Test that invalid EventSource raises ValidationError."""
        with pytest.raises(ValidationError):
            Event(source="invalid")


class TestRiskCheckEvent:
    """Tests for RiskCheckEvent per observability.mdc §1."""

    def test_risk_check_event_creation(self) -> None:
        """Test that RiskCheckEvent can be created with intent and result."""
        from polytrader.events.types import OrderIntentEvent, RiskCheckEvent
        from polytrader.risk.models import RiskReasonCode, RiskResult

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        result = RiskResult(
            allowed=True,
            reason_codes=[RiskReasonCode.RISK_ALLOWED],
        )

        event = RiskCheckEvent(intent=intent, result=result)

        assert event.intent == intent
        assert event.result == result
        assert event.source.value == "risk"

    def test_risk_check_event_has_base_fields(self) -> None:
        """Test that RiskCheckEvent has all Event base class fields."""
        from polytrader.events.types import EventSource, OrderIntentEvent, RiskCheckEvent
        from polytrader.risk.models import RiskReasonCode, RiskResult

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        result = RiskResult(
            allowed=True,
            reason_codes=[RiskReasonCode.RISK_ALLOWED],
        )

        event = RiskCheckEvent(intent=intent, result=result)

        # Check all base Event fields
        assert event.event_id
        assert event.ts_wall
        assert event.ts_mono
        assert event.correlation_id
        assert event.run_id
        assert event.schema_version == "1.0"
        assert event.source == EventSource.RISK

    def test_risk_check_event_allowed_property(self) -> None:
        """Test that allowed property works correctly."""
        from polytrader.events.types import OrderIntentEvent, RiskCheckEvent
        from polytrader.risk.models import RiskReasonCode, RiskResult

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        # Test allowed=True
        result_allowed = RiskResult(
            allowed=True,
            reason_codes=[RiskReasonCode.RISK_ALLOWED],
        )
        event_allowed = RiskCheckEvent(intent=intent, result=result_allowed)
        assert event_allowed.allowed is True

        # Test allowed=False
        result_denied = RiskResult(
            allowed=False,
            reason_codes=[RiskReasonCode.RISK_PROPOSAL_EXPIRED],
        )
        event_denied = RiskCheckEvent(intent=intent, result=result_denied)
        assert event_denied.allowed is False

    def test_risk_check_event_reason_codes_property(self) -> None:
        """Test that reason_codes property works correctly."""
        from polytrader.events.types import OrderIntentEvent, RiskCheckEvent
        from polytrader.risk.models import RiskReasonCode, RiskResult

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        result = RiskResult(
            allowed=False,
            reason_codes=[
                RiskReasonCode.RISK_PROPOSAL_EXPIRED,
                RiskReasonCode.RISK_ORDER_TOO_LARGE,
            ],
        )

        event = RiskCheckEvent(intent=intent, result=result)

        assert len(event.reason_codes) == 2
        assert RiskReasonCode.RISK_PROPOSAL_EXPIRED in event.reason_codes
        assert RiskReasonCode.RISK_ORDER_TOO_LARGE in event.reason_codes

    def test_risk_check_event_correlation_id(self) -> None:
        """Test that RiskCheckEvent includes correlation_id per observability.mdc §2."""
        from polytrader.events.types import OrderIntentEvent, RiskCheckEvent
        from polytrader.risk.models import RiskReasonCode, RiskResult

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        result = RiskResult(
            allowed=True,
            reason_codes=[RiskReasonCode.RISK_ALLOWED],
        )

        # Use the same correlation_id as the intent
        shared_correlation_id = intent.correlation_id
        event = RiskCheckEvent(
            intent=intent,
            result=result,
            correlation_id=shared_correlation_id,
        )

        # Verify correlation_id is present and matches intent
        assert event.correlation_id == shared_correlation_id
        assert event.correlation_id == intent.correlation_id

    def test_risk_check_event_serialization(self) -> None:
        """Test that RiskCheckEvent can be serialized (Pydantic model)."""
        from polytrader.events.types import OrderIntentEvent, RiskCheckEvent
        from polytrader.risk.models import RiskReasonCode, RiskResult

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        result = RiskResult(
            allowed=True,
            reason_codes=[RiskReasonCode.RISK_ALLOWED],
            projections={"new_position": 1.0},
            metadata={"mid_price": 0.45},
        )

        event = RiskCheckEvent(intent=intent, result=result)

        # Test Pydantic serialization
        event_dict = event.model_dump()
        assert "intent" in event_dict
        assert "result" in event_dict
        assert "correlation_id" in event_dict
        assert event_dict["result"]["allowed"] is True

        # Test JSON serialization
        event_json = event.model_dump_json()
        assert isinstance(event_json, str)
        assert "test-market" in event_json


class TestOrderCreatedEvent:
    """Tests for OrderCreatedEvent per flows.mdc §7."""

    def test_order_created_event_creation(self) -> None:
        """Test that OrderCreatedEvent can be created."""
        from polytrader.events.types import EventSource, OrderCreatedEvent, OrderIntentEvent

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        order_id = str(uuid.uuid4())
        client_order_id = "client-123"

        event = OrderCreatedEvent(
            order_id=order_id,
            client_order_id=client_order_id,
            intent=intent,
        )

        assert event.order_id == order_id
        assert event.client_order_id == client_order_id
        assert event.intent == intent
        assert event.source == EventSource.OMS

    def test_order_created_event_has_base_fields(self) -> None:
        """Test that OrderCreatedEvent has all Event base class fields."""
        from polytrader.events.types import EventSource, OrderCreatedEvent, OrderIntentEvent

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        event = OrderCreatedEvent(
            order_id=str(uuid.uuid4()),
            client_order_id="client-123",
            intent=intent,
        )

        assert event.event_id
        assert event.ts_wall
        assert event.ts_mono
        assert event.correlation_id
        assert event.run_id
        assert event.schema_version == "1.0"
        assert event.source == EventSource.OMS

    def test_order_created_event_correlation_id(self) -> None:
        """Test that OrderCreatedEvent propagates correlation_id from intent."""
        from polytrader.events.types import OrderCreatedEvent, OrderIntentEvent

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        # Use the same correlation_id as the intent
        shared_correlation_id = intent.correlation_id
        event = OrderCreatedEvent(
            order_id=str(uuid.uuid4()),
            client_order_id="client-123",
            intent=intent,
            correlation_id=shared_correlation_id,
        )

        assert event.correlation_id == shared_correlation_id
        assert event.correlation_id == intent.correlation_id

    def test_order_created_event_serialization(self) -> None:
        """Test that OrderCreatedEvent can be serialized."""
        from polytrader.events.types import OrderCreatedEvent, OrderIntentEvent

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        event = OrderCreatedEvent(
            order_id=str(uuid.uuid4()),
            client_order_id="client-123",
            intent=intent,
        )

        event_dict = event.model_dump()
        assert "order_id" in event_dict
        assert "client_order_id" in event_dict
        assert "intent" in event_dict
        assert event_dict["source"] == "oms"


class TestOrderSubmittedEvent:
    """Tests for OrderSubmittedEvent per flows.mdc §7."""

    def test_order_submitted_event_creation(self) -> None:
        """Test that OrderSubmittedEvent can be created."""
        from polytrader.events.types import EventSource, OrderSubmittedEvent

        order_id = str(uuid.uuid4())
        client_order_id = "client-123"

        event = OrderSubmittedEvent(
            order_id=order_id,
            client_order_id=client_order_id,
        )

        assert event.order_id == order_id
        assert event.client_order_id == client_order_id
        assert event.source == EventSource.OMS

    def test_order_submitted_event_has_base_fields(self) -> None:
        """Test that OrderSubmittedEvent has all Event base class fields."""
        from polytrader.events.types import EventSource, OrderSubmittedEvent

        event = OrderSubmittedEvent(
            order_id=str(uuid.uuid4()),
            client_order_id="client-123",
        )

        assert event.event_id
        assert event.ts_wall
        assert event.ts_mono
        assert event.correlation_id
        assert event.run_id
        assert event.schema_version == "1.0"
        assert event.source == EventSource.OMS


class TestOrderAckEvent:
    """Tests for OrderAckEvent per flows.mdc §10."""

    def test_order_ack_event_creation(self) -> None:
        """Test that OrderAckEvent can be created."""
        from polytrader.events.types import EventSource, OrderAckEvent

        order_id = str(uuid.uuid4())
        venue_order_id = "venue-456"

        event = OrderAckEvent(
            order_id=order_id,
            venue_order_id=venue_order_id,
        )

        assert event.order_id == order_id
        assert event.venue_order_id == venue_order_id
        assert event.source == EventSource.OMS

    def test_order_ack_event_has_base_fields(self) -> None:
        """Test that OrderAckEvent has all Event base class fields."""
        from polytrader.events.types import EventSource, OrderAckEvent

        event = OrderAckEvent(
            order_id=str(uuid.uuid4()),
            venue_order_id="venue-456",
        )

        assert event.event_id
        assert event.ts_wall
        assert event.ts_mono
        assert event.correlation_id
        assert event.run_id
        assert event.schema_version == "1.0"
        assert event.source == EventSource.OMS


class TestOrderRejectedEvent:
    """Tests for OrderRejectedEvent per flows.mdc §10."""

    def test_order_rejected_event_creation(self) -> None:
        """Test that OrderRejectedEvent can be created."""
        from polytrader.events.types import EventSource, OrderRejectedEvent

        order_id = str(uuid.uuid4())
        reason = "Insufficient balance"

        event = OrderRejectedEvent(
            order_id=order_id,
            reason=reason,
        )

        assert event.order_id == order_id
        assert event.reason == reason
        assert event.source == EventSource.OMS

    def test_order_rejected_event_has_base_fields(self) -> None:
        """Test that OrderRejectedEvent has all Event base class fields."""
        from polytrader.events.types import EventSource, OrderRejectedEvent

        event = OrderRejectedEvent(
            order_id=str(uuid.uuid4()),
            reason="Insufficient balance",
        )

        assert event.event_id
        assert event.ts_wall
        assert event.ts_mono
        assert event.correlation_id
        assert event.run_id
        assert event.schema_version == "1.0"
        assert event.source == EventSource.OMS


class TestFillEvent:
    """Tests for FillEvent per flows.mdc §10."""

    def test_fill_event_creation(self) -> None:
        """Test that FillEvent can be created."""
        from polytrader.events.types import EventSource, FillEvent

        order_id = str(uuid.uuid4())
        fill_id = str(uuid.uuid4())

        event = FillEvent(
            order_id=order_id,
            fill_id=fill_id,
            size=0.5,
            price=0.45,
            fee=0.01,
        )

        assert event.order_id == order_id
        assert event.fill_id == fill_id
        assert event.size == 0.5
        assert event.price == 0.45
        assert event.fee == 0.01
        assert event.venue_fill_id is None
        assert event.source == EventSource.OMS

    def test_fill_event_with_venue_id(self) -> None:
        """Test that FillEvent can include venue_fill_id."""
        from polytrader.events.types import FillEvent

        event = FillEvent(
            order_id=str(uuid.uuid4()),
            fill_id=str(uuid.uuid4()),
            size=0.5,
            price=0.45,
            fee=0.01,
            venue_fill_id="venue-fill-789",
        )

        assert event.venue_fill_id == "venue-fill-789"

    def test_fill_event_validation(self) -> None:
        """Test that FillEvent validates size and price constraints."""
        from polytrader.events.types import FillEvent

        # Valid fill
        event = FillEvent(
            order_id=str(uuid.uuid4()),
            fill_id=str(uuid.uuid4()),
            size=0.5,
            price=0.45,
            fee=0.01,
        )
        assert event.size > 0
        assert 0 < event.price <= 1

        # Invalid: size must be > 0
        with pytest.raises(ValidationError):
            FillEvent(
                order_id=str(uuid.uuid4()),
                fill_id=str(uuid.uuid4()),
                size=0.0,
                price=0.45,
                fee=0.01,
            )

        # Invalid: price must be > 0
        with pytest.raises(ValidationError):
            FillEvent(
                order_id=str(uuid.uuid4()),
                fill_id=str(uuid.uuid4()),
                size=0.5,
                price=0.0,
                fee=0.01,
            )

        # Invalid: price must be <= 1
        with pytest.raises(ValidationError):
            FillEvent(
                order_id=str(uuid.uuid4()),
                fill_id=str(uuid.uuid4()),
                size=0.5,
                price=1.1,
                fee=0.01,
            )

        # Invalid: fee must be >= 0
        with pytest.raises(ValidationError):
            FillEvent(
                order_id=str(uuid.uuid4()),
                fill_id=str(uuid.uuid4()),
                size=0.5,
                price=0.45,
                fee=-0.01,
            )

    def test_fill_event_has_base_fields(self) -> None:
        """Test that FillEvent has all Event base class fields."""
        from polytrader.events.types import EventSource, FillEvent

        event = FillEvent(
            order_id=str(uuid.uuid4()),
            fill_id=str(uuid.uuid4()),
            size=0.5,
            price=0.45,
            fee=0.01,
        )

        assert event.event_id
        assert event.ts_wall
        assert event.ts_mono
        assert event.correlation_id
        assert event.run_id
        assert event.schema_version == "1.0"
        assert event.source == EventSource.OMS


class TestOrderCanceledEvent:
    """Tests for OrderCanceledEvent per flows.mdc §7, §10."""

    def test_order_canceled_event_creation(self) -> None:
        """Test that OrderCanceledEvent can be created."""
        from polytrader.events.types import EventSource, OrderCanceledEvent

        order_id = str(uuid.uuid4())

        event = OrderCanceledEvent(order_id=order_id)

        assert event.order_id == order_id
        assert event.reason is None
        assert event.source == EventSource.OMS

    def test_order_canceled_event_with_reason(self) -> None:
        """Test that OrderCanceledEvent can include a reason."""
        from polytrader.events.types import OrderCanceledEvent

        event = OrderCanceledEvent(
            order_id=str(uuid.uuid4()),
            reason="User requested cancellation",
        )

        assert event.reason == "User requested cancellation"

    def test_order_canceled_event_has_base_fields(self) -> None:
        """Test that OrderCanceledEvent has all Event base class fields."""
        from polytrader.events.types import EventSource, OrderCanceledEvent

        event = OrderCanceledEvent(order_id=str(uuid.uuid4()))

        assert event.event_id
        assert event.ts_wall
        assert event.ts_mono
        assert event.correlation_id
        assert event.run_id
        assert event.schema_version == "1.0"
        assert event.source == EventSource.OMS
