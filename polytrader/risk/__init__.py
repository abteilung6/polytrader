"""Risk layer for pre-trade risk checks.

This module provides a hard gate before order creation, ensuring all orders
pass mandatory risk checks before reaching the OMS.

Per flows.mdc §6: Risk is a hard veto gate that runs before OMS submission.
"""

from polytrader.risk.engine import RiskChecker, RiskEngine
from polytrader.risk.limits_store import get_default_limits, load_limits_from_config
from polytrader.risk.models import (
    RiskContext,
    RiskLimits,
    RiskReasonCode,
    RiskResult,
)
from polytrader.risk.policies import (
    check_data_freshness,
    check_max_trades_per_market,
    check_position_limits,
    check_price_sanity,
    check_proposal_validity,
    check_rate_limits,
    check_strategy_activation,
    check_system_health,
    check_token_ownership,
)

# Ensure RiskContext model is rebuilt with forward references resolved
# This is safe to call multiple times
# No rebuild needed - no circular dependency anymore

__all__ = [
    "RiskChecker",
    "RiskContext",
    "RiskEngine",
    "RiskLimits",
    "RiskReasonCode",
    "RiskResult",
    "check_data_freshness",
    "check_max_trades_per_market",
    "check_position_limits",
    "check_price_sanity",
    "check_proposal_validity",
    "check_rate_limits",
    "check_strategy_activation",
    "check_system_health",
    "check_token_ownership",
    "get_default_limits",
    "load_limits_from_config",
]
