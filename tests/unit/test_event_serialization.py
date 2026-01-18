"""Unit tests for event serialization functions."""

from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from polytrader.events.stores import EventDbFields, serialize_event_for_db
from polytrader.events.types import EventSource, OrderCreatedEvent, SystemStartedEvent


class TestEventDbFields:
    def test_model_is_frozen(self) -> None:
        fields = EventDbFields(
            event_id=UUID("12345678-1234-5678-1234-567812345678"),
            ts_wall=datetime.now(),
            ts_mono=12345.0,
            run_id="run-123",
            source="ops",
            event_type="TestEvent",
        )
        with pytest.raises(ValidationError):
            fields.event_id = UUID("00000000-0000-0000-0000-000000000000")  # type: ignore[misc]

    def test_model_validates_ts_mono_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            EventDbFields(
                event_id=UUID("12345678-1234-5678-1234-567812345678"),
                ts_wall=datetime.now(),
                ts_mono=-1.0,
                run_id="run-123",
                source="ops",
                event_type="TestEvent",
            )

    def test_model_defaults(self) -> None:
        fields = EventDbFields(
            event_id=UUID("12345678-1234-5678-1234-567812345678"),
            ts_wall=datetime.now(),
            ts_mono=12345.0,
            run_id="run-123",
            source="ops",
            event_type="TestEvent",
        )
        assert fields.correlation_id is None
        assert fields.schema_version == "1.0"
        assert fields.event_data == {}


class TestSerializeEventForDb:
    def test_serialize_system_started_event(self) -> None:
        event = SystemStartedEvent()
        fields = serialize_event_for_db(event)
        assert isinstance(fields, EventDbFields)
        assert isinstance(fields.event_id, UUID)
        assert str(fields.event_id) == event.event_id
        assert fields.source == "ops"
        assert fields.event_type == "SystemStartedEvent"
        assert len(fields.event_data) == 0

    def test_serialize_order_created_event(self) -> None:
        from polytrader.events.types import OrderIntentEvent

        intent = OrderIntentEvent(
            market_slug="btc-updown-15m",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=100.0,
            reason="Test",
        )
        event = OrderCreatedEvent(
            order_id="order-123",
            client_order_id="client-456",
            intent=intent,
        )
        fields = serialize_event_for_db(event)
        assert fields.event_type == "OrderCreatedEvent"
        assert fields.source == "oms"
        assert fields.event_data["order_id"] == "order-123"

    def test_serialize_event_source_enum(self) -> None:
        event = SystemStartedEvent.model_construct(source=EventSource.RISK)
        fields = serialize_event_for_db(event)
        assert fields.source == "risk"

    def test_serialize_returns_all_required_fields(self) -> None:
        event = SystemStartedEvent()
        fields = serialize_event_for_db(event)
        dumped = fields.model_dump()
        required_keys = {
            "event_id",
            "ts_wall",
            "ts_mono",
            "correlation_id",
            "run_id",
            "schema_version",
            "source",
            "event_type",
            "event_data",
        }
        assert set(dumped.keys()) == required_keys

    def test_serialize_model_dump_unpacking(self) -> None:
        event = SystemStartedEvent()
        fields = serialize_event_for_db(event)
        dumped = fields.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["event_id"] == fields.event_id
