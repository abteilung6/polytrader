"""Risk policies: pure functions for risk checks per flows.mdc §6.

Per testing.mdc §1.A: Risk policies must be pure, deterministic functions.
All time access must use injected Clock for testability.
"""

import time
from typing import Any, Protocol

from polytrader.risk.models import RiskContext, RiskLimits, RiskReasonCode, RiskResult


class Clock(Protocol):
    """Clock protocol for deterministic time access per testing.mdc §1.A.

    Tests must use injected Clock (no time() directly).
    """

    def monotonic(self) -> float:
        """Get monotonic time."""
        ...


def check_proposal_validity(
    context: RiskContext, limits: RiskLimits, clock: Clock | None = None
) -> RiskResult:
    """Check if proposal is valid (TTL, size) per flows.mdc §6.

    This is the most basic check - if the proposal itself is invalid,
    all other checks are skipped.

    Args:
        context: Risk context with the order intent
        limits: Risk limits configuration
        clock: Optional clock for deterministic time (for testing)

    Returns:
        RiskResult with allowed=False if invalid, or partial result for further checks
    """
    intent = context.intent
    reasons: list[RiskReasonCode] = []
    metadata: dict[str, Any] = {}

    # Use injected clock if provided (for testing), otherwise use time.monotonic()
    current_time = clock.monotonic() if clock else time.monotonic()
    age = current_time - intent.ts_mono

    if age > intent.ttl_s:
        reasons.append(RiskReasonCode.RISK_PROPOSAL_EXPIRED)
        metadata["proposal_age_seconds"] = age
        metadata["proposal_ttl_seconds"] = intent.ttl_s
        return RiskResult(
            allowed=False,
            reason_codes=reasons,
            metadata=metadata,
        )

    # Check size
    if intent.size <= 0:
        reasons.append(RiskReasonCode.RISK_INVALID_SIZE)
        metadata["proposal_size"] = intent.size
        return RiskResult(
            allowed=False,
            reason_codes=reasons,
            metadata=metadata,
        )

    # Check max order size (RISK_ORDER_TOO_LARGE per trading.mdc §4)
    if intent.size > limits.max_order_size:
        reasons.append(RiskReasonCode.RISK_ORDER_TOO_LARGE)
        metadata["proposal_size"] = intent.size
        metadata["max_order_size"] = limits.max_order_size
        metadata["limits_version"] = limits.version
        return RiskResult(
            allowed=False,
            reason_codes=reasons,
            metadata=metadata,
        )

    # Proposal is valid, continue with other checks
    return RiskResult(
        allowed=True,  # Partial result - other policies may deny
        reason_codes=[RiskReasonCode.RISK_ALLOWED],
        metadata=metadata,
    )


def check_token_ownership(context: RiskContext, limits: RiskLimits) -> RiskResult:
    """Check if we own tokens for SELL orders.

    Args:
        context: Risk context
        limits: Risk limits (unused, but kept for consistency)

    Returns:
        RiskResult with allowed=False if insufficient tokens
    """
    intent = context.intent
    reasons: list[RiskReasonCode] = []
    metadata: dict[str, Any] = {}

    if intent.side == "SELL":
        key = (intent.market_slug, intent.outcome)
        if key not in context.owned_tokens:
            reasons.append(RiskReasonCode.RISK_INSUFFICIENT_TOKENS)
            metadata["market_slug"] = intent.market_slug
            metadata["outcome"] = intent.outcome
            return RiskResult(
                allowed=False,
                reason_codes=reasons,
                metadata=metadata,
            )

    return RiskResult(
        allowed=True,
        reason_codes=[RiskReasonCode.RISK_ALLOWED],
        metadata=metadata,
    )


