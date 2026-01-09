import asyncio
from unittest.mock import MagicMock, patch

import pytest

from polytrader.clob import IClobClient
from polytrader.events import ORDERS, PROPOSALS, EventBus
from polytrader.gamma import GammaClient, Market
from polytrader.order_manager import OrderManager
from polytrader.types import Order, OrderIntentEvent


class FakeClobClient(IClobClient):
    def __init__(self) -> None:
        self.balance = 100.0

    def get_balance_allowance(self, params) -> dict:
        return {"balance": str(self.balance)}

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


async def test_order_manager_executes_valid_proposal() -> None:
    bus = EventBus()
    fake_client = FakeClobClient()

    def client_factory():
        return fake_client

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock(spec=Market)
    market.get_token_id.return_value = "token123"
    gamma_client.get_market_by_slug.return_value = market

    manager = OrderManager(
        bus=bus,
        clob_client_factory=client_factory,
        gamma_client=gamma_client,
        max_trades_per_market=1,
    )

    proposal = OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        target_price=0.50,
        limit_price=0.30,
        size=1.0,
        reason="Test proposal",
        ttl_s=10.0,
    )

    order_queue = bus.subscribe(ORDERS)

    with patch("polytrader.order_manager.verify_usdc_balance", return_value=100.0):
        with patch("polytrader.order_manager.place_market_order", return_value={"order_id": "123"}):
            await manager._process_proposal(proposal)

    assert manager._has_traded("test-market", "UP")
    gamma_client.get_market_by_slug.assert_called_once_with("test-market")
    market.get_token_id.assert_called_once_with("UP")

    order = await asyncio.wait_for(order_queue.get(), timeout=1.0)
    assert isinstance(order, Order)
    assert order.market_slug == "test-market"
    assert order.outcome == "UP"
    assert order.side == "BUY"
    assert order.size == 1.0
    assert order.target_price == 0.50
    assert order.response == {"order_id": "123"}


async def test_order_manager_skips_expired_proposal() -> None:
    bus = EventBus()
    fake_client = FakeClobClient()

    def client_factory():
        return fake_client

    manager = OrderManager(
        bus=bus,
        clob_client_factory=client_factory,
        max_trades_per_market=1,
    )

    order_queue = bus.subscribe(ORDERS)

    import time as time_module

    # Create proposal with old timestamp to simulate expiration
    proposal = OrderIntentEvent.model_validate(
        {
            "market_slug": "test-market",
            "outcome": "UP",
            "side": "BUY",
            "target_price": 0.50,
            "limit_price": 0.30,
            "size": 1.0,
            "reason": "Expired proposal",
            "ttl_s": 2.0,
            "ts_mono": time_module.monotonic() - 5.0,  # 5 seconds ago
        }
    )

    await manager._process_proposal(proposal)

    assert not manager._has_traded("test-market", "UP")

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(order_queue.get(), timeout=0.1)


async def test_order_manager_skips_duplicate_trade() -> None:
    bus = EventBus()
    fake_client = FakeClobClient()

    def client_factory():
        return fake_client

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock(spec=Market)
    market.get_token_id.return_value = "token123"
    gamma_client.get_market_by_slug.return_value = market

    manager = OrderManager(
        bus=bus,
        clob_client_factory=client_factory,
        gamma_client=gamma_client,
        max_trades_per_market=1,
    )

    order_queue = bus.subscribe(ORDERS)

    proposal = OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        target_price=0.50,
        limit_price=0.30,
        size=1.0,
        reason="Test proposal",
        ttl_s=10.0,
    )

    manager._executed_trades.add(("test-market", "UP"))

    await manager._process_proposal(proposal)

    gamma_client.get_market_by_slug.assert_not_called()

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(order_queue.get(), timeout=0.1)


