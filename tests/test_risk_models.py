"""Tests for risk models.

Per testing.mdc §1.A: Unit tests for risk models (fast, deterministic).
"""

import pytest
from pydantic import ValidationError

from polytrader.risk.models import RiskContext, RiskLimits, RiskReasonCode, RiskResult


class TestRiskReasonCode:
    """Tests for RiskReasonCode enum."""

    def test_all_reason_codes_defined(self) -> None:
        """Test that all required reason codes from trading.mdc §4 are defined."""
        # Required codes per trading.mdc §4
        required_codes = {
            "RISK_MAX_POSITION",
            "RISK_MAX_NOTIONAL",
            "RISK_ORDER_TOO_LARGE",
            "RISK_PRICE_OUT_OF_BOUNDS",
            "RISK_DATA_STALE",
            "RISK_RATE_LIMIT",
            "RISK_KILL_SWITCH",
            "RISK_RECONCILE_DIVERGENCE",
        }

        defined_codes = {code.name for code in RiskReasonCode}

        for code in required_codes:
            assert code in defined_codes, f"Required reason code {code} not defined"

    def test_reason_code_values(self) -> None:
        """Test that reason codes have correct string values."""
        assert RiskReasonCode.RISK_MAX_POSITION.value == "RISK_MAX_POSITION"
        assert RiskReasonCode.RISK_MAX_NOTIONAL.value == "RISK_MAX_NOTIONAL"
        assert RiskReasonCode.RISK_ORDER_TOO_LARGE.value == "RISK_ORDER_TOO_LARGE"
        assert RiskReasonCode.RISK_ALLOWED.value == "RISK_ALLOWED"


class TestRiskResult:
    """Tests for RiskResult model."""

    def test_create_allowed_result(self) -> None:
        """Test creating an allowed risk result."""
        result = RiskResult(
            allowed=True,
            reason_codes=[RiskReasonCode.RISK_ALLOWED],
        )

        assert result.allowed is True
        assert result.reason_codes == [RiskReasonCode.RISK_ALLOWED]
        assert result.projections == {}
        assert result.metadata == {}

    def test_create_denied_result(self) -> None:
        """Test creating a denied risk result with reason codes."""
        result = RiskResult(
            allowed=False,
            reason_codes=[
                RiskReasonCode.RISK_MAX_POSITION,
                RiskReasonCode.RISK_DATA_STALE,
            ],
            metadata={"max_position": 10.0, "current_position": 15.0},
        )

        assert result.allowed is False
        assert RiskReasonCode.RISK_MAX_POSITION in result.reason_codes
        assert RiskReasonCode.RISK_DATA_STALE in result.reason_codes
        assert result.metadata["max_position"] == 10.0

    def test_result_with_projections(self) -> None:
        """Test risk result with projections."""
        result = RiskResult(
            allowed=True,
            reason_codes=[RiskReasonCode.RISK_ALLOWED],
            projections={
                "current_position": 5.0,
                "new_position": 7.0,
                "new_global_position": 12.0,
            },
        )

        assert result.projections["current_position"] == 5.0
        assert result.projections["new_position"] == 7.0
        assert result.projections["new_global_position"] == 12.0

    def test_result_with_metadata(self) -> None:
        """Test risk result with metadata (key inputs per trading.mdc §4)."""
        result = RiskResult(
            allowed=True,
            reason_codes=[RiskReasonCode.RISK_ALLOWED],
            metadata={
                "mid_price": 0.5,
                "qty": 1.0,
                "projected_position": 2.0,
                "limits_version": "1.0",
            },
        )

        # Verify key inputs per trading.mdc §4
        assert "mid_price" in result.metadata
        assert "qty" in result.metadata
        assert "projected_position" in result.metadata
        assert "limits_version" in result.metadata


