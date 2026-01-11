"""Tests for price sanity and data freshness policies.

Per testing.mdc §1.A: Unit tests for price and data freshness policies (fast, deterministic).
"""

from unittest.mock import MagicMock

from polytrader.events.types import MarketDataEvent, OrderIntentEvent
from polytrader.risk.models import RiskContext, RiskLimits, RiskReasonCode
from polytrader.risk.policies import check_data_freshness, check_price_sanity


class TestCheckPriceSanity:
    """Tests for check_price_sanity policy."""

    def test_check_price_sanity_buy_within_bounds(self) -> None:
        """Test that BUY orders with price within bounds are allowed."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,  # Within bounds (mid=0.45, max=0.45*1.1=0.495)
            size=1.0,
            reason="Test",
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,  # mid = 0.45
        )

        context = RiskContext(intent=intent, market_data=market_data)
        limits = RiskLimits(price_deviation_threshold=0.1, version="1.0")

        result = check_price_sanity(context, limits)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes
        assert result.metadata["mid_price"] == 0.45
        assert result.metadata["qty"] == 1.0
        assert result.metadata["limits_version"] == "1.0"

    def test_check_price_sanity_buy_out_of_bounds(self) -> None:
        """Test that BUY orders with price exceeding max are denied."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.50,  # Exceeds max (mid=0.45, max=0.45*1.1=0.495)
            size=1.0,
            reason="Test",
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,  # mid = 0.45
        )

        context = RiskContext(intent=intent, market_data=market_data)
        limits = RiskLimits(price_deviation_threshold=0.1, version="1.0")

        result = check_price_sanity(context, limits)

        assert result.allowed is False
        assert RiskReasonCode.RISK_PRICE_OUT_OF_BOUNDS in result.reason_codes
        assert result.metadata["limit_price"] == 0.50
        assert result.metadata["mid_price"] == 0.45
        assert abs(result.metadata["max_buy_price"] - 0.495) < 0.0001  # Floating point precision
        assert result.metadata["max_deviation"] == 0.1
        assert result.metadata["limits_version"] == "1.0"

    def test_check_price_sanity_sell_within_bounds(self) -> None:
        """Test that SELL orders with price within bounds are allowed."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="SELL",
            target_price=0.7,
            limit_price=0.65,  # Within bounds (mid=0.45, min=0.45*0.9=0.405)
            size=1.0,
            reason="Test",
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,  # mid = 0.45
        )

        context = RiskContext(intent=intent, market_data=market_data)
        limits = RiskLimits(price_deviation_threshold=0.1)

        result = check_price_sanity(context, limits)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_check_price_sanity_sell_out_of_bounds(self) -> None:
        """Test that SELL orders with price below min are denied."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="SELL",
            target_price=0.7,
            limit_price=0.40,  # Below min (mid=0.45, min=0.45*0.9=0.405)
            size=1.0,
            reason="Test",
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,  # mid = 0.45
        )

        context = RiskContext(intent=intent, market_data=market_data)
        limits = RiskLimits(price_deviation_threshold=0.1, version="1.0")

        result = check_price_sanity(context, limits)

        assert result.allowed is False
        assert RiskReasonCode.RISK_PRICE_OUT_OF_BOUNDS in result.reason_codes
        assert result.metadata["limit_price"] == 0.40
        assert result.metadata["mid_price"] == 0.45
        assert abs(result.metadata["min_sell_price"] - 0.405) < 0.0001  # Floating point precision
        assert result.metadata["max_deviation"] == 0.1
        assert result.metadata["limits_version"] == "1.0"

    def test_check_price_sanity_no_market_data(self) -> None:
        """Test that price sanity allows when no market data (data freshness will catch)."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        context = RiskContext(intent=intent, market_data=None)  # No market data
        limits = RiskLimits(price_deviation_threshold=0.1)

        result = check_price_sanity(context, limits)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes
        # Data freshness check will deny if no data

    def test_check_price_sanity_exact_boundary_buy(self) -> None:
        """Test that BUY orders at exactly max price are allowed."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.495,  # Exactly at max (mid=0.45, max=0.45*1.1=0.495)
            size=1.0,
            reason="Test",
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,  # mid = 0.45
        )

        context = RiskContext(intent=intent, market_data=market_data)
        limits = RiskLimits(price_deviation_threshold=0.1)

        result = check_price_sanity(context, limits)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_check_price_sanity_exact_boundary_sell(self) -> None:
        """Test that SELL orders at exactly min price are allowed."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="SELL",
            target_price=0.7,
            limit_price=0.405,  # Exactly at min (mid=0.45, min=0.45*0.9=0.405)
            size=1.0,
            reason="Test",
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,  # mid = 0.45
        )

        context = RiskContext(intent=intent, market_data=market_data)
        limits = RiskLimits(price_deviation_threshold=0.1)

        result = check_price_sanity(context, limits)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_check_price_sanity_different_threshold(self) -> None:
        """Test price sanity with different deviation threshold."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.50,  # Would be out of bounds with 0.1 threshold
            size=1.0,
            reason="Test",
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,  # mid = 0.45
        )

        context = RiskContext(intent=intent, market_data=market_data)
        limits = RiskLimits(price_deviation_threshold=0.2)  # 20% threshold

        result = check_price_sanity(context, limits)

        assert result.allowed is True  # 0.50 <= 0.45 * 1.2 = 0.54
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes


