import asyncio
from collections.abc import Callable

from polytrader.adapters import create_adapter_factory
from polytrader.clob import create_clob_client_factory
from polytrader.config import PolymarketSecrets
from polytrader.events import (
    MARKET_CHANGE,
    ORDERS,
    SYSTEM_LIFECYCLE,
    EventBus,
    MemoryEventStore,
    SystemStartedEvent,
    SystemStoppedEvent,
)
from polytrader.execution import create_execution_router_factory
from polytrader.logging_config import logger
from polytrader.market_discovery import MarketDiscoveryService
from polytrader.observer import create_observer_factory
from polytrader.oms import InMemoryOrderStore, OMSCore
from polytrader.oms.idempotency import IdempotencyStore
from polytrader.position_manager import create_position_manager_factory
from polytrader.risk import RiskChecker, RiskEngine, get_default_limits
from polytrader.store import MemoryMarketDataStore
from polytrader.supervisor import MarketSupervisor, SystemSupervisor
from polytrader.types import MarketChangeEvent, OrderExecutedEvent


def default_order_handler(order: OrderExecutedEvent) -> None:
    """Default handler for order events - logs using structured logging."""
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

        error_info = ""
        if "error" in response:
            error_info = f" ⚠️  {response['error']}"

        logger.bind(
            market_slug=order.market_slug,
            outcome=order.outcome,
            side=order.side,
            size=order.size,
            order_id=order_id,
            status=status,
        ).info(
            "✅ ORDER  {market:15s}  {outcome:4s}  {side:4s}  ${size:.2f}  "
            "ID:{order_id}  {status}{fill_info}{error_info}",
            market=market_short,
            outcome=order.outcome,
            side=order.side,
            size=order.size,
            order_id=order_id,
            status=status,
            fill_info=fill_info,
            error_info=error_info,
        )
        if order.proposal_reason:
            logger.bind(market_slug=order.market_slug, outcome=order.outcome).info(
                "Reason: {reason}", reason=order.proposal_reason
            )
    else:
        logger.bind(
            market_slug=order.market_slug,
            outcome=order.outcome,
            side=order.side,
            size=order.size,
        ).info(
            "✅ ORDER  {market:15s}  {outcome:4s}  {side:4s}  ${size:.2f}  Response: {response}",
            market=market_short,
            outcome=order.outcome,
            side=order.side,
            size=order.size,
            response=response,
        )


def default_market_change_handler(event: MarketChangeEvent) -> None:
    """Default handler for market change events - logs using structured logging."""
    if event.old_market:
        old_short = event.old_market.split("-")[-1] if "-" in event.old_market else event.old_market
        new_short = event.new_market.split("-")[-1] if "-" in event.new_market else event.new_market
        logger.bind(old_market=event.old_market, new_market=event.new_market).info(
            "🔄 Market: {old} → {new}", old=old_short, new=new_short
        )
    else:
        new_short = event.new_market.split("-")[-1] if "-" in event.new_market else event.new_market
        logger.bind(new_market=event.new_market).info("🚀 Started: {market}", market=new_short)


