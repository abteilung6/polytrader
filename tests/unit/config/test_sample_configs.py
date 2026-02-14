"""Tests for sample YAML config files.

Per Commit 4 of PLATFORM_CONFIGURATION_PROPOSAL.md:
- Both YAML files are valid and load without errors
- platform.yaml.example documents every configurable field
- platform.paper.yaml contains safe defaults suitable for paper trading

Per Pilot Live PILOT_LIVE.md Commit 1:
- platform.live-pilot.yaml loads and validates correctly
- Risk limits are ultra-conservative for infrastructure validation
- Tighter than paper on key dimensions (order size, rate limits, slippage)
"""

from pathlib import Path

import pytest

from polytrader.config.loader import load_platform_config

# Resolve paths relative to the repo root
REPO_ROOT = Path(__file__).parent.parent.parent.parent
PAPER_CONFIG = REPO_ROOT / "config" / "platform.paper.yaml"
EXAMPLE_CONFIG = REPO_ROOT / "config" / "platform.yaml.example"
LIVE_PILOT_CONFIG = REPO_ROOT / "config" / "platform.live-pilot.yaml"


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


class TestLivePilotConfigFile:
    """Live pilot config file: infrastructure validation profile.

    Per PILOT_LIVE.md Commit 1:
    - Config loads and validates correctly
    - Risk limits are ultra-conservative for first real trade
    - Tighter than paper on key dimensions
    - execution_enabled defaults to false (verified via default, not config)
    """

    @pytest.mark.asyncio
    async def test_live_pilot_config_loads_successfully(self) -> None:
        """platform.live-pilot.yaml loads without errors."""
        config = await load_platform_config(LIVE_PILOT_CONFIG)
        assert config.version == "1.0"

    @pytest.mark.asyncio
    async def test_live_pilot_risk_limits_ultra_conservative(self) -> None:
        """Risk limits are ultra-conservative for infrastructure validation.

        These exact values are the contract for Phase L1.
        """
        config = await load_platform_config(LIVE_PILOT_CONFIG)

        # Position limits — trivial sizes
        assert config.risk.max_position_per_market == 1.0, "Max $1 per market"
        assert config.risk.max_position_global == 5.0, "Max $5 total exposure"
        assert config.risk.max_notional_exposure == 10.0, "Max $10 notional"
        assert config.risk.max_order_size == 1.0, "Max $1 per order"
        assert config.risk.max_trades_per_market == 1, "1 trade per market"

        # Rate limits — very conservative
        assert config.risk.order_rate_limit_per_minute == 10, "10 orders/min max"
        assert config.risk.cancel_rate_limit_per_minute == 20, "20 cancels/min max"

        # Price safety
        assert config.risk.max_data_staleness_seconds == 5.0
        assert config.risk.price_deviation_threshold == 0.05, "5% max deviation"

    @pytest.mark.asyncio
    async def test_live_pilot_tighter_than_paper(self) -> None:
        """Live pilot has tighter limits than paper on key dimensions.

        This is a safety invariant: live pilot must be at least as
        conservative as paper on every risk dimension.
        """
        paper = await load_platform_config(PAPER_CONFIG)
        live = await load_platform_config(LIVE_PILOT_CONFIG)

        # Order size: live <= paper
        assert live.risk.max_order_size <= paper.risk.max_order_size

        # Global exposure: live <= paper
        assert live.risk.max_position_global <= paper.risk.max_position_global

        # Rate limits: live <= paper
        assert live.risk.order_rate_limit_per_minute <= paper.risk.order_rate_limit_per_minute

        # Price deviation: live <= paper (tighter band)
        assert live.risk.price_deviation_threshold <= paper.risk.price_deviation_threshold

        # Slippage: live <= paper (tighter execution)
        assert (
            live.execution.tactics.max_buy_slippage_bps
            <= paper.execution.tactics.max_buy_slippage_bps
        )
        assert (
            live.execution.tactics.max_sell_slippage_bps
            <= paper.execution.tactics.max_sell_slippage_bps
        )

        # Reconciliation: live more frequent (lower interval)
        assert live.reconciliation.interval_s <= paper.reconciliation.interval_s

    @pytest.mark.asyncio
    async def test_live_pilot_health_gates_strict(self) -> None:
        """Health gates are strict — same as paper (all active)."""
        config = await load_platform_config(LIVE_PILOT_CONFIG)

        assert config.health_gates.require_user_stream is True
        assert config.health_gates.max_reconciliation_divergences == 0
        assert config.health_gates.max_error_rate == 0.10

    @pytest.mark.asyncio
    async def test_live_pilot_circuit_breakers_strict(self) -> None:
        """Circuit breakers are strict — same as paper."""
        config = await load_platform_config(LIVE_PILOT_CONFIG)

        assert config.circuit_breakers.max_fill_mismatches == 1
        assert config.circuit_breakers.max_phantom_orders == 3
        assert config.circuit_breakers.max_orphan_orders == 3
        assert config.circuit_breakers.require_error_severity is True

    @pytest.mark.asyncio
    async def test_live_pilot_execution_tactics(self) -> None:
        """Execution tactics are tighter for live pilot."""
        config = await load_platform_config(LIVE_PILOT_CONFIG)

        # Tighter slippage bands
        assert config.execution.tactics.max_buy_slippage_bps == 30.0
        assert config.execution.tactics.max_sell_slippage_bps == 30.0
        assert config.execution.tactics.prefer_passive is True

    @pytest.mark.asyncio
    async def test_live_pilot_portfolio_minimal(self) -> None:
        """Portfolio uses minimal capital for pilot."""
        config = await load_platform_config(LIVE_PILOT_CONFIG)

        assert config.portfolio.fixed_size_usd == 1.0
        assert config.portfolio.starting_equity == 50.0

    @pytest.mark.asyncio
    async def test_live_pilot_reconciliation_frequent(self) -> None:
        """Reconciliation runs more frequently than paper."""
        config = await load_platform_config(LIVE_PILOT_CONFIG)

        assert config.reconciliation.interval_s == 30.0
        assert config.reconciliation.position_sync_interval_s == 30.0

    @pytest.mark.asyncio
    async def test_live_pilot_risk_limits_to_risk_model(self) -> None:
        """RiskConfig.to_risk_limits() produces correct RiskLimits model."""
        config = await load_platform_config(LIVE_PILOT_CONFIG)
        risk_limits = config.risk.to_risk_limits(version="pilot-1.0")

        assert risk_limits.version == "pilot-1.0"
        assert risk_limits.max_position_per_market == 1.0
        assert risk_limits.max_position_global == 5.0
        assert risk_limits.max_order_size == 1.0
        assert risk_limits.max_trades_per_market == 1
        assert risk_limits.order_rate_limit_per_minute == 10
        assert risk_limits.price_deviation_threshold == 0.05
