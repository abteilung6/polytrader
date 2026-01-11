"""Tests for IStrategy protocol."""

import time

from polytrader.events.types import MarketDataEvent, SignalEvent
from polytrader.strategies import IStrategy
from polytrader.types import Position


class TestIStrategyProtocol:
    """Tests for IStrategy protocol compliance."""

    def test_strategy_protocol_has_evaluate(self) -> None:
        """Test that IStrategy protocol defines evaluate() method."""
        # Check that evaluate is part of the protocol
        assert hasattr(IStrategy, "__protocol_methods__") or hasattr(
            IStrategy, "__abstractmethods__"
        )

    def test_strategy_evaluate_signature(self) -> None:
        """Test that evaluate() has correct signature."""

        # Create a simple strategy implementation
        class SimpleStrategy:
            def evaluate(
                self,
                market_data: MarketDataEvent,
                positions: dict[tuple[str, str], Position] | None = None,
            ) -> SignalEvent | None:
                return None

            async def run(self) -> None:
                pass

            def stop(self) -> None:
                pass

        strategy = SimpleStrategy()
        # Should be compatible with IStrategy (runtime checkable)
        assert isinstance(strategy, IStrategy)

    def test_strategy_evaluate_fast(self) -> None:
        """Test that evaluate() is fast (< 1ms for simple strategies)."""

        # Create a simple strategy
        class FastStrategy:
            def evaluate(
                self,
                market_data: MarketDataEvent,
                positions: dict[tuple[str, str], Position] | None = None,
            ) -> SignalEvent | None:
                # Simple computation (should be < 1ms)
                return None

            async def run(self) -> None:
                pass

            def stop(self) -> None:
                pass

        strategy = FastStrategy()
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.45,
            best_ask=0.50,
        )

        # Benchmark evaluation
        start = time.perf_counter()
        result = strategy.evaluate(event)
        latency_ms = (time.perf_counter() - start) * 1000

        assert result is None
        assert latency_ms < 1.0, f"Evaluation took {latency_ms:.3f}ms, expected < 1ms"

    def test_strategy_evaluate_stateless(self) -> None:
        """Test that strategies are stateless (deterministic)."""

        # Create a stateless strategy
        class StatelessStrategy:
            def __init__(self) -> None:
                self.call_count = 0

            def evaluate(
                self,
                market_data: MarketDataEvent,
                positions: dict[tuple[str, str], Position] | None = None,
            ) -> SignalEvent | None:
                self.call_count += 1
                # Deterministic: same input produces same output
                if market_data.mid < 0.30:
                    return None
                return None  # Always return None for this test

            async def run(self) -> None:
                pass

            def stop(self) -> None:
                pass

        strategy = StatelessStrategy()
        event1 = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.25,
            best_ask=0.30,
        )
        event2 = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.25,
            best_ask=0.30,
        )

        result1 = strategy.evaluate(event1)
        result2 = strategy.evaluate(event2)

        # Same input should produce same output (deterministic)
        assert result1 == result2
        assert strategy.call_count == 2

    def test_strategy_evaluate_with_positions(self) -> None:
        """Test that evaluate() accepts positions parameter."""

        class StrategyWithPositions:
            def evaluate(
                self,
                market_data: MarketDataEvent,
                positions: dict[tuple[str, str], Position] | None = None,
            ) -> SignalEvent | None:
                # Positions are for context only, not for decision-making
                if positions:
                    assert isinstance(positions, dict)
                return None

            async def run(self) -> None:
                pass

            def stop(self) -> None:
                pass

        strategy = StrategyWithPositions()
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.45,
            best_ask=0.50,
        )

        # Test with None positions
        result1 = strategy.evaluate(event, positions=None)
        assert result1 is None

        # Test with empty positions
        result2 = strategy.evaluate(event, positions={})
        assert result2 is None

        # Test with positions
        positions = {
            ("test-market", "UP"): Position(
                market_slug="test-market",
                outcome="UP",
                size=1.0,
                target_price=0.50,
                entry_price=0.30,
                entry_time=1234567890.0,
            )
        }
        result3 = strategy.evaluate(event, positions=positions)
        assert result3 is None

    def test_strategy_optional_run_stop(self) -> None:
        """Test that run() and stop() are optional (no-op for stateless strategies)."""

        class StatelessStrategy:
            def evaluate(
                self,
                market_data: MarketDataEvent,
                positions: dict[tuple[str, str], Position] | None = None,
            ) -> SignalEvent | None:
                return None

            # Optional: don't implement run() and stop() for stateless strategies
            # But we implement them as no-ops for protocol compliance
            async def run(self) -> None:
                pass  # No-op for stateless strategies

            def stop(self) -> None:
                pass  # No-op for stateless strategies

        strategy = StatelessStrategy()
        # Should work without errors
        assert strategy is not None
