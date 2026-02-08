"""Unit tests for ApprovedProposalRouter.

Per proposal: assert on which topic received which intents (events as audit truth).
"""

import asyncio

import pytest

from polytrader.events import (
    APPROVED_PROPOSALS,
    APPROVED_PROPOSALS_LIVE,
    APPROVED_PROPOSALS_PAPER,
    EventBus,
)
from polytrader.ops.control import ExecutionControl
from polytrader.platform.proposal_router import ApprovedProposalRouter
from tests.factories.events import create_order_intent_event


@pytest.fixture
def bus() -> EventBus:
    """In-memory event bus."""
    return EventBus()


@pytest.fixture
def execution_control() -> ExecutionControl:
    """Execution control (default disabled)."""
    return ExecutionControl()


@pytest.mark.asyncio
async def test_route_sends_to_paper_when_execution_disabled(
    bus: EventBus,
    execution_control: ExecutionControl,
) -> None:
    """When execution is disabled, all intents go to paper topic."""
    paper_queue = bus.subscribe(APPROVED_PROPOSALS_PAPER)
    live_queue = bus.subscribe(APPROVED_PROPOSALS_LIVE)
    execution_control.execution_enabled = False
    active: set[str] = set()
    router = ApprovedProposalRouter(
        bus=bus,
        execution_control=execution_control,
        get_active_strategies=lambda: active,
    )
    task = asyncio.create_task(router.run())
    await asyncio.sleep(0)
    intent = create_order_intent_event(strategy_id="s1", correlation_id="c1")
    await bus.publish(APPROVED_PROPOSALS, intent)
    received_paper = await asyncio.wait_for(paper_queue.get(), timeout=1.0)
    assert received_paper.correlation_id == "c1"
    assert received_paper.strategy_id == "s1"
    with pytest.raises(asyncio.QueueEmpty):
        live_queue.get_nowait()
    router.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_route_sends_to_paper_when_execution_enabled_but_empty_active_set(
    bus: EventBus,
    execution_control: ExecutionControl,
) -> None:
    """When execution is enabled but active set is empty, intents go to paper."""
    paper_queue = bus.subscribe(APPROVED_PROPOSALS_PAPER)
    live_queue = bus.subscribe(APPROVED_PROPOSALS_LIVE)
    execution_control.execution_enabled = True
    active: set[str] = set()
    router = ApprovedProposalRouter(
        bus=bus,
        execution_control=execution_control,
        get_active_strategies=lambda: active,
    )
    task = asyncio.create_task(router.run())
    await asyncio.sleep(0)
    intent = create_order_intent_event(strategy_id="s1", correlation_id="c1")
    await bus.publish(APPROVED_PROPOSALS, intent)
    received_paper = await asyncio.wait_for(paper_queue.get(), timeout=1.0)
    assert received_paper.strategy_id == "s1"
    with pytest.raises(asyncio.QueueEmpty):
        live_queue.get_nowait()
    router.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_route_sends_to_live_when_active_and_enabled(
    bus: EventBus,
    execution_control: ExecutionControl,
) -> None:
    """When execution enabled and strategy in active set, intent goes to live topic."""
    paper_queue = bus.subscribe(APPROVED_PROPOSALS_PAPER)
    live_queue = bus.subscribe(APPROVED_PROPOSALS_LIVE)
    execution_control.execution_enabled = True
    active: set[str] = {"s1"}
    router = ApprovedProposalRouter(
        bus=bus,
        execution_control=execution_control,
        get_active_strategies=lambda: active,
    )
    task = asyncio.create_task(router.run())
    await asyncio.sleep(0)
    intent = create_order_intent_event(strategy_id="s1", correlation_id="c1")
    await bus.publish(APPROVED_PROPOSALS, intent)
    received_live = await asyncio.wait_for(live_queue.get(), timeout=1.0)
    assert received_live.correlation_id == "c1"
    assert received_live.strategy_id == "s1"
    with pytest.raises(asyncio.QueueEmpty):
        paper_queue.get_nowait()
    router.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_route_sends_to_live_for_active_strategy_and_paper_for_others(
    bus: EventBus,
    execution_control: ExecutionControl,
) -> None:
    """With mixed strategies, active strategy intent goes to live, others to paper."""
    paper_queue = bus.subscribe(APPROVED_PROPOSALS_PAPER)
    live_queue = bus.subscribe(APPROVED_PROPOSALS_LIVE)
    execution_control.execution_enabled = True
    active: set[str] = {"active_one"}
    router = ApprovedProposalRouter(
        bus=bus,
        execution_control=execution_control,
        get_active_strategies=lambda: active,
    )
    task = asyncio.create_task(router.run())
    await asyncio.sleep(0)
    intent_live = create_order_intent_event(strategy_id="active_one", correlation_id="c_live")
    intent_paper = create_order_intent_event(strategy_id="other", correlation_id="c_paper")
    await bus.publish(APPROVED_PROPOSALS, intent_live)
    await bus.publish(APPROVED_PROPOSALS, intent_paper)
    received_live = await asyncio.wait_for(live_queue.get(), timeout=1.0)
    received_paper = await asyncio.wait_for(paper_queue.get(), timeout=1.0)
    assert received_live.strategy_id == "active_one"
    assert received_live.correlation_id == "c_live"
    assert received_paper.strategy_id == "other"
    assert received_paper.correlation_id == "c_paper"
    router.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
