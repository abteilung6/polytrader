"""Tests for system health and rate limit policies.

Per testing.mdc §1.A: Unit tests for system health policies (fast, deterministic).
"""

from polytrader.risk.models import RiskContext, RiskLimits, RiskReasonCode
from polytrader.risk.policies import check_rate_limits, check_system_health
from polytrader.types import OrderIntentEvent


class TestCheckSystemHealth:
    """Tests for check_system_health policy."""

    def test_check_system_health_kill_switch_active(self) -> None:
        """Test that kill switch denies all orders."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        context = RiskContext(
            intent=intent,
            kill_switch_active=True,  # Kill switch active
        )
        limits = RiskLimits(version="1.0")

        result = check_system_health(context, limits)

        assert result.allowed is False
        assert RiskReasonCode.RISK_KILL_SWITCH in result.reason_codes
        assert result.metadata["kill_switch_active"] is True
        assert result.metadata["limits_version"] == "1.0"

    def test_check_system_health_circuit_breaker_active(self) -> None:
        """Test that circuit breaker denies all orders."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        context = RiskContext(
            intent=intent,
            circuit_breaker_active=True,  # Circuit breaker active
        )
        limits = RiskLimits(version="1.0")

        result = check_system_health(context, limits)

        assert result.allowed is False
        assert RiskReasonCode.RISK_RECONCILE_DIVERGENCE in result.reason_codes
        assert result.metadata["circuit_breaker_active"] is True
        assert result.metadata["limits_version"] == "1.0"

    def test_check_system_health_reconciliation_unhealthy(self) -> None:
        """Test that unhealthy reconciliation denies all orders."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        context = RiskContext(
            intent=intent,
            reconciliation_healthy=False,  # Reconciliation unhealthy
        )
        limits = RiskLimits(version="1.0")

        result = check_system_health(context, limits)

        assert result.allowed is False
        assert RiskReasonCode.RISK_RECONCILE_DIVERGENCE in result.reason_codes
        assert result.metadata["reconciliation_healthy"] is False
        assert result.metadata["limits_version"] == "1.0"

    def test_check_system_health_all_healthy(self) -> None:
        """Test that system passes when all health gates are healthy."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        context = RiskContext(
            intent=intent,
            kill_switch_active=False,
            circuit_breaker_active=False,
            reconciliation_healthy=True,
        )
        limits = RiskLimits()

        result = check_system_health(context, limits)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_check_system_health_kill_switch_priority(self) -> None:
        """Test that kill switch takes priority over other health issues."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        context = RiskContext(
            intent=intent,
            kill_switch_active=True,  # Kill switch active
            circuit_breaker_active=True,  # Also circuit breaker
            reconciliation_healthy=False,  # Also unhealthy reconciliation
        )
        limits = RiskLimits()

        result = check_system_health(context, limits)

        # Kill switch should be checked first
        assert result.allowed is False
        assert RiskReasonCode.RISK_KILL_SWITCH in result.reason_codes
        assert "kill_switch_active" in result.metadata


class TestCheckRateLimits:
    """Tests for check_rate_limits policy."""

    def test_check_rate_limits_within_limit(self) -> None:
        """Test that orders within rate limit are allowed."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        context = RiskContext(
            intent=intent,
            order_count_last_minute=50,  # Below limit
        )
        limits = RiskLimits(order_rate_limit_per_minute=60)

        result = check_rate_limits(context, limits)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_check_rate_limits_at_limit(self) -> None:
        """Test that orders at exactly the rate limit are denied."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        context = RiskContext(
            intent=intent,
            order_count_last_minute=60,  # Exactly at limit
        )
        limits = RiskLimits(order_rate_limit_per_minute=60, version="1.0")

        result = check_rate_limits(context, limits)

        assert result.allowed is False
        assert RiskReasonCode.RISK_RATE_LIMIT in result.reason_codes
        assert result.metadata["order_count_last_minute"] == 60
        assert result.metadata["order_rate_limit"] == 60
        assert result.metadata["limits_version"] == "1.0"

    def test_check_rate_limits_exceeded(self) -> None:
        """Test that orders exceeding rate limit are denied."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        context = RiskContext(
            intent=intent,
            order_count_last_minute=70,  # Exceeds limit
        )
        limits = RiskLimits(order_rate_limit_per_minute=60, version="1.0")

        result = check_rate_limits(context, limits)

        assert result.allowed is False
        assert RiskReasonCode.RISK_RATE_LIMIT in result.reason_codes
        assert result.metadata["order_count_last_minute"] == 70
        assert result.metadata["order_rate_limit"] == 60
        assert result.metadata["limits_version"] == "1.0"

    def test_check_rate_limits_zero_orders(self) -> None:
        """Test that zero orders pass the rate limit check."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        context = RiskContext(
            intent=intent,
            order_count_last_minute=0,  # No orders
        )
        limits = RiskLimits(order_rate_limit_per_minute=60)

        result = check_rate_limits(context, limits)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_check_rate_limits_different_limit(self) -> None:
        """Test rate limits with different limit values."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        context = RiskContext(
            intent=intent,
            order_count_last_minute=100,  # 100 orders
        )
        limits = RiskLimits(order_rate_limit_per_minute=120)  # Higher limit

        result = check_rate_limits(context, limits)

        assert result.allowed is True  # 100 < 120
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_check_rate_limits_sell_order(self) -> None:
        """Test that rate limits apply to both BUY and SELL orders."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="SELL",
            target_price=0.7,
            limit_price=0.65,
            size=1.0,
            reason="Test",
        )

        context = RiskContext(
            intent=intent,
            order_count_last_minute=60,  # At limit
        )
        limits = RiskLimits(order_rate_limit_per_minute=60)

        result = check_rate_limits(context, limits)

        assert result.allowed is False  # Rate limit applies to all orders
        assert RiskReasonCode.RISK_RATE_LIMIT in result.reason_codes
