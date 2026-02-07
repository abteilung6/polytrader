"""Secret and infrastructure configuration loaded from .env via pydantic-settings.

This module contains ONLY items that must come from environment variables:
- PolymarketSecrets: wallet private key, funder, signature type
- DatabaseConfig: PostgreSQL host/port/user/password/database
- MetricsConfig: metrics backend and port
- get_database_url(): builds a connection string from DatabaseConfig

All platform *policy* configuration (risk limits, health gates, execution
settings, etc.) now lives in PlatformConfig loaded from YAML.
See polytrader.config.models and polytrader.config.loader.
"""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    Reads METRICS_BACKEND and METRICS_PORT from .env.
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
    """
    if config is None:
        config = DatabaseConfig()

    # Get password (SecretStr -> str)
    password = config.db_password.get_secret_value()

    # Build connection URL
    return f"postgresql://{config.db_user}:{password}@{config.db_host}:{config.db_port}/{config.db_database}"
