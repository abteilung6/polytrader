"""Risk engine: orchestrates all risk policies and aggregates results.

Per flows.mdc §6:
- Evaluate deterministic policies in fixed order
- Output RiskResult(allowed, reasons, projections)
- Emit RiskCheckEvent ALWAYS (in Commit 8)

Per architecture.mdc §1.C:
- risk/engine.py runs policies, aggregates result
"""

from typing import Any

from polytrader.risk.models import RiskContext, RiskLimits, RiskReasonCode, RiskResult
from polytrader.risk.policies import (
    Clock,
    check_data_freshness,
    check_max_trades_per_market,
    check_position_limits,
    check_price_sanity,
    check_proposal_validity,
    check_rate_limits,
    check_system_health,
    check_token_ownership,
)

# Type for risk policy functions
# Policies can have either (context, limits) -> RiskResult or
# (context, limits, clock) -> RiskResult. We handle the difference at runtime.
RiskPolicy = Any


class RiskEngine:
    """Risk engine that runs all risk policies and aggregates results.

    Per flows.mdc §6:
    - Evaluate deterministic policies in fixed order
    - Output RiskResult(allowed, reasons, projections)
    - Emit RiskCheckEvent ALWAYS (in Commit 8)

    Per architecture.mdc §1.C:
    - risk/engine.py runs policies, aggregates result

    Attributes:
        limits: Risk limits configuration
        clock: Optional clock for deterministic time (for testing)
        policies: List of policy functions to run (in fixed order per flows.mdc §6)
    """

    def __init__(self, limits: RiskLimits, clock: Clock | None = None) -> None:
        """Initialize risk engine.

        Args:
            limits: Risk limits configuration
            clock: Optional clock for deterministic time (for testing)
        """
        self.limits = limits
        self.clock = clock
        # Default policy set in fixed order per flows.mdc §6 (can be customized)
        self.policies: list[RiskPolicy] = [
            check_proposal_validity,  # First: basic validity
            check_system_health,  # Second: system health gates
            check_data_freshness,  # Third: data freshness
            check_token_ownership,  # Fourth: token ownership
            check_max_trades_per_market,  # Fifth: max trades
            check_position_limits,  # Sixth: position limits
            check_price_sanity,  # Seventh: price sanity
            check_rate_limits,  # Last: rate limits
        ]

    def check(self, context: RiskContext) -> RiskResult:
        """Run all risk policies in fixed order and aggregate results per flows.mdc §6.

        Policies are run in order. If any policy denies, the final result
        is denied. All policy results are aggregated (reason codes, projections, metadata).

        Args:
            context: Risk context with order intent and current state

        Returns:
            Aggregated RiskResult with final decision and all reason codes
        """
        all_reasons: list[RiskReasonCode] = []
        all_projections: dict[str, Any] = {}
        all_metadata: dict[str, Any] = {}
        allowed = True

        # Run all policies in fixed order per flows.mdc §6
        for policy in self.policies:
            # Pass clock to policies that need it
            if policy in (check_proposal_validity, check_data_freshness):
                result = policy(context, self.limits, self.clock)
            else:
                result = policy(context, self.limits)

            # Aggregate results
            all_reasons.extend(result.reason_codes)
            all_projections.update(result.projections)
            all_metadata.update(result.metadata)

            # If any policy denies, final result is denied
            if not result.allowed:
                allowed = False
                # Continue running policies for complete audit trail

        # Remove duplicate reason codes (keep order, first occurrence)
        unique_reasons = []
        seen = set()
        for reason in all_reasons:
            if reason not in seen:
                unique_reasons.append(reason)
                seen.add(reason)

        return RiskResult(
            allowed=allowed,
            reason_codes=unique_reasons,
            projections=all_projections,
            metadata=all_metadata,
        )
