"""Risk models: reason codes, results, limits, and context.

Per trading.mdc §4: Risk checks must emit allowed/denied, reason codes,
and key inputs (mid, qty, projected position, limits version).
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from polytrader.events.types import MarketDataEvent, OrderIntentEvent
    from polytrader.types import Outcome
else:
    # Import at runtime for Pydantic model validation
    from polytrader.events.types import MarketDataEvent, OrderIntentEvent
    from polytrader.types import Outcome


class RiskReasonCode(str, Enum):
    """Standardized risk denial reason codes per trading.mdc §4.

    These codes are used in RiskCheckEvent to explain why an order
    was denied. They enable programmatic handling and metrics.

    Examples from trading.mdc §4:
    - RISK_MAX_POSITION
    - RISK_MAX_NOTIONAL
    - RISK_ORDER_TOO_LARGE
    - RISK_PRICE_OUT_OF_BOUNDS
    - RISK_DATA_STALE
    - RISK_RATE_LIMIT
    - RISK_KILL_SWITCH
    - RISK_RECONCILE_DIVERGENCE
    """

    # Proposal validity
    RISK_PROPOSAL_EXPIRED = "RISK_PROPOSAL_EXPIRED"
    RISK_INVALID_SIZE = "RISK_INVALID_SIZE"

    # Position limits (per trading.mdc §4)
    RISK_MAX_POSITION = "RISK_MAX_POSITION"  # Per-market or global
    RISK_MAX_NOTIONAL = "RISK_MAX_NOTIONAL"  # Max notional exposure

    # Order limits
    RISK_ORDER_TOO_LARGE = "RISK_ORDER_TOO_LARGE"  # Per trading.mdc §4
    RISK_INSUFFICIENT_TOKENS = "RISK_INSUFFICIENT_TOKENS"
    RISK_INSUFFICIENT_BALANCE = "RISK_INSUFFICIENT_BALANCE"

    # Price checks (per trading.mdc §4)
    RISK_PRICE_OUT_OF_BOUNDS = "RISK_PRICE_OUT_OF_BOUNDS"

    # Rate limits (per trading.mdc §4)
    RISK_RATE_LIMIT = "RISK_RATE_LIMIT"  # Order or cancel rate

    # System health (per trading.mdc §4)
    RISK_DATA_STALE = "RISK_DATA_STALE"
    RISK_KILL_SWITCH = "RISK_KILL_SWITCH"  # Per trading.mdc §4
    RISK_RECONCILE_DIVERGENCE = "RISK_RECONCILE_DIVERGENCE"  # Per trading.mdc §4

    # Strategy activation
    RISK_STRATEGY_NOT_ACTIVE = "RISK_STRATEGY_NOT_ACTIVE"  # Strategy not active for live trading

    # Allow reason (for allowed checks)
    RISK_ALLOWED = "RISK_ALLOWED"


class RiskResult(BaseModel):
    """Result of a risk check per flows.mdc §6 and trading.mdc §4.

    Risk checks must emit:
    - allowed/denied
    - reason codes
    - key inputs (mid, qty, projected position, limits version)

    Attributes:
        allowed: Whether the order is allowed (True) or denied (False)
        reason_codes: List of reason codes explaining the decision
        projections: Computed risk projections (e.g., new position, exposure)
        metadata: Additional context (e.g., current position, limit values,
            mid price, qty, limits version)
    """

    allowed: bool = Field(description="Whether the order is allowed")
    reason_codes: list[RiskReasonCode] = Field(
        default_factory=list,
        description="Reason codes explaining the decision",
    )
    projections: dict[str, Any] = Field(
        default_factory=dict,
        description="Computed risk projections (new position, exposure, etc.)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context (current state, limits, mid, qty, limits version)",
    )


class RiskLimits(BaseModel):
    """Risk limits configuration per architecture.mdc §1.C and trading.mdc §7.

    All limits are versioned and validated. This model represents
    the current risk limits for the system.

    Per trading.mdc §7: Limits and strategy params must be validated and versioned.

    Attributes:
        version: Version of the limits (for auditability, per trading.mdc §7)
        max_position_per_market: Maximum position size per market/outcome (USD)
        max_position_global: Maximum total position size across all markets (USD)
        max_notional_exposure: Maximum notional exposure (USD)
        max_order_size: Maximum size for a single order (USD)
        max_trades_per_market: Maximum number of trades per market/outcome
        order_rate_limit_per_minute: Maximum orders per minute
        cancel_rate_limit_per_minute: Maximum cancels per minute
        max_data_staleness_seconds: Maximum age of market data before rejecting (seconds)
        price_deviation_threshold: Maximum price deviation from mid (as fraction, e.g., 0.1 = 10%)
    """

    version: str = Field(default="1.0", description="Version of the limits (for auditability)")
    max_position_per_market: float = Field(
        default=1.0,
        gt=0,
        description="Maximum position size per market/outcome (USD)",
    )
    max_position_global: float = Field(
        default=10.0,
        gt=0,
        description="Maximum total position size across all markets (USD)",
    )
    max_notional_exposure: float = Field(
        default=100.0,
        gt=0,
        description="Maximum notional exposure (USD)",
    )
    max_order_size: float = Field(
        default=10.0,
        gt=0,
        description="Maximum size for a single order (USD)",
    )
    max_trades_per_market: int = Field(
        default=1,
        ge=0,
        description="Maximum number of trades per market/outcome",
    )
    order_rate_limit_per_minute: int = Field(
        default=60,
        ge=0,
        description="Maximum orders per minute",
    )
    cancel_rate_limit_per_minute: int = Field(
        default=120,
        ge=0,
        description="Maximum cancels per minute",
    )
    max_data_staleness_seconds: float = Field(
        default=5.0,
        gt=0,
        description="Maximum age of market data before rejecting (seconds)",
    )
    price_deviation_threshold: float = Field(
        default=0.1,
        gt=0,
        le=1.0,
        description="Maximum price deviation from mid (fraction, e.g., 0.1 = 10%)",
    )


class RiskContext(BaseModel):
    """Context for risk checks per flows.mdc §6.

    Input to risk gate per flows.mdc §6:
    - OrderIntent
    - current net position
    - open orders
    - mid price / bands
    - limits version
    - system health flags (data stale, kill switch)

    Attributes:
        intent: The order intent being checked
        current_positions: Dict mapping (market_slug, outcome) -> position size (USD)
        global_position: Total position size across all markets (USD)
        open_orders: Set of (market_slug, outcome) tuples for open orders (for Phase 3)
        market_data: Latest market data for the intent's market (mid price, bands)
        owned_tokens: Set of (market_slug, outcome) tuples for tokens we own
        kill_switch_active: Whether kill switch is active
        circuit_breaker_active: Whether circuit breaker is active
        reconciliation_healthy: Whether reconciliation is healthy
        order_count_last_minute: Number of orders in the last minute
        cancel_count_last_minute: Number of cancels in the last minute
        limits_version: Version of the risk limits being used
    """

    intent: OrderIntentEvent = Field(description="Order intent being checked")
    current_positions: dict[tuple[str, Outcome], float] = Field(
        default_factory=dict,
        description="Current positions: (market_slug, outcome) -> size (USD)",
    )
    global_position: float = Field(
        default=0.0,
        ge=0,
        description="Total position size across all markets (USD)",
    )
    open_orders: set[tuple[str, Outcome]] = Field(
        default_factory=set,
        description="Set of (market_slug, outcome) tuples for open orders",
    )
    executed_trades: set[tuple[str, str, Outcome]] = Field(
        default_factory=set,
        description=(
            "Set of (strategy_id, market_slug, outcome) tuples for executed trades "
            "(for max_trades_per_market check — scoped per strategy instance)"
        ),
    )
    market_data: MarketDataEvent | None = Field(
        default=None,
        description="Latest market data for the intent's market (mid price, bands)",
    )
    owned_tokens: set[tuple[str, Outcome]] = Field(
        default_factory=set,
        description="Set of (market_slug, outcome) tuples for tokens we own",
    )
    kill_switch_active: bool = Field(
        default=False,
        description="Whether kill switch is active",
    )
    circuit_breaker_active: bool = Field(
        default=False,
        description="Whether circuit breaker is active",
    )
    reconciliation_healthy: bool = Field(
        default=True,
        description="Whether reconciliation is healthy",
    )
    order_count_last_minute: int = Field(
        default=0,
        ge=0,
        description="Number of orders in the last minute",
    )
    cancel_count_last_minute: int = Field(
        default=0,
        ge=0,
        description="Number of cancels in the last minute",
    )
    limits_version: str = Field(
        default="1.0",
        description="Version of the risk limits being used",
    )
    active_strategies: set[str] = Field(
        default_factory=set,
        description="Set of active strategy IDs for live trading (empty set = paper mode)",
    )
    is_paper_mode: bool = Field(
        default=True,
        description="Whether system is in paper mode (True) or live mode (False)",
    )


# Rebuild models after imports to resolve forward references
# This is safe because events/types.py doesn't import from risk/models
RiskContext.model_rebuild()
