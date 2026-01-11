import asyncio

from polytrader.adapters import IMarketDataAdapter
from polytrader.adapters.polymarket.market_data import GammaClient
from polytrader.clob import IClobClient
from polytrader.events import MARKET_CHANGE, MARKET_DATA, ORDERS, PROPOSALS, EventBus
from polytrader.events.types import SignalEvent
from polytrader.execution import ExecutionRouter
from polytrader.market_discovery import IMarketDiscoveryService
from polytrader.observer import IObserver
from polytrader.position_manager import IPositionManager, PositionManager
from polytrader.store import MemoryMarketDataStore
from polytrader.strategies import IStrategy
from polytrader.supervisor import MarketSupervisor
from polytrader.types import (
    MarketChangeEvent,
    MarketDataEvent,
    OrderExecutedEvent,
    OrderIntentEvent,
    Outcome,
    Position,
)


class FakeAdapter(IMarketDataAdapter):
    def __init__(self, market_slug: str) -> None:
        self.market_slug = market_slug
        self._running = False

    async def ticks(self):
        self._running = True
        while self._running:
            await asyncio.sleep(0.1)
            yield None

    def stop(self) -> None:
        self._running = False


class FakeObserver(IObserver):
    def __init__(self, bus: EventBus, adapter: IMarketDataAdapter, store) -> None:
        self._running = False

    async def run(self) -> None:
        self._running = True
        while self._running:
            await asyncio.sleep(0.1)

    def stop(self) -> None:
        self._running = False


class FakeStrategy(IStrategy):
    def __init__(self, market_slug: str) -> None:
        self.market_slug = market_slug
        self._running = False
        self.evaluations: list[MarketDataEvent] = []

    def evaluate(
        self,
        market_data: MarketDataEvent,
        positions: dict[tuple[str, str], Position] | None = None,
    ) -> SignalEvent | None:
        """Evaluate market data (fast, synchronous)."""
        self.evaluations.append(market_data)
        return None  # No signal generated

    async def run(self) -> None:
        """Optional background tasks (not needed for stateless strategies)."""
        self._running = True
        while self._running:
            await asyncio.sleep(0.1)

    def stop(self) -> None:
        """Stop background tasks."""
        self._running = False


class FakeExecutionRouter(ExecutionRouter):
    def __init__(self) -> None:
        self._running = False

    async def run(self) -> None:
        self._running = True
        while self._running:
            await asyncio.sleep(0.1)

    def stop(self) -> None:
        self._running = False


class FakeDiscoveryService(IMarketDiscoveryService):
    def __init__(self, initial_market: str | None = None) -> None:
        self.initial_market = initial_market
        self.current_market = initial_market
        self.calls: list[tuple[str, str]] = []

    async def get_current_market(self, pattern: str) -> str | None:
        self.calls.append(("get_current_market", pattern))
        return self.current_market

    async def get_next_market(self, pattern: str) -> str | None:
        self.calls.append(("get_next_market", pattern))
        return None


