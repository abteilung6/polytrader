"""Unit tests for RiskChecker per-lane rate limit counter reset.

Per PROPOSAL_PAPER_LIVE_RISK_LIMITS Commit 6: order_rate_limit_per_minute
is meaningful by resetting per-lane counters every N seconds.
Use injected Clock for determinism (unit_testing_techinical.mdc).
"""

from typing import cast

import pytest

from polytrader.events import APPROVED_PROPOSALS, PROPOSALS, EventBus, MemoryEventStore
from polytrader.events.types import MarketDataEvent
from polytrader.risk import get_default_limits
from polytrader.risk.engine import RiskChecker, RiskEngine
from polytrader.risk.policies import Clock
from polytrader.store import MemoryMarketDataStore
from tests.factories.events import create_order_intent_event


class AdvancingClock:
    """Clock with controllable monotonic time for tests."""

    def __init__(self, initial: float = 0.0) -> None:
        self._t = initial

    def monotonic(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


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
async def test_rate_counter_reset_clears_both_lanes() -> None:
    """After reset interval, _maybe_reset_rate_counters clears both lane counters."""
    bus, store = _make_bus_and_store()
    limits = get_default_limits()
    limits.order_rate_limit_per_minute = 10
    engine = RiskEngine(limits=limits)
    clock = AdvancingClock(0.0)
    checker = RiskChecker(
        bus=bus,
        engine=engine,
        store=store,
        clock=cast(Clock, clock),
        rate_reset_interval_s=60.0,
    )
    checker._order_count_last_minute_paper = 2
    checker._order_count_last_minute_live = 1
    checker._last_reset_monotonic = 0.0

    clock.advance(61.0)
    checker._maybe_reset_rate_counters()

    assert checker._order_count_last_minute_paper == 0
    assert checker._order_count_last_minute_live == 0


@pytest.mark.asyncio
async def test_after_reset_approval_within_limit_allowed() -> None:
    """After reset, approvals within limit are allowed (rate limit 1, two approvals after reset)."""
    import asyncio

    bus, store = _make_bus_and_store()
    limits = get_default_limits()
    limits.order_rate_limit_per_minute = 1
    limits.max_position_per_market = 10.0
    engine = RiskEngine(limits=limits)
    clock = AdvancingClock(0.0)
    checker = RiskChecker(
        bus=bus,
        engine=engine,
        store=store,
        clock=cast(Clock, clock),
        rate_reset_interval_s=60.0,
    )
    approved_queue = bus.subscribe(APPROVED_PROPOSALS)
    risk_task = asyncio.create_task(checker.run())
    await asyncio.sleep(0.02)

    # First approval (counter = 1)
    intent1 = create_order_intent_event(
        strategy_id="s1",
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        size=1.0,
        limit_price=0.45,
        target_price=0.5,
    )
    await bus.publish(PROPOSALS, intent1)
    await asyncio.wait_for(approved_queue.get(), timeout=1.0)
    assert checker._order_count_last_minute_paper == 1

    # Advance past reset interval; next proposal will trigger reset then check
    clock.advance(61.0)

    # Second proposal: reset runs first (counters -> 0), then check allows (1 <= 1)
    intent2 = create_order_intent_event(
        strategy_id="s2",
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        size=1.0,
        limit_price=0.45,
        target_price=0.5,
    )
    await bus.publish(PROPOSALS, intent2)
    approved2 = await asyncio.wait_for(approved_queue.get(), timeout=1.0)
    assert approved2.correlation_id == intent2.correlation_id
    assert checker._order_count_last_minute_paper == 1

    checker.stop()
    risk_task.cancel()
    try:
        await risk_task
    except asyncio.CancelledError:
        pass
