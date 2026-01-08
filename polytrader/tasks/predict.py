import asyncio
from collections.abc import Callable
from datetime import datetime

from polytrader.adapters import create_adapter_factory
from polytrader.clob import create_clob_client_factory
from polytrader.config import PolymarketSecrets
from polytrader.events import MARKET_CHANGE, PROPOSALS, EventBus
from polytrader.market_discovery import MarketDiscoveryService
from polytrader.models import create_model_factory
from polytrader.observer import create_observer_factory
from polytrader.order_manager import create_order_manager_factory
from polytrader.store import MemoryTickStore
from polytrader.supervisor import MarketSupervisor
from polytrader.types import MarketChangeEvent, TradeProposal


def default_proposal_handler(proposal: TradeProposal) -> None:
    """Default handler for proposal events - prints to stdout."""
    print("Trade Proposal:")
    print(f"  Timestamp: {proposal.ts:.3f}")
    print(f"  Market: {proposal.market_slug}")
    print(f"  Outcome: {proposal.outcome}")
    print(f"  Side: {proposal.side}")
    print(f"  Target Price: {proposal.target_price:.4f}")
    print(f"  Limit Price: {proposal.limit_price:.4f}")
    print(f"  Size: ${proposal.size}")
    print(f"  Reason: {proposal.reason}")
    print()


def default_market_change_handler(event: MarketChangeEvent) -> None:
    """Default handler for market change events - prints to stdout."""
    change_time = datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d %H:%M:%S")
    if event.old_market:
        print(f"\n🔄 Market transition at {change_time}:")
        print(f"   Old: {event.old_market}")
        print(f"   New: {event.new_market}\n")
    else:
        print(f"\n🚀 Started with market: {event.new_market} at {change_time}\n")


async def predict_task(
    market_pattern: str,
    frequency: float = 1.0,
    buy_threshold: float = 0.30,
    sell_threshold: float = 0.50,
    size: float = 1.0,
    min_history: int = 30,
    proposal_handler: Callable[[TradeProposal], None] | None = None,
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

    bus = EventBus()
    store = MemoryTickStore()
    discovery = MarketDiscoveryService()

    adapter_factory = create_adapter_factory(secrets, polling_frequency_hz=frequency)
    observer_factory = create_observer_factory(bus, store)
    model_factory = create_model_factory(
        bus,
        store,
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
        size=size,
        min_history=min_history,
    )
    clob_client_factory = create_clob_client_factory(secrets)
    order_manager_factory = create_order_manager_factory(
        bus, clob_client_factory, max_trades_per_market=1
    )

    supervisor = MarketSupervisor(
        pattern=market_pattern,
        discovery_service=discovery,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        model_factory=model_factory,
        order_manager_factory=order_manager_factory,
        bus=bus,
        store=store,
    )

    proposal_queue = bus.subscribe(PROPOSALS)
    market_change_queue = bus.subscribe(MARKET_CHANGE)

    supervisor_task = asyncio.create_task(supervisor.run())

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
        await asyncio.gather(supervisor_task, proposals_task, market_changes_task)
    except KeyboardInterrupt:
        supervisor.stop()
    finally:
        supervisor_task.cancel()
        proposals_task.cancel()
        market_changes_task.cancel()
        try:
            await supervisor_task
            await proposals_task
            await market_changes_task
        except asyncio.CancelledError:
            pass
