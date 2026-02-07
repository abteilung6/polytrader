"""Tests for position limit policies.

Per testing.mdc §1.A: Unit tests for position limit policies (fast, deterministic).
"""

from polytrader.events.types import MarketDataEvent, OrderIntentEvent
from polytrader.risk.models import RiskContext, RiskLimits, RiskReasonCode
from polytrader.risk.policies import check_max_trades_per_market, check_position_limits


class TestCheckPositionLimits:
    """Tests for check_position_limits policy."""

    def test_check_position_limits_per_market_exceeded(self) -> None:
        """Test that per-market position limit is enforced."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=5.0,
            reason="Test",
            strategy_id="simple_threshold",
        )

        context = RiskContext(
            intent=intent,
            current_positions={("test-market", "UP"): 3.0},  # Already have 3.0
            global_position=3.0,
        )
        limits = RiskLimits(
            max_position_per_market=5.0,  # Limit is 5.0, new position would be 8.0
            max_position_global=100.0,
            max_notional_exposure=1000.0,
        )

        result = check_position_limits(context, limits)

        assert result.allowed is False
        assert RiskReasonCode.RISK_MAX_POSITION in result.reason_codes
        assert result.projections["new_position"] == 8.0
        assert result.metadata["new_position"] == 8.0
        assert result.metadata["max_position_per_market"] == 5.0

    def test_check_position_limits_global_exceeded(self) -> None:
        """Test that global position limit is enforced."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=5.0,
            reason="Test",
            strategy_id="simple_threshold",
        )

        context = RiskContext(
            intent=intent,
            current_positions={("test-market", "UP"): 1.0},
            global_position=8.0,  # Already at 8.0
        )
        limits = RiskLimits(
            max_position_per_market=100.0,  # Per-market OK
            max_position_global=10.0,  # Global limit is 10.0, new would be 13.0
            max_notional_exposure=1000.0,
        )

        result = check_position_limits(context, limits)

        assert result.allowed is False
        assert RiskReasonCode.RISK_MAX_POSITION in result.reason_codes
        assert result.projections["new_global_position"] == 13.0
        assert result.metadata["new_global_position"] == 13.0
        assert result.metadata["max_position_global"] == 10.0

    def test_check_position_limits_notional_exceeded(self) -> None:
        """Test that notional exposure limit is enforced for BUY orders."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=50.0,
            reason="Test",
            strategy_id="simple_threshold",
        )

        context = RiskContext(
            intent=intent,
            current_positions={("test-market", "UP"): 1.0},
            global_position=60.0,  # Already at 60.0
        )
        limits = RiskLimits(
            max_position_per_market=100.0,
            max_position_global=200.0,
            max_notional_exposure=100.0,  # Notional limit is 100.0, new would be 110.0
        )

        result = check_position_limits(context, limits)

        assert result.allowed is False
        assert RiskReasonCode.RISK_MAX_NOTIONAL in result.reason_codes
        assert result.metadata["new_notional_exposure"] == 110.0
        assert result.metadata["max_notional_exposure"] == 100.0

    def test_check_position_limits_valid(self) -> None:
        """Test that valid positions pass the check."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=2.0,
            reason="Test",
            strategy_id="simple_threshold",
        )

        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
        )

        context = RiskContext(
            intent=intent,
            current_positions={("test-market", "UP"): 1.0},
            global_position=5.0,
            market_data=market_data,
        )
        limits = RiskLimits(
            max_position_per_market=10.0,
            max_position_global=100.0,
            max_notional_exposure=1000.0,
            version="1.0",
        )

        result = check_position_limits(context, limits)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes
        assert result.projections["new_position"] == 3.0
        assert result.projections["new_global_position"] == 7.0
        assert result.metadata["mid_price"] == 0.45
        assert result.metadata["qty"] == 2.0
        assert result.metadata["projected_position"] == 3.0
        assert result.metadata["limits_version"] == "1.0"

    def test_check_position_limits_sell_reduces_position(self) -> None:
        """Test that SELL orders reduce position correctly."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="SELL",
            target_price=0.7,
            limit_price=0.65,
            size=2.0,
            reason="Test",
            strategy_id="simple_threshold",
        )

        context = RiskContext(
            intent=intent,
            current_positions={("test-market", "UP"): 5.0},  # Start with 5.0
            global_position=10.0,
        )
        limits = RiskLimits(
            max_position_per_market=10.0,
            max_position_global=100.0,
            max_notional_exposure=1000.0,
        )

        result = check_position_limits(context, limits)

        assert result.allowed is True
        assert result.projections["new_position"] == 3.0  # 5.0 - 2.0
        assert result.projections["new_global_position"] == 8.0  # 10.0 - 2.0

    def test_check_position_limits_sell_negative_clamped(self) -> None:
        """Test that SELL orders that would go negative are clamped to 0."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="SELL",
            target_price=0.7,
            limit_price=0.65,
            size=10.0,  # Selling more than we have
            reason="Test",
            strategy_id="simple_threshold",
        )

        context = RiskContext(
            intent=intent,
            current_positions={("test-market", "UP"): 2.0},  # Only have 2.0
            global_position=5.0,
        )
        limits = RiskLimits(
            max_position_per_market=10.0,
            max_position_global=100.0,
            max_notional_exposure=1000.0,
        )

        result = check_position_limits(context, limits)

        assert result.allowed is True
        assert result.projections["new_position"] == 0.0  # Clamped to 0
        assert result.projections["new_global_position"] == 0.0  # Clamped to 0

    def test_check_position_limits_no_existing_position(self) -> None:
        """Test position limits with no existing position."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=3.0,
            reason="Test",
            strategy_id="simple_threshold",
        )

        context = RiskContext(
            intent=intent,
            current_positions={},  # No existing position
            global_position=0.0,
        )
        limits = RiskLimits(
            max_position_per_market=5.0,
            max_position_global=100.0,
            max_notional_exposure=1000.0,
        )

        result = check_position_limits(context, limits)

        assert result.allowed is True
        assert result.projections["current_position"] == 0.0
        assert result.projections["new_position"] == 3.0

    def test_check_position_limits_exact_limit_allowed(self) -> None:
        """Test that positions at exactly the limit are allowed."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=5.0,
            reason="Test",
            strategy_id="simple_threshold",
        )

        context = RiskContext(
            intent=intent,
            current_positions={("test-market", "UP"): 0.0},
            global_position=0.0,
        )
        limits = RiskLimits(
            max_position_per_market=5.0,  # Exactly at limit
            max_position_global=100.0,
            max_notional_exposure=1000.0,
        )

        result = check_position_limits(context, limits)

        assert result.allowed is True
        assert result.projections["new_position"] == 5.0


