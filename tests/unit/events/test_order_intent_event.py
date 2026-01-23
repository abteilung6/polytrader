"""Unit tests for OrderIntentEvent strategy_id field.

Per Commit 1.1: Test OrderIntentEvent requires and validates strategy_id field.
"""

import pytest
from pydantic import ValidationError

from polytrader.events.types import EventSource, OrderIntentEvent
from tests.factories.events import create_order_intent_event


class TestOrderIntentEventStrategyId:
    """Tests for OrderIntentEvent strategy_id field validation."""

    def test_order_intent_event_requires_strategy_id(self) -> None:
        """Test that OrderIntentEvent requires strategy_id field."""
        # Should raise ValidationError if strategy_id is missing
        with pytest.raises(ValidationError) as exc_info:
            OrderIntentEvent(  # type: ignore[call-arg]
                market_slug="test-market",
                outcome="UP",
                side="BUY",
                size=10.0,
                limit_price=0.5,
                target_price=0.6,
                reason="Test intent",
                # strategy_id missing - intentionally omitted to test validation
            )
        assert "strategy_id" in str(exc_info.value)

    def test_order_intent_event_with_valid_strategy_id(self) -> None:
        """Test that OrderIntentEvent creates successfully with valid strategy_id."""
        intent = create_order_intent_event(strategy_id="test_strategy")
        assert intent.strategy_id == "test_strategy"
        assert intent.market_slug == "test-market"
        assert intent.outcome == "UP"
        assert intent.side == "BUY"

    def test_order_intent_event_has_base_fields(self) -> None:
        """Test that OrderIntentEvent has all Event base class fields."""
        intent = create_order_intent_event(strategy_id="test_strategy")
        # Check base Event fields
        assert intent.event_id is not None
        assert intent.ts_wall is not None
        assert intent.ts_mono is not None
        assert intent.correlation_id is not None
        assert intent.run_id is not None
        assert intent.schema_version == "1.0"
        assert intent.source == EventSource.PORTFOLIO

    def test_order_intent_event_strategy_id_propagation(self) -> None:
        """Test that strategy_id is stored and accessible."""
        intent = create_order_intent_event(strategy_id="strategy_a")
        assert intent.strategy_id == "strategy_a"

        intent2 = create_order_intent_event(strategy_id="strategy_b")
        assert intent2.strategy_id == "strategy_b"
        assert intent2.strategy_id != intent.strategy_id

    @pytest.mark.parametrize(
        "strategy_id",
        [
            "simple_threshold",
            "winner_threshold",
            "strategy_with_underscores",
            "strategy-with-dashes",
            "strategy123",
        ],
    )
    def test_order_intent_event_accepts_various_strategy_ids(self, strategy_id: str) -> None:
        """Test that OrderIntentEvent accepts various strategy_id formats."""
        intent = create_order_intent_event(strategy_id=strategy_id)
        assert intent.strategy_id == strategy_id
