"""Tests for fill price calculation models.

Per Commit 2: Test fill price calculation for all models.
"""

import random

from polytrader.events.types import MarketDataEvent, OrderIntentEvent
from polytrader.execution.fill_models import (
    FillModel,
    calculate_fill_price,
    should_fill,
    should_reject,
)
from polytrader.store import MemoryMarketDataStore


class TestFillPriceCalculation:
    """Tests for fill price calculation."""

    def test_immediate_model_uses_limit_price(self) -> None:
        """Test that IMMEDIATE model uses limit price."""
        store = MemoryMarketDataStore()
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
        )

        fill_price = calculate_fill_price(FillModel.IMMEDIATE, intent, store)

        assert fill_price == 0.55

    def test_mid_price_model_uses_market_mid(self) -> None:
        """Test that MID_PRICE model uses current mid price."""
        store = MemoryMarketDataStore()
        # Add market data
        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.50,
            best_ask=0.60,
        )
        store.add(market_data)

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
        )

        fill_price = calculate_fill_price(FillModel.MID_PRICE, intent, store)

        assert fill_price == 0.55  # (0.50 + 0.60) / 2

    def test_mid_price_model_fallback_to_limit_if_no_data(self) -> None:
        """Test that MID_PRICE model falls back to limit price if no market data."""
        store = MemoryMarketDataStore()
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
        )

        fill_price = calculate_fill_price(FillModel.MID_PRICE, intent, store)

        assert fill_price == 0.55  # Falls back to limit price

    def test_slippage_model_buy_adds_slippage(self) -> None:
        """Test that SLIPPAGE model adds slippage for BUY orders."""
        store = MemoryMarketDataStore()
        # Add market data
        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.50,
            best_ask=0.60,
        )
        store.add(market_data)

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
        )

        slippage_bps = 10.0  # 10 basis points = 0.001
        fill_price = calculate_fill_price(
            FillModel.SLIPPAGE, intent, store, slippage_bps=slippage_bps
        )

        # Mid = 0.55, spread = 0.10, half spread = 0.05
        # Buy at ask (mid + half spread) + slippage = 0.55 + 0.05 + 0.001 = 0.601
        expected = 0.55 + 0.05 + 0.001
        assert abs(fill_price - expected) < 0.0001

    def test_slippage_model_sell_subtracts_slippage(self) -> None:
        """Test that SLIPPAGE model subtracts slippage for SELL orders."""
        store = MemoryMarketDataStore()
        # Add market data
        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.50,
            best_ask=0.60,
        )
        store.add(market_data)

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="SELL",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
        )

        slippage_bps = 10.0  # 10 basis points = 0.001
        fill_price = calculate_fill_price(
            FillModel.SLIPPAGE, intent, store, slippage_bps=slippage_bps
        )

        # Mid = 0.55, spread = 0.10, half spread = 0.05
        # Sell at bid (mid - half spread) - slippage = 0.55 - 0.05 - 0.001 = 0.499
        expected = 0.55 - 0.05 - 0.001
        assert abs(fill_price - expected) < 0.0001

    def test_slippage_model_clamps_to_valid_range(self) -> None:
        """Test that SLIPPAGE model clamps fill price to [0, 1]."""
        store = MemoryMarketDataStore()
        # Add market data with extreme spread
        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.01,
            best_ask=0.99,
        )
        store.add(market_data)

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="SELL",
            size=1.0,
            target_price=0.50,
            limit_price=0.50,
            reason="Test",
            ttl_s=60.0,
        )

        slippage_bps = 1000.0  # Large slippage
        fill_price = calculate_fill_price(
            FillModel.SLIPPAGE, intent, store, slippage_bps=slippage_bps
        )

        assert 0.0 <= fill_price <= 1.0


class TestFillProbability:
    """Tests for fill probability logic."""

    def test_should_fill_always_true_when_probability_one(self) -> None:
        """Test that should_fill returns True when probability is 1.0."""
        rng = random.Random(42)  # Seeded for determinism
        for _ in range(100):
            assert should_fill(1.0, rng) is True

    def test_should_fill_always_false_when_probability_zero(self) -> None:
        """Test that should_fill returns False when probability is 0.0."""
        rng = random.Random(42)  # Seeded for determinism
        for _ in range(100):
            assert should_fill(0.0, rng) is False

    def test_should_fill_stochastic(self) -> None:
        """Test that should_fill is stochastic for intermediate probabilities."""
        rng = random.Random(42)  # Seeded for determinism
        results = [should_fill(0.5, rng) for _ in range(100)]
        # Should have some True and some False (not all same)
        assert any(results) and not all(results)


class TestRejectionProbability:
    """Tests for rejection probability logic."""

    def test_should_reject_always_true_when_probability_one(self) -> None:
        """Test that should_reject returns True when probability is 1.0."""
        rng = random.Random(42)  # Seeded for determinism
        for _ in range(100):
            assert should_reject(1.0, rng) is True

    def test_should_reject_always_false_when_probability_zero(self) -> None:
        """Test that should_reject returns False when probability is 0.0."""
        rng = random.Random(42)  # Seeded for determinism
        for _ in range(100):
            assert should_reject(0.0, rng) is False

    def test_should_reject_stochastic(self) -> None:
        """Test that should_reject is stochastic for intermediate probabilities."""
        rng = random.Random(42)  # Seeded for determinism
        results = [should_reject(0.5, rng) for _ in range(100)]
        # Should have some True and some False (not all same)
        assert any(results) and not all(results)
