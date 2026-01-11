"""Tests for signal to target conversion."""

from polytrader.events.types import SignalEvent
from polytrader.portfolio.targets import convert_signal_to_target


class TestConvertSignalToTarget:
    """Tests for convert_signal_to_target function."""

    def test_convert_signal_to_target_positive_edge(self) -> None:
        """Test conversion with positive edge and confidence."""
        signal = SignalEvent(
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

        target = convert_signal_to_target(signal, fixed_size_usd=1.0)

        assert target is not None
        assert target.market_slug == "btc-updown-15m-1768122000"
        assert target.outcome == "UP"  # p_up > p_down
        assert target.target_exposure == 1.0
        assert "edge 0.5500" in target.rationale
        assert "confidence 0.8000" in target.rationale
        assert target.constraint_binding == []
        assert target.sizing_metadata["signal_edge"] == 0.55
        assert target.sizing_metadata["signal_confidence"] == 0.80
        assert target.sizing_metadata["size_method"] == "fixed"
        assert target.sizing_metadata["fixed_size_usd"] == 1.0

    def test_convert_signal_to_target_down_outcome(self) -> None:
        """Test conversion when p_down > p_up."""
        signal = SignalEvent(
            market_slug="test-market",
            outcome="DOWN",
            p_up=0.20,
            p_down=0.80,
            edge=0.60,
            confidence=0.90,
            model_id="test",
            model_version="1.0.0",
            rationale="Test",
        )

        target = convert_signal_to_target(signal, fixed_size_usd=2.0)

        assert target is not None
        assert target.outcome == "DOWN"  # p_down > p_up
        assert target.target_exposure == 2.0

    def test_convert_signal_to_target_zero_edge(self) -> None:
        """Test that zero edge returns None."""
        signal = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.5,
            p_down=0.5,
            edge=0.0,
            confidence=0.80,
            model_id="test",
            model_version="1.0.0",
            rationale="No edge",
        )

        target = convert_signal_to_target(signal)

        assert target is None

    def test_convert_signal_to_target_negative_edge(self) -> None:
        """Test that negative edge returns None."""
        signal = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.4,
            p_down=0.6,
            edge=-0.2,
            confidence=0.50,
            model_id="test",
            model_version="1.0.0",
            rationale="Negative edge",
        )

        target = convert_signal_to_target(signal)

        assert target is None

    def test_convert_signal_to_target_zero_confidence(self) -> None:
        """Test that zero confidence returns None."""
        signal = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.85,
            p_down=0.15,
            edge=0.55,
            confidence=0.0,
            model_id="test",
            model_version="1.0.0",
            rationale="No confidence",
        )

        target = convert_signal_to_target(signal)

        assert target is None

    def test_convert_signal_to_target_custom_fixed_size(self) -> None:
        """Test conversion with custom fixed size."""
        signal = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.85,
            p_down=0.15,
            edge=0.55,
            confidence=0.80,
            model_id="test",
            model_version="1.0.0",
            rationale="Test",
        )

        target = convert_signal_to_target(signal, fixed_size_usd=5.0)

        assert target is not None
        assert target.target_exposure == 5.0
        assert target.sizing_metadata["fixed_size_usd"] == 5.0
        assert "5.00 USD" in target.rationale

    def test_convert_signal_to_target_sizing_metadata(self) -> None:
        """Test that sizing_metadata includes signal information."""
        signal = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.85,
            p_down=0.15,
            edge=0.55,
            confidence=0.80,
            model_id="test",
            model_version="1.0.0",
            rationale="Test",
        )

        target = convert_signal_to_target(signal, fixed_size_usd=1.0)

        assert target is not None
        assert target.sizing_metadata["signal_edge"] == 0.55
        assert target.sizing_metadata["signal_confidence"] == 0.80
        assert target.sizing_metadata["signal_p_up"] == 0.85
        assert target.sizing_metadata["signal_p_down"] == 0.15
        assert target.sizing_metadata["size_method"] == "fixed"
