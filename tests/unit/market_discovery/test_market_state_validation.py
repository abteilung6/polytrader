"""Tests for enhanced market state validation using Gamma API fields."""

import time
from datetime import UTC, datetime, timedelta

import pytest

from polytrader.adapters.polymarket.market_data import Market
from polytrader.market_discovery import MarketDiscoveryService, MarketState
from polytrader.market_discovery.patterns import MarketPattern


@pytest.mark.asyncio
async def test_market_state_expired() -> None:
    """Test that expired markets return EXPIRED state."""
    from unittest.mock import MagicMock

    from polytrader.adapters.polymarket.market_data import GammaClient

    # Use a valid slug aligned to 15-minute boundary
    pattern = MarketPattern.parse("btc-updown-15m")
    now = int(time.time())
    window_start = (now // 900) * 900
    slug = pattern.generate_slug(window_start)

    # Market expired 1 hour ago
    expired_date = (datetime.now(UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")

    market = Market(
        id="1",
        slug=slug,
        outcomes='["Up", "Down"]',
        clobTokenIds='["1", "2"]',
        endDate=expired_date,
        active=True,
        closed=False,
        acceptingOrders=False,  # Not accepting orders (expired)
    )

    gamma_client = MagicMock(spec=GammaClient)
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    state = await discovery.get_market_state(slug)

    assert state == MarketState.EXPIRED


@pytest.mark.asyncio
async def test_market_state_resolved() -> None:
    """Test that resolved markets return RESOLVED state."""
    from unittest.mock import MagicMock

    from polytrader.adapters.polymarket.market_data import GammaClient
    from polytrader.market_discovery.patterns import MarketPattern

    # Use a valid slug aligned to 15-minute boundary
    pattern = MarketPattern.parse("btc-updown-15m")
    now = int(time.time())
    window_start = (now // 900) * 900
    slug = pattern.generate_slug(window_start)

    # Market expired and closed (resolved)
    expired_date = (datetime.now(UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")

    market = Market(
        id="1",
        slug=slug,
        outcomes='["Up", "Down"]',
        clobTokenIds='["1", "2"]',
        endDate=expired_date,
        active=True,
        closed=True,  # Market is resolved
        acceptingOrders=False,  # Not accepting orders (fully resolved)
    )

    gamma_client = MagicMock(spec=GammaClient)
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    state = await discovery.get_market_state(slug)

    assert state == MarketState.RESOLVED


@pytest.mark.asyncio
async def test_market_state_no_orderbook() -> None:
    """Test that markets without orderbook return NO_ORDERBOOK state."""
    from unittest.mock import MagicMock

    from polytrader.adapters.polymarket.market_data import GammaClient

    # Use a valid slug aligned to 15-minute boundary
    pattern = MarketPattern.parse("btc-updown-15m")
    now = int(time.time())
    window_start = (now // 900) * 900
    slug = pattern.generate_slug(window_start)

    # Market in the future, active, but not accepting orders
    future_date = (datetime.now(UTC) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")

    market = Market(
        id="1",
        slug=slug,
        outcomes='["Up", "Down"]',
        clobTokenIds='["1", "2"]',
        endDate=future_date,
        active=True,
        closed=False,
        acceptingOrders=False,  # No orderbook
    )

    gamma_client = MagicMock(spec=GammaClient)
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    state = await discovery.get_market_state(slug)

    assert state == MarketState.NO_ORDERBOOK


@pytest.mark.asyncio
async def test_market_state_active() -> None:
    """Test that active, tradeable markets return ACTIVE state."""
    from unittest.mock import MagicMock

    from polytrader.adapters.polymarket.market_data import GammaClient

    # Use a valid slug aligned to 15-minute boundary
    pattern = MarketPattern.parse("btc-updown-15m")
    now = int(time.time())
    window_start = (now // 900) * 900
    slug = pattern.generate_slug(window_start)

    # Market in the future, active, accepting orders
    future_date = (datetime.now(UTC) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")

    market = Market(
        id="1",
        slug=slug,
        outcomes='["Up", "Down"]',
        clobTokenIds='["1", "2"]',
        endDate=future_date,
        active=True,
        closed=False,
        acceptingOrders=True,
    )

    gamma_client = MagicMock(spec=GammaClient)
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    state = await discovery.get_market_state(slug)

    assert state == MarketState.ACTIVE


@pytest.mark.asyncio
async def test_market_state_priority_resolved_over_expired() -> None:
    """Test that RESOLVED takes priority over EXPIRED."""
    from unittest.mock import MagicMock

    from polytrader.adapters.polymarket.market_data import GammaClient

    # Use a valid slug aligned to 15-minute boundary
    pattern = MarketPattern.parse("btc-updown-15m")
    now = int(time.time())
    window_start = (now // 900) * 900
    slug = pattern.generate_slug(window_start)

    # Market expired and closed (resolved takes priority)
    expired_date = (datetime.now(UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")

    market = Market(
        id="1",
        slug=slug,
        outcomes='["Up", "Down"]',
        clobTokenIds='["1", "2"]',
        endDate=expired_date,
        active=True,
        closed=True,  # Resolved takes priority
        acceptingOrders=False,  # Not accepting orders (fully resolved)
    )

    gamma_client = MagicMock(spec=GammaClient)
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    state = await discovery.get_market_state(slug)

    assert state == MarketState.RESOLVED


@pytest.mark.asyncio
async def test_market_state_priority_expired_over_no_orderbook() -> None:
    """Test that EXPIRED takes priority over NO_ORDERBOOK.

    If a market is expired, it doesn't matter if it has an orderbook or not.
    Priority: RESOLVED > EXPIRED > NO_ORDERBOOK > ACTIVE
    """
    from unittest.mock import MagicMock

    from polytrader.adapters.polymarket.market_data import GammaClient

    # Use a valid slug aligned to 15-minute boundary
    pattern = MarketPattern.parse("btc-updown-15m")
    now = int(time.time())
    window_start = (now // 900) * 900
    slug = pattern.generate_slug(window_start)

    # Market expired and not accepting orders (expired takes priority)
    expired_date = (datetime.now(UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")

    market = Market(
        id="1",
        slug=slug,
        outcomes='["Up", "Down"]',
        clobTokenIds='["1", "2"]',
        endDate=expired_date,
        active=True,
        closed=False,
        acceptingOrders=False,
    )

    gamma_client = MagicMock(spec=GammaClient)
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    state = await discovery.get_market_state(slug)

    assert state == MarketState.EXPIRED


def test_market_is_expired() -> None:
    """Test Market.is_expired() helper method."""
    # Expired market
    expired_date = (datetime.now(UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    market = Market(
        id="1",
        slug="test",
        outcomes='["Up", "Down"]',
        clobTokenIds='["1", "2"]',
        endDate=expired_date,
    )
    assert market.is_expired() is True

    # Future market
    future_date = (datetime.now(UTC) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    market = Market(
        id="1",
        slug="test",
        outcomes='["Up", "Down"]',
        clobTokenIds='["1", "2"]',
        endDate=future_date,
    )
    assert market.is_expired() is False

    # Market without endDate
    market = Market(
        id="1",
        slug="test",
        outcomes='["Up", "Down"]',
        clobTokenIds='["1", "2"]',
        endDate=None,
    )
    assert market.is_expired() is False  # Conservative: assume not expired


def test_market_is_resolved() -> None:
    """Test Market.is_resolved() helper method."""
    market = Market(
        id="1",
        slug="test",
        outcomes='["Up", "Down"]',
        clobTokenIds='["1", "2"]',
        closed=True,
    )
    assert market.is_resolved() is True

    market = Market(
        id="1",
        slug="test",
        outcomes='["Up", "Down"]',
        clobTokenIds='["1", "2"]',
        closed=False,
    )
    assert market.is_resolved() is False


def test_market_is_tradeable() -> None:
    """Test Market.is_tradeable() helper method."""
    # Tradeable market
    market = Market(
        id="1",
        slug="test",
        outcomes='["Up", "Down"]',
        clobTokenIds='["1", "2"]',
        active=True,
        closed=False,
        acceptingOrders=True,
    )
    assert market.is_tradeable() is True

    # Not tradeable: not active
    market = Market(
        id="1",
        slug="test",
        outcomes='["Up", "Down"]',
        clobTokenIds='["1", "2"]',
        active=False,
        closed=False,
        acceptingOrders=True,
    )
    assert market.is_tradeable() is False

    # Not tradeable: closed
    market = Market(
        id="1",
        slug="test",
        outcomes='["Up", "Down"]',
        clobTokenIds='["1", "2"]',
        active=True,
        closed=True,
        acceptingOrders=True,
    )
    assert market.is_tradeable() is False

    # Not tradeable: not accepting orders
    market = Market(
        id="1",
        slug="test",
        outcomes='["Up", "Down"]',
        clobTokenIds='["1", "2"]',
        active=True,
        closed=False,
        acceptingOrders=False,
    )
    assert market.is_tradeable() is False