async def auto_buy_task(
    market_pattern: str,
    frequency: float = 1.0,
    buy_threshold: float = 0.30,
    sell_threshold: float = 0.50,
    size: float = 1.0,
    min_history: int = 30,
    max_trades: int = 1,
    order_handler: Callable[[OrderExecutedEvent], None] | None = None,
    market_change_handler: Callable[[MarketChangeEvent], None] | None = None,
    secrets: PolymarketSecrets | None = None,
) -> None:
    """Automatically execute trades based on model predictions.

    Args:
        market_pattern: Market pattern (e.g., 'btc-updown-15m') or market slug
        frequency: Polling frequency in Hz
        buy_threshold: Buy threshold price
        sell_threshold: Sell threshold price
        size: Trade size in USD
        min_history: Minimum history ticks required
        max_trades: Maximum trades per market/outcome
        order_handler: Callback for each executed order (default: prints to stdout)
        market_change_handler: Callback for market changes (default: prints to stdout)
        secrets: Polymarket secrets (defaults to loading from env)
    """
    if secrets is None:
        secrets = PolymarketSecrets()

    if order_handler is None:
        order_handler = default_order_handler

    if market_change_handler is None:
        market_change_handler = default_market_change_handler

    store = MemoryMarketDataStore()
    event_store = MemoryEventStore()
    bus = EventBus(store=event_store)
    discovery = MarketDiscoveryService(bus=bus)

    # Emit system started event (auto-persisted by EventBus)
    started_event = SystemStartedEvent()
    await bus.publish(SYSTEM_LIFECYCLE, started_event)

    adapter_factory = create_adapter_factory(secrets, polling_frequency_hz=frequency)
    observer_factory = create_observer_factory(bus, store)

    # Create strategy factory (replaces old model factory)
    from polytrader.strategies import create_simple_threshold_factory

    strategy_factory = create_simple_threshold_factory(
        store=store,
        buy_threshold=buy_threshold,
        min_history=min_history,
    )

    clob_client_factory = create_clob_client_factory(secrets)
    execution_router_factory = create_execution_router_factory(bus, clob_client_factory)
    position_manager_factory = create_position_manager_factory(
        bus, clob_client_factory, sync_interval=60.0
    )

    # Create service factories for SystemSupervisor
    from polytrader.portfolio import PortfolioService

    def portfolio_service_factory() -> PortfolioService:
        position_manager = (
            position_manager_factory() if position_manager_factory is not None else None
        )
        return PortfolioService(
            bus=bus,
            store=store,
            position_manager=position_manager,
            fixed_size_usd=size,
        )

    def risk_checker_factory() -> RiskChecker:
        risk_limits = get_default_limits()
        risk_engine = RiskEngine(limits=risk_limits)
        return RiskChecker(bus=bus, engine=risk_engine, store=store)

    def oms_core_factory() -> OMSCore:
        oms_store = InMemoryOrderStore(bus)
        idempotency_store = IdempotencyStore()
        return OMSCore(bus=bus, store=oms_store, idempotency_store=idempotency_store)

    # Create supervisors
    system_supervisor = SystemSupervisor(
        bus=bus,
        store=store,
        portfolio_service_factory=portfolio_service_factory,
        risk_checker_factory=risk_checker_factory,
        oms_core_factory=oms_core_factory,
        execution_router_factory=execution_router_factory,
        position_manager_factory=position_manager_factory,
    )

    order_queue = bus.subscribe(ORDERS)
    market_change_queue = bus.subscribe(MARKET_CHANGE)

    # Start supervisors (system first, then market)
    await system_supervisor.start()

    # Create market supervisor after system supervisor is started (to get position manager)
    market_supervisor = MarketSupervisor(
        pattern=market_pattern,
        discovery_service=discovery,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        strategy_factory=strategy_factory,
        bus=bus,
        store=store,
        position_manager=system_supervisor.get_position_manager(),  # Query from SystemSupervisor
    )

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

    try:
        await asyncio.gather(
            system_supervisor_task,
            market_supervisor_task,
            orders_task,
            market_changes_task,
        )
    except KeyboardInterrupt:
        market_supervisor.stop()
        await system_supervisor.stop()
        # Emit system stopped event (auto-persisted by EventBus)
        stopped_event = SystemStoppedEvent(reason="KeyboardInterrupt")
        await bus.publish(SYSTEM_LIFECYCLE, stopped_event)
    except Exception as e:
        # Emit system stopped event with error reason (auto-persisted by EventBus)
        stopped_event = SystemStoppedEvent(reason=f"Error: {type(e).__name__}: {str(e)}")
        await bus.publish(SYSTEM_LIFECYCLE, stopped_event)
        raise
    finally:
        system_supervisor_task.cancel()
        market_supervisor_task.cancel()
        orders_task.cancel()
        market_changes_task.cancel()
        try:
            await system_supervisor_task
            await market_supervisor_task
            await orders_task
            await market_changes_task
        except asyncio.CancelledError:
            pass
        # Stop supervisors
        market_supervisor.stop()
        await system_supervisor.stop()
        # Emit system stopped event if not already emitted (auto-persisted by EventBus)
        if not any(
            isinstance(e, SystemStoppedEvent)
            for e in event_store.read_stream(event_type=SystemStoppedEvent)
        ):
            stopped_event = SystemStoppedEvent(reason="Normal shutdown")
            await bus.publish(SYSTEM_LIFECYCLE, stopped_event)
