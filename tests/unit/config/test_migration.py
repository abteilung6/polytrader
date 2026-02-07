"""Tests for backward compatibility and migration from legacy config.

Per Commit 7 of PLATFORM_CONFIGURATION_PROPOSAL.md:
- Legacy imports (CLOB_API_URL, CHAIN_ID, etc.) still work
- load_config() emits deprecation warning
- Legacy constants match PlatformConfig.venue defaults
- Existing test_config_loading.py tests still pass (backward compat)
"""

import warnings

import pytest

from polytrader.config.models import PlatformConfig


class TestLegacyImportsStillWork:
    """All existing imports from polytrader.config continue to work."""

    def test_clob_api_url_importable(self) -> None:
        """CLOB_API_URL importable from polytrader.config."""
        from polytrader.config import CLOB_API_URL

        assert CLOB_API_URL == "https://clob.polymarket.com"

    def test_chain_id_importable(self) -> None:
        """CHAIN_ID importable from polytrader.config."""
        from polytrader.config import CHAIN_ID

        assert CHAIN_ID == 137

    def test_polymarket_secrets_importable(self) -> None:
        """PolymarketSecrets importable from polytrader.config."""
        from polytrader.config import PolymarketSecrets

        assert PolymarketSecrets is not None

    def test_database_config_importable(self) -> None:
        """DatabaseConfig importable from polytrader.config."""
        from polytrader.config import DatabaseConfig

        assert DatabaseConfig is not None

    def test_metrics_config_importable(self) -> None:
        """MetricsConfig importable from polytrader.config."""
        from polytrader.config import MetricsConfig

        assert MetricsConfig is not None

    def test_get_database_url_importable(self) -> None:
        """get_database_url importable from polytrader.config."""
        from polytrader.config import get_database_url

        assert callable(get_database_url)

    def test_calculate_config_hash_importable(self) -> None:
        """calculate_config_hash importable from polytrader.config."""
        from polytrader.config import calculate_config_hash

        assert callable(calculate_config_hash)

    def test_validate_config_importable(self) -> None:
        """validate_config importable from polytrader.config."""
        from polytrader.config import validate_config

        assert callable(validate_config)

    def test_load_config_importable(self) -> None:
        """load_config importable from polytrader.config."""
        from polytrader.config import load_config

        assert callable(load_config)

    def test_platform_config_importable(self) -> None:
        """PlatformConfig importable from polytrader.config."""
        from polytrader.config import PlatformConfig

        assert PlatformConfig is not None


class TestLegacyConstantsMatchConfig:
    """Legacy constants match PlatformConfig.venue defaults."""

    def test_clob_api_url_matches(self) -> None:
        """CLOB_API_URL constant matches PlatformConfig.venue.clob_api_url."""
        from polytrader.config import CLOB_API_URL

        config = PlatformConfig()
        assert CLOB_API_URL == config.venue.clob_api_url

    def test_chain_id_matches(self) -> None:
        """CHAIN_ID constant matches PlatformConfig.venue.chain_id."""
        from polytrader.config import CHAIN_ID

        config = PlatformConfig()
        assert CHAIN_ID == config.venue.chain_id


class TestLoadConfigDeprecation:
    """load_config() emits deprecation warning."""

    @pytest.mark.asyncio
    async def test_load_config_emits_deprecation_warning(self) -> None:
        """load_config() emits DeprecationWarning."""
        from polytrader.config import load_config

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await load_config()
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "load_platform_config" in str(w[0].message)

    @pytest.mark.asyncio
    async def test_load_config_still_works(self) -> None:
        """load_config() still returns a dict despite deprecation."""
        from polytrader.config import load_config

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = await load_config()
            assert isinstance(result, dict)


class TestNewConfigAvailable:
    """New config system is available alongside legacy."""

    def test_platform_config_from_config_package(self) -> None:
        """PlatformConfig importable from polytrader.config."""
        from polytrader.config import PlatformConfig

        config = PlatformConfig()
        assert config.version == "1.0"

    @pytest.mark.asyncio
    async def test_load_platform_config_from_config_package(self) -> None:
        """load_platform_config importable from polytrader.config."""
        from polytrader.config import load_platform_config

        config = await load_platform_config(None)
        assert isinstance(config, PlatformConfig)
