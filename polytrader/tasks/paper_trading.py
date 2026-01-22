"""Paper trading task for simulated trading with performance metrics.

Per Commit 5: Create Paper Trading Task and CLI Command
- Orchestrates paper trading components (PaperExecutionAdapter, PaperPositionManager)
- Displays performance metrics periodically
- Handles graceful shutdown
"""

import asyncio
from collections.abc import Callable

from polytrader.events import (
    MARKET_CHANGE,
    ORDERS,
    SYSTEM_LIFECYCLE,
    EventBus,
    MemoryEventStore,
    SystemStartedEvent,
    SystemStoppedEvent,
)
from polytrader.events.types import MarketChangeEvent, OrderExecutedEvent
from polytrader.execution.fill_models import FillModel
from polytrader.logging_config import logger
from polytrader.market_discovery import MarketDiscoveryService
from polytrader.position_manager.paper import PaperPositionManager
from polytrader.tasks.builders import PaperTradingSystemBuilder


def default_order_handler(order: OrderExecutedEvent) -> None:
    """Default handler for order events in paper trading."""
    market_short = (
        order.market_slug.split("-")[-1] if "-" in order.market_slug else order.market_slug
    )

    response = order.response
    if isinstance(response, dict):
        order_id = response.get("order_id") or response.get("id") or "N/A"
        status = response.get("status") or response.get("state") or "N/A"
        fills = response.get("fills", [])

        fill_info = ""
        if fills:
            fill_info = f" ({len(fills)} fill(s))"
        elif status.lower() not in ["filled", "complete"]:
            fill_info = " (pending)"

        logger.bind(
            market_slug=order.market_slug,
            outcome=order.outcome,
            side=order.side,
            size=order.size,
            order_id=order_id,
            status=status,
        ).info(
            "📝 PAPER ORDER  {market:15s}  {outcome:4s}  {side:4s}  ${size:.2f}  "
            "ID:{order_id}  {status}{fill_info}",
            market=market_short,
            outcome=order.outcome,
            side=order.side,
            size=order.size,
            order_id=order_id,
            status=status,
            fill_info=fill_info,
        )
    else:
        logger.bind(
            market_slug=order.market_slug,
            outcome=order.outcome,
            side=order.side,
            size=order.size,
        ).info(
            "📝 PAPER ORDER  {market:15s}  {outcome:4s}  {side:4s}  ${size:.2f}  "
            "Response: {response}",
            market=market_short,
            outcome=order.outcome,
            side=order.side,
            size=order.size,
            response=response,
        )


def default_market_change_handler(event: MarketChangeEvent) -> None:
    """Default handler for market change events in paper trading."""
    if event.old_market:
        old_short = event.old_market.split("-")[-1] if "-" in event.old_market else event.old_market
        new_short = event.new_market.split("-")[-1] if "-" in event.new_market else event.new_market
        logger.bind(old_market=event.old_market, new_market=event.new_market).info(
            "🔄 Market: {old} → {new}", old=old_short, new=new_short
        )
    else:
        new_short = event.new_market.split("-")[-1] if "-" in event.new_market else event.new_market
        logger.bind(new_market=event.new_market).info("🚀 Started: {market}", market=new_short)