async def test_supervisor_initializes_with_market() -> None:
    """Test supervisor initializes with a discovered market."""
    bus = EventBus()
    store = MemoryMarketDataStore()
    discovery = FakeDiscoveryService(initial_market="test-market-1")

    def adapter_factory(slug: str) -> FakeAdapter:
        return FakeAdapter(slug)

    def observer_factory(adapter: IMarketDataAdapter) -> FakeObserver:
        return FakeObserver(bus, adapter, store)

    def strategy_factory(slug: str) -> IStrategy:
        return FakeStrategy(slug)

    def execution_router_factory() -> FakeExecutionRouter:
        return FakeExecutionRouter()

    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=discovery,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        strategy_factory=strategy_factory,
        execution_router_factory=execution_router_factory,
        bus=bus,
        store=store,
        monitor_interval=0.1,
    )

    assert supervisor.current_market is None

    task = asyncio.create_task(supervisor.run())
    await asyncio.sleep(0.05)

    assert supervisor.current_market == "test-market-1"
    assert supervisor.adapter is not None
    assert supervisor.observer is not None
    assert supervisor.strategy is not None
    assert supervisor.execution_router is not None

    supervisor.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_supervisor_transitions_on_market_change() -> None:
    """Test supervisor transitions when market changes."""
    bus = EventBus()
    store = MemoryMarketDataStore()
    discovery = FakeDiscoveryService(initial_market="test-market-1")

    def adapter_factory(slug: str) -> FakeAdapter:
        return FakeAdapter(slug)

    def observer_factory(adapter: IMarketDataAdapter) -> FakeObserver:
        return FakeObserver(bus, adapter, store)

    def strategy_factory(slug: str) -> IStrategy:
        return FakeStrategy(slug)

    def execution_router_factory() -> FakeExecutionRouter:
        return FakeExecutionRouter()

    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=discovery,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        strategy_factory=strategy_factory,
        execution_router_factory=execution_router_factory,
        bus=bus,
        store=store,
        monitor_interval=0.1,
    )

    task = asyncio.create_task(supervisor.run())
    await asyncio.sleep(0.05)

    assert supervisor.current_market == "test-market-1"
    old_adapter = supervisor.adapter

    discovery.current_market = "test-market-2"
    await asyncio.sleep(0.15)

    assert supervisor.current_market == "test-market-2"
    assert supervisor.adapter is not None
    assert supervisor.adapter != old_adapter
    assert isinstance(supervisor.adapter, FakeAdapter)
    assert supervisor.adapter.market_slug == "test-market-2"

    supervisor.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_supervisor_publishes_market_change_events() -> None:
    """Test supervisor publishes market change events."""
    bus = EventBus()
    store = MemoryMarketDataStore()
    discovery = FakeDiscoveryService(initial_market="test-market-1")

    def adapter_factory(slug: str) -> FakeAdapter:
        return FakeAdapter(slug)

    def observer_factory(adapter: IMarketDataAdapter) -> FakeObserver:
        return FakeObserver(bus, adapter, store)

    def strategy_factory(slug: str) -> IStrategy:
        return FakeStrategy(slug)

    def execution_router_factory() -> FakeExecutionRouter:
        return FakeExecutionRouter()

    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=discovery,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        strategy_factory=strategy_factory,
        execution_router_factory=execution_router_factory,
        bus=bus,
        store=store,
        monitor_interval=0.1,
    )

    change_queue = bus.subscribe(MARKET_CHANGE)

    task = asyncio.create_task(supervisor.run())
    await asyncio.sleep(0.05)

    event = await asyncio.wait_for(change_queue.get(), timeout=0.5)
    assert isinstance(event, MarketChangeEvent)
    assert event.new_market == "test-market-1"
    assert event.old_market is None
    # Verify Event base class fields
    assert hasattr(event, "event_id")
    assert hasattr(event, "ts_wall")
    assert hasattr(event, "ts_mono")
    assert hasattr(event, "correlation_id")
    assert hasattr(event, "run_id")
    assert event.schema_version == "1.0"
    from polytrader.events.types import EventSource

    assert event.source == EventSource.OPS

    discovery.current_market = "test-market-2"
    await asyncio.sleep(0.15)

    event = await asyncio.wait_for(change_queue.get(), timeout=0.5)
    assert isinstance(event, MarketChangeEvent)
    assert event.new_market == "test-market-2"
    assert event.old_market == "test-market-1"
    # Verify Event base class fields
    assert hasattr(event, "event_id")
    assert hasattr(event, "ts_wall")
    assert hasattr(event, "ts_mono")
    assert hasattr(event, "correlation_id")
    assert hasattr(event, "run_id")
    assert event.schema_version == "1.0"
    assert event.source == EventSource.OPS

    supervisor.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_supervisor_stops_components_on_transition() -> None:
    """Test supervisor stops old components before starting new ones."""
    bus = EventBus()
    store = MemoryMarketDataStore()
    discovery = FakeDiscoveryService(initial_market="test-market-1")

    def adapter_factory(slug: str) -> FakeAdapter:
        return FakeAdapter(slug)

    def observer_factory(adapter: IMarketDataAdapter) -> FakeObserver:
        return FakeObserver(bus, adapter, store)

    def strategy_factory(slug: str) -> IStrategy:
        return FakeStrategy(slug)

    def execution_router_factory() -> FakeExecutionRouter:
        return FakeExecutionRouter()

    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=discovery,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        strategy_factory=strategy_factory,
        execution_router_factory=execution_router_factory,
        bus=bus,
        store=store,
        monitor_interval=0.1,
    )

    task = asyncio.create_task(supervisor.run())
    await asyncio.sleep(0.05)

    old_observer = supervisor.observer
    old_strategy = supervisor.strategy
    old_execution_router = supervisor.execution_router

    assert isinstance(old_observer, FakeObserver)
    assert isinstance(old_strategy, FakeStrategy)
    assert isinstance(old_execution_router, FakeExecutionRouter)
    assert old_observer._running
    assert old_strategy._running
    assert old_execution_router._running

    discovery.current_market = "test-market-2"
    await asyncio.sleep(0.15)

    assert not old_observer._running
    assert not old_strategy._running
    assert not old_execution_router._running

    assert supervisor.observer is not None
    assert supervisor.strategy is not None
    assert supervisor.execution_router is not None

    supervisor.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_supervisor_without_execution_router_does_not_execute_orders() -> None:
    """Test that supervisor without execution router (predict mode) doesn't execute orders."""
    bus = EventBus()
    store = MemoryMarketDataStore()
    discovery = FakeDiscoveryService(initial_market="test-market-1")

    def adapter_factory(slug: str) -> FakeAdapter:
        return FakeAdapter(slug)

    def observer_factory(adapter: IMarketDataAdapter) -> FakeObserver:
        return FakeObserver(bus, adapter, store)

    def strategy_factory(slug: str) -> IStrategy:
        return FakeStrategy(slug)

    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=discovery,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        strategy_factory=strategy_factory,
        execution_router_factory=None,  # No execution in predict mode
        bus=bus,
        store=store,
        monitor_interval=0.1,
    )

    # Track orders published
    orders_published = []
    order_queue = bus.subscribe(ORDERS)

    async def collect_orders() -> None:
        """Collect any orders that are published."""
        try:
            while True:
                order = await asyncio.wait_for(order_queue.get(), timeout=0.2)
                orders_published.append(order)
        except TimeoutError:
            pass

    collect_task = asyncio.create_task(collect_orders())

    task = asyncio.create_task(supervisor.run())
    await asyncio.sleep(0.05)

    # Verify no execution router was created
    assert supervisor.execution_router is None

    # Publish a proposal (simulating what the model would do)
    proposal = OrderIntentEvent(
        market_slug="test-market-1",
        outcome="UP",
        side="BUY",
        target_price=0.50,
        limit_price=0.30,
        size=1.0,
        reason="Test proposal",
        ttl_s=10.0,
    )
    await bus.publish(PROPOSALS, proposal)

    # Wait for processing
    await asyncio.sleep(0.1)

    # Verify no orders were published
    assert len(orders_published) == 0, (
        f"Expected no orders without execution router, but got {len(orders_published)} orders"
    )

    supervisor.stop()
    task.cancel()
    collect_task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    try:
        await collect_task
    except asyncio.CancelledError:
        pass


