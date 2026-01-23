"""Integration tests for strategy activation risk check.

Per Platform_Proposal.md §2.3: Tests verify end-to-end flow where inactive
strategies are denied and active strategies are allowed.
"""

import pytest

from polytrader.events import EventBus
from polytrader.events.types import MarketDataEvent
from polytrader.risk import RiskEngine, get_default_limits
from polytrader.risk.models import RiskContext, RiskReasonCode
from polytrader.store import MemoryMarketDataStore
from tests.factories.events import create_order_intent_event


@pytest.fixture
def bus() -> EventBus:
    """Create event bus for tests."""
    return EventBus()


@pytest.fixture
def store() -> MemoryMarketDataStore:
    """Create market data store for tests."""
    return MemoryMarketDataStore()


@pytest.mark.asyncio
async def test_inactive_strategy_intent_denied(
    bus: EventBus,
    store: MemoryMarketDataStore,  # noqa: ARG001
) -> None:
    """Test end-to-end: inactive strategy intent → RiskCheckEvent with denied."""
    # Add market data
    market_data = MarketDataEvent(
        market_slug="test-market",
        outcome="UP",
        best_bid=0.45,
        best_ask=0.55,
    )
    store.add(market_data)

    # Create intent from inactive strategy
    intent = create_order_intent_event(
        strategy_id="inactive_strategy",
        market_slug="test-market",
    )

    # Test with risk engine directly
    risk_limits = get_default_limits()
    risk_engine = RiskEngine(limits=risk_limits)

    context = RiskContext(
        intent=intent,
        market_data=market_data,
        active_strategies=set(),  # Empty set (inactive)
        is_paper_mode=False,
        reconciliation_healthy=True,
    )

    result = risk_engine.check(context)

    # Should be denied by strategy activation policy
    assert result.allowed is False
    assert RiskReasonCode.RISK_STRATEGY_NOT_ACTIVE in result.reason_codes


@pytest.mark.asyncio
async def test_active_strategy_intent_allowed(
    bus: EventBus,
    store: MemoryMarketDataStore,  # noqa: ARG001
) -> None:
    """Test end-to-end: active strategy intent → RiskCheckEvent with allowed."""
    # Add market data
    market_data = MarketDataEvent(
        market_slug="test-market",
        outcome="UP",
        best_bid=0.45,
        best_ask=0.55,
    )
    store.add(market_data)

    # Create intent from active strategy
    intent = create_order_intent_event(
        strategy_id="active_strategy",
        market_slug="test-market",
    )

    # Test with active strategy using risk engine directly
    risk_limits = get_default_limits()
    risk_engine = RiskEngine(limits=risk_limits)

    # Create context with active strategy
    context = RiskContext(
        intent=intent,
        market_data=market_data,
        active_strategies={"active_strategy"},
        is_paper_mode=False,
        reconciliation_healthy=True,
    )

    result = risk_engine.check(context)

    # Active strategy should pass (if other policies pass)
    # Note: This test verifies the policy works, not the full RiskChecker flow
    assert RiskReasonCode.RISK_STRATEGY_NOT_ACTIVE not in result.reason_codes


@pytest.mark.asyncio
async def test_paper_mode_all_strategies_allowed(
    bus: EventBus,
    store: MemoryMarketDataStore,  # noqa: ARG001
) -> None:
    """Test paper mode: all strategies allowed regardless of activation."""
    # Add market data
    market_data = MarketDataEvent(
        market_slug="test-market",
        outcome="UP",
        best_bid=0.45,
        best_ask=0.55,
    )
    store.add(market_data)

    # Create intent from inactive strategy
    intent = create_order_intent_event(
        strategy_id="inactive_strategy",
        market_slug="test-market",
    )

    # Test with paper mode
    risk_limits = get_default_limits()
    risk_engine = RiskEngine(limits=risk_limits)

    context = RiskContext(
        intent=intent,
        market_data=market_data,
        active_strategies=set(),  # Empty set (inactive)
        is_paper_mode=True,  # Paper mode
        reconciliation_healthy=True,
    )

    result = risk_engine.check(context)

    # Paper mode should allow (strategy activation policy won't deny)
    # Note: Other policies may deny, but strategy activation won't
    assert RiskReasonCode.RISK_STRATEGY_NOT_ACTIVE not in result.reason_codes


@pytest.mark.asyncio
async def test_live_mode_only_active_strategies_allowed(
    bus: EventBus,
    store: MemoryMarketDataStore,  # noqa: ARG001
) -> None:
    """Test live mode: only active strategies allowed."""
    # Add market data
    market_data = MarketDataEvent(
        market_slug="test-market",
        outcome="UP",
        best_bid=0.45,
        best_ask=0.55,
    )
    store.add(market_data)

    risk_limits = get_default_limits()
    risk_engine = RiskEngine(limits=risk_limits)

    # Test inactive strategy
    inactive_intent = create_order_intent_event(
        strategy_id="inactive_strategy",
        market_slug="test-market",
    )
    inactive_context = RiskContext(
        intent=inactive_intent,
        market_data=market_data,
        active_strategies={"active_strategy"},  # inactive_strategy not in set
        is_paper_mode=False,
        reconciliation_healthy=True,
    )
    inactive_result = risk_engine.check(inactive_context)

    # Test active strategy
    active_intent = create_order_intent_event(
        strategy_id="active_strategy",
        market_slug="test-market",
    )
    active_context = RiskContext(
        intent=active_intent,
        market_data=market_data,
        active_strategies={"active_strategy"},
        is_paper_mode=False,
        reconciliation_healthy=True,
    )
    active_result = risk_engine.check(active_context)

    # Inactive strategy should be denied
    assert inactive_result.allowed is False
    assert RiskReasonCode.RISK_STRATEGY_NOT_ACTIVE in inactive_result.reason_codes

    # Active strategy should pass (if other policies pass)
    assert RiskReasonCode.RISK_STRATEGY_NOT_ACTIVE not in active_result.reason_codes
