"""Reproducibility metadata models for strategy instances.

Per feedback: Every decision must be reproducible given inputs + code ref.
This metadata enables deterministic replay.

This module provides RunIdentity model and utilities for capturing all
information needed to reproduce a trading decision.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RunIdentity:
    """Reproducibility metadata for strategy instance execution.

    Per proposal: Every decision must be reproducible given inputs + code ref.
    This model captures all necessary information to deterministically replay
    a trading decision.

    Attributes:
        template_code_ref: Git SHA / build artifact digest of template code
        config_hash: SHA256 hash of config (for reproducibility)
        dependency_set: Versions of key libs / model artifacts (JSONB-compatible dict)
        market_data_snapshot_ref: Market data stream ID / snapshot reference
    """

    template_code_ref: str
    config_hash: str
    dependency_set: dict[str, str]
    market_data_snapshot_ref: str | None

    def __post_init__(self) -> None:
        """Validate RunIdentity itself."""
        if not self.template_code_ref:
            raise ValueError("template_code_ref cannot be empty")

        if not self.config_hash:
            raise ValueError("config_hash cannot be empty")

        # Validate config_hash is SHA256 (64 hex characters)
        if len(self.config_hash) != 64:
            raise ValueError(
                f"config_hash must be SHA256 (64 hex chars), got {len(self.config_hash)}"
            )

        # Validate dependency_set is a dict with string keys and values
        if not isinstance(self.dependency_set, dict):
            raise ValueError("dependency_set must be a dictionary")

        for key, value in self.dependency_set.items():
            if not isinstance(key, str):
                raise ValueError("dependency_set keys must be strings")
            if not isinstance(value, str):
                raise ValueError("dependency_set values must be strings")


def calculate_config_hash(config: dict[str, Any]) -> str:
    """Calculate SHA256 hash of configuration.

    Per proposal: Config hash is used for reproducibility and audit trail.
    Hash is deterministic (same config = same hash).

    Args:
        config: Configuration dictionary

    Returns:
        SHA256 hash as hexadecimal string (64 characters)

    Note:
        This is a pure function (no side effects, deterministic).
        Uses sorted keys for deterministic hashing regardless of dict order.
    """
    # Serialize config to JSON (sorted keys for deterministic hashing)
    config_json = json.dumps(config, sort_keys=True, separators=(",", ":"))
    config_bytes = config_json.encode("utf-8")
    return hashlib.sha256(config_bytes).hexdigest()


def collect_dependency_set(package_names: list[str] | None = None) -> dict[str, str]:
    """Collect versions of key dependencies.

    Per proposal: Dependency set captures versions of key libs / model artifacts.
    This enables reproducibility by ensuring same dependency versions are used.

    Args:
        package_names: List of package names to collect versions for.
            If None, collects versions for common trading system packages.

    Returns:
        Dictionary mapping package name to version string

    Note:
        This function reads from installed packages (importlib.metadata).
        It is deterministic for a given environment but may vary across environments.
    """
    if package_names is None:
        # Default: collect versions for common trading system packages
        package_names = [
            "polytrader",
            "numpy",
            "pandas",
            "pydantic",
            "sqlalchemy",
            "fastapi",
        ]

    dependency_set: dict[str, str] = {}

    for package_name in package_names:
        try:
            # Get package version from installed metadata
            version = importlib.metadata.version(package_name)
            dependency_set[package_name] = version
        except importlib.metadata.PackageNotFoundError:
            # Package not installed - skip it
            pass

    return dependency_set


def create_run_identity(
    template_code_ref: str,
    config: dict[str, Any],
    market_data_snapshot_ref: str | None = None,
    dependency_packages: list[str] | None = None,
) -> RunIdentity:
    """Create RunIdentity from template code ref and config.

    Convenience function to create RunIdentity with automatic config hash
    and dependency set collection.

    Args:
        template_code_ref: Git SHA / build artifact digest of template code
        config: Configuration dictionary
        market_data_snapshot_ref: Market data stream ID / snapshot reference
        dependency_packages: List of package names to collect versions for.
            If None, uses default packages.

    Returns:
        RunIdentity instance

    Note:
        This is a convenience function. Config hash and dependency set are
        calculated automatically.
    """
    config_hash = calculate_config_hash(config)
    dependency_set = collect_dependency_set(dependency_packages)

    return RunIdentity(
        template_code_ref=template_code_ref,
        config_hash=config_hash,
        dependency_set=dependency_set,
        market_data_snapshot_ref=market_data_snapshot_ref,
    )
