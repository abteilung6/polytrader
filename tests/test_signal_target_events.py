"""Tests for SignalEvent and TargetEvent per flows.mdc §4, §5 and observability.mdc §1."""

import pytest
from pydantic import ValidationError

from polytrader.common.ids import generate_correlation_id
from polytrader.events.types import EventSource, SignalEvent, TargetEvent


class TestSignalEvent:
    """Tests for SignalEvent per flows.mdc §4 and observability.mdc §1."""

    def test_signal_event_creation(self) -> None:
        """Test that SignalEvent can be created with all required fields."""
        event = SignalEvent(
            market_slug="btc-updown-15m-1768122000",
            outcome="UP",
            p_up=0.85,
            p_down=0.15,
            edge=0.55,
            confidence=0.80,
            model_id="simple_threshold",
            model_version="1.0.0",
            rationale="Price 0.2800 below buy threshold 0.3000",
        )

        assert event.market_slug == "btc-updown-15m-1768122000"
        assert event.outcome == "UP"
        assert event.p_up == 0.85
        assert event.p_down == 0.15
        assert event.edge == 0.55
        assert event.confidence == 0.80
        assert event.model_id == "simple_threshold"
        assert event.model_version == "1.0.0"
        assert event.rationale == "Price 0.2800 below buy threshold 0.3000"
        assert event.source == EventSource.STRATEGY

    def test_signal_event_has_base_fields(self) -> None:
        """Test that SignalEvent has all Event base class fields."""
        event = SignalEvent(
            market_slug="btc-updown-15m-1768122000",
            outcome="UP",
            p_up=0.85,
            p_down=0.15,
            edge=0.55,
            confidence=0.80,
            model_id="simple_threshold",
            model_version="1.0.0",
            rationale="Test signal",
        )

        # Check all base Event fields
        assert event.event_id
        assert event.ts_wall
        assert event.ts_mono
        assert event.correlation_id
        assert event.run_id
        assert event.schema_version == "1.0"
        assert event.source == EventSource.STRATEGY

    def test_signal_event_optional_fields(self) -> None:
        """Test that SignalEvent optional fields work correctly."""
        # Without optional fields
        event1 = SignalEvent(
            market_slug="btc-updown-15m-1768122000",
            outcome="UP",
            p_up=0.85,
            p_down=0.15,
            edge=0.55,
            confidence=0.80,
            model_id="simple_threshold",
            model_version="1.0.0",
            rationale="Test",
        )
        assert event1.snapshot_hash is None
        assert event1.snapshot_version is None

        # With optional fields
        event2 = SignalEvent(
            market_slug="btc-updown-15m-1768122000",
            outcome="UP",
            p_up=0.85,
            p_down=0.15,
            edge=0.55,
            confidence=0.80,
            model_id="simple_threshold",
            model_version="1.0.0",
            rationale="Test",
            snapshot_hash="snapshot_hash_xyz",
            snapshot_version="1.0",
        )
        assert event2.snapshot_hash == "snapshot_hash_xyz"
        assert event2.snapshot_version == "1.0"

    def test_signal_event_validation_p_up_range(self) -> None:
        """Test that p_up must be in range [0.0, 1.0]."""
        # Valid: p_up = 0.0
        event1 = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.0,
            p_down=1.0,
            edge=-0.5,
            confidence=0.5,
            model_id="test",
            model_version="1.0",
            rationale="Test",
        )
        assert event1.p_up == 0.0

        # Valid: p_up = 1.0
        event2 = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=1.0,
            p_down=0.0,
            edge=0.5,
            confidence=1.0,
            model_id="test",
            model_version="1.0",
            rationale="Test",
        )
        assert event2.p_up == 1.0

        # Invalid: p_up < 0.0
        with pytest.raises(ValidationError):
            SignalEvent(
                market_slug="test-market",
                outcome="UP",
                p_up=-0.1,
                p_down=1.0,
                edge=0.5,
                confidence=0.5,
                model_id="test",
                model_version="1.0",
                rationale="Test",
            )

        # Invalid: p_up > 1.0
        with pytest.raises(ValidationError):
            SignalEvent(
                market_slug="test-market",
                outcome="UP",
                p_up=1.1,
                p_down=0.0,
                edge=0.5,
                confidence=0.5,
                model_id="test",
                model_version="1.0",
                rationale="Test",
            )

    def test_signal_event_validation_p_down_range(self) -> None:
        """Test that p_down must be in range [0.0, 1.0]."""
        # Valid: p_down = 0.0
        event1 = SignalEvent(
            market_slug="test-market",
            outcome="DOWN",
            p_up=1.0,
            p_down=0.0,
            edge=0.5,
            confidence=0.5,
            model_id="test",
            model_version="1.0",
            rationale="Test",
        )
        assert event1.p_down == 0.0

        # Valid: p_down = 1.0
        event2 = SignalEvent(
            market_slug="test-market",
            outcome="DOWN",
            p_up=0.0,
            p_down=1.0,
            edge=0.5,
            confidence=1.0,
            model_id="test",
            model_version="1.0",
            rationale="Test",
        )
        assert event2.p_down == 1.0

        # Invalid: p_down < 0.0
        with pytest.raises(ValidationError):
            SignalEvent(
                market_slug="test-market",
                outcome="DOWN",
                p_up=1.0,
                p_down=-0.1,
                edge=0.5,
                confidence=0.5,
                model_id="test",
                model_version="1.0",
                rationale="Test",
            )

        # Invalid: p_down > 1.0
        with pytest.raises(ValidationError):
            SignalEvent(
                market_slug="test-market",
                outcome="DOWN",
                p_up=0.0,
                p_down=1.1,
                edge=0.5,
                confidence=0.5,
                model_id="test",
                model_version="1.0",
                rationale="Test",
            )

    def test_signal_event_validation_confidence_range(self) -> None:
        """Test that confidence must be in range [0.0, 1.0]."""
        # Valid: confidence = 0.0
        event1 = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.5,
            p_down=0.5,
            edge=0.0,
            confidence=0.0,
            model_id="test",
            model_version="1.0",
            rationale="Test",
        )
        assert event1.confidence == 0.0

        # Valid: confidence = 1.0
        event2 = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=1.0,
            p_down=0.0,
            edge=0.5,
            confidence=1.0,
            model_id="test",
            model_version="1.0",
            rationale="Test",
        )
        assert event2.confidence == 1.0

        # Invalid: confidence < 0.0
        with pytest.raises(ValidationError):
            SignalEvent(
                market_slug="test-market",
                outcome="UP",
                p_up=0.5,
                p_down=0.5,
                edge=0.0,
                confidence=-0.1,
                model_id="test",
                model_version="1.0",
                rationale="Test",
            )

        # Invalid: confidence > 1.0
        with pytest.raises(ValidationError):
            SignalEvent(
                market_slug="test-market",
                outcome="UP",
                p_up=0.5,
                p_down=0.5,
                edge=0.0,
                confidence=1.1,
                model_id="test",
                model_version="1.0",
                rationale="Test",
            )

    def test_signal_event_edge_can_be_negative(self) -> None:
        """Test that edge can be negative (no edge)."""
        # Valid: negative edge (no edge)
        event = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.4,
            p_down=0.6,
            edge=-0.2,
            confidence=0.3,
            model_id="test",
            model_version="1.0",
            rationale="No edge signal",
        )
        assert event.edge == -0.2

    def test_signal_event_correlation_id_propagation(self) -> None:
        """Test that correlation_id can be propagated from MarketDataEvent."""
        shared_correlation_id = generate_correlation_id()

        event = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.85,
            p_down=0.15,
            edge=0.55,
            confidence=0.80,
            model_id="simple_threshold",
            model_version="1.0.0",
            rationale="Test",
            correlation_id=shared_correlation_id,
        )

        assert event.correlation_id == shared_correlation_id

    def test_signal_event_is_immutable(self) -> None:
        """Test that SignalEvent is immutable (frozen Pydantic model)."""
        event = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.85,
            p_down=0.15,
            edge=0.55,
            confidence=0.80,
            model_id="simple_threshold",
            model_version="1.0.0",
            rationale="Test",
        )

        with pytest.raises(ValidationError):
            event.p_up = 0.9  # type: ignore[misc]

    def test_signal_event_serialization(self) -> None:
        """Test that SignalEvent can be serialized to dict/JSON."""
        event = SignalEvent(
            market_slug="btc-updown-15m-1768122000",
            outcome="UP",
            p_up=0.85,
            p_down=0.15,
            edge=0.55,
            confidence=0.80,
            model_id="simple_threshold",
            model_version="1.0.0",
            rationale="Test signal",
        )

        # Pydantic model can be serialized
        event_dict = event.model_dump()
        assert event_dict["market_slug"] == "btc-updown-15m-1768122000"
        assert event_dict["outcome"] == "UP"
        assert event_dict["p_up"] == 0.85
        assert event_dict["source"] == "strategy"


