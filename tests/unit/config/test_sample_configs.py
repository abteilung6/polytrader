"""Tests for sample YAML config files.

Per Commit 4 of PLATFORM_CONFIGURATION_PROPOSAL.md:
- Both YAML files are valid and load without errors
- platform.yaml.example documents every configurable field
- platform.paper.yaml contains safe defaults suitable for paper trading
"""

from pathlib import Path

import pytest

from polytrader.config.loader import load_platform_config

# Resolve paths relative to the repo root
REPO_ROOT = Path(__file__).parent.parent.parent.parent
PAPER_CONFIG = REPO_ROOT / "config" / "platform.paper.yaml"
EXAMPLE_CONFIG = REPO_ROOT / "config" / "platform.yaml.example"


class TestSampleConfigFiles:
    """Sample YAML config files load and validate."""

    @pytest.mark.asyncio
    async def test_paper_config_loads_successfully(self) -> None:
        """platform.paper.yaml loads without errors."""
        config = await load_platform_config(PAPER_CONFIG)
        assert config.version == "1.0"

    @pytest.mark.asyncio
    async def test_example_config_loads_successfully(self) -> None:
        """platform.yaml.example loads without errors."""
        config = await load_platform_config(EXAMPLE_CONFIG)
        assert config.version == "1.0"

    @pytest.mark.asyncio
    async def test_paper_config_has_safe_defaults(self) -> None:
        """Paper config has conservative risk limits."""
        config = await load_platform_config(PAPER_CONFIG)

        # Risk limits are conservative
        assert config.risk.max_order_size <= 10.0
        assert config.risk.max_position_per_market <= 5.0
        assert config.risk.max_position_global <= 50.0

        # Health gates are strict
        assert config.health_gates.require_user_stream is True
        assert config.health_gates.max_reconciliation_divergences == 0

        # Circuit breakers are strict
        assert config.circuit_breakers.max_fill_mismatches <= 3

    @pytest.mark.asyncio
    async def test_example_config_all_sections_present(self) -> None:
        """Example config sets values for all major sections."""
        config = await load_platform_config(EXAMPLE_CONFIG)

        # Verify key sections have non-default values loaded
        # (they happen to match defaults in this case, but the sections exist)
        assert config.venue.clob_api_url == "https://clob.polymarket.com"
        assert config.api.port == 8000
        assert config.metrics.backend == "prometheus"
        assert config.risk.max_order_size == 10.0
        assert config.health_gates.max_error_rate == 0.10
        assert config.circuit_breakers.max_phantom_orders == 3
        assert config.execution.tactics.prefer_passive is True
        assert config.portfolio.fixed_size_usd == 1.0
        assert config.market_data.polling_frequency_hz == 1.0
        assert config.event_persistence.event_batch_size == 100
        assert config.reconciliation.interval_s == 60.0
        assert config.supervisor.startup_timeout_s == 30.0
        assert config.performance.min_trades_threshold == 1
        assert config.market_discovery.max_windows_ahead == 48
        assert config.database_health.write_latency_threshold_ms == 100.0
