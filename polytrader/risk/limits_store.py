"""Risk limits store per architecture.mdc §1.C.

This module provides a centralized interface for loading and managing
risk limits configuration. It ensures limits are validated and versioned
per trading.mdc §7.
"""

from polytrader.risk.models import RiskLimits


def get_default_limits() -> RiskLimits:
    """Get default risk limits.

    These are conservative defaults suitable for production.
    They can be overridden via configuration.

    Per trading.mdc §7: Limits must be validated and versioned.

    Returns:
        Default RiskLimits instance with conservative values
    """
    return RiskLimits(
        version="1.0",
        max_position_per_market=1.0,
        max_position_global=10.0,
        max_notional_exposure=100.0,
        max_order_size=10.0,
        max_trades_per_market=1,
        order_rate_limit_per_minute=60,
        cancel_rate_limit_per_minute=120,
        max_data_staleness_seconds=5.0,
        price_deviation_threshold=0.1,
    )


def load_limits_from_config(config: dict) -> RiskLimits:
    """Load risk limits from configuration dictionary per architecture.mdc §1.C.

    Validates the configuration and returns a RiskLimits instance.
    Raises ValueError if configuration is invalid.

    Per trading.mdc §7: Limits and strategy params must be validated and versioned.

    Args:
        config: Configuration dictionary with risk limits.
            Can be partial - missing fields will use defaults from RiskLimits model.
            Must include 'version' for auditability (defaults to "1.0" if missing).

    Returns:
        RiskLimits instance with validated configuration

    Raises:
        ValueError: If configuration is invalid (e.g., negative values, out of range)

    Example:
        >>> config = {
        ...     "version": "2.0",
        ...     "max_order_size": 20.0,
        ...     "max_position_per_market": 5.0,
        ... }
        >>> limits = load_limits_from_config(config)
        >>> assert limits.version == "2.0"
        >>> assert limits.max_order_size == 20.0
    """
    try:
        # Ensure version is present (for auditability)
        if "version" not in config:
            config = {**config, "version": "1.0"}

        # Pydantic will validate all fields
        return RiskLimits(**config)
    except Exception as e:
        raise ValueError(f"Invalid risk limits configuration: {e}") from e