class TestTargetEvent:
    """Tests for TargetEvent per flows.mdc §5 and observability.mdc §1."""

    def test_target_event_creation(self) -> None:
        """Test that TargetEvent can be created with all required fields."""
        event = TargetEvent(
            market_slug="btc-updown-15m-1768122000",
            outcome="UP",
            target_exposure=1.0,
            target_rationale="Signal edge 0.55 > 0.0, applying fixed size 1.0 USD",
        )

        assert event.market_slug == "btc-updown-15m-1768122000"
        assert event.outcome == "UP"
        assert event.target_exposure == 1.0
        assert event.target_rationale == "Signal edge 0.55 > 0.0, applying fixed size 1.0 USD"
        assert event.constraint_binding == []
        assert event.sizing_metadata == {}
        assert event.source == EventSource.PORTFOLIO

    def test_target_event_has_base_fields(self) -> None:
        """Test that TargetEvent has all Event base class fields."""
        event = TargetEvent(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            target_rationale="Test target",
        )

        # Check all base Event fields
        assert event.event_id
        assert event.ts_wall
        assert event.ts_mono
        assert event.correlation_id
        assert event.run_id
        assert event.schema_version == "1.0"
        assert event.source == EventSource.PORTFOLIO

    def test_target_event_with_constraints(self) -> None:
        """Test that TargetEvent can include constraint binding."""
        event = TargetEvent(
            market_slug="test-market",
            outcome="UP",
            target_exposure=0.5,  # Clipped from 1.0
            target_rationale="Target clipped by constraints",
            constraint_binding=["max_position", "capital_limit"],
        )

        assert event.constraint_binding == ["max_position", "capital_limit"]
        assert event.target_exposure == 0.5

    def test_target_event_with_sizing_metadata(self) -> None:
        """Test that TargetEvent can include sizing metadata."""
        event = TargetEvent(
            market_slug="test-market",
            outcome="UP",
            target_exposure=16.32,
            target_rationale="Profit-targeted sizing",
            sizing_metadata={
                "sizing_method": "profit_targeted",
                "target_profit_usdc": 10.0,
                "needed_profit": 10.0,
                "price": 0.62,
                "required_investment": 16.32,
            },
        )

        assert event.sizing_metadata["sizing_method"] == "profit_targeted"
        assert event.sizing_metadata["target_profit_usdc"] == 10.0
        assert event.sizing_metadata["required_investment"] == 16.32

    def test_target_event_validation_exposure_non_negative(self) -> None:
        """Test that target_exposure must be >= 0.0."""
        # Valid: target_exposure = 0.0 (no action)
        event1 = TargetEvent(
            market_slug="test-market",
            outcome="UP",
            target_exposure=0.0,
            target_rationale="No target (zero exposure)",
        )
        assert event1.target_exposure == 0.0

        # Valid: target_exposure > 0.0
        event2 = TargetEvent(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            target_rationale="Positive target",
        )
        assert event2.target_exposure == 1.0

        # Invalid: target_exposure < 0.0
        with pytest.raises(ValidationError):
            TargetEvent(
                market_slug="test-market",
                outcome="UP",
                target_exposure=-0.1,
                target_rationale="Invalid negative target",
            )

    def test_target_event_default_constraint_binding(self) -> None:
        """Test that constraint_binding defaults to empty list."""
        event = TargetEvent(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            target_rationale="Test",
        )

        assert event.constraint_binding == []
        assert isinstance(event.constraint_binding, list)

    def test_target_event_default_sizing_metadata(self) -> None:
        """Test that sizing_metadata defaults to empty dict."""
        event = TargetEvent(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            target_rationale="Test",
        )

        assert event.sizing_metadata == {}
        assert isinstance(event.sizing_metadata, dict)

    def test_target_event_correlation_id_propagation(self) -> None:
        """Test that correlation_id can be propagated from SignalEvent."""
        shared_correlation_id = generate_correlation_id()

        event = TargetEvent(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            target_rationale="Test",
            correlation_id=shared_correlation_id,
        )

        assert event.correlation_id == shared_correlation_id

    def test_target_event_is_immutable(self) -> None:
        """Test that TargetEvent is immutable (frozen Pydantic model)."""
        event = TargetEvent(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            target_rationale="Test",
        )

        with pytest.raises(ValidationError):
            event.target_exposure = 2.0  # type: ignore[misc]

    def test_target_event_serialization(self) -> None:
        """Test that TargetEvent can be serialized to dict/JSON."""
        event = TargetEvent(
            market_slug="btc-updown-15m-1768122000",
            outcome="UP",
            target_exposure=1.0,
            target_rationale="Test target",
            constraint_binding=["max_position"],
            sizing_metadata={"current_position": 0.0},
        )

        # Pydantic model can be serialized
        event_dict = event.model_dump()
        assert event_dict["market_slug"] == "btc-updown-15m-1768122000"
        assert event_dict["outcome"] == "UP"
        assert event_dict["target_exposure"] == 1.0
        assert event_dict["constraint_binding"] == ["max_position"]
        assert event_dict["sizing_metadata"] == {"current_position": 0.0}
        assert event_dict["source"] == "portfolio"
