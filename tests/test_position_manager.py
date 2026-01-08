"""Tests for PositionManager."""

import asyncio
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from polytrader.clob import IClobClient, IClobClientFactory
from polytrader.events import PROPOSALS, EventBus
from polytrader.gamma import GammaClient
from polytrader.position_manager import PositionManager
from polytrader.types import MarketTick, Order, Outcome, TradeProposal


class FakeClobClient(IClobClient):
    def __init__(self) -> None:
        pass

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

    def get_orders(self, params) -> list[dict[str, Any]]:
        return []


def create_fake_clob_factory() -> IClobClientFactory:
    def factory() -> IClobClient:
        return FakeClobClient()

    return factory


@pytest.mark.asyncio
async def test_position_manager_creates_position_from_buy_order() -> None:
    """Test that PositionManager creates a position from a BUY order."""
    bus = EventBus()
    clob_factory = create_fake_clob_factory()
    gamma_client = MagicMock(spec=GammaClient)

    manager = PositionManager(
        bus=bus,
        clob_client_factory=clob_factory,
        gamma_client=gamma_client,
        sync_interval=0,  # Disable sync for test
    )

    # Create a BUY order
    order = Order(
        ts=time.time(),
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        size=1.0,
        target_price=0.50,
        proposal_reason="Test buy",
        response={"order_id": "123", "status": "filled"},
    )

    # Process the order
    await manager._handle_order(order)

    # Check position was created
    positions = manager.get_positions()
    assert len(positions) == 1

    key: tuple[str, Outcome] = ("test-market", "UP")
    assert key in positions

    position = positions[key]
    assert position.market_slug == "test-market"
    assert position.outcome == "UP"
    assert position.size == 1.0
    assert position.target_price == 0.50
    assert position.order_id == "123"


@pytest.mark.asyncio
async def test_position_manager_removes_position_from_sell_order() -> None:
    """Test that PositionManager removes a position from a SELL order."""
    bus = EventBus()
    clob_factory = create_fake_clob_factory()
    gamma_client = MagicMock(spec=GammaClient)

    manager = PositionManager(
        bus=bus,
        clob_client_factory=clob_factory,
        gamma_client=gamma_client,
        sync_interval=0,
    )

    # Create and add a position
    buy_order = Order(
        ts=time.time(),
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        size=1.0,
        target_price=0.50,
        proposal_reason="Test buy",
        response={"order_id": "123", "status": "filled"},
    )
    await manager._handle_order(buy_order)

    assert len(manager.get_positions()) == 1

    # Create a SELL order
    sell_order = Order(
        ts=time.time(),
        market_slug="test-market",
        outcome="UP",
        side="SELL",
        size=1.0,
        target_price=None,
        proposal_reason="Test sell",
        response={"order_id": "456", "status": "filled"},
    )

    # Process the SELL order
    await manager._handle_order(sell_order)

    # Check position was removed
    positions = manager.get_positions()
    assert len(positions) == 0


@pytest.mark.asyncio
async def test_position_manager_generates_sell_proposal_when_target_reached() -> None:
    """Test that PositionManager generates SELL proposal when target price is reached."""
    bus = EventBus()
    clob_factory = create_fake_clob_factory()
    gamma_client = MagicMock(spec=GammaClient)

    manager = PositionManager(
        bus=bus,
        clob_client_factory=clob_factory,
        gamma_client=gamma_client,
        sync_interval=0,
    )

    # Create a position
    buy_order = Order(
        ts=time.time(),
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        size=1.0,
        target_price=0.50,
        proposal_reason="Test buy",
        response={"order_id": "123", "status": "filled"},
    )
    await manager._handle_order(buy_order)

    # Subscribe to proposals
    proposal_queue = bus.subscribe(PROPOSALS)

    # Create a tick with price above target
    tick = MarketTick(
        ts=time.time(),
        market_slug="test-market",
        outcome="UP",
        best_bid=0.49,
        best_ask=0.51,  # Mid price = 0.50, which is >= target
    )

    # Check target prices
    await manager._check_target_prices(tick)

    # Check that SELL proposal was generated
    proposal = await asyncio.wait_for(proposal_queue.get(), timeout=1.0)
    assert isinstance(proposal, TradeProposal)
    assert proposal.side == "SELL"
    assert proposal.market_slug == "test-market"
    assert proposal.outcome == "UP"
    assert proposal.size == 1.0


@pytest.mark.asyncio
async def test_position_manager_does_not_generate_proposal_below_target() -> None:
    """Test that PositionManager does not generate proposal when price is below target."""
    bus = EventBus()
    clob_factory = create_fake_clob_factory()
    gamma_client = MagicMock(spec=GammaClient)

    manager = PositionManager(
        bus=bus,
        clob_client_factory=clob_factory,
        gamma_client=gamma_client,
        sync_interval=0,
    )

    # Create a position
    buy_order = Order(
        ts=time.time(),
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        size=1.0,
        target_price=0.50,
        proposal_reason="Test buy",
        response={"order_id": "123", "status": "filled"},
    )
    await manager._handle_order(buy_order)

    # Subscribe to proposals
    proposal_queue = bus.subscribe(PROPOSALS)

    # Create a tick with price below target
    tick = MarketTick(
        ts=time.time(),
        market_slug="test-market",
        outcome="UP",
        best_bid=0.39,
        best_ask=0.41,  # Mid price = 0.40, which is < target
    )

    # Check target prices
    await manager._check_target_prices(tick)

    # Check that no proposal was generated (queue should be empty)
    try:
        proposal = await asyncio.wait_for(proposal_queue.get(), timeout=0.1)
        pytest.fail(f"Unexpected proposal generated: {proposal}")
    except TimeoutError:
        pass  # Expected - no proposal should be generated


@pytest.mark.asyncio
async def test_position_manager_handles_multiple_positions() -> None:
    """Test that PositionManager can handle multiple positions for different outcomes."""
    bus = EventBus()
    clob_factory = create_fake_clob_factory()
    gamma_client = MagicMock(spec=GammaClient)

    manager = PositionManager(
        bus=bus,
        clob_client_factory=clob_factory,
        gamma_client=gamma_client,
        sync_interval=0,
    )

    # Create positions for UP and DOWN
    buy_order_up = Order(
        ts=time.time(),
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        size=1.0,
        target_price=0.50,
        proposal_reason="Test buy UP",
        response={"order_id": "123", "status": "filled"},
    )
    buy_order_down = Order(
        ts=time.time(),
        market_slug="test-market",
        outcome="DOWN",
        side="BUY",
        size=1.0,
        target_price=0.50,
        proposal_reason="Test buy DOWN",
        response={"order_id": "456", "status": "filled"},
    )

    await manager._handle_order(buy_order_up)
    await manager._handle_order(buy_order_down)

    # Check both positions exist
    positions = manager.get_positions()
    assert len(positions) == 2
    assert ("test-market", "UP") in positions
    assert ("test-market", "DOWN") in positions
