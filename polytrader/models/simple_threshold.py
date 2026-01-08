from polytrader.events import PROPOSALS, TICKS, EventBus
from polytrader.logging_config import logger
from polytrader.models.protocol import ITradingModel
from polytrader.store import ITickStore
from polytrader.types import MarketTick, Outcome, TradeProposal


class SimpleThresholdModel(ITradingModel):
    def __init__(
        self,
        bus: EventBus,
        store: ITickStore,
        market_slug: str,
        outcomes: set[Outcome] | None = None,
        buy_threshold: float = 0.30,
        sell_threshold: float = 0.50,
        size: float = 1.0,
        min_history: int = 30,
        outcome_thresholds: dict[Outcome, dict[str, float]] | None = None,
    ) -> None:
        self.bus = bus
        self.store = store
        self.market_slug = market_slug
        self.outcomes = outcomes or {"UP", "DOWN"}
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.size = size
        self.min_history = min_history
        self.outcome_thresholds = outcome_thresholds or {}
        self._running = False

    async def run(self) -> None:
        self._running = True
        tick_queue = self.bus.subscribe(TICKS)
        try:
            while self._running:
                tick = await tick_queue.get()
                await self.on_tick(tick)
        except Exception:
            logger.exception("Model error")
            raise
        finally:
            self._running = False

    async def on_tick(self, tick: MarketTick) -> None:
        """Process tick and generate proposals for configured outcomes.

        Filters ticks by market_slug and outcome, then applies threshold logic
        to generate trade proposals.
        """
        if tick.market_slug != self.market_slug:
            return

        if tick.outcome not in self.outcomes:
            return

        # Get outcome-specific thresholds if available
        thresholds = self.outcome_thresholds.get(tick.outcome, {})
        buy_thresh = thresholds.get("buy", self.buy_threshold)
        sell_thresh = thresholds.get("sell", self.sell_threshold)

        # Check history requirement
        history = self.store.history(tick.market_slug, tick.outcome)
        if len(history) < self.min_history:
            logger.debug(
                "Insufficient history: {current}/{required} ticks",
                current=len(history),
                required=self.min_history,
            )
            return

        mid_price = tick.mid

        # Generate BUY proposal if price below threshold
        if mid_price < buy_thresh:
            proposal = TradeProposal(
                ts=tick.ts,
                market_slug=tick.market_slug,
                outcome=tick.outcome,  # Use the outcome from the tick
                side="BUY",
                target_price=sell_thresh,
                limit_price=tick.best_ask,
                size=self.size,
                reason=(
                    f"Price {mid_price:.4f} below buy threshold {buy_thresh} for {tick.outcome}"
                ),
            )
            await self.bus.publish(PROPOSALS, proposal)
            logger.bind(market_slug=tick.market_slug, outcome=tick.outcome, price=mid_price).info(
                "Published BUY proposal: {reason}", reason=proposal.reason
            )

        # Generate SELL proposal if price above threshold
        elif mid_price > sell_thresh:
            proposal = TradeProposal(
                ts=tick.ts,
                market_slug=tick.market_slug,
                outcome=tick.outcome,  # Use the outcome from the tick
                side="SELL",
                target_price=sell_thresh,
                limit_price=tick.best_bid,
                size=self.size,
                reason=(
                    f"Price {mid_price:.4f} above sell threshold {sell_thresh} for {tick.outcome}"
                ),
            )
            await self.bus.publish(PROPOSALS, proposal)
            logger.bind(market_slug=tick.market_slug, outcome=tick.outcome, price=mid_price).info(
                "Published SELL proposal: {reason}", reason=proposal.reason
            )
        else:
            logger.debug(
                "No proposal: price {price:.4f} between thresholds "
                "(buy: {buy_thresh}, sell: {sell_thresh})",
                price=mid_price,
                buy_thresh=buy_thresh,
                sell_thresh=sell_thresh,
            )

    def stop(self) -> None:
        self._running = False
