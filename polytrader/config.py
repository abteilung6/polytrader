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