def check_price_sanity(context: RiskContext, limits: RiskLimits) -> RiskResult:
    """Check if order price is within acceptable bounds per trading.mdc §3.

    Validates that the limit price is not too far from the market mid price.
    This prevents orders with stale or incorrect prices.

    Per trading.mdc §3: Apply price bands:
    - if buy: limit_price <= mid * (1 + price_deviation_threshold)
    - if sell: limit_price >= mid * (1 - price_deviation_threshold)

    Args:
        context: Risk context with market data
        limits: Risk limits with price_deviation_threshold

    Returns:
        RiskResult with allowed=False if price is out of bounds
    """
    intent = context.intent
    reasons: list[RiskReasonCode] = []
    metadata: dict[str, Any] = {}

    # If no market data, we can't check price (but don't deny - data freshness check will handle)
    if context.market_data is None:
        return RiskResult(
            allowed=True,
            reason_codes=[RiskReasonCode.RISK_ALLOWED],
            metadata=metadata,
        )

    market_data = context.market_data
    mid_price = market_data.mid
    limit_price = intent.limit_price

    # Calculate deviation from mid
    deviation = abs(limit_price - mid_price)
    max_deviation = limits.price_deviation_threshold

    # Per trading.mdc §3: Apply price bands
    if intent.side == "BUY":
        max_price = mid_price * (1 + max_deviation)
        if limit_price > max_price:
            reasons.append(RiskReasonCode.RISK_PRICE_OUT_OF_BOUNDS)
            metadata["limit_price"] = limit_price
            metadata["mid_price"] = mid_price
            metadata["max_buy_price"] = max_price
            metadata["deviation"] = deviation
            metadata["max_deviation"] = max_deviation
            metadata["limits_version"] = limits.version
            return RiskResult(
                allowed=False,
                reason_codes=reasons,
                metadata=metadata,
            )
    else:  # SELL
        min_price = mid_price * (1 - max_deviation)
        if limit_price < min_price:
            reasons.append(RiskReasonCode.RISK_PRICE_OUT_OF_BOUNDS)
            metadata["limit_price"] = limit_price
            metadata["mid_price"] = mid_price
            metadata["min_sell_price"] = min_price
            metadata["deviation"] = deviation
            metadata["max_deviation"] = max_deviation
            metadata["limits_version"] = limits.version
            return RiskResult(
                allowed=False,
                reason_codes=reasons,
                metadata=metadata,
            )

    # Include key inputs per trading.mdc §4
    metadata["mid_price"] = mid_price
    metadata["qty"] = intent.size
    metadata["limits_version"] = limits.version

    return RiskResult(
        allowed=True,
        reason_codes=[RiskReasonCode.RISK_ALLOWED],
        metadata=metadata,
    )


def check_data_freshness(
    context: RiskContext, limits: RiskLimits, clock: Clock | None = None
) -> RiskResult:
    """Check if market data is fresh enough per flows.mdc §6.

    Rejects orders if market data is too stale. This prevents trading
    on outdated information.

    For Polymarket bitcoin trading: Missing or stale market data is a hard
    gate - we must not trade without current price information.

    Args:
        context: Risk context with market data
        limits: Risk limits with max_data_staleness_seconds
        clock: Optional clock for deterministic time (for testing)

    Returns:
        RiskResult with allowed=False if data is stale or missing
    """
    intent = context.intent
    reasons: list[RiskReasonCode] = []
    metadata: dict[str, Any] = {}

    # If no market data, deny (we need data to trade safely)
    # This is a hard gate for live trading
    if context.market_data is None:
        reasons.append(RiskReasonCode.RISK_DATA_STALE)
        metadata["market_slug"] = intent.market_slug
        metadata["reason"] = "No market data available"
        metadata["limits_version"] = limits.version
        return RiskResult(
            allowed=False,
            reason_codes=reasons,
            metadata=metadata,
        )

    market_data = context.market_data
    current_time = clock.monotonic() if clock else time.monotonic()
    data_age = current_time - market_data.ts_mono

    if data_age > limits.max_data_staleness_seconds:
        reasons.append(RiskReasonCode.RISK_DATA_STALE)
        metadata["data_age_seconds"] = data_age
        metadata["max_staleness_seconds"] = limits.max_data_staleness_seconds
        metadata["limits_version"] = limits.version
        return RiskResult(
            allowed=False,
            reason_codes=reasons,
            metadata=metadata,
        )

    return RiskResult(
        allowed=True,
        reason_codes=[RiskReasonCode.RISK_ALLOWED],
        metadata=metadata,
    )


