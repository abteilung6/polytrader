"""Integration tests for strategy metrics per observability.mdc §4.

Per Commit 4: Integrate strategy metrics in strategy and portfolio layers.
"""

from polytrader.events.types import MarketDataEvent, SignalEvent
from polytrader.obs.metrics import MemoryMetricsCollector, set_metrics_collector
from polytrader.portfolio.intents import convert_target_to_intent
from polytrader.portfolio.models import Target
from polytrader.store import MemoryMarketDataStore
from polytrader.strategies.simple_threshold.strategy import SimpleThresholdStrategy


class TestStrategyMetrics:
    """Integration tests for strategy metrics emission."""

    def test_strategy_eval_metrics_on_signal_generation(self) -> None:
        """Test that strategy_eval_total and strategy_eval_latency_ms are emitted."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        store = MemoryMarketDataStore()
        strategy = SimpleThresholdStrategy(
            market_slug="test-market",
            store=store,
            buy_threshold=0.30,
            min_history=0,  # No history requirement for test
        )

        # Add market data to store (to meet history requirement)
        for _ in range(30):
            market_data = MarketDataEvent(
                market_slug="test-market",
                outcome="UP",
                best_bid=0.25,
                best_ask=0.30,
            )
            store.add(market_data)

        # Create market data that will trigger a signal (price below threshold)
        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.20,
            best_ask=0.25,  # mid = 0.225, below threshold 0.30
        )

        # Evaluate strategy
        signal = strategy.evaluate(market_data)

        # Verify signal was generated
        assert signal is not None
        assert signal.model_id == "simple_threshold"

        # Verify strategy metrics were emitted
        assert (
            collector.get_counter("strategy_eval_total", labels={"strategy_id": "simple_threshold"})
            == 1
        )

        # Verify latency histogram was recorded
        percentiles = collector.get_histogram_percentiles(
            "strategy_eval_latency_ms", labels={"strategy_id": "simple_threshold"}
        )
        assert 0.5 in percentiles
        assert percentiles[0.5] >= 0.0  # Latency should be non-negative

    def test_strategy_eval_metrics_on_no_signal(self) -> None:
        """Test that metrics are emitted even when no signal is generated."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        store = MemoryMarketDataStore()
        strategy = SimpleThresholdStrategy(
            market_slug="test-market",
            store=store,
            buy_threshold=0.30,
            min_history=0,
        )

        # Add market data to store
        for _ in range(30):
            market_data = MarketDataEvent(
                market_slug="test-market",
                outcome="UP",
                best_bid=0.25,
                best_ask=0.30,
            )
            store.add(market_data)

        # Create market data that will NOT trigger a signal (price above threshold)
        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.35,
            best_ask=0.40,  # mid = 0.375, above threshold 0.30
        )

        # Evaluate strategy (should return None)
        signal = strategy.evaluate(market_data)

        # Verify no signal was generated
        assert signal is None

        # Verify strategy metrics were still emitted (evaluation happened)
        assert (
            collector.get_counter("strategy_eval_total", labels={"strategy_id": "simple_threshold"})
            == 1
        )

        # Verify latency histogram was recorded
        percentiles = collector.get_histogram_percentiles(
            "strategy_eval_latency_ms", labels={"strategy_id": "simple_threshold"}
        )
        assert 0.5 in percentiles

    def test_strategy_eval_latency_measurement(self) -> None:
        """Test that strategy evaluation latency is measured correctly."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        store = MemoryMarketDataStore()
        strategy = SimpleThresholdStrategy(
            market_slug="test-market",
            store=store,
            buy_threshold=0.30,
            min_history=0,
        )

        # Add market data to store
        for _ in range(30):
            market_data = MarketDataEvent(
                market_slug="test-market",
                outcome="UP",
                best_bid=0.25,
                best_ask=0.30,
            )
            store.add(market_data)

        # Create market data that will trigger a signal
        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.20,
            best_ask=0.25,
        )

        # Evaluate multiple times to get latency distribution
        for _ in range(5):
            strategy.evaluate(market_data)

        # Verify multiple evaluations were recorded
        assert (
            collector.get_counter("strategy_eval_total", labels={"strategy_id": "simple_threshold"})
            == 5
        )

        # Verify latency histogram has multiple values
        percentiles = collector.get_histogram_percentiles(
            "strategy_eval_latency_ms", labels={"strategy_id": "simple_threshold"}
        )
        assert 0.5 in percentiles
        # Latency should be very small (< 100ms for fast strategy)
        assert percentiles[0.5] < 100.0

    def test_order_intent_metrics(self) -> None:
        """Test that order_intents_total is emitted when creating OrderIntentEvent."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        # Create target
        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        # Create market data
        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.25,
            best_ask=0.30,
        )

        # Create signal with model_id
        signal = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.7,
            p_down=0.3,
            edge=0.4,
            confidence=0.8,
            model_id="simple_threshold",
            model_version="1.0.0",
            rationale="Test signal",
        )

        # Convert target to intent
        intent = convert_target_to_intent(target, market_data, signal, size=1.0)

        # Verify intent was created
        assert intent is not None
        assert intent.market_slug == "test-market"
        assert intent.outcome == "UP"
        assert intent.side == "BUY"

        # Verify order intent metric was emitted
        assert (
            collector.get_counter(
                "order_intents_total",
                labels={
                    "strategy_id": "simple_threshold",
                    "market_slug": "test-market",
                    "outcome": "UP",
                    "side": "BUY",
                },
            )
            == 1
        )

    def test_order_intent_metrics_multiple_intents(self) -> None:
        """Test that order_intents_total works correctly with multiple intents."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.25,
            best_ask=0.30,
        )

        signal = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.7,
            p_down=0.3,
            edge=0.4,
            confidence=0.8,
            model_id="simple_threshold",
            model_version="1.0.0",
            rationale="Test signal",
        )

        # Create multiple intents
        for i in range(3):
            target = Target(
                market_slug="test-market",
                outcome="UP",
                target_exposure=1.0,
                rationale=f"Test target {i}",
                constraint_binding=[],
                sizing_metadata={},
            )
            intent = convert_target_to_intent(target, market_data, signal, size=1.0)
            assert intent is not None

        # Verify counter incremented correctly
        assert (
            collector.get_counter(
                "order_intents_total",
                labels={
                    "strategy_id": "simple_threshold",
                    "market_slug": "test-market",
                    "outcome": "UP",
                    "side": "BUY",
                },
            )
            == 3
        )

    def test_order_intent_metrics_different_labels(self) -> None:
        """Test that order_intents_total works correctly with different labels."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        signal1 = SignalEvent(
            market_slug="test-market-1",
            outcome="UP",
            p_up=0.7,
            p_down=0.3,
            edge=0.4,
            confidence=0.8,
            model_id="simple_threshold",
            model_version="1.0.0",
            rationale="Test signal 1",
        )

        signal2 = SignalEvent(
            market_slug="test-market-2",
            outcome="DOWN",
            p_up=0.3,
            p_down=0.7,
            edge=0.4,
            confidence=0.8,
            model_id="winner_threshold",
            model_version="1.0.0",
            rationale="Test signal 2",
        )

        market_data1 = MarketDataEvent(
            market_slug="test-market-1",
            outcome="UP",
            best_bid=0.25,
            best_ask=0.30,
        )

        market_data2 = MarketDataEvent(
            market_slug="test-market-2",
            outcome="DOWN",
            best_bid=0.25,
            best_ask=0.30,
        )

        # Create intents with different labels
        target1 = Target(
            market_slug="test-market-1",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target 1",
            constraint_binding=[],
            sizing_metadata={},
        )
        intent1 = convert_target_to_intent(target1, market_data1, signal1, size=1.0)
        assert intent1 is not None

        target2 = Target(
            market_slug="test-market-2",
            outcome="DOWN",
            target_exposure=1.0,
            rationale="Test target 2",
            constraint_binding=[],
            sizing_metadata={},
        )
        intent2 = convert_target_to_intent(target2, market_data2, signal2, size=1.0)
        assert intent2 is not None

        # Verify metrics are isolated per label combination
        assert (
            collector.get_counter(
                "order_intents_total",
                labels={
                    "strategy_id": "simple_threshold",
                    "market_slug": "test-market-1",
                    "outcome": "UP",
                    "side": "BUY",
                },
            )
            == 1
        )
        assert (
            collector.get_counter(
                "order_intents_total",
                labels={
                    "strategy_id": "winner_threshold",
                    "market_slug": "test-market-2",
                    "outcome": "DOWN",
                    "side": "BUY",
                },
            )
            == 1
        )

    def test_order_intent_metrics_no_intent_when_size_zero(self) -> None:
        """Test that order_intents_total is NOT emitted when intent is None (size <= 0)."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

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
            best_bid=0.25,
            best_ask=0.30,
        )

        signal = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.7,
            p_down=0.3,
            edge=0.4,
            confidence=0.8,
            model_id="simple_threshold",
            model_version="1.0.0",
            rationale="Test signal",
        )

        # Convert with size = 0 (should return None)
        intent = convert_target_to_intent(target, market_data, signal, size=0.0)

        # Verify no intent was created
        assert intent is None

        # Verify no metric was emitted
        assert (
            collector.get_counter(
                "order_intents_total",
                labels={
                    "strategy_id": "simple_threshold",
                    "market_slug": "test-market",
                    "outcome": "UP",
                    "side": "BUY",
                },
            )
            == 0
        )

    def test_order_intent_metrics_no_intent_when_no_liquidity(self) -> None:
        """Test that order_intents_total is NOT emitted when no liquidity (best_ask = 0)."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        target = Target(
            market_slug="test-market",
            outcome="UP",
            target_exposure=1.0,
            rationale="Test target",
            constraint_binding=[],
            sizing_metadata={},
        )

        # Market data with no liquidity (best_ask = 0)
        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.0,
            best_ask=0.0,
        )

        signal = SignalEvent(
            market_slug="test-market",
            outcome="UP",
            p_up=0.7,
            p_down=0.3,
            edge=0.4,
            confidence=0.8,
            model_id="simple_threshold",
            model_version="1.0.0",
            rationale="Test signal",
        )

        # Convert with no liquidity (should return None)
        intent = convert_target_to_intent(target, market_data, signal, size=1.0)

        # Verify no intent was created
        assert intent is None

        # Verify no metric was emitted
        assert (
            collector.get_counter(
                "order_intents_total",
                labels={
                    "strategy_id": "simple_threshold",
                    "market_slug": "test-market",
                    "outcome": "UP",
                    "side": "BUY",
                },
            )
            == 0
        )
