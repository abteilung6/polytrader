"""Tests for RiskChecker max_trades_per_market race condition fix.

This test verifies that the fix prevents multiple orders from passing
risk checks when max_trades_per_market=1, even when orders arrive rapidly
before the first one executes.

Per testing.mdc §1.B: Integration tests for risk checker behavior.
"""

import asyncio

import pytest

from polytrader.events import APPROVED_PROPOSALS, ORDERS, PROPOSALS, EventBus, MemoryEventStore
from polytrader.events.types import MarketDataEvent, OrderExecutedEvent, OrderIntentEvent
from polytrader.risk import RiskChecker, RiskEngine, get_default_limits
from polytrader.store import MemoryMarketDataStore


class TestRiskCheckerMaxTradesRaceCondition:
    """Tests for max_trades_per_market race condition fix."""

    @pytest.mark.asyncio
    async def test_approved_orders_tracked_immediately(self) -> None:
        """Test that approved orders are tracked immediately, not waiting for execution."""
        bus = EventBus(store=MemoryEventStore())
        store = MemoryMarketDataStore()

        # Add market data
        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
        )
        store.add(market_data)

        # Create risk checker with max_trades_per_market=1
        limits = get_default_limits()
        limits.max_trades_per_market = 1
        engine = RiskEngine(limits=limits)
        checker = RiskChecker(bus=bus, engine=engine, store=store)

        # Subscribe to approved proposals
        approved_queue = bus.subscribe(APPROVED_PROPOSALS)

        # Start risk checker
        risk_task = asyncio.create_task(checker.run())
        await asyncio.sleep(0.01)  # Give time to subscribe

        # Create first order intent
        intent1 = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="First order",
            ttl_s=60.0,
            strategy_id="simple_threshold",
        )

        # Publish first order
        await bus.publish(PROPOSALS, intent1)
        await asyncio.sleep(0.01)  # Give time to process

        # First order should be approved
        approved1 = await asyncio.wait_for(approved_queue.get(), timeout=1.0)
        assert approved1.correlation_id == intent1.correlation_id

        # Verify it's tracked in approved_trades (by checking that second order is blocked)
        intent2 = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Second order",
            ttl_s=60.0,
            strategy_id="simple_threshold",
        )

        # Publish second order (should be denied)
        await bus.publish(PROPOSALS, intent2)
        await asyncio.sleep(0.01)  # Give time to process

        # Second order should NOT be approved (should timeout waiting)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(approved_queue.get(), timeout=0.1)

        # Cleanup
        checker.stop()
        risk_task.cancel()
        try:
            await risk_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_multiple_rapid_orders_only_first_approved(self) -> None:
        """Test that when multiple orders arrive rapidly, only the first is approved."""
        bus = EventBus(store=MemoryEventStore())
        store = MemoryMarketDataStore()

        # Add market data
        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
        )
        store.add(market_data)

        # Create risk checker with max_trades_per_market=1
        limits = get_default_limits()
        limits.max_trades_per_market = 1
        engine = RiskEngine(limits=limits)
        checker = RiskChecker(bus=bus, engine=engine, store=store)

        # Subscribe to approved proposals
        approved_queue = bus.subscribe(APPROVED_PROPOSALS)

        # Start risk checker
        risk_task = asyncio.create_task(checker.run())
        await asyncio.sleep(0.01)  # Give time to subscribe

        # Create and publish 5 orders rapidly (simulating race condition)
        intents = []
        for i in range(5):
            intent = OrderIntentEvent(
                market_slug="test-market",
                outcome="UP",
                side="BUY",
                target_price=0.5,
                limit_price=0.45,
                size=1.0,
                reason=f"Order {i + 1}",
                ttl_s=60.0,
                strategy_id="simple_threshold",
            )
            intents.append(intent)
            await bus.publish(PROPOSALS, intent)
            # No sleep between publishes - rapid fire to test race condition

        # Give time for all to process
        await asyncio.sleep(0.1)

        # Only first order should be approved
        approved = await asyncio.wait_for(approved_queue.get(), timeout=0.5)
        assert approved.correlation_id == intents[0].correlation_id

        # No more approvals should come (should timeout)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(approved_queue.get(), timeout=0.1)

        # Cleanup
        checker.stop()
        risk_task.cancel()
        try:
            await risk_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_executed_order_moves_from_approved_to_executed(self) -> None:
        """Test that when an order executes, it moves from approved_trades to executed_trades."""
        bus = EventBus(store=MemoryEventStore())
        store = MemoryMarketDataStore()

        # Add market data
        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
        )
        store.add(market_data)

        # Create risk checker with max_trades_per_market=1
        limits = get_default_limits()
        limits.max_trades_per_market = 1
        engine = RiskEngine(limits=limits)
        checker = RiskChecker(bus=bus, engine=engine, store=store)

        # Subscribe to approved proposals
        approved_queue = bus.subscribe(APPROVED_PROPOSALS)

        # Start risk checker
        risk_task = asyncio.create_task(checker.run())
        await asyncio.sleep(0.01)  # Give time to subscribe

        # Create and publish first order
        intent1 = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="First order",
            ttl_s=60.0,
            strategy_id="simple_threshold",
        )

        await bus.publish(PROPOSALS, intent1)
        await asyncio.sleep(0.01)

        # First order should be approved
        approved1 = await asyncio.wait_for(approved_queue.get(), timeout=1.0)
        assert approved1.correlation_id == intent1.correlation_id

        # Simulate order execution by publishing OrderExecutedEvent
        executed_event = OrderExecutedEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.5,
            proposal_reason="First order",
            response={"order_id": "test-123", "status": "filled"},
            correlation_id=intent1.correlation_id,
        )

        await bus.publish(ORDERS, executed_event)
        await asyncio.sleep(0.01)  # Give time to process

        # Now try a second order - should still be denied because
        # the first order is now in executed_trades
        intent2 = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Second order",
            ttl_s=60.0,
            strategy_id="simple_threshold",
        )

        await bus.publish(PROPOSALS, intent2)
        await asyncio.sleep(0.01)

        # Second order should NOT be approved
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(approved_queue.get(), timeout=0.1)

        # Cleanup
        checker.stop()
        risk_task.cancel()
        try:
            await risk_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_different_markets_allowed(self) -> None:
        """Test that orders for different markets/outcomes are still allowed."""
        bus = EventBus(store=MemoryEventStore())
        store = MemoryMarketDataStore()

        # Add market data for both markets
        market_data1 = MarketDataEvent(
            market_slug="test-market-1",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
        )
        market_data2 = MarketDataEvent(
            market_slug="test-market-2",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
        )
        store.add(market_data1)
        store.add(market_data2)

        # Create risk checker with max_trades_per_market=1
        limits = get_default_limits()
        limits.max_trades_per_market = 1
        engine = RiskEngine(limits=limits)
        checker = RiskChecker(bus=bus, engine=engine, store=store)

        # Subscribe to approved proposals
        approved_queue = bus.subscribe(APPROVED_PROPOSALS)

        # Start risk checker
        risk_task = asyncio.create_task(checker.run())
        await asyncio.sleep(0.01)  # Give time to subscribe

        # First order for market 1
        intent1 = OrderIntentEvent(
            market_slug="test-market-1",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Market 1 order",
            ttl_s=60.0,
            strategy_id="simple_threshold",
        )

        await bus.publish(PROPOSALS, intent1)
        await asyncio.sleep(0.01)

        approved1 = await asyncio.wait_for(approved_queue.get(), timeout=1.0)
        assert approved1.correlation_id == intent1.correlation_id

        # Second order for different market should be allowed
        intent2 = OrderIntentEvent(
            market_slug="test-market-2",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Market 2 order",
            ttl_s=60.0,
            strategy_id="simple_threshold",
        )

        await bus.publish(PROPOSALS, intent2)
        await asyncio.sleep(0.01)

        approved2 = await asyncio.wait_for(approved_queue.get(), timeout=1.0)
        assert approved2.correlation_id == intent2.correlation_id

        # Cleanup
        checker.stop()
        risk_task.cancel()
        try:
            await risk_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_different_strategies_can_trade_same_market(self) -> None:
        """Test that different strategy instances can trade the same market/outcome.

        This is the KEY regression test: the old code tracked trades globally
        by (market_slug, outcome), blocking all strategies after the first trade.
        The fix scopes tracking by (strategy_id, market_slug, outcome).
        """
        bus = EventBus(store=MemoryEventStore())
        store = MemoryMarketDataStore()

        # Add market data
        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
        )
        store.add(market_data)

        # Create risk checker with max_trades_per_market=1
        limits = get_default_limits()
        limits.max_trades_per_market = 1
        engine = RiskEngine(limits=limits)
        checker = RiskChecker(bus=bus, engine=engine, store=store)

        # Subscribe to approved proposals
        approved_queue = bus.subscribe(APPROVED_PROPOSALS)

        # Start risk checker
        risk_task = asyncio.create_task(checker.run())
        await asyncio.sleep(0.01)  # Give time to subscribe

        # Strategy instance A trades the market
        intent_a = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Strategy A order",
            ttl_s=60.0,
            strategy_id="strategy_instance_A",
        )

        await bus.publish(PROPOSALS, intent_a)
        await asyncio.sleep(0.01)

        approved_a = await asyncio.wait_for(approved_queue.get(), timeout=1.0)
        assert approved_a.correlation_id == intent_a.correlation_id

        # Strategy instance B trades the SAME market — should be ALLOWED
        intent_b = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Strategy B order",
            ttl_s=60.0,
            strategy_id="strategy_instance_B",
        )

        await bus.publish(PROPOSALS, intent_b)
        await asyncio.sleep(0.01)

        approved_b = await asyncio.wait_for(approved_queue.get(), timeout=1.0)
        assert approved_b.correlation_id == intent_b.correlation_id

        # Same strategy A tries again — should be BLOCKED
        intent_a2 = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Strategy A second order",
            ttl_s=60.0,
            strategy_id="strategy_instance_A",
        )

        await bus.publish(PROPOSALS, intent_a2)
        await asyncio.sleep(0.01)

        # Strategy A's second order should NOT be approved (should timeout)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(approved_queue.get(), timeout=0.1)

        # Cleanup
        checker.stop()
        risk_task.cancel()
        try:
            await risk_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_sell_orders_always_allowed(self) -> None:
        """Test that SELL orders are always allowed even after BUY order (for max_trades check)."""
        bus = EventBus(store=MemoryEventStore())
        store = MemoryMarketDataStore()

        # Add market data
        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
        )
        store.add(market_data)

        # Create risk checker with max_trades_per_market=1
        limits = get_default_limits()
        limits.max_trades_per_market = 1
        engine = RiskEngine(limits=limits)
        checker = RiskChecker(bus=bus, engine=engine, store=store)

        # Subscribe to approved proposals
        approved_queue = bus.subscribe(APPROVED_PROPOSALS)

        # Start risk checker
        risk_task = asyncio.create_task(checker.run())
        await asyncio.sleep(0.01)  # Give time to subscribe

        # First BUY order
        buy_intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="BUY order",
            ttl_s=60.0,
            strategy_id="simple_threshold",
        )

        await bus.publish(PROPOSALS, buy_intent)
        await asyncio.sleep(0.01)

        approved_buy = await asyncio.wait_for(approved_queue.get(), timeout=1.0)
        assert approved_buy.correlation_id == buy_intent.correlation_id

        # Execute the BUY order so we have tokens to sell
        executed_event = OrderExecutedEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.5,
            proposal_reason="BUY order",
            response={"order_id": "test-buy-123", "status": "filled"},
            correlation_id=buy_intent.correlation_id,
        )

        await bus.publish(ORDERS, executed_event)
        await asyncio.sleep(0.01)  # Give time to process

        # SELL order should still be allowed (max_trades check doesn't block SELL)
        sell_intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="SELL",
            target_price=0.7,
            limit_price=0.65,
            size=1.0,
            reason="SELL order",
            ttl_s=60.0,
            strategy_id="simple_threshold",
        )

        await bus.publish(PROPOSALS, sell_intent)
        await asyncio.sleep(0.01)

        approved_sell = await asyncio.wait_for(approved_queue.get(), timeout=1.0)
        assert approved_sell.correlation_id == sell_intent.correlation_id

        # Cleanup
        checker.stop()
        risk_task.cancel()
        try:
            await risk_task
        except asyncio.CancelledError:
            pass
