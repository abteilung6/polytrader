"""Unit tests for RiskCheckEvent lane field (paper vs live).

Per PROPOSAL_PAPER_LIVE_RISK_LIMITS Commit 5: every RiskCheckEvent has lane set.
Assert on emitted event (events as audit truth, testing.mdc §6).
"""

import asyncio
from typing import cast

import pytest

from polytrader.events import PROPOSALS, RISK_CHECKS, EventBus, MemoryEventStore
from polytrader.events.types import MarketDataEvent, RiskCheckEvent
from polytrader.ops.control import ExecutionControl
from polytrader.risk import RiskChecker, RiskEngine, get_default_limits
from polytrader.store import MemoryMarketDataStore
from tests.factories.events import create_order_intent_event


class _MockExecutionControl:
    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled


@pytest.mark.asyncio
async def test_risk_check_event_contains_paper_lane_when_intent_paper() -> None:
    """When lane is paper, emitted RiskCheckEvent has lane='paper'."""
    bus = EventBus(store=MemoryEventStore())
    store = MemoryMarketDataStore()
    store.add(
        MarketDataEvent(market_slug="m", outcome="UP", best_bid=0.44, best_ask=0.46)
    )
    limits = get_default_limits()
    engine = RiskEngine(limits=limits)
    checker = RiskChecker(bus=bus, engine=engine, store=store)
    risk_queue = bus.subscribe(RISK_CHECKS)
    task = asyncio.create_task(checker.run())
    await asyncio.sleep(0.02)

    intent = create_order_intent_event(
        strategy_id="paper_s",
        market_slug="m",
        outcome="UP",
        side="BUY",
        size=1.0,
        limit_price=0.45,
        target_price=0.5,
    )
    await bus.publish(PROPOSALS, intent)
    event = await asyncio.wait_for(risk_queue.get(), timeout=1.0)

    assert isinstance(event, RiskCheckEvent)
    assert event.lane == "paper"

    checker.stop()
    task.cancel()
    try:
        await task
    except Exception:
        pass


@pytest.mark.asyncio
async def test_risk_check_event_contains_live_lane_when_intent_live() -> None:
    """When execution enabled and strategy in active set, emitted RiskCheckEvent has lane='live'."""
    bus = EventBus(store=MemoryEventStore())
    store = MemoryMarketDataStore()
    store.add(
        MarketDataEvent(market_slug="m", outcome="UP", best_bid=0.44, best_ask=0.46)
    )
    limits = get_default_limits()
    engine = RiskEngine(limits=limits)
    control = _MockExecutionControl(enabled=True)

    def active() -> set[str]:
        return {"live_s"}

    checker = RiskChecker(
        bus=bus,
        engine=engine,
        store=store,
        execution_control=cast(ExecutionControl, control),
        get_active_strategies=active,
    )
    risk_queue = bus.subscribe(RISK_CHECKS)
    task = asyncio.create_task(checker.run())
    await asyncio.sleep(0.02)

    intent = create_order_intent_event(
        strategy_id="live_s",
        market_slug="m",
        outcome="UP",
        side="BUY",
        size=1.0,
        limit_price=0.45,
        target_price=0.5,
    )
    await bus.publish(PROPOSALS, intent)
    event = await asyncio.wait_for(risk_queue.get(), timeout=1.0)

    assert isinstance(event, RiskCheckEvent)
    assert event.lane == "live"

    checker.stop()
    task.cancel()
    try:
        await task
    except Exception:
        pass
