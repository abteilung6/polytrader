"""Unit tests for lane-specific event topics (paper/live).

Per proposal: APPROVED_PROPOSALS_PAPER/LIVE, SUBMIT_ORDER_COMMANDS_PAPER/LIVE,
CANCEL_ORDER_COMMANDS_PAPER/LIVE. Assert topic getters return distinct instances
and publish/subscribe on a lane topic only delivers to that lane's subscribers.
"""

import asyncio

import pytest

from polytrader.events import (
    APPROVED_PROPOSALS,
    APPROVED_PROPOSALS_LIVE,
    APPROVED_PROPOSALS_PAPER,
    CANCEL_ORDER_COMMANDS,
    CANCEL_ORDER_COMMANDS_LIVE,
    CANCEL_ORDER_COMMANDS_PAPER,
    SUBMIT_ORDER_COMMANDS,
    SUBMIT_ORDER_COMMANDS_LIVE,
    SUBMIT_ORDER_COMMANDS_PAPER,
    EventBus,
)
from polytrader.events.types import OrderIntentEvent


class TestLaneTopicGettersReturnDistinctInstances:
    """Lane topic getters return distinct topic instances."""

    def test_approved_proposals_paper_and_live_are_distinct(self) -> None:
        """PAPER and LIVE approved-proposal topics are distinct from each other and from base."""
        assert APPROVED_PROPOSALS_PAPER.name != APPROVED_PROPOSALS_LIVE.name
        assert APPROVED_PROPOSALS_PAPER.name != APPROVED_PROPOSALS.name
        assert APPROVED_PROPOSALS_LIVE.name != APPROVED_PROPOSALS.name

    def test_submit_order_commands_paper_and_live_are_distinct(self) -> None:
        """PAPER and LIVE submit-command topics are distinct from each other and from base."""
        assert SUBMIT_ORDER_COMMANDS_PAPER.name != SUBMIT_ORDER_COMMANDS_LIVE.name
        assert SUBMIT_ORDER_COMMANDS_PAPER.name != SUBMIT_ORDER_COMMANDS.name
        assert SUBMIT_ORDER_COMMANDS_LIVE.name != SUBMIT_ORDER_COMMANDS.name

    def test_cancel_order_commands_paper_and_live_are_distinct(self) -> None:
        """PAPER and LIVE cancel-command topics are distinct from each other and from base."""
        assert CANCEL_ORDER_COMMANDS_PAPER.name != CANCEL_ORDER_COMMANDS_LIVE.name
        assert CANCEL_ORDER_COMMANDS_PAPER.name != CANCEL_ORDER_COMMANDS.name
        assert CANCEL_ORDER_COMMANDS_LIVE.name != CANCEL_ORDER_COMMANDS.name


@pytest.mark.asyncio
async def test_publish_to_paper_lane_only_delivers_to_paper_subscriber() -> None:
    """Publish on APPROVED_PROPOSALS_PAPER delivers only to paper subscriber, not live."""
    bus = EventBus()
    paper_queue = bus.subscribe(APPROVED_PROPOSALS_PAPER)
    live_queue = bus.subscribe(APPROVED_PROPOSALS_LIVE)
    intent = OrderIntentEvent(
        event_id="e1",
        ts_wall="2026-02-08T12:00:00+00:00",
        ts_mono=0.0,
        correlation_id="c1",
        strategy_id="s1",
        market_slug="m1",
        outcome="UP",
        side="BUY",
        size=1.0,
        target_price=0.5,
        limit_price=0.5,
        reason="test",
    )
    await bus.publish(APPROVED_PROPOSALS_PAPER, intent)
    received = await asyncio.wait_for(paper_queue.get(), timeout=0.5)
    assert received.correlation_id == "c1"
    assert received.strategy_id == "s1"
    # Live queue must not receive (same bus, different topic)
    with pytest.raises(asyncio.QueueEmpty):
        live_queue.get_nowait()