async def test_order_manager_skips_invalid_size() -> None:
    bus = EventBus()
    fake_client = FakeClobClient()

    def client_factory():
        return fake_client

    manager = OrderManager(
        bus=bus,
        clob_client_factory=client_factory,
        max_trades_per_market=1,
    )

    order_queue = bus.subscribe(ORDERS)

    # Use model_construct to bypass validation for testing invalid size
    proposal = OrderIntentEvent.model_construct(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        target_price=0.50,
        limit_price=0.30,
        size=0.0,  # Invalid size for testing
        reason="Invalid size",
        ttl_s=10.0,
    )

    await manager._process_proposal(proposal)

    assert not manager._has_traded("test-market", "UP")

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(order_queue.get(), timeout=0.1)


async def test_order_manager_subscribes_to_proposals() -> None:
    bus = EventBus()
    fake_client = FakeClobClient()

    def client_factory():
        return fake_client

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock(spec=Market)
    market.get_token_id.return_value = "token123"
    gamma_client.get_market_by_slug.return_value = market

    manager = OrderManager(
        bus=bus,
        clob_client_factory=client_factory,
        gamma_client=gamma_client,
        max_trades_per_market=1,
    )

    proposal = OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        target_price=0.50,
        limit_price=0.30,
        size=1.0,
        reason="Test proposal",
        ttl_s=10.0,
    )

    order_queue = bus.subscribe(ORDERS)

    manager_task = asyncio.create_task(manager.run())
    await asyncio.sleep(0.01)

    async def mock_to_thread(func, *args):
        if args:
            result = func(*args)
        else:
            result = func()
        return result

    with patch("polytrader.order_manager.verify_usdc_balance", return_value=100.0):
        with patch("polytrader.order_manager.place_market_order", return_value={"order_id": "123"}):
            with patch("polytrader.order_manager.asyncio.to_thread", side_effect=mock_to_thread):
                await bus.publish(PROPOSALS, proposal)

                for _ in range(200):
                    if manager._has_traded("test-market", "UP"):
                        break
                    await asyncio.sleep(0.01)

    assert manager._has_traded("test-market", "UP")

    order = await asyncio.wait_for(order_queue.get(), timeout=1.0)
    assert isinstance(order, Order)
    assert order.market_slug == "test-market"
    assert order.outcome == "UP"
    assert order.side == "BUY"

    manager.stop()
    manager_task.cancel()
    try:
        await manager_task
    except asyncio.CancelledError:
        pass


async def test_order_manager_reset_trades() -> None:
    bus = EventBus()
    fake_client = FakeClobClient()

    def client_factory():
        return fake_client

    manager = OrderManager(
        bus=bus,
        clob_client_factory=client_factory,
        max_trades_per_market=1,
    )

    manager._executed_trades.add(("test-market", "UP"))
    assert manager._has_traded("test-market", "UP")

    manager.reset_trades()
    assert not manager._has_traded("test-market", "UP")


async def test_order_manager_executes_sell_from_position_manager_despite_no_tokens() -> None:
    """Test that SELL proposals from position manager are executed even if _has_tokens is False.

    This verifies the fix where position manager SELL proposals are trusted
    even when token tracking is out of sync.
    """
    bus = EventBus()
    fake_client = FakeClobClient()

    def client_factory():
        return fake_client

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock(spec=Market)
    market.get_token_id.return_value = "token123"
    gamma_client.get_market_by_slug.return_value = market

    manager = OrderManager(
        bus=bus,
        clob_client_factory=client_factory,
        gamma_client=gamma_client,
        max_trades_per_market=1,
    )

    # Simulate token tracking out of sync: we have a position but _owned_tokens is empty
    # This is the scenario that was causing the bug
    assert not manager._has_tokens("test-market", "UP")

    order_queue = bus.subscribe(ORDERS)

    # SELL proposal from position manager (identified by "Target price reached" in reason)
    proposal = OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="SELL",
        target_price=0.60,
        limit_price=0.61,
        size=1.0,
        reason="Target price reached: 0.6100 >= 0.6000 (entry: 0.4000)",
        ttl_s=10.0,
    )

    with patch(
        "polytrader.order_manager.place_market_order",
        return_value={"order_id": "456", "status": "filled"},
    ):
        await manager._process_proposal(proposal)

    # Verify order was executed
    order = await asyncio.wait_for(order_queue.get(), timeout=1.0)
    assert isinstance(order, Order)
    assert order.market_slug == "test-market"
    assert order.outcome == "UP"
    assert order.side == "SELL"
    assert order.size == 1.0
    assert order.response == {"order_id": "456", "status": "filled"}

    # Verify token tracking was updated: after SELL, tokens should be removed
    assert not manager._has_tokens("test-market", "UP")

    # Verify SELL order was NOT added to _executed_trades (only BUY orders are tracked)
    assert not manager._has_traded("test-market", "UP")

    gamma_client.get_market_by_slug.assert_called_once_with("test-market")
    market.get_token_id.assert_called_once_with("UP")