def check_position_limits(context: RiskContext, limits: RiskLimits) -> RiskResult:
    """Check position limits (per-market and global) per flows.mdc §6.

    Args:
        context: Risk context with current positions
        limits: Risk limits configuration

    Returns:
        RiskResult with allowed=False if limits would be exceeded
    """
    intent = context.intent
    reasons: list[RiskReasonCode] = []
    metadata: dict[str, Any] = {}
    projections: dict[str, Any] = {}

    # Calculate new position after this order
    key = (intent.market_slug, intent.outcome)
    current_position = context.current_positions.get(key, 0.0)

    if intent.side == "BUY":
        new_position = current_position + intent.size
    else:  # SELL
        new_position = current_position - intent.size
        # Can't go negative (handled by token ownership check, but be safe)
        if new_position < 0:
            new_position = 0.0

    projections["current_position"] = current_position
    projections["new_position"] = new_position
    projections["position_delta"] = intent.size if intent.side == "BUY" else -intent.size

    # Check per-market limit (RISK_MAX_POSITION per trading.mdc §4)
    if abs(new_position) > limits.max_position_per_market:
        reasons.append(RiskReasonCode.RISK_MAX_POSITION)
        metadata["new_position"] = new_position
        metadata["max_position_per_market"] = limits.max_position_per_market
        metadata["limits_version"] = limits.version
        return RiskResult(
            allowed=False,
            reason_codes=reasons,
            projections=projections,
            metadata=metadata,
        )

    # Calculate new global position
    new_global_position = context.global_position
    if intent.side == "BUY":
        new_global_position += intent.size
    else:  # SELL
        new_global_position -= intent.size
        if new_global_position < 0:
            new_global_position = 0.0

    projections["current_global_position"] = context.global_position
    projections["new_global_position"] = new_global_position

    # Check global limit (RISK_MAX_POSITION per trading.mdc §4)
    if new_global_position > limits.max_position_global:
        reasons.append(RiskReasonCode.RISK_MAX_POSITION)
        metadata["new_global_position"] = new_global_position
        metadata["max_position_global"] = limits.max_position_global
        metadata["limits_version"] = limits.version
        return RiskResult(
            allowed=False,
            reason_codes=reasons,
            projections=projections,
            metadata=metadata,
        )

    # Check notional exposure (RISK_MAX_NOTIONAL per trading.mdc §4)
    if intent.side == "BUY":
        new_notional = new_global_position
        if new_notional > limits.max_notional_exposure:
            reasons.append(RiskReasonCode.RISK_MAX_NOTIONAL)
            metadata["new_notional_exposure"] = new_notional
            metadata["max_notional_exposure"] = limits.max_notional_exposure
            metadata["limits_version"] = limits.version
            return RiskResult(
                allowed=False,
                reason_codes=reasons,
                projections=projections,
                metadata=metadata,
            )

    # Include key inputs per trading.mdc §4 (mid, qty, projected position, limits version)
    if context.market_data:
        metadata["mid_price"] = context.market_data.mid
    metadata["qty"] = intent.size
    metadata["projected_position"] = new_position
    metadata["limits_version"] = limits.version

    return RiskResult(
        allowed=True,
        reason_codes=[RiskReasonCode.RISK_ALLOWED],
        projections=projections,
        metadata=metadata,
    )