async def display_performance_metrics(
    position_manager: PaperPositionManager,
    interval_seconds: float = 60.0,
) -> None:
    """Periodically display performance metrics.

    Args:
        position_manager: Paper position manager with performance metrics
        interval_seconds: How often to display metrics (default: 60.0)
    """
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            metrics = position_manager.get_performance_metrics()
            starting_equity = position_manager.get_starting_equity()
            unrealized_pnl = position_manager.calculate_unrealized_pnl()
            summary = metrics.get_summary(
                starting_equity=starting_equity, unrealized_pnl=unrealized_pnl
            )

            logger.info("=" * 70)
            logger.info("📊 PAPER TRADING PERFORMANCE METRICS")
            logger.info("=" * 70)
            logger.info(f"Total Trades: {summary['total_trades']}")
            logger.info(f"Win Rate: {summary['win_rate_pct']:.1f}%")
            logger.info(f"Total Realized P&L: ${summary['total_realized_pnl']:.2f}")
            if summary.get("unrealized_pnl", 0.0) != 0.0:
                logger.info(f"Unrealized P&L: ${summary['unrealized_pnl']:.2f}")
            logger.info(f"Average P&L per Trade: ${summary['average_pnl']:.2f}")
            avg_win = summary.get("average_win")
            avg_loss = summary.get("average_loss")
            if avg_win is not None and avg_win > 0:
                logger.info(f"Average Win: ${avg_win:.2f}")
            if avg_loss is not None and avg_loss < 0:
                logger.info(f"Average Loss: ${avg_loss:.2f}")
            if summary["best_trade_pnl"] is not None:
                logger.info(f"Best Trade: ${summary['best_trade_pnl']:.2f}")
            if summary["worst_trade_pnl"] is not None:
                logger.info(f"Worst Trade: ${summary['worst_trade_pnl']:.2f}")
            logger.info(f"Current Drawdown: ${summary['drawdown']:.2f}")
            logger.info(f"Current Equity: ${summary['current_equity']:.2f}")
            logger.info("=" * 70)
        except Exception:
            logger.exception("Error displaying performance metrics")


