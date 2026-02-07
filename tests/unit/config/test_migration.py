"""Tests for config package public API after legacy cleanup.

Verifies that:
- Secret/infrastructure imports (PolymarketSecrets, DatabaseConfig, etc.) still work
- Legacy constants and functions are removed (no CLOB_API_URL, CHAIN_ID, load_config)
- PlatformConfig and load_platform_config are the canonical API
- Venue config values are accessible through PlatformConfig
"""

import pytest

from polytrader.config.models import PlatformConfig


class TestSecretImportsWork:
    """Secret and infrastructure imports from polytrader.config still work."""

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


class TestLegacyItemsRemoved:
    """Legacy constants and functions are no longer in the public API."""

    def test_no_clob_api_url(self) -> None:
        """CLOB_API_URL is no longer exported from polytrader.config."""
        import polytrader.config as cfg

        assert not hasattr(cfg, "CLOB_API_URL")

    def test_no_chain_id(self) -> None:
        """CHAIN_ID is no longer exported from polytrader.config."""
        import polytrader.config as cfg

        assert not hasattr(cfg, "CHAIN_ID")

    def test_no_load_config(self) -> None:
        """load_config is no longer exported from polytrader.config."""
        import polytrader.config as cfg

        assert not hasattr(cfg, "load_config")

    def test_no_validate_config(self) -> None:
        """validate_config is no longer exported from polytrader.config."""
        import polytrader.config as cfg

        assert not hasattr(cfg, "validate_config")

    def test_no_calculate_config_hash(self) -> None:
        """calculate_config_hash is no longer exported from polytrader.config."""
        import polytrader.config as cfg

        assert not hasattr(cfg, "calculate_config_hash")


class TestVenueConfigReplacement:
    """CLOB_API_URL and CHAIN_ID are now in PlatformConfig.venue."""

    def test_clob_api_url_in_venue_config(self) -> None:
        """CLOB API URL accessible via PlatformConfig.venue."""
        config = PlatformConfig()
        assert config.venue.clob_api_url == "https://clob.polymarket.com"

    def test_chain_id_in_venue_config(self) -> None:
        """Chain ID accessible via PlatformConfig.venue."""
        config = PlatformConfig()
        assert config.venue.chain_id == 137


class TestCanonicalConfigAPI:
    """PlatformConfig and load_platform_config are the canonical API."""

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
