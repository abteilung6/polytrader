"""Tests for risk policies.

Per testing.mdc §1.A: Unit tests for risk policies (fast, deterministic).
"""

from unittest.mock import MagicMock

from polytrader.events.types import OrderIntentEvent
from polytrader.risk.models import RiskContext, RiskLimits, RiskReasonCode
from polytrader.risk.policies import check_proposal_validity, check_token_ownership


class TestCheckProposalValidity:
    """Tests for check_proposal_validity policy."""

    def test_check_proposal_validity_expired(self) -> None:
        """Test that expired proposals are rejected."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Test",
            ttl_s=2.0,
            strategy_id="simple_threshold",
        )

        # Create context with intent that's 3 seconds old (expired)
        clock = MagicMock()
        clock.monotonic.return_value = intent.ts_mono + 3.0

        context = RiskContext(intent=intent)
        limits = RiskLimits(max_order_size=10.0)

        result = check_proposal_validity(context, limits, clock=clock)

        assert result.allowed is False
        assert RiskReasonCode.RISK_PROPOSAL_EXPIRED in result.reason_codes
        assert result.metadata["proposal_age_seconds"] == 3.0
        assert result.metadata["proposal_ttl_seconds"] == 2.0

    def test_check_proposal_validity_invalid_size(self) -> None:
        """Test that proposals with size <= 0 are rejected."""
        # Use model_construct to bypass Pydantic validation for testing
        # (Pydantic normally validates size > 0, but policy should check defensively)
        intent = OrderIntentEvent.model_construct(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=0.0,  # Invalid size
            reason="Test",
            strategy_id="simple_threshold",
        )

        clock = MagicMock()
        clock.monotonic.return_value = intent.ts_mono + 0.5  # Not expired

        context = RiskContext(intent=intent)
        limits = RiskLimits(max_order_size=10.0)

        result = check_proposal_validity(context, limits, clock=clock)

        assert result.allowed is False
        assert RiskReasonCode.RISK_INVALID_SIZE in result.reason_codes
        assert result.metadata["proposal_size"] == 0.0

    def test_check_proposal_validity_too_large(self) -> None:
        """Test that proposals exceeding max_order_size are rejected."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=15.0,  # Exceeds max_order_size
            reason="Test",
            strategy_id="simple_threshold",
        )

        clock = MagicMock()
        clock.monotonic.return_value = intent.ts_mono + 0.5  # Not expired

        context = RiskContext(intent=intent)
        limits = RiskLimits(max_order_size=10.0, version="1.0")

        result = check_proposal_validity(context, limits, clock=clock)

        assert result.allowed is False
        assert RiskReasonCode.RISK_ORDER_TOO_LARGE in result.reason_codes
        assert result.metadata["proposal_size"] == 15.0
        assert result.metadata["max_order_size"] == 10.0
        assert result.metadata["limits_version"] == "1.0"

    def test_check_proposal_validity_valid(self) -> None:
        """Test that valid proposals pass the check."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=5.0,  # Valid size
            reason="Test",
            strategy_id="simple_threshold",
        )

        clock = MagicMock()
        clock.monotonic.return_value = intent.ts_mono + 0.5  # Not expired

        context = RiskContext(intent=intent)
        limits = RiskLimits(max_order_size=10.0)

        result = check_proposal_validity(context, limits, clock=clock)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes
        assert result.metadata == {}

    def test_check_proposal_validity_with_clock(self) -> None:
        """Test that clock injection works for deterministic testing."""
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

        # Use deterministic clock
        clock = MagicMock()
        clock.monotonic.return_value = intent.ts_mono + 0.1  # Not expired

        context = RiskContext(intent=intent)
        limits = RiskLimits(max_order_size=10.0)

        result = check_proposal_validity(context, limits, clock=clock)

        assert result.allowed is True
        clock.monotonic.assert_called_once()

    def test_check_proposal_validity_without_clock(self) -> None:
        """Test that function works without clock (uses time.monotonic())."""
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

        context = RiskContext(intent=intent)
        limits = RiskLimits(max_order_size=10.0)

        # Should work without clock (uses time.monotonic())
        result = check_proposal_validity(context, limits, clock=None)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_check_proposal_validity_exact_max_size(self) -> None:
        """Test that proposals at exactly max_order_size are allowed."""
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=10.0,  # Exactly max_order_size
            reason="Test",
            strategy_id="simple_threshold",
        )

        clock = MagicMock()
        clock.monotonic.return_value = intent.ts_mono + 0.5

        context = RiskContext(intent=intent)
        limits = RiskLimits(max_order_size=10.0)

        result = check_proposal_validity(context, limits, clock=clock)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes


class TestCheckTokenOwnership:
    """Tests for check_token_ownership policy."""

    def test_check_token_ownership_sell_without_tokens(self) -> None:
        """Test that SELL orders without tokens are rejected."""
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
            owned_tokens=set(),  # No tokens owned
        )
        limits = RiskLimits()

        result = check_token_ownership(context, limits)

        assert result.allowed is False
        assert RiskReasonCode.RISK_INSUFFICIENT_TOKENS in result.reason_codes
        assert result.metadata["market_slug"] == "test-market"
        assert result.metadata["outcome"] == "UP"

    def test_check_token_ownership_sell_with_tokens(self) -> None:
        """Test that SELL orders with tokens are allowed."""
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
            owned_tokens={("test-market", "UP")},  # Tokens owned
        )
        limits = RiskLimits()

        result = check_token_ownership(context, limits)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_check_token_ownership_buy(self) -> None:
        """Test that BUY orders are always allowed (no token check needed)."""
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
            owned_tokens=set(),  # No tokens, but BUY doesn't need them
        )
        limits = RiskLimits()

        result = check_token_ownership(context, limits)

        assert result.allowed is True
        assert RiskReasonCode.RISK_ALLOWED in result.reason_codes

    def test_check_token_ownership_sell_wrong_outcome(self) -> None:
        """Test that SELL orders for wrong outcome are rejected."""
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
            owned_tokens={("test-market", "DOWN")},  # Wrong outcome
        )
        limits = RiskLimits()

        result = check_token_ownership(context, limits)

        assert result.allowed is False
        assert RiskReasonCode.RISK_INSUFFICIENT_TOKENS in result.reason_codes

    def test_check_token_ownership_sell_wrong_market(self) -> None:
        """Test that SELL orders for wrong market are rejected."""
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
            owned_tokens={("other-market", "UP")},  # Wrong market
        )
        limits = RiskLimits()

        result = check_token_ownership(context, limits)

        assert result.allowed is False
        assert RiskReasonCode.RISK_INSUFFICIENT_TOKENS in result.reason_codes
