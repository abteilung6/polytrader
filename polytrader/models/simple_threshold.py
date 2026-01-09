from polytrader.events import MARKET_DATA, PROPOSALS, EventBus
from polytrader.logging_config import logger
from polytrader.models.protocol import ITradingModel
from polytrader.store import IMarketDataStore
from polytrader.types import MarketDataEvent, OrderIntentEvent, Outcome


class SimpleThresholdModel(ITradingModel):
    def __init__(
        self,
        bus: EventBus,
        store: IMarketDataStore,
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
        market_data_queue = self.bus.subscribe(MARKET_DATA)
        try:
            while self._running:
                event = await market_data_queue.get()
                await self.on_tick(event)
        except Exception:
            logger.exception("Model error")
            raise
        finally:
            self._running = False

    async def on_tick(self, event: MarketDataEvent) -> None:
        """Process market data event and generate proposals for configured outcomes.

        Filters events by market_slug and outcome, then applies threshold logic
        to generate trade proposals.
        """
        if event.market_slug != self.market_slug:
            return

        if event.outcome not in self.outcomes:
            return

        # Get outcome-specific thresholds if available
        thresholds = self.outcome_thresholds.get(event.outcome, {})
        buy_thresh = thresholds.get("buy", self.buy_threshold)
        sell_thresh = thresholds.get("sell", self.sell_threshold)

        # Check history requirement
        history = self.store.history(event.market_slug, event.outcome)
        if len(history) < self.min_history:
            logger.bind(
                market_slug=event.market_slug,
                outcome=event.outcome,
                current=len(history),
                required=self.min_history,
            ).info(
                "⏳ Building history: {current}/{required} events (need {required} before trading)",
                current=len(history),
                required=self.min_history,
            )
            return

        mid_price = event.mid

        # Generate BUY proposal if price below threshold
        if mid_price < buy_thresh:
            proposal = OrderIntentEvent(
                market_slug=event.market_slug,
                outcome=event.outcome,
                side="BUY",
                target_price=sell_thresh,
                limit_price=event.best_ask,
                size=self.size,
                reason=(
                    f"Price {mid_price:.4f} below buy threshold {buy_thresh} for {event.outcome}"
                ),
            )
            await self.bus.publish(PROPOSALS, proposal)
            logger.bind(market_slug=event.market_slug, outcome=event.outcome, price=mid_price).info(
                "Published BUY proposal: {reason}", reason=proposal.reason
            )

        # Generate SELL proposal if price above threshold
        elif mid_price > sell_thresh:
            proposal = OrderIntentEvent(
                market_slug=event.market_slug,
                outcome=event.outcome,
                side="SELL",
                target_price=sell_thresh,
                limit_price=event.best_bid,
                size=self.size,
                reason=(
                    f"Price {mid_price:.4f} above sell threshold {sell_thresh} for {event.outcome}"
                ),
            )
            await self.bus.publish(PROPOSALS, proposal)
            logger.bind(market_slug=event.market_slug, outcome=event.outcome, price=mid_price).info(
                "Published SELL proposal: {reason}", reason=proposal.reason
            )
        else:
            logger.bind(
                market_slug=event.market_slug,
                outcome=event.outcome,
                price=mid_price,
                buy_thresh=buy_thresh,
                sell_thresh=sell_thresh,
            ).info(
                "⏸️  No trade: price {price:.4f} between thresholds "
                "(buy < {buy_thresh:.4f}, sell > {sell_thresh:.4f})",
                price=mid_price,
                buy_thresh=buy_thresh,
                sell_thresh=sell_thresh,
            )

    def stop(self) -> None:
        self._running = False
