"""Platform configuration package.

- models.py: PlatformConfig and all sub-config Pydantic models (policy)
- loader.py: YAML loading, validation, hashing, ConfigLoadedEvent emission
- legacy.py: Secret/infrastructure config from .env (PolymarketSecrets, DatabaseConfig, etc.)

Usage:
    from polytrader.config import PlatformConfig, load_platform_config
    from polytrader.config import PolymarketSecrets, get_database_url, MetricsConfig
"""

# Environment-based secret/infrastructure config (from .env)
from polytrader.config.legacy import (  # noqa: F401
    DatabaseConfig,
    MetricsConfig,
    PolymarketSecrets,
    get_database_url,
)

# Platform policy config (from YAML)
from polytrader.config.loader import load_platform_config  # noqa: F401
from polytrader.config.models import PlatformConfig  # noqa: F401

__all__ = [
    # Environment-based (.env)
    "DatabaseConfig",
    "MetricsConfig",
    "PolymarketSecrets",
    "get_database_url",
    # Platform policy (YAML)
    "PlatformConfig",
    "load_platform_config",
]
