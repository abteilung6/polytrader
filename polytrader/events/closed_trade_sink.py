"""Closed-trade sink: projects StrategyClosedTradeEvent into the dedicated read-model table.

Per PERFORMANCE_OVERVIEW_PROPOSAL.md §4:
- Subscribes to STRATEGY_CLOSED_TRADES topic on the EventBus.
- Inserts one row per event into strategy_closed_trades table.
- Idempotent via ON CONFLICT (event_id) DO NOTHING.
- Runs as a background asyncio task alongside EventSink.
- Never blocks or affects trading components.

This is intentionally separate from EventSink (which writes all events to the
generic events table with JSONB). This sink writes to typed columns optimized
for windowed GROUP BY aggregation.
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polytrader.events.bus import EventBus
from polytrader.events.types import StrategyClosedTradeEvent
from polytrader.logging_config import logger

# SQL for idempotent upsert — ON CONFLICT (event_id) DO NOTHING
_INSERT_SQL = text("""
INSERT INTO strategy_closed_trades (
    event_id,
    strategy_id,
    execution_mode,
    exit_ts_wall,
    entry_time,
    exit_time,
    pnl,
    pnl_pct,
    result,
    size,
    duration_seconds,
    market_slug,
    outcome,
    entry_price,
    exit_price
) VALUES (
    :event_id,
    :strategy_id,
    :execution_mode,
    :exit_ts_wall,
    :entry_time,
    :exit_time,
    :pnl,
    :pnl_pct,
    :result,
    :size,
    :duration_seconds,
    :market_slug,
    :outcome,
    :entry_price,
    :exit_price
)
ON CONFLICT (event_id) DO NOTHING
""")


class ClosedTradeSink:
    """Writes StrategyClosedTradeEvent to the strategy_closed_trades table.

    Lifecycle:
        sink = ClosedTradeSink(bus, session_factory)
        task = asyncio.create_task(sink.run())
        # ... later ...
        await sink.stop()

    Thread safety: single-consumer — one asyncio.Queue per subscription.
    """

    def __init__(
        self,
        bus: EventBus,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Initialize the closed-trade sink.

        Args:
            bus: EventBus to subscribe to STRATEGY_CLOSED_TRADES.
            session_factory: SQLAlchemy async session factory for DB writes.
        """
        self._bus = bus
        self._session_factory = session_factory
        self._running = False
        self._queue: asyncio.Queue[StrategyClosedTradeEvent] | None = None

    async def run(self) -> None:
        """Subscribe and consume closed-trade events until stop() is called."""
        import polytrader.events as events_module

        topic = events_module.STRATEGY_CLOSED_TRADES
        self._queue = self._bus.subscribe(topic)
        self._running = True

        logger.info("ClosedTradeSink started — projecting to strategy_closed_trades table")

        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except TimeoutError:
                continue
            except Exception:
                logger.exception("ClosedTradeSink: unexpected error reading queue")
                continue

            if isinstance(event, StrategyClosedTradeEvent):
                await self._persist(event)

    async def _persist(self, event: StrategyClosedTradeEvent) -> None:
        """Insert one closed-trade row (idempotent)."""
        try:
            async with self._session_factory() as session:
                await session.execute(
                    _INSERT_SQL,
                    {
                        "event_id": event.event_id,
                        "strategy_id": event.strategy_id,
                        "execution_mode": event.execution_mode,
                        "exit_ts_wall": event.ts_wall,
                        "entry_time": event.entry_time,
                        "exit_time": event.exit_time,
                        "pnl": event.pnl,
                        "pnl_pct": event.pnl_pct,
                        "result": event.result,
                        "size": event.size,
                        "duration_seconds": event.exit_time - event.entry_time,
                        "market_slug": event.market_slug,
                        "outcome": event.outcome,
                        "entry_price": event.entry_price,
                        "exit_price": event.exit_price,
                    },
                )
                await session.commit()

            logger.debug(
                "ClosedTradeSink persisted trade for strategy={strategy_id} pnl={pnl:.4f}",
                strategy_id=event.strategy_id,
                pnl=event.pnl,
                event_id=str(event.event_id),
            )
        except Exception:
            # Never crash the sink — log and continue
            logger.exception(
                "ClosedTradeSink: failed to persist trade event_id={event_id}",
                event_id=str(event.event_id),
            )

    async def stop(self) -> None:
        """Stop the sink gracefully."""
        if not self._running:
            return
        self._running = False
        logger.info("ClosedTradeSink stopped")
