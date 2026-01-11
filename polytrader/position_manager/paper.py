"""Paper position manager for simulated position tracking.

Per Commit 3: Paper trading position manager that tracks positions from FillEvents
without external API dependencies.

Per flows.mdc §11: Post-Trade (Positions / PnL / Ledger)
- Maintain positions from fills (event-driven)
- Compute realized/unrealized PnL
- Reconcile balances with venue (not applicable for paper trading)

Per architecture.mdc: Position managers track positions from fills.
This implementation is event-driven only, no external API sync.
"""

import asyncio
from typing import TYPE_CHECKING

from polytrader.events import FILLS, MARKET_DATA, EventBus
from polytrader.events.types import FillEvent, MarketDataEvent
from polytrader.logging_config import logger
from polytrader.oms.store import IOrderStore
from polytrader.position_manager import IPositionManager
from polytrader.position_manager.outcome_tracker import OutcomeTracker
from polytrader.position_manager.performance_metrics import PerformanceMetrics
from polytrader.types import Outcome, Position

if TYPE_CHECKING:
    from polytrader.oms.models import Order
else:
    # Import at runtime for type annotations
    from polytrader.oms.models import Order  # noqa: F401


class PaperPositionManager(IPositionManager):
    """Paper trading position manager.

    Tracks positions from FillEvents emitted by PaperExecutionAdapter.
    No external API dependencies - purely event-driven.

    Attributes:
        _bus: Event bus for subscribing to FILLS
        _store: Order store for looking up order details from order_id
        _positions: Internal position tracking: (market_slug, outcome) -> Position
        _running: Flag to control async loop
    """

    def __init__(
        self,
        bus: EventBus,
        store: IOrderStore,
        starting_equity: float = 1000.0,
    ) -> None:
        """Initialize paper position manager.

        Args:
            bus: Event bus for subscribing to FILLS
            store: Order store for looking up order details
            starting_equity: Initial equity for performance metrics calculation
        """
        self._bus = bus
        self._store = store
        self._starting_equity = starting_equity

        # Internal position tracking: (market_slug, outcome) -> Position
        self._positions: dict[tuple[str, Outcome], Position] = {}

        # Track cumulative fills per position for partial fills
        # (market_slug, outcome) -> (total_size, total_cost)
        self._position_fills: dict[tuple[str, Outcome], tuple[float, float]] = {}

        # Track latest market prices for unrealized P&L calculation
        # (market_slug, outcome) -> current_mid_price
        self._latest_prices: dict[tuple[str, Outcome], float] = {}

        # Outcome tracking and performance metrics (Commit 4)
        self._outcome_tracker = OutcomeTracker()
        self._performance_metrics = PerformanceMetrics(self._outcome_tracker)

        self._running = False

    async def run(self) -> None:
        """Start the position manager.

        Subscribes to FILLS and MARKET_DATA topics to track positions and prices.
        """
        self._running = True
        logger.info("Starting PaperPositionManager")

        # Subscribe to FILLS and MARKET_DATA topics
        fills_queue = self._bus.subscribe(FILLS)
        market_data_queue = self._bus.subscribe(MARKET_DATA)

        async def process_fills() -> None:
            """Process fill events."""
            try:
                while self._running:
                    fill_event = await fills_queue.get()
                    if isinstance(fill_event, FillEvent):
                        await self._handle_fill(fill_event)
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Error in fill processor")

        async def process_market_data() -> None:
            """Process market data events."""
            try:
                while self._running:
                    market_event = await market_data_queue.get()
                    if isinstance(market_event, MarketDataEvent):
                        self._handle_market_data(market_event)
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Error in market data processor")

        try:
            # Run both processors concurrently (like ExecutionRouter)
            await asyncio.gather(
                process_fills(),
                process_market_data(),
            )

        except Exception:
            logger.exception("PaperPositionManager error")
            raise
        finally:
            self._running = False
            logger.info("PaperPositionManager stopped")

    def _handle_market_data(self, market_event: MarketDataEvent) -> None:
        """Handle a market data event and update latest prices.

        Args:
            market_event: Market data event with current bid/ask prices
        """
        key = (market_event.market_slug, market_event.outcome)
        # Store the mid price for unrealized P&L calculation
        self._latest_prices[key] = market_event.mid
        logger.bind(
            market_slug=market_event.market_slug,
            outcome=market_event.outcome,
            mid_price=market_event.mid,
        ).debug(
            "Updated market price: {market_slug}/{outcome} = {mid_price:.4f}",
            market_slug=market_event.market_slug,
            outcome=market_event.outcome,
            mid_price=market_event.mid,
        )

    async def _handle_fill(self, fill_event: FillEvent) -> None:
        """Handle a fill event and update positions.

        Per flows.mdc §11: Positions are derived from fills (events).

        Args:
            fill_event: Fill event from paper execution adapter
        """
        logger.bind(
            order_id=fill_event.order_id,
            fill_id=fill_event.fill_id,
        ).debug(
            "Processing fill event: order_id={order_id}, fill_id={fill_id}",
            order_id=fill_event.order_id,
            fill_id=fill_event.fill_id,
        )

        # Look up order to get market_slug, outcome, and side
        order = self._store.get_order(fill_event.order_id)
        if order is None:
            logger.bind(
                order_id=fill_event.order_id,
                fill_id=fill_event.fill_id,
            ).warning(
                "Fill event for unknown order: {order_id} (fill_id: {fill_id})",
                order_id=fill_event.order_id,
                fill_id=fill_event.fill_id,
            )
            return

        market_slug = order.market_slug
        outcome = order.outcome
        side = order.side
        key = (market_slug, outcome)

        if side == "BUY":
            await self._handle_buy_fill(key, fill_event, order)
        elif side == "SELL":
            await self._handle_sell_fill(key, fill_event, order)
        else:
            logger.bind(
                market_slug=market_slug,
                outcome=outcome,
                side=side,
            ).warning(
                "Unknown side for fill: {side} (market: {market_slug}/{outcome})",
                side=side,
                market_slug=market_slug,
                outcome=outcome,
            )

    async def _handle_buy_fill(
        self,
        key: tuple[str, Outcome],
        fill_event: FillEvent,
        order: "Order",
    ) -> None:
        """Handle a BUY fill - add or update position.

        Args:
            key: Position key (market_slug, outcome)
            fill_event: Fill event
            order: Order that was filled
        """
        market_slug, outcome = key

        # Update cumulative fills
        if key in self._position_fills:
            total_size, total_cost = self._position_fills[key]
            total_size += fill_event.size
            total_cost += fill_event.size * fill_event.price
        else:
            total_size = fill_event.size
            total_cost = fill_event.size * fill_event.price

        self._position_fills[key] = (total_size, total_cost)

        # Calculate average entry price
        avg_entry_price = total_cost / total_size if total_size > 0 else fill_event.price

        # Get target price from order intent
        target_price = order.intent.target_price

        # Create or update position
        if key in self._positions:
            # Update existing position (partial fill)
            position = self._positions[key]
            position.size = total_size
            position.entry_price = avg_entry_price
            # Keep original entry_time and order_id from first fill
        else:
            # Create new position
            position = Position(
                market_slug=market_slug,
                outcome=outcome,
                size=total_size,
                target_price=target_price,
                entry_price=avg_entry_price,
                entry_time=fill_event.ts_mono,
                order_id=order.order_id,
            )
            self._positions[key] = position

        logger.bind(
            market_slug=market_slug,
            outcome=outcome,
            fill_size=fill_event.size,
            fill_price=fill_event.price,
            total_size=total_size,
            avg_entry_price=avg_entry_price,
            target_price=target_price,
        ).info(
            "📈 Position updated (BUY fill): {market_slug}/{outcome} | "
            "fill=${fill_size:.2f} @ {fill_price:.4f} | "
            "total=${total_size:.2f} @ avg {avg_entry_price:.4f} | "
            "target={target_price:.4f}",
            market_slug=market_slug,
            outcome=outcome,
            fill_size=fill_event.size,
            fill_price=fill_event.price,
            total_size=total_size,
            avg_entry_price=avg_entry_price,
            target_price=target_price,
        )

    async def _handle_sell_fill(
        self,
        key: tuple[str, Outcome],
        fill_event: FillEvent,
        order: "Order",  # noqa: UP037
    ) -> None:
        """Handle a SELL fill - reduce or close position.

        Args:
            key: Position key (market_slug, outcome)
            fill_event: Fill event
            order: Order that was filled
        """
        market_slug, outcome = key

        if key not in self._positions:
            logger.bind(
                market_slug=market_slug,
                outcome=outcome,
                fill_size=fill_event.size,
            ).warning(
                "SELL fill for position we don't track: {market_slug}/{outcome} "
                "(fill_size: ${fill_size:.2f})",
                market_slug=market_slug,
                outcome=outcome,
                fill_size=fill_event.size,
            )
            return

        position = self._positions[key]

        # Reduce position size
        position.size -= fill_event.size

        # Calculate P&L for this fill
        pnl = (fill_event.price - position.entry_price) * fill_event.size
        pnl_pct = (
            ((fill_event.price - position.entry_price) / position.entry_price) * 100
            if position.entry_price > 0
            else 0
        )

        # Check if position is fully closed
        if position.size <= 0:
            # Position fully closed
            position_duration = fill_event.ts_mono - position.entry_time
            position_duration_minutes = position_duration / 60.0

            # Calculate total P&L (approximate - using this fill's price)
            original_size = position.size + fill_event.size  # Original position size
            total_pnl = (fill_event.price - position.entry_price) * original_size

            logger.bind(
                market_slug=market_slug,
                outcome=outcome,
                fill_size=fill_event.size,
                fill_price=fill_event.price,
                entry_price=position.entry_price,
                pnl=total_pnl,
                pnl_pct=pnl_pct,
                duration_minutes=position_duration_minutes,
            ).info(
                "📉 Position closed (SELL fill): {market_slug}/{outcome} | "
                "fill=${fill_size:.2f} @ {fill_price:.4f} | "
                "entry={entry_price:.4f} | "
                "P&L=${pnl:+.2f} ({pnl_pct:+.1f}%) | duration={duration_minutes:.1f}m",
                market_slug=market_slug,
                outcome=outcome,
                fill_size=fill_event.size,
                fill_price=fill_event.price,
                entry_price=position.entry_price,
                pnl=total_pnl,
                pnl_pct=pnl_pct,
                duration_minutes=position_duration_minutes,
            )

            # Record closed position in outcome tracker (Commit 4)
            self._outcome_tracker.record_closed_position(
                market_slug=market_slug,
                outcome=outcome,
                entry_price=position.entry_price,
                exit_price=fill_event.price,
                size=original_size,
                entry_time=position.entry_time,
                exit_time=fill_event.ts_mono,
            )

            # Update performance metrics
            self._performance_metrics.update_metrics()

            # Remove position
            del self._positions[key]
            self._position_fills.pop(key, None)
        else:
            # Partial close
            logger.bind(
                market_slug=market_slug,
                outcome=outcome,
                fill_size=fill_event.size,
                fill_price=fill_event.price,
                remaining_size=position.size,
                pnl=pnl,
                pnl_pct=pnl_pct,
            ).info(
                "📊 Position partially closed (SELL fill): {market_slug}/{outcome} | "
                "fill=${fill_size:.2f} @ {fill_price:.4f} | "
                "remaining=${remaining_size:.2f} | "
                "P&L=${pnl:+.2f} ({pnl_pct:+.1f}%)",
                market_slug=market_slug,
                outcome=outcome,
                fill_size=fill_event.size,
                fill_price=fill_event.price,
                remaining_size=position.size,
                pnl=pnl,
                pnl_pct=pnl_pct,
            )

    def stop(self) -> None:
        """Stop the position manager."""
        self._running = False
        logger.info("Stopping PaperPositionManager")

    def get_positions(self) -> dict[tuple[str, Outcome], Position] | None:
        """Get all current positions.

        Returns:
            Dictionary mapping (market_slug, outcome) to Position, or None if not available.
        """
        if not self._positions:
            return {}
        return self._positions.copy()

    def get_position(self, market_slug: str, outcome: Outcome) -> Position | None:
        """Get position for a specific market and outcome.

        Args:
            market_slug: Market identifier
            outcome: Market outcome ("UP" or "DOWN")

        Returns:
            Position if exists, None otherwise
        """
        key = (market_slug, outcome)
        return self._positions.get(key)

    def get_outcome_tracker(self) -> OutcomeTracker:
        """Get the outcome tracker.

        Returns:
            OutcomeTracker instance for accessing closed positions
        """
        return self._outcome_tracker

    def get_performance_metrics(self) -> PerformanceMetrics:
        """Get the performance metrics calculator.

        Returns:
            PerformanceMetrics instance for accessing performance statistics
        """
        return self._performance_metrics

    def get_starting_equity(self) -> float:
        """Get the starting equity.

        Returns:
            Starting equity value
        """
        return self._starting_equity

    def calculate_unrealized_pnl(
        self, current_prices: dict[tuple[str, Outcome], float] | None = None
    ) -> float:
        """Calculate unrealized P&L from open positions.

        Uses the latest market prices from MarketDataEvent subscriptions.
        Falls back to provided current_prices if available, otherwise uses entry_price
        (which means no unrealized P&L if no market data is available).

        Args:
            current_prices: Optional dict mapping (market_slug, outcome) -> current price.
                           If provided, overrides tracked market prices.

        Returns:
            Total unrealized P&L across all open positions
        """
        unrealized_pnl = 0.0
        for key, position in self._positions.items():
            # Priority: 1) provided current_prices, 2) tracked latest prices,
            # 3) entry_price (no P&L)
            if current_prices and key in current_prices:
                current_price = current_prices[key]
            elif key in self._latest_prices:
                current_price = self._latest_prices[key]
            else:
                # No market data available - use entry price (no unrealized P&L)
                current_price = position.entry_price

            # Unrealized P&L = (current_price - entry_price) * size
            position_pnl = (current_price - position.entry_price) * position.size
            unrealized_pnl += position_pnl

        return unrealized_pnl
