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
