"""Execution tactics: Apply execution policies.

Per flows.mdc §8: Execution applies deterministic tactics:
- Limit pricing rules
- Post-only preference
- Child split sizing (optional, Phase 2)
- Throttling
"""

from polytrader.execution.pricing import apply_limit_pricing
from polytrader.execution.throttle import ExecutionThrottle
from polytrader.types import OrderIntentEvent


class ExecutionTactics:
    """Execution tactics engine.

    Per flows.mdc §8: Applies deterministic execution policies.

    Attributes:
        throttle: Execution throttle instance
        max_buy_slippage_bps: Max buy slippage in basis points
        max_sell_slippage_bps: Max sell slippage in basis points
        prefer_passive: Whether to prefer passive (post-only) orders
    """

    def __init__(
        self,
        throttle: ExecutionThrottle | None = None,
        max_buy_slippage_bps: float = 50.0,
        max_sell_slippage_bps: float = 50.0,
        prefer_passive: bool = True,
    ) -> None:
        """Initialize execution tactics.

        Args:
            throttle: Execution throttle (defaults to new instance)
            max_buy_slippage_bps: Max buy slippage in basis points (default 50 = 0.5%)
            max_sell_slippage_bps: Max sell slippage in basis points (default 50 = 0.5%)
            prefer_passive: Whether to prefer passive orders (default True)
        """
        from polytrader.execution.throttle import ExecutionThrottle

        self.throttle = throttle or ExecutionThrottle()
        self.max_buy_slippage_bps = max_buy_slippage_bps
        self.max_sell_slippage_bps = max_sell_slippage_bps
        self.prefer_passive = prefer_passive

    def apply_tactics(
        self,
        intent: OrderIntentEvent,
        mid_price: float,
        client_order_id: str,
    ) -> OrderIntentEvent:
        """Apply execution tactics to order intent.

        Per flows.mdc §8: Applies pricing, post-only, throttling.

        Args:
            intent: Original order intent
            mid_price: Current mid price
            client_order_id: Idempotency key (for throttling)

        Returns:
            Modified intent with tactics applied

        Raises:
            ValueError: If throttled
        """
        # Check throttle
        if not self.throttle.check_order_throttle(client_order_id):
            raise ValueError(f"Order throttled: {client_order_id}")

        # Apply pricing rules
        adjusted_limit_price = apply_limit_pricing(
            intent,
            mid_price,
            self.max_buy_slippage_bps,
            self.max_sell_slippage_bps,
        )

        # Apply post-only preference (for now, just record in intent)
        # Future: Add post_only flag to OrderIntentEvent or create new field
        # TODO: Use when implementing post-only
        # use_post_only = should_use_post_only(intent, self.prefer_passive)

        # Create modified intent with adjusted price
        # Note: OrderIntentEvent is immutable, so we create a copy
        modified_intent = intent.model_copy(update={"limit_price": adjusted_limit_price})

        # Store post_only preference (we'll use this when calling adapter)
        # For now, we'll pass it through the adapter call
        # Future: Add post_only to OrderIntentEvent model
        return modified_intent
