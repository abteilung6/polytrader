"""Unit tests for platform config risk.paper / risk.live (split limits).

Per PROPOSAL_PAPER_LIVE_RISK_LIMITS Commit 3:
- Config without risk.paper/live loads unchanged (single risk).
- Config with both risk.paper and risk.live yields two distinct RiskLimits (risk_paper, risk_live).
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from polytrader.config.loader import load_platform_config
from polytrader.config.models import PlatformConfig


class TestLoadRiskConfigWithoutPaperLive:
    """Config without risk.paper / risk.live returns single risk, no split."""

    def test_load_risk_config_without_paper_live_returns_single_limits(self) -> None:
        """Plain risk block: risk_paper and risk_live are None; risk is the only limits."""
        data = {"risk": {"max_order_size": 5.0, "max_position_per_market": 2.0}}
        config = PlatformConfig.model_validate(data)

        assert config.risk.max_order_size == 5.0
        assert config.risk.max_position_per_market == 2.0
        assert config.risk_paper is None
        assert config.risk_live is None

    def test_default_config_has_no_split_limits(self) -> None:
        """Default PlatformConfig() has risk_paper and risk_live None."""
        config = PlatformConfig()
        assert config.risk_paper is None
        assert config.risk_live is None


class TestLoadRiskConfigWithPaperAndLive:
    """Config with risk.paper and risk.live yields two limits."""

    @pytest.mark.asyncio
    async def test_load_risk_config_with_paper_and_live_returns_two_limits(self) -> None:
        """YAML with risk.paper and risk.live: risk_paper and risk_live are set and distinct."""
        yaml_data = {
            "risk": {
                "paper": {
                    "max_order_size": 20.0,
                    "max_position_per_market": 100.0,
                    "order_rate_limit_per_minute": 120,
                },
                "live": {
                    "max_order_size": 5.0,
                    "max_position_per_market": 10.0,
                    "order_rate_limit_per_minute": 30,
                },
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_data, f)
            config_path = Path(f.name)

        try:
            config = await load_platform_config(config_path)

            assert config.risk_paper is not None
            assert config.risk_live is not None
            assert config.risk_paper.max_order_size == 20.0
            assert config.risk_paper.max_position_per_market == 100.0
            assert config.risk_paper.order_rate_limit_per_minute == 120
            assert config.risk_live.max_order_size == 5.0
            assert config.risk_live.max_position_per_market == 10.0
            assert config.risk_live.order_rate_limit_per_minute == 30
            # Main risk field uses paper when split (backward compat)
            assert config.risk.max_order_size == 20.0
        finally:
            config_path.unlink()
