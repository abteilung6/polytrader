"""Risk layer for pre-trade risk checks.

This module provides a hard gate before order creation, ensuring all orders
pass mandatory risk checks before reaching the OMS.

Per flows.mdc §6: Risk is a hard veto gate that runs before OMS submission.
"""

from polytrader.risk.models import (
    RiskContext,
    RiskLimits,
    RiskReasonCode,
    RiskResult,
    _rebuild_risk_context_model,
)
from polytrader.risk.policies import (
    check_max_trades_per_market,
    check_position_limits,
    check_proposal_validity,
    check_token_ownership,
)

# Ensure RiskContext model is rebuilt with forward references resolved
# This is safe to call multiple times
_rebuild_risk_context_model()

__all__ = [
    "RiskContext",
    "RiskLimits",
    "RiskReasonCode",
    "RiskResult",
    "check_max_trades_per_market",
    "check_position_limits",
    "check_proposal_validity",
    "check_token_ownership",
]
