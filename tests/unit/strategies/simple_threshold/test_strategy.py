"""Tests for SimpleThresholdStrategy."""

import time

import pytest

from polytrader.events.types import MarketDataEvent, SignalEvent
from polytrader.store import MemoryMarketDataStore
from polytrader.strategies.simple_threshold import SimpleThresholdStrategy


class TestSimpleThresholdStrategy:
    """Tests for SimpleThresholdStrategy."""

    def test_strategy_generates_signal_below_threshold(self) -> None:
        """Test that strategy generates signal when price < threshold."""
        store = MemoryMarketDataStore()
        strategy = SimpleThresholdStrategy(
            market_slug="test-market",
            store=store,
            buy_threshold=0.30,
            min_history=0,  # No history requirement for this test
        )

        # Add some history
        for _i in range(5):
            event = MarketDataEvent(
                market_slug="test-market",
                outcome="UP",
                best_bid=0.25,
                best_ask=0.30,
            )
            store.add(event)

        # Price below threshold should generate signal
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.25,
            best_ask=0.30,
        )
        signal = strategy.evaluate(event)

        assert signal is not None
        assert isinstance(signal, SignalEvent)
        assert signal.market_slug == "test-market"
        assert signal.outcome == "UP"
        assert signal.model_id == "simple_threshold"
        assert signal.edge > 0.0
        assert signal.confidence > 0.0

    def test_strategy_no_signal_above_threshold(self) -> None:
        """Test that strategy returns None when price >= threshold."""
        store = MemoryMarketDataStore()
        strategy = SimpleThresholdStrategy(
            market_slug="test-market",
            store=store,
            buy_threshold=0.30,
            min_history=0,
        )

        # Add some history
        for _i in range(5):
            event = MarketDataEvent(
                market_slug="test-market",
                outcome="UP",
                best_bid=0.35,
                best_ask=0.40,
            )
            store.add(event)

        # Price above threshold should not generate signal
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.35,
            best_ask=0.40,
        )
        signal = strategy.evaluate(event)

        assert signal is None

    def test_strategy_requires_min_history(self) -> None:
        """Test that strategy requires min_history before generating signals."""
        store = MemoryMarketDataStore()
        strategy = SimpleThresholdStrategy(
            market_slug="test-market",
            store=store,
            buy_threshold=0.30,
            min_history=10,
        )

        # Add only 5 events (less than min_history)
        for _i in range(5):
            event = MarketDataEvent(
                market_slug="test-market",
                outcome="UP",
                best_bid=0.25,
                best_ask=0.30,
            )
            store.add(event)

        # Price below threshold but insufficient history
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.25,
            best_ask=0.30,
        )
        signal = strategy.evaluate(event)

        assert signal is None

        # Add more history to reach min_history
        for _i in range(5):
            event = MarketDataEvent(
                market_slug="test-market",
                outcome="UP",
                best_bid=0.25,
                best_ask=0.30,
            )
            store.add(event)

        # Now should generate signal
        signal = strategy.evaluate(event)
        assert signal is not None

    def test_strategy_probability_calculation(self) -> None:
        """Test that p_up and p_down are calculated correctly."""
        store = MemoryMarketDataStore()
        strategy = SimpleThresholdStrategy(
            market_slug="test-market",
            store=store,
            buy_threshold=0.30,
            min_history=0,
        )

        # Add history
        for _i in range(5):
            event = MarketDataEvent(
                market_slug="test-market",
                outcome="UP",
                best_bid=0.20,
                best_ask=0.25,
            )
            store.add(event)

        # Price = 0.225 (mid of 0.20 and 0.25)
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.20,
            best_ask=0.25,
        )
        signal = strategy.evaluate(event)

        assert signal is not None
        # p_up should be approximately 1 - 0.225 = 0.775
        # p_down should be approximately 0.225
        assert 0.0 <= signal.p_up <= 1.0
        assert 0.0 <= signal.p_down <= 1.0
        # Probabilities should sum to approximately 1.0 (allowing for normalization)
        assert abs(signal.p_up + signal.p_down - 1.0) < 0.01

    def test_strategy_edge_calculation(self) -> None:
        """Test that edge is calculated correctly."""
        store = MemoryMarketDataStore()
        buy_threshold = 0.30
        strategy = SimpleThresholdStrategy(
            market_slug="test-market",
            store=store,
            buy_threshold=buy_threshold,
            min_history=0,
        )

        # Add history
        for _i in range(5):
            event = MarketDataEvent(
                market_slug="test-market",
                outcome="UP",
                best_bid=0.20,
                best_ask=0.25,
            )
            store.add(event)

        # Price = 0.225, threshold = 0.30
        # Edge should be 0.30 - 0.225 = 0.075
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.20,
            best_ask=0.25,
        )
        signal = strategy.evaluate(event)

        assert signal is not None
        expected_edge = buy_threshold - 0.225  # 0.075
        assert abs(signal.edge - expected_edge) < 0.001

    def test_strategy_confidence_calculation(self) -> None:
        """Test that confidence is normalized correctly."""
        store = MemoryMarketDataStore()
        buy_threshold = 0.30
        strategy = SimpleThresholdStrategy(
            market_slug="test-market",
            store=store,
            buy_threshold=buy_threshold,
            min_history=0,
        )

        # Add history
        for _i in range(5):
            event = MarketDataEvent(
                market_slug="test-market",
                outcome="UP",
                best_bid=0.10,
                best_ask=0.15,
            )
            store.add(event)

        # Price = 0.125, threshold = 0.30
        # Edge = 0.30 - 0.125 = 0.175
        # Confidence = 0.175 / 0.30 = 0.583
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.10,
            best_ask=0.15,
        )
        signal = strategy.evaluate(event)

        assert signal is not None
        expected_confidence = (buy_threshold - 0.125) / buy_threshold
        assert abs(signal.confidence - expected_confidence) < 0.001
        assert 0.0 <= signal.confidence <= 1.0

    def test_strategy_confidence_clamped_to_one(self) -> None:
        """Test that confidence is clamped to 1.0."""
        store = MemoryMarketDataStore()
        buy_threshold = 0.30
        strategy = SimpleThresholdStrategy(
            market_slug="test-market",
            store=store,
            buy_threshold=buy_threshold,
            min_history=0,
        )

        # Add history
        for _i in range(5):
            event = MarketDataEvent(
                market_slug="test-market",
                outcome="UP",
                best_bid=0.01,
                best_ask=0.02,
            )
            store.add(event)

        # Price = 0.015, threshold = 0.30
        # Edge = 0.30 - 0.015 = 0.285
        # Confidence = 0.285 / 0.30 = 0.95 (should be clamped to 1.0 if > 1.0)
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.01,
            best_ask=0.02,
        )
        signal = strategy.evaluate(event)

        assert signal is not None
        assert signal.confidence <= 1.0

    def test_strategy_correlation_id_propagation(self) -> None:
        """Test that correlation_id propagates from MarketDataEvent."""
        from polytrader.common.ids import generate_correlation_id

        store = MemoryMarketDataStore()
        strategy = SimpleThresholdStrategy(
            market_slug="test-market",
            store=store,
            buy_threshold=0.30,
            min_history=0,
        )

        # Add history
        for _i in range(5):
            event = MarketDataEvent(
                market_slug="test-market",
                outcome="UP",
                best_bid=0.25,
                best_ask=0.30,
            )
            store.add(event)

        corr_id = generate_correlation_id()
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.25,
            best_ask=0.30,
            correlation_id=corr_id,
        )
        signal = strategy.evaluate(event)

        assert signal is not None
        assert signal.correlation_id == corr_id

    def test_strategy_evaluation_fast(self) -> None:
        """Test that evaluation is fast (< 1ms)."""
        store = MemoryMarketDataStore()
        strategy = SimpleThresholdStrategy(
            market_slug="test-market",
            store=store,
            buy_threshold=0.30,
            min_history=0,
        )

        # Add history
        for _i in range(5):
            event = MarketDataEvent(
                market_slug="test-market",
                outcome="UP",
                best_bid=0.25,
                best_ask=0.30,
            )
            store.add(event)

        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.25,
            best_ask=0.30,
        )

        # Benchmark evaluation
        latencies = []
        for _ in range(100):
            start = time.perf_counter()
            _ = strategy.evaluate(event)  # Evaluate but don't store result
            latency_ms = (time.perf_counter() - start) * 1000
            latencies.append(latency_ms)

        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        # Average should be < 1ms, max should be < 5ms (accounting for system variance)
        assert avg_latency < 1.0, f"Average latency {avg_latency:.3f}ms, expected < 1ms"
        assert max_latency < 5.0, f"Max latency {max_latency:.3f}ms, expected < 5ms"

    def test_strategy_filters_by_market(self) -> None:
        """Test that strategy only evaluates events for its market."""
        store = MemoryMarketDataStore()
        strategy = SimpleThresholdStrategy(
            market_slug="test-market-1",
            store=store,
            buy_threshold=0.30,
            min_history=0,
        )

        # Add history for correct market
        for _i in range(5):
            event = MarketDataEvent(
                market_slug="test-market-1",
                outcome="UP",
                best_bid=0.25,
                best_ask=0.30,
            )
            store.add(event)

        # Event for different market should return None
        event = MarketDataEvent(
            market_slug="test-market-2",
            outcome="UP",
            best_bid=0.25,
            best_ask=0.30,
        )
        signal = strategy.evaluate(event)

        assert signal is None

    def test_strategy_validation_buy_threshold_range(self) -> None:
        """Test that buy_threshold is validated."""
        store = MemoryMarketDataStore()

        # Valid threshold
        strategy = SimpleThresholdStrategy(
            market_slug="test-market",
            store=store,
            buy_threshold=0.30,
        )
        assert strategy.buy_threshold == 0.30

        # Invalid threshold (too high)
        with pytest.raises(ValueError, match="buy_threshold must be between 0.0 and 1.0"):
            SimpleThresholdStrategy(
                market_slug="test-market",
                store=store,
                buy_threshold=1.5,
            )

        # Invalid threshold (negative)
        with pytest.raises(ValueError, match="buy_threshold must be between 0.0 and 1.0"):
            SimpleThresholdStrategy(
                market_slug="test-market",
                store=store,
                buy_threshold=-0.1,
            )

    def test_strategy_validation_min_history(self) -> None:
        """Test that min_history is validated."""
        store = MemoryMarketDataStore()

        # Valid min_history
        strategy = SimpleThresholdStrategy(
            market_slug="test-market",
            store=store,
            min_history=30,
        )
        assert strategy.min_history == 30

        # Invalid min_history (negative)
        with pytest.raises(ValueError, match="min_history must be >= 0"):
            SimpleThresholdStrategy(
                market_slug="test-market",
                store=store,
                min_history=-1,
            )

    def test_strategy_no_sell_signals(self) -> None:
        """Test that strategy never generates SELL signals (only BUY/UP signals)."""
        store = MemoryMarketDataStore()
        strategy = SimpleThresholdStrategy(
            market_slug="test-market",
            store=store,
            buy_threshold=0.30,
            min_history=0,
        )

        # Add history
        for _i in range(5):
            event = MarketDataEvent(
                market_slug="test-market",
                outcome="UP",
                best_bid=0.25,
                best_ask=0.30,
            )
            store.add(event)

        # Price below threshold should generate UP signal
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.25,
            best_ask=0.30,
        )
        signal = strategy.evaluate(event)

        assert signal is not None
        assert signal.outcome == "UP"  # Always UP, never DOWN or SELL

    def test_strategy_signal_deduplication(self) -> None:
        """Test that strategy deduplicates signals (prevents spamming).

        Strategy tracks last signal sent per market/outcome and skips
        duplicate signals until price goes above threshold.
        """
        store = MemoryMarketDataStore()
        strategy = SimpleThresholdStrategy(
            market_slug="test-market",
            store=store,
            buy_threshold=0.30,
            min_history=0,
        )

        # Add history
        for _i in range(5):
            event = MarketDataEvent(
                market_slug="test-market",
                outcome="UP",
                best_bid=0.25,
                best_ask=0.30,
            )
            store.add(event)

        # Price below threshold - should generate signal
        event_below = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.25,
            best_ask=0.30,  # mid = 0.275 < 0.30 threshold
        )

        # First evaluation should produce signal
        signal1 = strategy.evaluate(event_below)
        assert signal1 is not None
        assert signal1.edge > 0
        assert signal1.confidence > 0

        # Second evaluation with same price should skip (deduplication)
        signal2 = strategy.evaluate(event_below)
        assert signal2 is None, "Should skip duplicate signal for same market/outcome"

        # Price above threshold - should clear tracking
        event_above = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.35,
            best_ask=0.40,  # mid = 0.375 > 0.30 threshold
        )
        signal3 = strategy.evaluate(event_above)
        assert signal3 is None, "No signal when price above threshold"

        # Price drops below threshold again - should generate new signal
        signal4 = strategy.evaluate(event_below)
        assert signal4 is not None, "Should generate new signal after price went above threshold"
        assert signal4.edge == signal1.edge, "Same price should produce same edge"
        assert signal4.confidence == signal1.confidence, "Same price should produce same confidence"
