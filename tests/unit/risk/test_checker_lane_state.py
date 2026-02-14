"""Unit tests for RiskChecker per-lane state (paper vs live).

Component: RiskChecker (risk/engine.py)
Stage: Risk (flows.mdc §6)
Contract: Context and limits are lane-specific; paper approvals do not affect live state.
"""

import asyncio
from typing import cast

import pytest

from polytrader.events import APPROVED_PROPOSALS, PROPOSALS, EventBus, MemoryEventStore
from polytrader.events.types import MarketDataEvent
from polytrader.ops.control import ExecutionControl
from polytrader.risk import RiskChecker, RiskEngine, get_default_limits
from polytrader.store import MemoryMarketDataStore
from polytrader.types import Outcome
from tests.factories.events import create_order_intent_event

# Outcome for set key type (str literal "UP" is valid Outcome)
_UP: Outcome = "UP"


class _MockExecutionControl:
    """Minimal mock for ExecutionControl (is_enabled only)."""

    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled


def _make_bus_and_store() -> tuple[EventBus, MemoryMarketDataStore]:
    bus = EventBus(store=MemoryEventStore())
    store = MemoryMarketDataStore()
    store.add(
        MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
        )
    )
    return bus, store


@pytest.mark.asyncio
async def test_approval_increments_paper_counter_when_lane_paper() -> None:
    """When lane is paper, approval increments paper counter and adds to paper approved set."""
    bus, store = _make_bus_and_store()
    limits = get_default_limits()
    engine = RiskEngine(limits=limits)
    # No execution_control → lane always paper
    checker = RiskChecker(bus=bus, engine=engine, store=store)
    approved_queue = bus.subscribe(APPROVED_PROPOSALS)
    risk_task = asyncio.create_task(checker.run())
    await asyncio.sleep(0.02)

    intent = create_order_intent_event(
        strategy_id="paper_strategy",
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        size=1.0,
        limit_price=0.45,
        target_price=0.5,
    )
    await bus.publish(PROPOSALS, intent)
    await asyncio.wait_for(approved_queue.get(), timeout=1.0)

    assert checker._order_count_last_minute_paper == 1
    assert checker._order_count_last_minute_live == 0
    key = (intent.strategy_id, intent.market_slug, intent.outcome)
    assert key in checker._approved_trades_paper
    assert key not in checker._approved_trades_live

    checker.stop()
    risk_task.cancel()
    try:
        await risk_task
    except Exception:
        pass


@pytest.mark.asyncio
async def test_approval_increments_live_counter_when_lane_live() -> None:
    """When execution enabled and strategy in active set, approval increments live counter."""
    bus, store = _make_bus_and_store()
    limits = get_default_limits()
    engine = RiskEngine(limits=limits)
    control = _MockExecutionControl(enabled=True)

    def active() -> set[str]:
        return {"live_strategy"}

    checker = RiskChecker(
        bus=bus,
        engine=engine,
        store=store,
        execution_control=cast(ExecutionControl, control),
        get_active_strategies=active,
    )
    approved_queue = bus.subscribe(APPROVED_PROPOSALS)
    risk_task = asyncio.create_task(checker.run())
    await asyncio.sleep(0.02)

    intent = create_order_intent_event(
        strategy_id="live_strategy",
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        size=1.0,
        limit_price=0.45,
        target_price=0.5,
    )
    await bus.publish(PROPOSALS, intent)
    await asyncio.wait_for(approved_queue.get(), timeout=1.0)

    assert checker._order_count_last_minute_live == 1
    assert checker._order_count_last_minute_paper == 0
    key = (intent.strategy_id, intent.market_slug, intent.outcome)
    assert key in checker._approved_trades_live
    assert key not in checker._approved_trades_paper

    checker.stop()
    risk_task.cancel()
    try:
        await risk_task
    except Exception:
        pass


def test_build_context_uses_paper_state_for_paper_lane_intent() -> None:
    """Context for paper lane is built from paper approved/executed state only."""
    bus, store = _make_bus_and_store()
    limits = get_default_limits()
    engine = RiskEngine(limits=limits)
    checker = RiskChecker(bus=bus, engine=engine, store=store)
    key: tuple[str, str, Outcome] = ("s1", "test-market", _UP)
    checker._approved_trades_paper.add(key)
    checker._order_count_last_minute_paper = 2
    # Live state empty
    intent = create_order_intent_event(strategy_id="s2", market_slug="test-market", outcome="UP")
    context = checker._build_context(intent, "paper")
    assert context.current_positions[("test-market", "UP")] == 1.0
    assert context.global_position == 1.0
    assert context.order_count_last_minute == 2
    assert context.limits_version == limits.version


def test_build_context_uses_live_state_for_live_lane_intent() -> None:
    """Context for live lane is built from live approved/executed state only."""
    bus, store = _make_bus_and_store()
    limits = get_default_limits()
    engine = RiskEngine(limits=limits)
    checker = RiskChecker(bus=bus, engine=engine, store=store)
    key = ("s1", "test-market", _UP)
    checker._approved_trades_live.add(key)
    checker._order_count_last_minute_live = 1
    # Paper state empty
    intent = create_order_intent_event(strategy_id="s2", market_slug="test-market", outcome="UP")
    context = checker._build_context(intent, "live")
    assert context.current_positions[("test-market", "UP")] == 1.0
    assert context.global_position == 1.0
    assert context.order_count_last_minute == 1
    assert context.limits_version == limits.version


@pytest.mark.asyncio
async def test_paper_approvals_do_not_affect_live_rate_limit() -> None:
    """Many paper approvals do not consume live rate limit; first live intent is allowed."""
    bus, store = _make_bus_and_store()
    limits = get_default_limits()
    limits.order_rate_limit_per_minute = 10  # allow 3 paper + 1 live (counters are per-lane)
    limits.max_position_per_market = 10.0  # allow multiple paper + one live in same market
    engine = RiskEngine(limits=limits)
    control = _MockExecutionControl(enabled=True)

    def active() -> set[str]:
        return {"live_only"}

    checker = RiskChecker(
        bus=bus,
        engine=engine,
        store=store,
        execution_control=cast(ExecutionControl, control),
        get_active_strategies=active,
    )
    approved_queue = bus.subscribe(APPROVED_PROPOSALS)
    risk_task = asyncio.create_task(checker.run())
    await asyncio.sleep(0.02)

    # Several paper intents (different strategies, not in active set)
    for i in range(3):
        intent = create_order_intent_event(
            strategy_id=f"paper_{i}",
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            limit_price=0.45,
            target_price=0.5,
        )
        await bus.publish(PROPOSALS, intent)
        await asyncio.wait_for(approved_queue.get(), timeout=1.0)
    assert checker._order_count_last_minute_paper == 3
    assert checker._order_count_last_minute_live == 0

    # One live intent — should be allowed (live rate limit not consumed by paper)
    live_intent = create_order_intent_event(
        strategy_id="live_only",
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        size=1.0,
        limit_price=0.45,
        target_price=0.5,
    )
    await bus.publish(PROPOSALS, live_intent)
    approved = await asyncio.wait_for(approved_queue.get(), timeout=1.0)
    assert approved.correlation_id == live_intent.correlation_id
    assert checker._order_count_last_minute_live == 1

    checker.stop()
    risk_task.cancel()
    try:
        await risk_task
    except Exception:
        pass
