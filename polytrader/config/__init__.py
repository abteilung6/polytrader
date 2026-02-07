"""Platform configuration package.

Re-exports all symbols from the legacy config module for backward compatibility,
plus new PlatformConfig model hierarchy.

Usage (new):
    from polytrader.config import PlatformConfig
    config = PlatformConfig()

Usage (existing — unchanged):
    from polytrader.config import PolymarketSecrets, get_database_url, MetricsConfig
"""

# Re-export everything from legacy module for backward compatibility.
# All existing imports like `from polytrader.config import PolymarketSecrets` continue to work.
from polytrader.config.legacy import (  # noqa: F401
    CHAIN_ID,
    CLOB_API_URL,
    DatabaseConfig,
    MetricsConfig,
    PolymarketSecrets,
    calculate_config_hash,
    get_database_url,
    load_config,
    validate_config,
)

# New platform config models
from polytrader.config.models import PlatformConfig  # noqa: F401

__all__ = [
    # Legacy exports (backward compat)
    "CHAIN_ID",
    "CLOB_API_URL",
    "DatabaseConfig",
    "MetricsConfig",
    "PolymarketSecrets",
    "calculate_config_hash",
    "get_database_url",
    "load_config",
    "validate_config",
    # New exports
    "PlatformConfig",
]
