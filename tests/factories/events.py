"""Factories for creating event objects in tests.

Per unit_testing_techinical.mdc §5: All domain objects MUST be created via factories.
"""

import uuid

from polytrader.events.types import (
    FillEvent,
    MarketDataEvent,
    OrderIntentEvent,
    SignalEvent,
)
from polytrader.types import Outcome, Side


def create_order_intent_event(
    market_slug: str = "test-market",
    outcome: Outcome = "UP",
    side: Side = "BUY",
    size: float = 10.0,
    limit_price: float = 0.5,
    target_price: float = 0.6,
    reason: str = "Test intent",
    strategy_id: str = "simple_threshold",
    correlation_id: str | None = None,
    ttl_s: float = 60.0,
) -> OrderIntentEvent:
    """Create a test OrderIntentEvent with deterministic defaults.

    Args:
        market_slug: Market identifier
        outcome: Market outcome
        side: Trade side
        size: Order size in USD (default: 10.0)
        limit_price: Limit price (default: 0.5)
        target_price: Target price (default: 0.6)
        reason: Reason for intent
        strategy_id: Strategy identifier (default: "simple_threshold")
        correlation_id: Correlation ID (optional)
        ttl_s: Time-to-live in seconds

    Returns:
        OrderIntentEvent with specified parameters
    """
    # Only pass correlation_id if explicitly provided (not None)
    # Otherwise let Event base class generate it via default_factory
    kwargs: dict[str, object] = {
        "market_slug": market_slug,
        "outcome": outcome,
        "side": side,
        "size": size,
        "limit_price": limit_price,
        "target_price": target_price,
        "reason": reason,
        "strategy_id": strategy_id,
        "ttl_s": ttl_s,
    }
    if correlation_id is not None:
        kwargs["correlation_id"] = correlation_id

    return OrderIntentEvent(**kwargs)


def create_signal_event(
    market_slug: str = "test-market",
    outcome: Outcome = "UP",
    p_up: float = 0.7,
    p_down: float = 0.3,
    edge: float = 0.2,
    confidence: float = 0.8,
    model_id: str = "simple_threshold",
    model_version: str = "1.0.0",
    rationale: str = "Test signal",
    correlation_id: str | None = None,
) -> SignalEvent:
    """Create a test SignalEvent with deterministic defaults.

    Args:
        market_slug: Market identifier
        outcome: Market outcome
        p_up: Probability UP wins
        p_down: Probability DOWN wins
        edge: Edge score
        confidence: Confidence level
        model_id: Strategy/model identifier (default: "simple_threshold")
        model_version: Model version
        rationale: Signal rationale
        correlation_id: Correlation ID (optional)

    Returns:
        SignalEvent with specified parameters
    """
    # Only pass correlation_id if explicitly provided (not None)
    # Otherwise let Event base class generate it via default_factory
    kwargs: dict[str, object] = {
        "market_slug": market_slug,
        "outcome": outcome,
        "p_up": p_up,
        "p_down": p_down,
        "edge": edge,
        "confidence": confidence,
        "model_id": model_id,
        "model_version": model_version,
        "rationale": rationale,
    }
    if correlation_id is not None:
        kwargs["correlation_id"] = correlation_id

    return SignalEvent(**kwargs)


def create_market_data_event(
    market_slug: str = "test-market",
    outcome: Outcome = "UP",
    best_bid: float = 0.45,
    best_ask: float = 0.55,
    correlation_id: str | None = None,
) -> MarketDataEvent:
    """Create a test MarketDataEvent with deterministic defaults.

    Args:
        market_slug: Market identifier
        outcome: Market outcome
        best_bid: Best bid price (default: 0.45)
        best_ask: Best ask price (default: 0.55)
        correlation_id: Correlation ID (optional)

    Returns:
        MarketDataEvent with specified parameters
    """
    # Only pass correlation_id if explicitly provided (not None)
    # Otherwise let Event base class generate it via default_factory
    kwargs: dict[str, object] = {
        "market_slug": market_slug,
        "outcome": outcome,
        "best_bid": best_bid,
        "best_ask": best_ask,
    }
    if correlation_id is not None:
        kwargs["correlation_id"] = correlation_id

    return MarketDataEvent(**kwargs)


def create_fill_event(
    order_id: str | None = None,
    fill_id: str | None = None,
    size: float = 10.0,
    price: float = 0.5,
    fee: float = 0.0,
    venue_fill_id: str | None = None,
    correlation_id: str | None = None,
    ts_mono: float | None = None,
) -> FillEvent:
    """Create a test FillEvent with deterministic defaults.

    Args:
        order_id: Order ID (defaults to generated UUID)
        fill_id: Fill ID (defaults to generated UUID)
        size: Fill size in USD (default: 10.0)
        price: Fill price (default: 0.5)
        fee: Fee amount (default: 0.0)
        venue_fill_id: Venue fill ID (optional)
        correlation_id: Correlation ID (optional)
        ts_mono: Monotonic timestamp (defaults to current time)

    Returns:
        FillEvent with specified parameters
    """
    kwargs: dict[str, object] = {
        "order_id": order_id or str(uuid.uuid4()),
        "fill_id": fill_id or str(uuid.uuid4()),
        "size": size,
        "price": price,
        "fee": fee,
    }
    if venue_fill_id is not None:
        kwargs["venue_fill_id"] = venue_fill_id
    if correlation_id is not None:
        kwargs["correlation_id"] = correlation_id
    if ts_mono is not None:
        kwargs["ts_mono"] = ts_mono

    return FillEvent(**kwargs)