class TestRiskLimits:
    """Tests for RiskLimits model."""

    def test_default_limits(self) -> None:
        """Test creating default risk limits."""
        limits = RiskLimits()

        assert limits.version == "1.0"
        assert limits.max_position_per_market == 1.0
        assert limits.max_position_global == 10.0
        assert limits.max_notional_exposure == 100.0
        assert limits.max_order_size == 10.0
        assert limits.max_trades_per_market == 1
        assert limits.order_rate_limit_per_minute == 60
        assert limits.cancel_rate_limit_per_minute == 120
        assert limits.max_data_staleness_seconds == 5.0
        assert limits.price_deviation_threshold == 0.1

    def test_custom_limits(self) -> None:
        """Test creating custom risk limits."""
        limits = RiskLimits(
            version="2.0",
            max_position_per_market=5.0,
            max_position_global=50.0,
            max_order_size=20.0,
        )

        assert limits.version == "2.0"
        assert limits.max_position_per_market == 5.0
        assert limits.max_position_global == 50.0
        assert limits.max_order_size == 20.0

    def test_limits_validation_positive_values(self) -> None:
        """Test that limits must be positive."""
        with pytest.raises(ValidationError):
            RiskLimits(max_position_per_market=-1.0)

        with pytest.raises(ValidationError):
            RiskLimits(max_order_size=0.0)

    def test_limits_validation_price_deviation_range(self) -> None:
        """Test that price_deviation_threshold is in valid range [0, 1]."""
        # Valid: 0 < threshold <= 1
        limits = RiskLimits(price_deviation_threshold=0.5)
        assert limits.price_deviation_threshold == 0.5

        # Invalid: > 1
        with pytest.raises(ValidationError):
            RiskLimits(price_deviation_threshold=1.5)

        # Invalid: <= 0
        with pytest.raises(ValidationError):
            RiskLimits(price_deviation_threshold=0.0)

    def test_limits_validation_non_negative_integers(self) -> None:
        """Test that integer limits must be non-negative."""
        # Valid: >= 0
        limits = RiskLimits(max_trades_per_market=0)
        assert limits.max_trades_per_market == 0

        limits = RiskLimits(order_rate_limit_per_minute=100)
        assert limits.order_rate_limit_per_minute == 100

        # Invalid: < 0
        with pytest.raises(ValidationError):
            RiskLimits(max_trades_per_market=-1)

    def test_limits_version_auditability(self) -> None:
        """Test that limits version is tracked for auditability per trading.mdc §7."""
        limits = RiskLimits(version="1.5")
        assert limits.version == "1.5"

        # Version can be any string (for flexibility)
        limits = RiskLimits(version="2024-01-15-v2")
        assert limits.version == "2024-01-15-v2"


class TestRiskContext:
    """Tests for RiskContext model."""

    def test_create_context_with_intent(self) -> None:
        """Test creating a risk context with order intent."""
        from polytrader.types import OrderIntentEvent

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        context = RiskContext(intent=intent)

        assert context.intent == intent
        assert context.current_positions == {}
        assert context.global_position == 0.0
        assert context.open_orders == set()
        assert context.market_data is None
        assert context.owned_tokens == set()
        assert context.kill_switch_active is False
        assert context.circuit_breaker_active is False
        assert context.reconciliation_healthy is True
        assert context.order_count_last_minute == 0
        assert context.cancel_count_last_minute == 0
        assert context.limits_version == "1.0"

    def test_create_context_with_positions(self) -> None:
        """Test creating a risk context with current positions."""
        from polytrader.types import OrderIntentEvent

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        positions = {
            ("test-market", "UP"): 2.0,
            ("other-market", "DOWN"): 1.0,
        }

        context = RiskContext(
            intent=intent,
            current_positions=positions,
            global_position=3.0,
        )

        assert context.current_positions == positions
        assert context.global_position == 3.0

    def test_create_context_with_market_data(self) -> None:
        """Test creating a risk context with market data."""
        from polytrader.types import MarketDataEvent, OrderIntentEvent

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

        assert context.market_data == market_data
        assert context.market_data.mid == 0.45

    def test_create_context_with_owned_tokens(self) -> None:
        """Test creating a risk context with owned tokens."""
        from polytrader.types import OrderIntentEvent

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="SELL",
            target_price=0.7,
            limit_price=0.65,
            size=1.0,
            reason="Test",
        )

        owned_tokens = {("test-market", "UP")}

        context = RiskContext(intent=intent, owned_tokens=owned_tokens)

        assert context.owned_tokens == owned_tokens

    def test_create_context_with_system_health(self) -> None:
        """Test creating a risk context with system health flags."""
        from polytrader.types import OrderIntentEvent

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
            kill_switch_active=True,
            circuit_breaker_active=False,
            reconciliation_healthy=False,
        )

        assert context.kill_switch_active is True
        assert context.circuit_breaker_active is False
        assert context.reconciliation_healthy is False

    def test_create_context_with_rate_limits(self) -> None:
        """Test creating a risk context with rate limit state."""
        from polytrader.types import OrderIntentEvent

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
            order_count_last_minute=50,
            cancel_count_last_minute=10,
        )

        assert context.order_count_last_minute == 50
        assert context.cancel_count_last_minute == 10

    def test_context_validation_global_position_non_negative(self) -> None:
        """Test that global_position must be non-negative."""
        from polytrader.types import OrderIntentEvent

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        # Valid: >= 0
        context = RiskContext(intent=intent, global_position=0.0)
        assert context.global_position == 0.0

        context = RiskContext(intent=intent, global_position=10.0)
        assert context.global_position == 10.0

        # Invalid: < 0
        with pytest.raises(ValidationError):
            RiskContext(intent=intent, global_position=-1.0)

    def test_context_validation_rate_limits_non_negative(self) -> None:
        """Test that rate limit counts must be non-negative."""
        from polytrader.types import OrderIntentEvent

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
        )

        # Valid: >= 0
        context = RiskContext(intent=intent, order_count_last_minute=0)
        assert context.order_count_last_minute == 0

        context = RiskContext(intent=intent, cancel_count_last_minute=0)
        assert context.cancel_count_last_minute == 0

        # Invalid: < 0
        with pytest.raises(ValidationError):
            RiskContext(intent=intent, order_count_last_minute=-1)

        with pytest.raises(ValidationError):
            RiskContext(intent=intent, cancel_count_last_minute=-1)
