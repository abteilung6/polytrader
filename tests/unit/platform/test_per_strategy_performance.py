"""Unit tests for PerStrategyPerformanceTracker.

Per Platform_Proposal.md §3.2: Tests verify per-strategy position tracking,
PnL calculation, and metrics emission.
"""

import pytest

from polytrader.obs.metrics import MemoryMetricsCollector, set_metrics_collector
from polytrader.platform.performance import PerStrategyPerformanceTracker
from polytrader.types import Outcome
from tests.factories.events import (
    create_fill_event,
    create_market_data_event,
    create_order_intent_event,
)
from tests.factories.orders import create_order


@pytest.fixture(autouse=True)
def memory_metrics_collector():
    """Use MemoryMetricsCollector for tests that need to query values directly."""
    collector = MemoryMetricsCollector()
    set_metrics_collector(collector)
    yield collector
    set_metrics_collector(None)


class TestPerStrategyPerformanceTracker:
    """Tests for PerStrategyPerformanceTracker."""

    def test_tracks_positions_per_strategy(self) -> None:
        """Test that positions are tracked per strategy."""
        tracker = PerStrategyPerformanceTracker()

        strategy_1 = "strategy_1"
        strategy_2 = "strategy_2"
        market = "test-market"
        outcome: Outcome = "UP"

        # Create orders for different strategies
        order_1 = create_order(
            market_slug=market,
            outcome=outcome,
            intent=create_order_intent_event(
                market_slug=market,
                outcome=outcome,
                strategy_id=strategy_1,
            ),
        )
        order_2 = create_order(
            market_slug=market,
            outcome=outcome,
            intent=create_order_intent_event(
                market_slug=market,
                outcome=outcome,
                strategy_id=strategy_2,
            ),
        )

        # Record BUY fills for both strategies
        fill_1 = create_fill_event(order_id=order_1.order_id, size=10.0, price=0.5)
        fill_2 = create_fill_event(order_id=order_2.order_id, size=20.0, price=0.5)

        tracker.record_buy_fill(strategy_1, market, outcome, fill_1, order_1)
        tracker.record_buy_fill(strategy_2, market, outcome, fill_2, order_2)

        # Verify positions are tracked separately
        positions_1 = tracker.get_positions(strategy_1)
        positions_2 = tracker.get_positions(strategy_2)

        assert len(positions_1) == 1
        assert len(positions_2) == 1
        assert positions_1[(market, outcome)].size == 10.0
        assert positions_2[(market, outcome)].size == 20.0

    def test_calculates_pnl_per_strategy(self) -> None:
        """Test PnL calculation per strategy."""
        tracker = PerStrategyPerformanceTracker()

        strategy = "strategy_1"
        market = "test-market"
        outcome: Outcome = "UP"

        # Create and fill BUY order
        order = create_order(
            market_slug=market,
            outcome=outcome,
            intent=create_order_intent_event(
                market_slug=market,
                outcome=outcome,
                strategy_id=strategy,
            ),
        )
        buy_fill = create_fill_event(order_id=order.order_id, size=10.0, price=0.4)
        tracker.record_buy_fill(strategy, market, outcome, buy_fill, order)

        # Update market price for unrealized P&L
        market_data = create_market_data_event(
            market_slug=market,
            outcome=outcome,
            best_bid=0.45,
            best_ask=0.55,
        )
        tracker.update_market_price(market_data)

        # Check unrealized P&L (should be positive: (0.5 - 0.4) * 10 = 1.0)
        unrealized = tracker.calculate_unrealized_pnl(strategy)
        assert unrealized == pytest.approx(1.0, abs=0.01)

        # Close position with SELL fill
        sell_fill = create_fill_event(order_id=order.order_id, size=10.0, price=0.6)
        tracker.record_sell_fill(strategy, market, outcome, sell_fill, order)

        # Check realized P&L (should be: (0.6 - 0.4) * 10 = 2.0)
        realized = tracker.calculate_realized_pnl(strategy)
        assert realized == pytest.approx(2.0, abs=0.01)

    def test_emits_metrics_per_strategy(self) -> None:
        """Test metrics are emitted per strategy."""
        from polytrader.obs.metrics import get_metrics_collector

        tracker = PerStrategyPerformanceTracker()
        collector = get_metrics_collector()

        strategy = "strategy_1"
        market = "test-market"
        outcome: Outcome = "UP"

        # Get initial PnL value (before any trades)
        initial_pnl = collector.get_gauge(
            "pnl_realized",
            labels={"strategy_id": strategy},
        )

        # Create and fill BUY order
        order = create_order(
            market_slug=market,
            outcome=outcome,
            intent=create_order_intent_event(
                market_slug=market,
                outcome=outcome,
                strategy_id=strategy,
            ),
        )
        buy_fill = create_fill_event(order_id=order.order_id, size=10.0, price=0.4)
        tracker.record_buy_fill(strategy, market, outcome, buy_fill, order)

        # Check position metric was emitted with strategy_id
        position_gauge = collector.get_gauge(
            "position_net",
            labels={"market": market, "outcome": outcome, "strategy_id": strategy},
        )
        assert position_gauge == 10.0

        # Close position
        sell_fill = create_fill_event(order_id=order.order_id, size=10.0, price=0.6)
        tracker.record_sell_fill(strategy, market, outcome, sell_fill, order)

        # Check PnL metric was emitted with strategy_id (cumulative)
        # After closing position, PnL should increase by 2.0
        final_pnl = collector.get_gauge(
            "pnl_realized",
            labels={"strategy_id": strategy},
        )
        pnl_delta = final_pnl - initial_pnl
        assert pnl_delta == pytest.approx(2.0, abs=0.01)

    def test_performance_summary_per_strategy(self) -> None:
        """Test performance summary per strategy."""
        tracker = PerStrategyPerformanceTracker(starting_equity=1000.0)

        strategy_1 = "strategy_1"
        strategy_2 = "strategy_2"
        market = "test-market"
        outcome: Outcome = "UP"

        # Strategy 1: Win
        order_1 = create_order(
            market_slug=market,
            outcome=outcome,
            intent=create_order_intent_event(
                market_slug=market,
                outcome=outcome,
                strategy_id=strategy_1,
            ),
        )
        buy_fill_1 = create_fill_event(order_id=order_1.order_id, size=10.0, price=0.4)
        tracker.record_buy_fill(strategy_1, market, outcome, buy_fill_1, order_1)
        sell_fill_1 = create_fill_event(order_id=order_1.order_id, size=10.0, price=0.6)
        tracker.record_sell_fill(strategy_1, market, outcome, sell_fill_1, order_1)

        # Strategy 2: Loss
        order_2 = create_order(
            market_slug=market,
            outcome=outcome,
            intent=create_order_intent_event(
                market_slug=market,
                outcome=outcome,
                strategy_id=strategy_2,
            ),
        )
        buy_fill_2 = create_fill_event(order_id=order_2.order_id, size=10.0, price=0.6)
        tracker.record_buy_fill(strategy_2, market, outcome, buy_fill_2, order_2)
        sell_fill_2 = create_fill_event(order_id=order_2.order_id, size=10.0, price=0.4)
        tracker.record_sell_fill(strategy_2, market, outcome, sell_fill_2, order_2)

        # Get performance summaries
        summary_1 = tracker.get_performance_summary(strategy_1)
        summary_2 = tracker.get_performance_summary(strategy_2)

        # Strategy 1 should have positive P&L
        assert summary_1["total_realized_pnl"] == pytest.approx(2.0, abs=0.01)
        assert summary_1["win_rate_pct"] == 100.0
        assert summary_1["total_trades"] == 1

        # Strategy 2 should have negative P&L
        assert summary_2["total_realized_pnl"] == pytest.approx(-2.0, abs=0.01)
        assert summary_2["win_rate_pct"] == 0.0
        assert summary_2["total_trades"] == 1

    def test_list_strategies(self) -> None:
        """Test listing all strategies with tracked positions or trades."""
        tracker = PerStrategyPerformanceTracker()

        strategy_1 = "strategy_1"
        strategy_2 = "strategy_2"
        market = "test-market"
        outcome: Outcome = "UP"

        # Strategy 1: Open position
        order_1 = create_order(
            market_slug=market,
            outcome=outcome,
            intent=create_order_intent_event(
                market_slug=market,
                outcome=outcome,
                strategy_id=strategy_1,
            ),
        )
        buy_fill_1 = create_fill_event(order_id=order_1.order_id, size=10.0, price=0.4)
        tracker.record_buy_fill(strategy_1, market, outcome, buy_fill_1, order_1)

        # Strategy 2: Closed trade
        order_2 = create_order(
            market_slug=market,
            outcome=outcome,
            intent=create_order_intent_event(
                market_slug=market,
                outcome=outcome,
                strategy_id=strategy_2,
            ),
        )
        buy_fill_2 = create_fill_event(order_id=order_2.order_id, size=10.0, price=0.4)
        tracker.record_buy_fill(strategy_2, market, outcome, buy_fill_2, order_2)
        sell_fill_2 = create_fill_event(order_id=order_2.order_id, size=10.0, price=0.6)
        tracker.record_sell_fill(strategy_2, market, outcome, sell_fill_2, order_2)

        # List strategies
        strategies = tracker.list_strategies()
        assert len(strategies) == 2
        assert strategy_1 in strategies
        assert strategy_2 in strategies
