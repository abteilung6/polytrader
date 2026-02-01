"""Volatility-Filtered Mean Reversion strategy per VFMR roadmap.

Commit 5: Schema and validation only; strategy logic in later commits.
"""

from polytrader.strategies.volatility_filtered_mean_reversion.schema import (
    VFMR_SCHEMA,
)

__all__ = ["VFMR_SCHEMA"]