class TestCheckDataFreshness:
    """Tests for check_data_freshness policy."""

    def test_check_data_freshness_fresh_data(self) -> None:
        """Test that fresh market data passes the check."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
        )

        clock = MagicMock()
        clock.monotonic.return_value = market_data.ts_mono + 2.0  # 2 seconds old

        context = RiskContext(intent=intent, market_data=market_data)
        limits = RiskLimits(max_data_staleness_seconds=5.0, version="1.0")

        result = check_data_freshness(context, limits, clock=clock)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_check_data_freshness_stale_data(self) -> None:
        """Test that stale market data is denied."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
        )

        clock = MagicMock()
        clock.monotonic.return_value = market_data.ts_mono + 10.0  # 10 seconds old

        context = RiskContext(intent=intent, market_data=market_data)
        limits = RiskLimits(max_data_staleness_seconds=5.0, version="1.0")

        result = check_data_freshness(context, limits, clock=clock)

        assert result.allowed is False
        assert RiskReasonCode.RISK_DATA_STALE in result.reason_codes
        assert result.metadata["data_age_seconds"] == 10.0
        assert result.metadata["max_staleness_seconds"] == 5.0
        assert result.metadata["limits_version"] == "1.0"

    def test_check_data_freshness_no_market_data(self) -> None:
        """Test that missing market data is denied (hard gate)."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        context = RiskContext(intent=intent, market_data=None)  # No market data
        limits = RiskLimits(max_data_staleness_seconds=5.0, version="1.0")

        result = check_data_freshness(context, limits)

        assert result.allowed is False
        assert RiskReasonCode.RISK_DATA_STALE in result.reason_codes
        assert result.metadata["market_slug"] == "test-market"
        assert result.metadata["reason"] == "No market data available"
        assert result.metadata["limits_version"] == "1.0"

    def test_check_data_freshness_exact_boundary(self) -> None:
        """Test that data at exactly the staleness limit is allowed."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
        )

        clock = MagicMock()
        clock.monotonic.return_value = market_data.ts_mono + 5.0  # Exactly at limit

        context = RiskContext(intent=intent, market_data=market_data)
        limits = RiskLimits(max_data_staleness_seconds=5.0)

        result = check_data_freshness(context, limits, clock=clock)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_check_data_freshness_with_clock(self) -> None:
        """Test that clock injection works for deterministic testing."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
        )

        clock = MagicMock()
        clock.monotonic.return_value = market_data.ts_mono + 1.0

        context = RiskContext(intent=intent, market_data=market_data)
        limits = RiskLimits(max_data_staleness_seconds=5.0)

        result = check_data_freshness(context, limits, clock=clock)

        assert result.allowed is True
        clock.monotonic.assert_called_once()

    def test_check_data_freshness_without_clock(self) -> None:
        """Test that function works without clock (uses time.monotonic())."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
        )

        context = RiskContext(intent=intent, market_data=market_data)
        limits = RiskLimits(max_data_staleness_seconds=5.0)

        # Should work without clock (uses time.monotonic())
        result = check_data_freshness(context, limits, clock=None)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_check_data_freshness_different_staleness_limit(self) -> None:
        """Test data freshness with different staleness limits."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
        )

        clock = MagicMock()
        clock.monotonic.return_value = market_data.ts_mono + 10.0  # 10 seconds old

        context = RiskContext(intent=intent, market_data=market_data)
        limits = RiskLimits(max_data_staleness_seconds=15.0)  # 15 second limit

        result = check_data_freshness(context, limits, clock=clock)

        assert result.allowed is True  # 10 < 15
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes
