"""Approved proposal router: split approved intents into paper vs live lane.

Per proposal: subscribes to APPROVED_PROPOSALS, routes each intent to
APPROVED_PROPOSALS_PAPER or APPROVED_PROPOSALS_LIVE based on execution_enabled
and active_strategies. Does not mutate intents; forwards same OrderIntentEvent.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from polytrader.events import (
    APPROVED_PROPOSALS,
    APPROVED_PROPOSALS_LIVE,
    APPROVED_PROPOSALS_PAPER,
)
from polytrader.events.bus import EventBus, Topic
from polytrader.events.types import OrderIntentEvent
from polytrader.logging_config import logger
from polytrader.obs.logging import bind_correlation_context
from polytrader.ops.control import ExecutionControl


class ApprovedProposalRouter:
    """Routes approved intents to paper or live topic by execution state and active strategies.

    Subscribes to APPROVED_PROPOSALS. For each intent:
    - If execution_enabled and strategy_id in active_strategies → APPROVED_PROPOSALS_LIVE
    - Else → APPROVED_PROPOSALS_PAPER

    Does not mutate the intent; forwards the same OrderIntentEvent (preserves correlation_id).
    """

    def __init__(
        self,
        bus: EventBus,
        execution_control: ExecutionControl,
        get_active_strategies: Callable[[], set[str]],
        *,
        approved_topic: Topic[OrderIntentEvent] | None = None,
        paper_topic: Topic[OrderIntentEvent] | None = None,
        live_topic: Topic[OrderIntentEvent] | None = None,
    ) -> None:
        """Initialize the proposal router.

        Args:
            bus: Event bus for subscribe/publish
            execution_control: Execution control for is_enabled()
            get_active_strategies: Callable returning current set of active strategy IDs
            approved_topic: Topic to subscribe to (default: APPROVED_PROPOSALS)
            paper_topic: Topic for paper intents (default: APPROVED_PROPOSALS_PAPER)
            live_topic: Topic for live intents (default: APPROVED_PROPOSALS_LIVE)
        """
        self._bus = bus
        self._execution_control = execution_control
        self._get_active_strategies = get_active_strategies
        self._approved_topic = approved_topic if approved_topic is not None else APPROVED_PROPOSALS
        self._paper_topic = paper_topic if paper_topic is not None else APPROVED_PROPOSALS_PAPER
        self._live_topic = live_topic if live_topic is not None else APPROVED_PROPOSALS_LIVE
        self._running = False

    async def run(self) -> None:
        """Run the router loop: subscribe to approved proposals, route to paper/live."""
        self._running = True
        queue = self._bus.subscribe(self._approved_topic)
        while self._running:
            try:
                intent = await asyncio.wait_for(queue.get(), timeout=0.1)
                await self._route(intent)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                bind_correlation_context(
                    logger,
                    correlation_id="",
                    event_type="ProposalRouterError",
                    error_class="system",
                ).exception("Error routing approved proposal")
        self._running = False

    async def _route(self, intent: OrderIntentEvent) -> None:
        """Route a single intent to paper or live topic and log."""
        enabled = self._execution_control.is_enabled()
        active = self._get_active_strategies()
        if enabled and intent.strategy_id in active:
            topic = self._live_topic
            lane = "live"
        else:
            topic = self._paper_topic
            lane = "paper"
        bind_correlation_context(
            logger,
            correlation_id=intent.correlation_id,
            strategy_id=intent.strategy_id,
        ).debug("Proposal routed", lane=lane)
        await self._bus.publish(topic, intent)

    def stop(self) -> None:
        """Signal the run loop to stop."""
        self._running = False
