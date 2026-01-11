import asyncio
from collections.abc import Callable

from polytrader.adapters import create_adapter_factory
from polytrader.config import PolymarketSecrets
from polytrader.events import (
    MARKET_CHANGE,
    PROPOSALS,
    SYSTEM_LIFECYCLE,
    EventBus,
    MemoryEventStore,
    SystemStartedEvent,
    SystemStoppedEvent,
)
from polytrader.logging_config import logger
from polytrader.market_discovery import MarketDiscoveryService
from polytrader.observer import create_observer_factory
from polytrader.store import MemoryMarketDataStore
from polytrader.supervisor import MarketSupervisor, SystemSupervisor
from polytrader.types import MarketChangeEvent, OrderIntentEvent


def default_proposal_handler(proposal: OrderIntentEvent) -> None:
    """Default handler for proposal events - logs using structured logging."""
    market_short = (
        proposal.market_slug.split("-")[-1] if "-" in proposal.market_slug else proposal.market_slug
    )
    logger.bind(
        market_slug=proposal.market_slug,
        outcome=proposal.outcome,
        side=proposal.side,
        size=proposal.size,
    ).info(
        "💡 PROPOSAL  {market:15s}  {outcome:4s}  {side:4s}  ${size:.2f}  "
        "@{limit_price:.4f}  target:{target_price:.4f}  {reason}",
        market=market_short,
        outcome=proposal.outcome,
        side=proposal.side,
        size=proposal.size,
        limit_price=proposal.limit_price,
        target_price=proposal.target_price,
        reason=proposal.reason,
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


async def predict_task(
    market_pattern: str,
    frequency: float = 1.0,
    buy_threshold: float = 0.30,
    sell_threshold: float = 0.50,
    size: float = 1.0,
    min_history: int = 30,
    proposal_handler: Callable[[OrderIntentEvent], None] | None = None,
    market_change_handler: Callable[[MarketChangeEvent], None] | None = None,
    secrets: PolymarketSecrets | None = None,
) -> None:
    """Run trading model predictions.

    Args:
        market_pattern: Market pattern (e.g., 'btc-updown-15m') or market slug
        frequency: Polling frequency in Hz
        buy_threshold: Buy threshold price
        sell_threshold: Sell threshold price
        size: Trade size in USD
        min_history: Minimum history ticks required
        proposal_handler: Callback for each proposal (default: prints to stdout)
        market_change_handler: Callback for market changes (default: prints to stdout)
        secrets: Polymarket secrets (defaults to loading from env)
    """
    if secrets is None:
        secrets = PolymarketSecrets()

    if proposal_handler is None:
        proposal_handler = default_proposal_handler

    if market_change_handler is None:
        market_change_handler = default_market_change_handler

    store = MemoryMarketDataStore()
    event_store = MemoryEventStore()
    bus = EventBus(store=event_store)
    discovery = MarketDiscoveryService()

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

    # Create service factories for SystemSupervisor (predict mode: no execution)
    from polytrader.oms import InMemoryOrderStore, OMSCore
    from polytrader.oms.idempotency import IdempotencyStore
    from polytrader.portfolio import PortfolioService
    from polytrader.risk import RiskChecker, RiskEngine, get_default_limits

    def portfolio_service_factory() -> PortfolioService:
        return PortfolioService(
            bus=bus,
            store=store,
            position_manager=None,  # No position manager in predict mode
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
    # Predict mode: SystemSupervisor without ExecutionRouter (proposals go to handler)
    system_supervisor = SystemSupervisor(
        bus=bus,
        store=store,
        portfolio_service_factory=portfolio_service_factory,
        risk_checker_factory=risk_checker_factory,
        oms_core_factory=oms_core_factory,
        execution_router_factory=None,  # No execution in predict mode
        position_manager_factory=None,  # No position manager in predict mode
    )

    market_supervisor = MarketSupervisor(
        pattern=market_pattern,
        discovery_service=discovery,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        strategy_factory=strategy_factory,
        bus=bus,
        store=store,
        position_manager=None,  # No position manager in predict mode
    )

    proposal_queue = bus.subscribe(PROPOSALS)
    market_change_queue = bus.subscribe(MARKET_CHANGE)

    # Start supervisors (system first, then market)
    await system_supervisor.start()
    await market_supervisor.start()

    system_supervisor_task = asyncio.create_task(system_supervisor.run())
    market_supervisor_task = asyncio.create_task(market_supervisor.run())

    async def handle_proposals() -> None:
        """Handle proposal events."""
        while True:
            proposal = await proposal_queue.get()
            proposal_handler(proposal)

    async def handle_market_changes() -> None:
        """Handle market change events."""
        while True:
            event = await market_change_queue.get()
            market_change_handler(event)

    proposals_task = asyncio.create_task(handle_proposals())
    market_changes_task = asyncio.create_task(handle_market_changes())

    try:
        await asyncio.gather(
            system_supervisor_task,
            market_supervisor_task,
            proposals_task,
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
        proposals_task.cancel()
        market_changes_task.cancel()
        try:
            await system_supervisor_task
            await market_supervisor_task
            await proposals_task
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