class TestCheckMaxTradesPerMarket:
    """Tests for check_max_trades_per_market policy."""

    def test_check_max_trades_per_market_buy_already_traded(self) -> None:
        """Test that BUY orders are denied if this strategy already traded."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            strategy_id="simple_threshold",
        )

        context = RiskContext(
            intent=intent,
            # Same strategy already traded this market/outcome
            executed_trades={("simple_threshold", "test-market", "UP")},
        )
        limits = RiskLimits(max_trades_per_market=1, version="1.0")

        result = check_max_trades_per_market(context, limits)

        assert result.allowed is False
        assert RiskReasonCode.RISK_MAX_POSITION in result.reason_codes
        assert result.metadata["strategy_id"] == "simple_threshold"
        assert result.metadata["market_slug"] == "test-market"
        assert result.metadata["outcome"] == "UP"
        assert result.metadata["max_trades_per_market"] == 1
        assert result.metadata["limits_version"] == "1.0"

    def test_check_max_trades_per_market_buy_not_traded(self) -> None:
        """Test that BUY orders are allowed if not yet traded."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            strategy_id="simple_threshold",
        )

        context = RiskContext(
            intent=intent,
            executed_trades=set(),  # Not traded yet
        )
        limits = RiskLimits(max_trades_per_market=1)

        result = check_max_trades_per_market(context, limits)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_check_max_trades_per_market_sell_always_allowed(self) -> None:
        """Test that SELL orders are always allowed (even if already traded)."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="SELL",
            target_price=0.7,
            limit_price=0.65,
            size=1.0,
            reason="Test",
            strategy_id="simple_threshold",
        )

        context = RiskContext(
            intent=intent,
            executed_trades={
                ("simple_threshold", "test-market", "UP")
            },  # Already traded, but SELL is OK
        )
        limits = RiskLimits(max_trades_per_market=1)

        result = check_max_trades_per_market(context, limits)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_check_max_trades_per_market_different_outcome(self) -> None:
        """Test that trading different outcome is allowed."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="DOWN",  # Different outcome
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            strategy_id="simple_threshold",
        )

        context = RiskContext(
            intent=intent,
            executed_trades={("simple_threshold", "test-market", "UP")},  # Traded UP, but not DOWN
        )
        limits = RiskLimits(max_trades_per_market=1)

        result = check_max_trades_per_market(context, limits)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_check_max_trades_per_market_different_market(self) -> None:
        """Test that trading different market is allowed."""
        intent = OrderIntentEvent(
            market_slug="other-market",  # Different market
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            strategy_id="simple_threshold",
        )

        context = RiskContext(
            intent=intent,
            executed_trades={("simple_threshold", "test-market", "UP")},  # Different market
        )
        limits = RiskLimits(max_trades_per_market=1)

        result = check_max_trades_per_market(context, limits)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_check_max_trades_per_market_different_strategy_allowed(self) -> None:
        """Test that different strategy instances can trade the same market/outcome.

        This is the KEY regression test for the bug where only one instance
        per template could trade.  Scoping by strategy_id means instance B
        is NOT blocked by instance A's trade on the same market.
        """
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            strategy_id="strategy_instance_B",  # Different strategy instance
        )

        context = RiskContext(
            intent=intent,
            # Instance A already traded this market — but B should NOT be blocked
            executed_trades={("strategy_instance_A", "test-market", "UP")},
        )
        limits = RiskLimits(max_trades_per_market=1)

        result = check_max_trades_per_market(context, limits)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_check_max_trades_per_market_same_strategy_blocked(self) -> None:
        """Test that the SAME strategy instance is blocked from re-trading the same market."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            strategy_id="strategy_instance_A",
        )

        context = RiskContext(
            intent=intent,
            # Same instance already traded — should be blocked
            executed_trades={("strategy_instance_A", "test-market", "UP")},
        )
        limits = RiskLimits(max_trades_per_market=1)

        result = check_max_trades_per_market(context, limits)

        assert result.allowed is False
        assert RiskReasonCode.RISK_MAX_POSITION in result.reason_codes
