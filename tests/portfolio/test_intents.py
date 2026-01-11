"""Tests for target to order intent conversion."""

from polytrader.common.ids import generate_correlation_id
from polytrader.events.types import EventSource, MarketDataEvent, SignalEvent
from polytrader.portfolio.intents import convert_target_to_intent
from polytrader.portfolio.models import Target


class TestConvertTargetToIntent:
    """Tests for convert_target_to_intent function."""

    def test_convert_target_to_intent_positive_size(self) -> None:
        """Test conversion with positive size."""
        target = Target(
            market_slug="btc-updown-15m-1768122000",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        market_data = MarketDataEvent(
            market_slug="btc-updown-15m-1768122000",
            outcome="UP",
            best_bid=0.45,
            best_ask=0.50,
        )

        signal = SignalEvent(
            market_slug="btc-updown-15m-1768122000",
            outcome="UP",
            p_up=0.85,
            p_down=0.15,
            edge=0.55,
            confidence=0.80,
            model_id="test",
            model_version="1.0.0",
            rationale="Test signal",
        )

        intent = convert_target_to_intent(
            target=target,
            market_data=market_data,
            signal=signal,
            size=1.0,
        )

        assert intent is not None
        assert intent.market_slug == "btc-updown-15m-1768122000"
        assert intent.outcome == "UP"
        assert intent.side == "BUY"
        assert intent.size == 1.0
        assert intent.limit_price == 0.50  # best_ask for BUY
        assert intent.target_price == 0.475  # mid price
        assert intent.correlation_id == signal.correlation_id
        assert intent.source == EventSource.PORTFOLIO
        assert intent.ttl_s == 60.0

    def test_convert_target_to_intent_zero_liquidity(self) -> None:
        """Test that zero liquidity (best_ask=0.0) returns None."""
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.0010,
            best_ask=0.0,  # No liquidity
        )

        signal = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.85,
            p_down=0.15,
            edge=0.55,
            confidence=0.80,
            model_id="test",
            model_version="1.0.0",
            rationale="Test signal",
        )

        intent = convert_target_to_intent(
            target=target,
            market_data=market_data,
            signal=signal,
            size=1.0,
        )

        assert intent is None, "Should return None when best_ask=0.0 (no liquidity)"

    def test_convert_target_to_intent_zero_size(self) -> None:
        """Test that zero size returns None."""
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.45,
            best_ask=0.50,
        )

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

        intent = convert_target_to_intent(
            target=target,
            market_data=market_data,
            signal=signal,
            size=0.0,
        )

        assert intent is None

    def test_convert_target_to_intent_negative_size(self) -> None:
        """Test that negative size returns None."""
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.45,
            best_ask=0.50,
        )

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

        intent = convert_target_to_intent(
            target=target,
            market_data=market_data,
            signal=signal,
            size=-0.1,
        )

        assert intent is None

    def test_convert_target_to_intent_correlation_id_propagation(self) -> None:
        """Test that correlation_id propagates from signal."""
        shared_correlation_id = generate_correlation_id()

        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.45,
            best_ask=0.50,
        )

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
            correlation_id=shared_correlation_id,
        )

        intent = convert_target_to_intent(
            target=target,
            market_data=market_data,
            signal=signal,
            size=1.0,
        )

        assert intent is not None
        assert intent.correlation_id == shared_correlation_id
        assert intent.correlation_id == signal.correlation_id

    def test_convert_target_to_intent_reason_includes_rationale(self) -> None:
        """Test that reason includes target rationale."""
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Signal edge 0.55 > 0",
            constraint_binding=[],
            sizing_metadata={},
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.45,
            best_ask=0.50,
        )

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

        intent = convert_target_to_intent(
            target=target,
            market_data=market_data,
            signal=signal,
            size=1.0,
        )

        assert intent is not None
        assert "Signal edge 0.55 > 0" in intent.reason
        assert "Order size: 1.00 USD" in intent.reason
        assert "limit_price: 0.5000" in intent.reason

    def test_convert_target_to_intent_always_buy(self) -> None:
        """Test that all orders are BUY (no SELL orders yet)."""
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.45,
            best_ask=0.50,
        )

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

        intent = convert_target_to_intent(
            target=target,
            market_data=market_data,
            signal=signal,
            size=1.0,
        )

        assert intent is not None
        assert intent.side == "BUY"
