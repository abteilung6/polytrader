"""Integration tests for signal→intent strategy_id propagation.

Per Commit 1.1: Test end-to-end that SignalEvent.model_id propagates
to OrderIntentEvent.strategy_id.
"""

import pytest

from polytrader.events.bus import EventBus
from polytrader.events.store import MemoryEventStore
from polytrader.events.types import OrderIntentEvent
from polytrader.portfolio.intents import convert_target_to_intent
from polytrader.portfolio.models import Target
from tests.factories.events import (
    create_market_data_event,
    create_signal_event,
)


class TestSignalToIntentStrategyIdPropagation:
    """Integration tests for strategy_id propagation from SignalEvent to OrderIntentEvent."""

    def test_end_to_end_strategy_id_propagation(self) -> None:
        """Test end-to-end: SignalEvent.model_id → OrderIntentEvent.strategy_id."""
        # Create signal with model_id
        signal = create_signal_event(
            market_slug="test-market",
            outcome="UP",
            model_id="simple_threshold",
            correlation_id="corr-123",
        )

        # Create market data
        market_data = create_market_data_event(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.45,
            best_ask=0.55,
        )

        # Create target
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        # Convert to intent
        intent = convert_target_to_intent(target, market_data, signal, size=10.0)

        # Assert strategy_id propagated
        assert intent is not None
        assert isinstance(intent, OrderIntentEvent)
        assert intent.strategy_id == "simple_threshold"
        assert intent.strategy_id == signal.model_id
        assert intent.correlation_id == signal.correlation_id

    def test_multiple_signals_different_strategy_ids(self) -> None:
        """Test that multiple signals with different model_ids produce different strategy_ids."""
        signals = [
            create_signal_event(model_id="strategy_a", correlation_id="corr-1"),
            create_signal_event(model_id="strategy_b", correlation_id="corr-2"),
            create_signal_event(model_id="strategy_c", correlation_id="corr-3"),
        ]

        market_data = create_market_data_event()
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        intents = []
        for signal in signals:
            intent = convert_target_to_intent(target, market_data, signal, size=10.0)
            assert intent is not None
            intents.append(intent)

        # Assert each intent has correct strategy_id
        assert intents[0].strategy_id == "strategy_a"
        assert intents[1].strategy_id == "strategy_b"
        assert intents[2].strategy_id == "strategy_c"

        # Assert all strategy_ids are different
        assert len({intent.strategy_id for intent in intents}) == 3

    @pytest.mark.asyncio
    async def test_strategy_id_propagates_through_event_bus(self) -> None:
        """Test that strategy_id is preserved when events flow through event bus."""
        bus = EventBus(store=MemoryEventStore())

        # Create signal
        signal = create_signal_event(model_id="simple_threshold", correlation_id="corr-123")

        # Publish signal
        from polytrader.events import SIGNALS

        await bus.publish(SIGNALS, signal)

        # Create intent from signal
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

        # Assert strategy_id preserved
        assert intent is not None
        assert intent.strategy_id == signal.model_id

        # Publish intent
        from polytrader.events import PROPOSALS

        await bus.publish(PROPOSALS, intent)

        # Verify intent can be retrieved with strategy_id
        assert intent.strategy_id == "simple_threshold"
