import logging

from polytrader.events import PROPOSALS, TICKS, EventBus
from polytrader.models.protocol import ITradingModel
from polytrader.store import ITickStore
from polytrader.types import MarketTick, Outcome, TradeProposal

logger = logging.getLogger(__name__)


class SimpleThresholdModel(ITradingModel):
    def __init__(
        self,
        bus: EventBus,
        store: ITickStore,
        market_id: str,
        outcome: Outcome,
        buy_threshold: float = 0.30,
        sell_threshold: float = 0.50,
        size: float = 1.0,
        min_history: int = 30,
    ) -> None:
        self.bus = bus
        self.store = store
        self.market_id = market_id
        self.outcome = outcome
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.size = size
        self.min_history = min_history
        self._running = False

    async def run(self) -> None:
        self._running = True
        tick_queue = self.bus.subscribe(TICKS)
        try:
            while self._running:
                tick = await tick_queue.get()
                await self.on_tick(tick)
        except Exception as e:
            logger.error(f"Model error: {e}", exc_info=True)
            raise
        finally:
            self._running = False

    async def on_tick(self, tick: MarketTick) -> None:
        if tick.market_id != self.market_id or tick.outcome != self.outcome:
            return

        history = self.store.history(tick.market_id, tick.outcome)
        if len(history) < self.min_history:
            logger.debug(
                f"Insufficient history: {len(history)}/{self.min_history} ticks. "
                f"Market: {tick.market_id}, Outcome: {tick.outcome}"
            )
            return

        mid_price = tick.mid

        if mid_price < self.buy_threshold:
            proposal = TradeProposal(
                ts=tick.ts,
                market_id=tick.market_id,
                outcome=tick.outcome,
                side="BUY",
                target_price=self.sell_threshold,
                limit_price=tick.best_ask,
                size=self.size,
                reason=f"Price {mid_price:.4f} below buy threshold {self.buy_threshold}",
            )
            await self.bus.publish(PROPOSALS, proposal)
            logger.info(f"Published BUY proposal: {proposal.reason}")
        elif mid_price > self.sell_threshold:
            proposal = TradeProposal(
                ts=tick.ts,
                market_id=tick.market_id,
                outcome=tick.outcome,
                side="SELL",
                target_price=self.sell_threshold,
                limit_price=tick.best_bid,
                size=self.size,
                reason=f"Price {mid_price:.4f} above sell threshold {self.sell_threshold}",
            )
            await self.bus.publish(PROPOSALS, proposal)
            logger.info(f"Published SELL proposal: {proposal.reason}")
        else:
            logger.debug(
                f"No proposal: price {mid_price:.4f} between thresholds "
                f"(buy: {self.buy_threshold}, sell: {self.sell_threshold})"
            )

    def stop(self) -> None:
        self._running = False
