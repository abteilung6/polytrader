import asyncio
from collections.abc import Callable
from datetime import datetime

from polytrader.adapters import create_adapter_factory
from polytrader.clob import create_clob_client_factory
from polytrader.config import PolymarketSecrets
from polytrader.events import MARKET_CHANGE, ORDERS, EventBus
from polytrader.market_discovery import MarketDiscoveryService
from polytrader.models import create_model_factory
from polytrader.observer import create_observer_factory
from polytrader.order_manager import create_order_manager_factory
from polytrader.store import MemoryTickStore
from polytrader.supervisor import MarketSupervisor
from polytrader.types import MarketChangeEvent, Order


def default_order_handler(order: Order) -> None:
    """Default handler for order events - prints to stdout."""
    order_time = datetime.fromtimestamp(order.ts).strftime("%Y-%m-%d %H:%M:%S")

    print("\n" + "=" * 60)
    print("✅ ORDER EXECUTED SUCCESSFULLY")
    print("=" * 60)
    print(f"Time:        {order_time}")
    print(f"Market:      {order.market_slug}")
    print(f"Outcome:     {order.outcome}")
    print(f"Side:        {order.side}")
    print(f"Size:        ${order.size:.2f} USDC")
    print(f"Reason:      {order.proposal_reason}")

    response = order.response
    if isinstance(response, dict):
        order_id = response.get("order_id") or response.get("id") or "N/A"
        status = response.get("status") or response.get("state") or "N/A"
        fills = response.get("fills", [])

        print("\nOrder Details:")
        print(f"  Order ID:   {order_id}")
        print(f"  Status:     {status}")

        if fills:
            print(f"  Fills:      {len(fills)} fill(s)")
            for i, fill in enumerate(fills, 1):
                price = fill.get("price", "N/A")
                size = fill.get("size", "N/A")
                print(f"    Fill {i}: {size} @ {price}")
        else:
            print("  Fills:      No fills yet")

        if "error" in response:
            print(f"  ⚠️  Error:   {response['error']}")

        print("\nFull Response:")
        for key, value in response.items():
            if key not in ["order_id", "id", "status", "state", "fills"]:
                print(f"  {key}: {value}")
    else:
        print(f"\nResponse: {response}")

    print("=" * 60 + "\n")


def default_market_change_handler(event: MarketChangeEvent) -> None:
    """Default handler for market change events - prints to stdout."""
    change_time = datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d %H:%M:%S")
    if event.old_market:
        print(f"\n🔄 Market transition at {change_time}:")
        print(f"   Old: {event.old_market}")
        print(f"   New: {event.new_market}\n")
    else:
        print(f"\n🚀 Started with market: {event.new_market} at {change_time}\n")


async def auto_buy_task(
    market_pattern: str,
    frequency: float = 1.0,
    buy_threshold: float = 0.30,
    sell_threshold: float = 0.50,
    size: float = 1.0,
    min_history: int = 30,
    max_trades: int = 1,
    order_handler: Callable[[Order], None] | None = None,
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
        bus, clob_client_factory, max_trades_per_market=max_trades
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

    order_queue = bus.subscribe(ORDERS)
    market_change_queue = bus.subscribe(MARKET_CHANGE)

    supervisor_task = asyncio.create_task(supervisor.run())

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
        await asyncio.gather(supervisor_task, orders_task, market_changes_task)
    except KeyboardInterrupt:
        supervisor.stop()
    finally:
        supervisor_task.cancel()
        orders_task.cancel()
        market_changes_task.cancel()
        try:
            await supervisor_task
            await orders_task
            await market_changes_task
        except asyncio.CancelledError:
            pass
