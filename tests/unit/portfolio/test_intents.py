"""Unit tests for convert_target_to_intent strategy_id propagation.

Per Commit 1.1: Test that strategy_id propagates from SignalEvent.model_id to OrderIntentEvent.
"""

import pytest

from polytrader.portfolio.intents import convert_target_to_intent
from polytrader.portfolio.models import Target
from tests.factories.events import (
    create_market_data_event,
    create_signal_event,
)


class TestConvertTargetToIntentStrategyId:
    """Tests for strategy_id propagation in convert_target_to_intent()."""

    def test_strategy_id_propagates_from_signal_model_id(self) -> None:
        """Test that strategy_id propagates from SignalEvent.model_id."""
        signal = create_signal_event(model_id="strategy_a")
        market_data = create_market_data_event()
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        intent = convert_target_to_intent(target, market_data, signal, size=10.0)

        assert intent is not None
        assert intent.strategy_id == "strategy_a"
        assert intent.strategy_id == signal.model_id

    def test_strategy_id_propagates_correlation_id(self) -> None:
        """Test that correlation_id is also propagated from signal."""
        signal = create_signal_event(model_id="strategy_a", correlation_id="corr-123")
        market_data = create_market_data_event()
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        intent = convert_target_to_intent(target, market_data, signal, size=10.0)

        assert intent is not None
        assert intent.strategy_id == signal.model_id
        assert intent.correlation_id == signal.correlation_id

    @pytest.mark.parametrize(
        "model_id",
        [
            "simple_threshold",
            "winner_threshold",
            "strategy_with_underscores",
            "strategy-with-dashes",
        ],
    )
    def test_strategy_id_propagates_various_model_ids(self, model_id: str) -> None:
        """Test that various model_id values propagate correctly."""
        signal = create_signal_event(model_id=model_id)
        market_data = create_market_data_event()
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        intent = convert_target_to_intent(target, market_data, signal, size=10.0)

        assert intent is not None
        assert intent.strategy_id == model_id
        assert intent.strategy_id == signal.model_id

    def test_strategy_id_propagates_with_different_signals(self) -> None:
        """Test that different signals produce different strategy_ids."""
        signal1 = create_signal_event(model_id="strategy_a")
        signal2 = create_signal_event(model_id="strategy_b")
        market_data = create_market_data_event()
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        intent1 = convert_target_to_intent(target, market_data, signal1, size=10.0)
        intent2 = convert_target_to_intent(target, market_data, signal2, size=10.0)

        assert intent1 is not None
        assert intent2 is not None
        assert intent1.strategy_id == "strategy_a"
        assert intent2.strategy_id == "strategy_b"
        assert intent1.strategy_id != intent2.strategy_id

    def test_strategy_id_propagates_when_size_zero_returns_none(self) -> None:
        """Test that None is returned when size is zero (no strategy_id propagation needed)."""
        signal = create_signal_event(model_id="strategy_a")
        market_data = create_market_data_event()
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        intent = convert_target_to_intent(target, market_data, signal, size=0.0)

        assert intent is None

    def test_strategy_id_propagates_when_no_liquidity_returns_none(self) -> None:
        """Test that None is returned when no liquidity (no strategy_id propagation needed)."""
        signal = create_signal_event(model_id="strategy_a")
        market_data = create_market_data_event(best_ask=0.0)  # No liquidity
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        intent = convert_target_to_intent(target, market_data, signal, size=10.0)

        assert intent is None
