"""Tests for PositionManager."""

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from polytrader.clob import IClobClient, IClobClientFactory
from polytrader.events import PROPOSALS, EventBus
from polytrader.gamma import GammaClient
from polytrader.position_manager import PositionManager
from polytrader.types import MarketDataEvent, OrderExecutedEvent, OrderIntentEvent, Outcome


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
    order = OrderExecutedEvent(
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
    buy_order = OrderExecutedEvent(
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
    sell_order = OrderExecutedEvent(
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
    buy_order = OrderExecutedEvent(
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

    # Create an event with price above target
    event = MarketDataEvent(
        market_slug="test-market",
        outcome="UP",
        best_bid=0.49,
        best_ask=0.51,  # Mid price = 0.50, which is >= target
    )

    # Check target prices
    await manager._check_target_prices(event)

    # Check that SELL proposal was generated
    proposal = await asyncio.wait_for(proposal_queue.get(), timeout=1.0)
    assert isinstance(proposal, OrderIntentEvent)
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
    buy_order = OrderExecutedEvent(
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

    # Create an event with price below target
    event = MarketDataEvent(
        market_slug="test-market",
        outcome="UP",
        best_bid=0.39,
        best_ask=0.41,  # Mid price = 0.40, which is < target
    )

    # Check target prices
    await manager._check_target_prices(event)

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
    buy_order_up = OrderExecutedEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        size=1.0,
        target_price=0.50,
        proposal_reason="Test buy UP",
        response={"order_id": "123", "status": "filled"},
    )
    buy_order_down = OrderExecutedEvent(
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


@pytest.mark.asyncio
async def test_position_manager_caches_token_id() -> None:
    """Test that PositionManager caches token_id when creating positions."""
    bus = EventBus()
    clob_factory = create_fake_clob_factory()
    gamma_client = MagicMock(spec=GammaClient)

    # Mock market with token_id
    market = MagicMock()
    market.get_token_id.return_value = "token-123"
    gamma_client.get_market_by_slug.return_value = market

    manager = PositionManager(
        bus=bus,
        clob_client_factory=clob_factory,
        gamma_client=gamma_client,
        sync_interval=0,
    )

    # Create a BUY order
    order = OrderExecutedEvent(
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

    # Verify token_id was cached
    market_info = manager._get_market_from_token("token-123")
    assert market_info is not None
    assert market_info == ("test-market", "UP")

    # Verify Gamma API was called
    gamma_client.get_market_by_slug.assert_called_once_with("test-market")
    market.get_token_id.assert_called_once_with("UP")


@pytest.mark.asyncio
async def test_position_manager_parses_external_order() -> None:
    """Test that PositionManager can parse external orders."""
    bus = EventBus()
    clob_factory = create_fake_clob_factory()
    gamma_client = MagicMock(spec=GammaClient)

    manager = PositionManager(
        bus=bus,
        clob_client_factory=clob_factory,
        gamma_client=gamma_client,
        sync_interval=0,
    )

    # Test various order formats
    order1 = {
        "token_id": "token-123",
        "status": "FILLED",
        "side": "BUY",
        "size": "1.0",
        "order_id": "123",
    }
    parsed1 = manager._parse_external_order(order1)
    assert parsed1 is not None
    assert parsed1.token_id == "token-123"
    assert parsed1.status == "FILLED"
    assert parsed1.side == "BUY"
    assert parsed1.size == 1.0
    assert parsed1.order_id == "123"

    # Test with asset_id
    order2 = {
        "asset_id": "token-456",
        "status": "CANCELLED",
        "side": "SELL",
        "amount": "2.0",
        "id": "456",
    }
    parsed2 = manager._parse_external_order(order2)
    assert parsed2 is not None
    assert parsed2.token_id == "token-456"
    assert parsed2.status == "CANCELLED"
    assert parsed2.side == "SELL"
    assert parsed2.size == 2.0

    # Test with nested asset
    order3 = {"asset": {"token_id": "token-789"}, "status": "OPEN", "side": "BUY", "size": "3.0"}
    parsed3 = manager._parse_external_order(order3)
    assert parsed3 is not None
    assert parsed3.token_id == "token-789"

    # Test with missing token_id
    order4 = {"status": "FILLED", "side": "BUY"}
    parsed4 = manager._parse_external_order(order4)
    assert parsed4 is None


@pytest.mark.asyncio
async def test_position_manager_reconciles_with_external_orders() -> None:
    """Test that PositionManager reconciles internal positions with external orders."""
    bus = EventBus()
    clob_factory = create_fake_clob_factory()
    gamma_client = MagicMock(spec=GammaClient)

    manager = PositionManager(
        bus=bus,
        clob_client_factory=clob_factory,
        gamma_client=gamma_client,
        sync_interval=0,
    )

    # Create a position and cache its token_id
    buy_order = OrderExecutedEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        size=1.0,
        target_price=0.50,
        proposal_reason="Test buy",
        response={"order_id": "123", "status": "filled"},
    )
    await manager._handle_order(buy_order)

    # Mock market for token_id lookup
    market = MagicMock()
    market.get_token_id.return_value = "token-123"
    gamma_client.get_market_by_slug.return_value = market

    # Cache the token_id
    await manager._cache_token_id("test-market", "UP")

    # Create external orders
    external_orders = [
        {
            "token_id": "token-123",
            "status": "FILLED",
            "side": "BUY",
            "size": "1.0",
            "order_id": "123",
        },
        {
            "token_id": "token-456",  # Unknown token
            "status": "FILLED",
            "side": "BUY",
            "size": "1.0",
            "order_id": "456",
        },
    ]

    # Reconcile
    await manager._reconcile_positions(external_orders)

    # Verify position still exists (confirmed by external order)
    positions = manager.get_positions()
    assert ("test-market", "UP") in positions


@pytest.mark.asyncio
async def test_position_manager_removes_stale_positions() -> None:
    """Test that PositionManager removes positions when external orders are CANCELLED."""
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
    buy_order = OrderExecutedEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        size=1.0,
        target_price=0.50,
        proposal_reason="Test buy",
        response={"order_id": "123", "status": "filled"},
    )
    await manager._handle_order(buy_order)

    # Mock market for token_id lookup
    market = MagicMock()
    market.get_token_id.return_value = "token-123"
    gamma_client.get_market_by_slug.return_value = market

    # Cache the token_id
    await manager._cache_token_id("test-market", "UP")

    # Verify position exists
    positions = manager.get_positions()
    assert ("test-market", "UP") in positions

    # Create external CANCELLED order
    external_orders = [
        {
            "token_id": "token-123",
            "status": "CANCELLED",
            "side": "BUY",
            "size": "1.0",
            "order_id": "123",
        },
    ]

    # Reconcile
    await manager._reconcile_positions(external_orders)

    # Verify position was removed
    positions = manager.get_positions()
    assert ("test-market", "UP") not in positions


@pytest.mark.asyncio
async def test_position_manager_creates_position_from_external_order() -> None:
    """Test that PositionManager creates positions for externally filled orders."""
    bus = EventBus()
    clob_factory = create_fake_clob_factory()
    gamma_client = MagicMock(spec=GammaClient)

    manager = PositionManager(
        bus=bus,
        clob_client_factory=clob_factory,
        gamma_client=gamma_client,
        sync_interval=0,
    )

    # Mock market for token_id lookup
    market = MagicMock()
    market.get_token_id.return_value = "token-123"
    gamma_client.get_market_by_slug.return_value = market

    # Cache the token_id (simulating a previous trade or lookup)
    await manager._cache_token_id("test-market", "UP")

    # Verify no position exists
    positions = manager.get_positions()
    assert ("test-market", "UP") not in positions

    # Create external FILLED BUY order
    external_orders = [
        {
            "token_id": "token-123",
            "status": "FILLED",
            "side": "BUY",
            "size": "2.0",
            "order_id": "456",
        },
    ]

    # Reconcile
    await manager._reconcile_positions(external_orders)

    # Verify position was created
    positions = manager.get_positions()
    assert ("test-market", "UP") in positions
    position = positions[("test-market", "UP")]
    assert position.size == 2.0
    assert position.order_id == "456"


@pytest.mark.asyncio
async def test_position_manager_get_market_from_token() -> None:
    """Test that PositionManager can look up market from token_id."""
    bus = EventBus()
    clob_factory = create_fake_clob_factory()
    gamma_client = MagicMock(spec=GammaClient)

    manager = PositionManager(
        bus=bus,
        clob_client_factory=clob_factory,
        gamma_client=gamma_client,
        sync_interval=0,
    )

    # Initially, token not in cache
    assert manager._get_market_from_token("token-123") is None

    # Add to cache
    manager._token_to_market["token-123"] = ("test-market", "UP")

    # Now should find it
    market_info = manager._get_market_from_token("token-123")
    assert market_info is not None
    assert market_info == ("test-market", "UP")