def check_max_trades_per_market(context: RiskContext, limits: RiskLimits) -> RiskResult:
    """Check max trades per market/outcome (for BUY orders only).

    This is a simple check: if we've already traded or approved a trade for
    this market/outcome, deny additional BUY orders. SELL orders are allowed.

    Note: This uses executed_trades from RiskContext, which includes both
    executed trades and approved orders (to prevent race conditions).
    In Phase 3 (OMS), this will come from OMS state.

    Args:
        context: Risk context
        limits: Risk limits configuration

    Returns:
        RiskResult with allowed=False if max trades exceeded
    """
    intent = context.intent
    reasons: list[RiskReasonCode] = []
    metadata: dict[str, Any] = {}

    # Only check BUY orders
    if intent.side != "BUY":
        return RiskResult(
            allowed=True,
            reason_codes=[RiskReasonCode.RISK_ALLOWED],
            metadata=metadata,
        )

    # Check if we've already traded or approved a trade for this market/outcome
    # executed_trades includes both executed and approved trades to prevent
    # race condition where multiple orders pass risk checks before first executes
    key = (intent.market_slug, intent.outcome)

    if key in context.executed_trades:
        reasons.append(RiskReasonCode.RISK_MAX_POSITION)  # Reuse code
        metadata["market_slug"] = intent.market_slug
        metadata["outcome"] = intent.outcome
        metadata["max_trades_per_market"] = limits.max_trades_per_market
        metadata["limits_version"] = limits.version
        return RiskResult(
            allowed=False,
            reason_codes=reasons,
            metadata=metadata,
        )

    return RiskResult(
        allowed=True,
        reason_codes=[RiskReasonCode.RISK_ALLOWED],
        metadata=metadata,
    )


def check_system_health(context: RiskContext, limits: RiskLimits) -> RiskResult:
    """Check system health gates per flows.mdc §13.

    These are hard gates that prevent all trading if system is unhealthy.

    Args:
        context: Risk context with system state
        limits: Risk limits (unused, but kept for consistency)

    Returns:
        RiskResult with allowed=False if any health gate is active
    """
    reasons: list[RiskReasonCode] = []
    metadata: dict[str, Any] = {}

    if context.kill_switch_active:
        reasons.append(RiskReasonCode.RISK_KILL_SWITCH)
        metadata["kill_switch_active"] = True
        metadata["limits_version"] = limits.version
        return RiskResult(
            allowed=False,
            reason_codes=reasons,
            metadata=metadata,
        )

    if context.circuit_breaker_active:
        reasons.append(RiskReasonCode.RISK_RECONCILE_DIVERGENCE)  # Reuse for circuit breaker
        metadata["circuit_breaker_active"] = True
        metadata["limits_version"] = limits.version
        return RiskResult(
            allowed=False,
            reason_codes=reasons,
            metadata=metadata,
        )

    if not context.reconciliation_healthy:
        reasons.append(RiskReasonCode.RISK_RECONCILE_DIVERGENCE)
        metadata["reconciliation_healthy"] = False
        metadata["limits_version"] = limits.version
        return RiskResult(
            allowed=False,
            reason_codes=reasons,
            metadata=metadata,
        )

    return RiskResult(
        allowed=True,
        reason_codes=[RiskReasonCode.RISK_ALLOWED],
        metadata=metadata,
    )


def check_rate_limits(context: RiskContext, limits: RiskLimits) -> RiskResult:
    """Check order and cancel rate limits per flows.mdc §6.

    Args:
        context: Risk context with rate limit state
        limits: Risk limits configuration

    Returns:
        RiskResult with allowed=False if rate limits exceeded
    """
    reasons: list[RiskReasonCode] = []
    metadata: dict[str, Any] = {}

    # Check order rate limit
    if context.order_count_last_minute >= limits.order_rate_limit_per_minute:
        reasons.append(RiskReasonCode.RISK_RATE_LIMIT)
        metadata["order_count_last_minute"] = context.order_count_last_minute
        metadata["order_rate_limit"] = limits.order_rate_limit_per_minute
        metadata["limits_version"] = limits.version
        return RiskResult(
            allowed=False,
            reason_codes=reasons,
            metadata=metadata,
        )

    # Note: Cancel rate limit is checked separately (not blocking order submission)
    # but included for completeness

    return RiskResult(
        allowed=True,
        reason_codes=[RiskReasonCode.RISK_ALLOWED],
        metadata=metadata,
    )