async def test_supervisor_with_position_manager_end_to_end() -> None:
    """End-to-end test: Supervisor with PositionManager tracks positions.

    Verifies that PositionManager creates positions from BUY orders,
    monitors ticks, generates SELL proposals when target is reached,
    and removes positions after SELL orders.
    """
    from unittest.mock import MagicMock

    bus = EventBus()
    store = MemoryMarketDataStore()
    market_slug = "test-market-1"
    discovery = FakeDiscoveryService(initial_market=market_slug)

    # Fake CLOB client
    class FakeClobClient(IClobClient):
        def get_balance_allowance(self, params) -> dict:
            return {"balance": "1000000"}

        def create_market_order(self, order_args) -> dict:
            return {"signed_order": "fake"}

        def post_order(self, signed_order, order_type) -> dict:
            return {"order_id": "123", "status": "filled"}

        def create_or_derive_api_creds(self) -> dict:
            return {"api_key": "fake", "api_secret": "fake", "api_passphrase": "fake"}

        def set_api_creds(self, creds) -> None:
            pass

        def get_orders(self, params) -> list[dict]:
            return []

    def clob_factory() -> IClobClient:
        return FakeClobClient()

    # Fake adapter that emits ticks
    class TickEmittingAdapter(IMarketDataAdapter):
        def __init__(self, market_slug: str) -> None:
            self.market_slug = market_slug
            self._running = False

        async def ticks(self):
            self._running = True
            tick_count = 0
            while self._running:
                await asyncio.sleep(0.05)
                # Emit ticks for both UP and DOWN
                for outcome_str in ["UP", "DOWN"]:
                    outcome: Outcome = outcome_str  # type: ignore[assignment]
                    # Start with price below target (0.40), then above target (0.55)
                    price = 0.40 if tick_count < 2 else 0.55
                    event = MarketDataEvent(
                        market_slug=self.market_slug,
                        outcome=outcome,
                        best_bid=price - 0.01,
                        best_ask=price + 0.01,
                    )
                    yield event
                tick_count += 1
                if tick_count >= 3:
                    break

        def stop(self) -> None:
            self._running = False

    # Fake observer that just passes ticks through
    class PassThroughObserver(IObserver):
        def __init__(self, bus: EventBus, adapter: IMarketDataAdapter, store) -> None:
            self.bus = bus
            self.adapter = adapter
            self._running = False

        async def run(self) -> None:
            self._running = True
            async for event in self.adapter.ticks():
                await self.bus.publish(MARKET_DATA, event)
                store.add(event)

        def stop(self) -> None:
            self._running = False

    # Fake strategy that publishes a BUY proposal via background task
    # (This simulates the old model behavior until Commit 4 refactors it)
    class ProposalPublishingStrategy(IStrategy):
        def __init__(self, market_slug: str, bus: EventBus) -> None:
            self.market_slug = market_slug
            self.bus = bus
            self._running = False
            self._proposal_sent = False

        def evaluate(
            self,
            market_data: MarketDataEvent,
            positions: dict[tuple[str, str], Position] | None = None,
        ) -> SignalEvent | None:
            # For testing: return None (proposal published via background task)
            return None

        async def run(self) -> None:
            self._running = True
            # Subscribe to ticks and publish a proposal on first tick
            # (This simulates old model behavior until Commit 4)
            market_data_queue = self.bus.subscribe(MARKET_DATA)
            while self._running:
                try:
                    event = await asyncio.wait_for(market_data_queue.get(), timeout=0.1)
                    if not self._proposal_sent and event.outcome == "UP":
                        # Publish BUY proposal with target_price
                        proposal = OrderIntentEvent(
                            market_slug=event.market_slug,
                            outcome=event.outcome,
                            side="BUY",
                            target_price=0.50,
                            limit_price=event.best_ask,
                            size=1.0,
                            reason="Test BUY proposal",
                            ttl_s=10.0,
                        )
                        await self.bus.publish(PROPOSALS, proposal)
                        self._proposal_sent = True
                except TimeoutError:
                    continue

        def stop(self) -> None:
            self._running = False

    # Fake order manager that executes orders
    class ExecutingExecutionRouter(ExecutionRouter):
        """Fake execution router that publishes OrderExecutedEvent for testing."""

        def __init__(self, bus: EventBus) -> None:
            from unittest.mock import MagicMock

            from polytrader.adapters.polymarket.trading import ClobVenueAdapter

            # Create a minimal fake adapter
            fake_adapter = MagicMock(spec=ClobVenueAdapter)
            super().__init__(bus=bus, adapter=fake_adapter)
            self._running = False
            self.orders_published: list[OrderExecutedEvent] = []

        async def run(self) -> None:
            # Override run to simulate order execution for testing
            self._running = True
            proposal_queue = bus.subscribe(PROPOSALS)
            while self._running:
                try:
                    proposal = await asyncio.wait_for(proposal_queue.get(), timeout=0.1)
                    # Execute order immediately
                    order = OrderExecutedEvent(
                        market_slug=proposal.market_slug,
                        outcome=proposal.outcome,
                        side=proposal.side,
                        size=proposal.size,
                        target_price=proposal.target_price if proposal.side == "BUY" else None,
                        proposal_reason=proposal.reason,
                        response={"order_id": f"order-{proposal.side}", "status": "filled"},
                    )
                    await bus.publish(ORDERS, order)
                    self.orders_published.append(order)
                except TimeoutError:
                    continue

        def stop(self) -> None:
            self._running = False

    def adapter_factory(slug: str) -> IMarketDataAdapter:
        return TickEmittingAdapter(slug)

    def observer_factory(adapter: IMarketDataAdapter) -> IObserver:
        return PassThroughObserver(bus, adapter, store)

    def strategy_factory(slug: str) -> IStrategy:
        return ProposalPublishingStrategy(slug, bus)

    def execution_router_factory() -> ExecutionRouter:
        return ExecutingExecutionRouter(bus)

    gamma_client = MagicMock(spec=GammaClient)

    def position_manager_factory() -> IPositionManager:
        return PositionManager(
            bus=bus,
            clob_client_factory=clob_factory,
            gamma_client=gamma_client,
            sync_interval=0,  # Disable sync for test
        )

    supervisor = MarketSupervisor(
        pattern="test-pattern",
        discovery_service=discovery,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        strategy_factory=strategy_factory,
        execution_router_factory=execution_router_factory,
        bus=bus,
        store=store,
        position_manager_factory=position_manager_factory,
        monitor_interval=0.1,
    )

    # Track orders and proposals
    orders_published = []
    proposals_published = []
    order_queue = bus.subscribe(ORDERS)
    proposal_queue = bus.subscribe(PROPOSALS)

    async def collect_orders() -> None:
        """Collect orders."""
        try:
            while True:
                order = await asyncio.wait_for(order_queue.get(), timeout=0.5)
                orders_published.append(order)
        except TimeoutError:
            pass

    async def collect_proposals() -> None:
        """Collect proposals."""
        try:
            while True:
                proposal = await asyncio.wait_for(proposal_queue.get(), timeout=0.5)
                proposals_published.append(proposal)
        except TimeoutError:
            pass

    collect_orders_task = asyncio.create_task(collect_orders())
    collect_proposals_task = asyncio.create_task(collect_proposals())

    supervisor_task = asyncio.create_task(supervisor.run())

    # Wait for the flow to complete
    # Give enough time for ticks to be emitted, proposals to be generated,
    # orders to be executed, and positions to be created
    await asyncio.sleep(1.0)

    # Verify PositionManager was created
    assert supervisor.position_manager is not None
    assert isinstance(supervisor.position_manager, PositionManager)

    # Verify BUY order was executed
    assert len(orders_published) >= 1, "Expected at least one order (BUY)"
    buy_order = next((o for o in orders_published if o.side == "BUY"), None)
    assert buy_order is not None, "Expected BUY order"
    assert buy_order.target_price == 0.50, "BUY order should have target_price"

    # Verify SELL proposal was generated when target price reached
    sell_proposals = [p for p in proposals_published if p.side == "SELL"]
    assert len(sell_proposals) > 0, "Expected SELL proposal when target price reached"

    # Verify SELL order was executed
    sell_orders = [o for o in orders_published if o.side == "SELL"]
    assert len(sell_orders) > 0, "Expected SELL order to be executed"

    # Verify position lifecycle: The position was created (evidenced by SELL order)
    # and then removed after SELL. Since the flow is fast, we verify the end state.
    final_positions = supervisor.position_manager.get_positions()
    assert final_positions is not None
    assert ("test-market-1", "UP") not in final_positions, (
        "Position should be removed after SELL order. "
        f"Current positions: {list(final_positions.keys())}"
    )

    # Verify the complete flow: BUY → Position created → SELL proposal → SELL order
    # The fact that we have both BUY and SELL orders proves the position existed
    # and was managed correctly
    assert len(orders_published) >= 2, (
        f"Expected at least 2 orders (BUY and SELL), got {len(orders_published)}"
    )

    supervisor.stop()
    supervisor_task.cancel()
    collect_orders_task.cancel()
    collect_proposals_task.cancel()

    try:
        await supervisor_task
    except asyncio.CancelledError:
        pass

    try:
        await collect_orders_task
    except asyncio.CancelledError:
        pass

    try:
        await collect_proposals_task
    except asyncio.CancelledError:
        pass