async def paper_trading_task(
    market_pattern: str,
    frequency: float = 1.0,
    buy_threshold: float = 0.30,
    sell_threshold: float = 0.50,
    size: float = 1.0,
    min_history: int = 30,
    max_trades: int = 1,
    fill_model: FillModel = FillModel.MID_PRICE,
    fill_probability: float = 1.0,
    rejection_probability: float = 0.0,
    latency_ms: float = 50.0,
    metrics_interval: float = 60.0,
    starting_equity: float = 1000.0,
    order_handler: Callable[[OrderExecutedEvent], None] | None = None,
    market_change_handler: Callable[[MarketChangeEvent], None] | None = None,
) -> None:
    """Run paper trading with simulated execution and performance tracking.

    Args:
        market_pattern: Market pattern (e.g., 'btc-updown-15m') or market slug
        frequency: Polling frequency in Hz
        buy_threshold: Buy threshold price
        sell_threshold: Sell threshold price
        size: Trade size in USD
        min_history: Minimum history ticks required
        max_trades: Maximum trades per market/outcome
        fill_model: Fill simulation model (default: MID_PRICE)
        fill_probability: Probability of fill (0-1, default: 1.0)
        rejection_probability: Probability of rejection (0-1, default: 0.0)
        latency_ms: Simulated latency in milliseconds (default: 50.0)
        metrics_interval: How often to display performance metrics in seconds (default: 60.0)
        order_handler: Callback for each executed order (default: logs to stdout)
        market_change_handler: Callback for market changes (default: logs to stdout)
    """
    if order_handler is None:
        order_handler = default_order_handler

    if market_change_handler is None:
        market_change_handler = default_market_change_handler

    # Initialize core infrastructure
    # Create market data store (with optional PostgreSQL persistence)
    from polytrader.store_factory import create_market_data_store

    store = create_market_data_store(enable_postgres=True)
    event_store = MemoryEventStore()
    bus = EventBus(store=event_store)
    discovery = MarketDiscoveryService(bus=bus)

    # Emit system started event
    started_event = SystemStartedEvent()
    await bus.publish(SYSTEM_LIFECYCLE, started_event)

    # Build paper trading system using builder
    builder = (
        PaperTradingSystemBuilder(
            bus=bus,
            store=store,
            discovery=discovery,
            market_pattern=market_pattern,
            frequency=frequency,
        )
        .strategy_config(buy_threshold=buy_threshold, min_history=min_history)
        .execution_config(
            size=size,
            fill_model=fill_model,
            fill_probability=fill_probability,
            rejection_probability=rejection_probability,
            latency_ms=latency_ms,
        )
        .position_config(starting_equity=starting_equity)
    )

    # Load configuration (Phase 7, optional for paper trading)
    await builder.load_config(config_path=None)  # Load from environment for now

    # Build supervisors
    system_supervisor = builder.build_system_supervisor()

    order_queue = bus.subscribe(ORDERS)
    market_change_queue = bus.subscribe(MARKET_CHANGE)

    # Start system supervisor first
    await system_supervisor.start()

    # Get paper position manager for metrics display and market supervisor
    position_manager = system_supervisor.get_position_manager()
    if not isinstance(position_manager, PaperPositionManager):
        raise RuntimeError("Expected PaperPositionManager but got different type")

    # Build and start market supervisor
    market_supervisor = builder.build_market_supervisor(position_manager=position_manager)
    await market_supervisor.start()

    system_supervisor_task = asyncio.create_task(system_supervisor.run())
    market_supervisor_task = asyncio.create_task(market_supervisor.run())

    async def handle_orders() -> None:
        """Handle order events."""
        while True:
            order = await order_queue.get()
            order_handler(order)

    async def handle_market_changes() -> None:
        """Handle market change events."""
        while True:
            event = await market_change_queue.get()
            market_change_handler(event)

    orders_task = asyncio.create_task(handle_orders())
    market_changes_task = asyncio.create_task(handle_market_changes())
    metrics_task = asyncio.create_task(
        display_performance_metrics(position_manager, metrics_interval)
    )

    try:
        await asyncio.gather(
            system_supervisor_task,
            market_supervisor_task,
            orders_task,
            market_changes_task,
            metrics_task,
        )
    except KeyboardInterrupt:
        market_supervisor.stop()
        await system_supervisor.stop()
        # Display final metrics
        metrics = position_manager.get_performance_metrics()
        final_starting_equity = position_manager.get_starting_equity()
        final_unrealized_pnl = position_manager.calculate_unrealized_pnl()
        summary = metrics.get_summary(
            starting_equity=final_starting_equity, unrealized_pnl=final_unrealized_pnl
        )
        logger.info("=" * 70)
        logger.info("📊 FINAL PAPER TRADING PERFORMANCE METRICS")
        logger.info("=" * 70)
        logger.info(f"Total Trades: {summary['total_trades']}")
        logger.info(f"Win Rate: {summary['win_rate_pct']:.1f}%")
        logger.info(f"Total Realized P&L: ${summary['total_realized_pnl']:.2f}")
        if summary.get("unrealized_pnl", 0.0) != 0.0:
            logger.info(f"Unrealized P&L: ${summary['unrealized_pnl']:.2f}")
        logger.info(f"Average P&L per Trade: ${summary['average_pnl']:.2f}")
        if summary["best_trade_pnl"] is not None:
            logger.info(f"Best Trade: ${summary['best_trade_pnl']:.2f}")
        if summary["worst_trade_pnl"] is not None:
            logger.info(f"Worst Trade: ${summary['worst_trade_pnl']:.2f}")
        logger.info(f"Current Equity: ${summary['current_equity']:.2f}")
        logger.info("=" * 70)
        # Emit system stopped event
        stopped_event = SystemStoppedEvent(reason="KeyboardInterrupt")
        await bus.publish(SYSTEM_LIFECYCLE, stopped_event)
    except Exception as e:
        # Emit system stopped event with error reason
        stopped_event = SystemStoppedEvent(reason=f"Error: {type(e).__name__}: {str(e)}")
        await bus.publish(SYSTEM_LIFECYCLE, stopped_event)
        raise
    finally:
        system_supervisor_task.cancel()
        market_supervisor_task.cancel()
        orders_task.cancel()
        market_changes_task.cancel()
        metrics_task.cancel()
        try:
            await system_supervisor_task
            await market_supervisor_task
            await orders_task
            await market_changes_task
            await metrics_task
        except asyncio.CancelledError:
            pass
        # Stop supervisors
        market_supervisor.stop()
        await system_supervisor.stop()

        # Flush and close store (ensures all ticks are persisted)
        if hasattr(store, "close"):
            try:
                await store.close()
            except Exception:
                logger.exception("Error closing market data store")

        # Emit system stopped event if not already emitted
        if not any(
            isinstance(e, SystemStoppedEvent)
            for e in event_store.read_stream(event_type=SystemStoppedEvent)
        ):
            stopped_event = SystemStoppedEvent(reason="Normal shutdown")
            await bus.publish(SYSTEM_LIFECYCLE, stopped_event)
