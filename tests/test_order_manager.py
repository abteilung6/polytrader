import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from polytrader.clob import IClobClient
from polytrader.events import ORDERS, PROPOSALS, EventBus
from polytrader.gamma import GammaClient, Market
from polytrader.order_manager import OrderManager
from polytrader.types import Order, TradeProposal


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

    proposal = TradeProposal(
        ts=time.time(),
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

    proposal = TradeProposal(
        ts=time.time() - 5.0,
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        target_price=0.50,
        limit_price=0.30,
        size=1.0,
        reason="Expired proposal",
        ttl_s=2.0,
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

    proposal = TradeProposal(
        ts=time.time(),
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

    proposal = TradeProposal(
        ts=time.time(),
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        target_price=0.50,
        limit_price=0.30,
        size=0.0,
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

    proposal = TradeProposal(
        ts=time.time(),
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
