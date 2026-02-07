"""Configuration module: Polymarket secrets, database config, and general config loading.

This module contains:
- Polymarket-specific configuration (secrets, API URLs)
- Database configuration (PostgreSQL connection settings)
- General config loading and validation (Phase 7)

Configuration is separated into:
- Secrets: Sensitive values (private keys, passwords) using SecretStr
- Config: Non-sensitive settings (hosts, ports, database names)
"""

import hashlib
import json
import warnings
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from polytrader.events import SYSTEM_LIFECYCLE
from polytrader.events.bus import EventBus
from polytrader.events.types import ConfigLoadedEvent

# DEPRECATED: Use PlatformConfig().venue.clob_api_url instead.
# These constants are kept for backward compatibility and will be removed
# in a future version. New code should use PlatformConfig.
CLOB_API_URL = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet


class PolymarketSecrets(BaseSettings):
    """Polymarket-specific secrets (wallet authentication).

    These are sensitive values that should be kept secret.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Wallet Authentication
    private_key: SecretStr = Field(
        ...,
        description="Private key for wallet authentication",
        alias="PRIVATE_KEY",
    )

    funder: str | None = Field(
        default=None,
        description="Funder address (proxy/smart wallet address) - required for Magic wallets",
        alias="FUNDER",
    )

    signature_type: int = Field(
        default=1,
        description="Signature type: 0=EOA/MetaMask, 1=Magic wallet, 2=Browser wallet proxy",
        alias="SIGNATURE_TYPE",
    )


class DatabaseConfig(BaseSettings):
    """Database configuration (PostgreSQL).

    Separates non-sensitive configuration from secrets (password).
    Per architecture: PostgreSQL is mandatory for event persistence.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database connection settings (non-sensitive)
    db_host: str = Field(
        default="localhost",
        description="PostgreSQL host",
        alias="DB_HOST",
    )

    db_port: int = Field(
        default=5432,
        description="PostgreSQL port",
        alias="DB_PORT",
    )

    db_database: str = Field(
        ...,
        description="PostgreSQL database name",
        alias="DB_DATABASE",
    )

    db_user: str = Field(
        ...,
        description="PostgreSQL user",
        alias="DB_USER",
    )

    # Database secret (sensitive)
    db_password: SecretStr = Field(
        ...,
        description="PostgreSQL password",
        alias="DB_PASSWORD",
    )


class MetricsConfig(BaseSettings):
    """Metrics configuration (Prometheus metrics backend and server).

    Per Commit 3 & 4: Configuration for metrics backend selection and
    dedicated metrics server port. Defaults to Prometheus backend on port 9100.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    metrics_backend: str = Field(
        default="prometheus",
        description="Metrics backend: 'prometheus' or 'memory' (default: prometheus)",
        alias="METRICS_BACKEND",
    )

    metrics_port: int = Field(
        default=9100,
        description="Metrics server port (default: 9100, separate from control API :8000)",
        alias="METRICS_PORT",
    )


def get_database_url(config: DatabaseConfig | None = None) -> str:
    """Get PostgreSQL connection URL from configuration.

    Args:
        config: DatabaseConfig instance. If None, loads from environment.

    Returns:
        PostgreSQL connection URL in format: postgresql://user:password@host:port/database

    Raises:
        ValueError: If required configuration is missing

    Example:
        >>> config = DatabaseConfig()
        >>> url = get_database_url(config)
        >>> assert url.startswith("postgresql://")
    """
    if config is None:
        config = DatabaseConfig()

    # Get password (SecretStr -> str)
    password = config.db_password.get_secret_value()

    # Build connection URL
    return f"postgresql://{config.db_user}:{password}@{config.db_host}:{config.db_port}/{config.db_database}"


# General config loading functions (Phase 7)


def calculate_config_hash(config: dict[str, Any]) -> str:
    """Calculate SHA256 hash of configuration.

    Per Phase 7: Config hash is used for audit trail and verification.

    Args:
        config: Configuration dictionary

    Returns:
        SHA256 hash as hexadecimal string
    """
    # Serialize config to JSON (sorted keys for deterministic hashing)
    config_json = json.dumps(config, sort_keys=True, separators=(",", ":"))
    config_bytes = config_json.encode("utf-8")
    return hashlib.sha256(config_bytes).hexdigest()


def validate_config(config: dict[str, Any]) -> None:
    """Validate configuration structure.

    Per Phase 7: Config must be validated before use.

    Args:
        config: Configuration dictionary to validate

    Raises:
        ValueError: If configuration is invalid

    Note:
        This is a basic validation. More specific validation can be added
        for different config sections (risk_limits, health_gates, etc.).
    """
    if not isinstance(config, dict):
        raise ValueError(f"Config must be a dictionary, got {type(config)}")

    # Config should have a version field (optional but recommended)
    if "version" in config:
        if not isinstance(config["version"], str):
            raise ValueError("Config version must be a string")


async def load_config(
    config_path: str | Path | None = None,
    bus: EventBus | None = None,
) -> dict[str, Any]:
    """Load and validate configuration (DEPRECATED).

    .. deprecated::
        Use ``load_platform_config()`` from ``polytrader.config.loader`` instead.
        This function loads untyped JSON dicts. The new loader validates YAML
        into a typed PlatformConfig model with Pydantic constraints.

    Per Phase 7: Load config from file or environment, validate, calculate hash,
    and emit ConfigLoadedEvent.

    Args:
        config_path: Path to config file (JSON). If None, loads from environment.
        bus: Event bus for emitting ConfigLoadedEvent (optional)

    Returns:
        Configuration dictionary

    Raises:
        FileNotFoundError: If config_path is provided but file doesn't exist
        ValueError: If configuration is invalid
        json.JSONDecodeError: If config file is not valid JSON
    """
    warnings.warn(
        "load_config() is deprecated. Use load_platform_config() from "
        "polytrader.config.loader instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    # Load config from file or environment
    if config_path is not None:
        config_path_obj = Path(config_path)
        if not config_path_obj.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        # Load JSON file
        with open(config_path_obj, encoding="utf-8") as f:
            config: dict[str, Any] = json.load(f)
    else:
        # Load from environment (for now, return empty dict - can be enhanced)
        # In practice, this could load from environment variables or use pydantic-settings
        config = {}

    # Validate config
    validate_config(config)

    # Calculate config hash
    config_hash = calculate_config_hash(config)

    # Get config version (default to "1.0" if not present)
    config_version = config.get("version", "1.0")

    # Emit ConfigLoadedEvent
    if bus is not None:
        event = ConfigLoadedEvent(
            config_hash=config_hash,
            config_version=config_version if config_version != "1.0" else None,
        )
        await bus.publish(SYSTEM_LIFECYCLE, event)

    return config
