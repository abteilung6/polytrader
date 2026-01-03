from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

CLOB_API_URL = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet


class PolymarketSecrets(BaseSettings):
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

    # API Credentials
    clob_api_key: str = Field(
        ...,
        description="CLOB API key",
        alias="CLOB_API_KEY",
    )
    clob_secret: SecretStr = Field(
        ...,
        description="CLOB API secret",
        alias="CLOB_SECRET",
    )
    clob_pass_phrase: SecretStr = Field(
        ...,
        description="CLOB API passphrase",
        alias="CLOB_PASS_PHRASE",
    )