async def test_order_manager_executes_sell_after_buy() -> None:
    """Test that SELL proposals are not blocked by _has_traded check.

    This verifies that we can sell positions even after buying them,
    which is essential for position management.
    """
    bus = EventBus()
    fake_client = FakeClobClient()

    def client_factory():
        return fake_client

    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock(spec=Market)
    market.get_token_id.return_value = "token123"
    gamma_client.get_market_by_slug.return_value = market

    manager = OrderManager(
        bus=bus,
        clob_client_factory=client_factory,
        gamma_client=gamma_client,
        max_trades_per_market=1,
    )

    order_queue = bus.subscribe(ORDERS)

    # First, execute a BUY order
    buy_proposal = OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        target_price=0.60,
        limit_price=0.30,
        size=1.0,
        reason="Price below threshold",
        ttl_s=10.0,
    )

    with patch("polytrader.order_manager.verify_usdc_balance", return_value=100.0):
        with patch(
            "polytrader.order_manager.place_market_order",
            return_value={"order_id": "123", "status": "filled"},
        ):
            await manager._process_proposal(buy_proposal)

    # Verify BUY was executed and tracked
    assert manager._has_traded("test-market", "UP")
    assert manager._has_tokens("test-market", "UP")

    buy_order = await asyncio.wait_for(order_queue.get(), timeout=1.0)
    assert buy_order.side == "BUY"

    # Now try to SELL - this should work even though we've already traded
    sell_proposal = OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="SELL",
        target_price=0.60,
        limit_price=0.61,
        size=1.0,
        reason="Target price reached: 0.6100 >= 0.6000 (entry: 0.4000)",
        ttl_s=10.0,
    )

    with patch(
        "polytrader.order_manager.place_market_order",
        return_value={"order_id": "789", "status": "filled"},
    ):
        await manager._process_proposal(sell_proposal)

    # Verify SELL was executed
    sell_order = await asyncio.wait_for(order_queue.get(), timeout=1.0)
    assert isinstance(sell_order, Order)
    assert sell_order.market_slug == "test-market"
    assert sell_order.outcome == "UP"
    assert sell_order.side == "SELL"
    assert sell_order.size == 1.0

    # Verify tokens were removed
    assert not manager._has_tokens("test-market", "UP")

    # Verify _has_traded still returns True (we did trade, but SELL doesn't clear it)
    # This is expected - _has_traded tracks that we've traded, not that we currently hold
    assert manager._has_traded("test-market", "UP")


async def test_order_manager_skips_sell_without_tokens_unless_from_position_manager() -> None:
    """Test that SELL proposals without tokens are skipped unless from position manager."""
    bus = EventBus()
    fake_client = FakeClobClient()

    def client_factory():
        return fake_client

    manager = OrderManager(
        bus=bus,
        clob_client_factory=client_factory,
        max_trades_per_market=1,
    )

    order_queue = bus.subscribe(ORDERS)

    # SELL proposal from model (not position manager) - should be skipped
    proposal = OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="SELL",
        target_price=0.60,
        limit_price=0.61,
        size=1.0,
        reason="Price 0.6100 above sell threshold 0.6 for UP",  # Model reason, not position manager
        ttl_s=10.0,
    )

    assert not manager._has_tokens("test-market", "UP")

    await manager._process_proposal(proposal)

    # Verify order was NOT executed
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(order_queue.get(), timeout=0.1)
