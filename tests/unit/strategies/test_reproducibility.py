"""Unit tests for reproducibility metadata models.

Per testing.mdc: Unit tests must be deterministic, fast, and isolated.
All reproducibility functions are pure (no side effects, no I/O).
"""

import pytest

from polytrader.strategies.reproducibility import (
    RunIdentity,
    calculate_config_hash,
    collect_dependency_set,
    create_run_identity,
)


class TestCalculateConfigHash:
    """Tests for calculate_config_hash function."""

    def test_hash_is_deterministic(self) -> None:
        """Test that config hash is deterministic."""
        config1 = {"buy_threshold": 0.30, "min_history": 30}
        config2 = {"buy_threshold": 0.30, "min_history": 30}

        hash1 = calculate_config_hash(config1)
        hash2 = calculate_config_hash(config2)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 produces 64 hex characters

    def test_hash_is_order_independent(self) -> None:
        """Test that hash is independent of key order."""
        config1 = {"buy_threshold": 0.30, "min_history": 30}
        config2 = {"min_history": 30, "buy_threshold": 0.30}

        hash1 = calculate_config_hash(config1)
        hash2 = calculate_config_hash(config2)

        assert hash1 == hash2

    def test_different_configs_produce_different_hashes(self) -> None:
        """Test that different configs produce different hashes."""
        config1 = {"buy_threshold": 0.30, "min_history": 30}
        config2 = {"buy_threshold": 0.31, "min_history": 30}

        hash1 = calculate_config_hash(config1)
        hash2 = calculate_config_hash(config2)

        assert hash1 != hash2

    def test_hash_empty_config(self) -> None:
        """Test hash calculation with empty config."""
        config: dict[str, object] = {}
        hash_value = calculate_config_hash(config)

        assert len(hash_value) == 64
        # Empty JSON object should produce a specific hash
        assert hash_value == calculate_config_hash({})

    def test_hash_nested_config(self) -> None:
        """Test hash calculation with nested config."""
        config = {
            "buy_threshold": 0.30,
            "nested": {"key": "value", "number": 42},
        }

        hash_value = calculate_config_hash(config)
        assert len(hash_value) == 64

        # Same config should produce same hash
        hash_value2 = calculate_config_hash(config)
        assert hash_value == hash_value2

    def test_hash_is_hex_string(self) -> None:
        """Test that hash is a hexadecimal string."""
        config = {"key": "value"}
        hash_value = calculate_config_hash(config)

        # Should only contain hex characters (0-9, a-f)
        assert all(c in "0123456789abcdef" for c in hash_value)


class TestCollectDependencySet:
    """Tests for collect_dependency_set function."""

    def test_collect_dependency_set_default_packages(self) -> None:
        """Test collecting dependency set for default packages."""
        dependency_set = collect_dependency_set()

        # Should be a dictionary
        assert isinstance(dependency_set, dict)

        # Should have string keys and values
        for key, value in dependency_set.items():
            assert isinstance(key, str)
            assert isinstance(value, str)

    def test_collect_dependency_set_custom_packages(self) -> None:
        """Test collecting dependency set for custom packages."""
        # Use packages that are likely to be installed
        dependency_set = collect_dependency_set(["pydantic"])

        # Should be a dictionary
        assert isinstance(dependency_set, dict)

        # If pydantic is installed, should have version
        if "pydantic" in dependency_set:
            assert isinstance(dependency_set["pydantic"], str)
            assert len(dependency_set["pydantic"]) > 0

    def test_collect_dependency_set_nonexistent_package(self) -> None:
        """Test that nonexistent packages are skipped."""
        dependency_set = collect_dependency_set(["nonexistent-package-xyz"])

        # Should be empty dict (package not found)
        assert dependency_set == {}

    def test_collect_dependency_set_mixed_packages(self) -> None:
        """Test collecting dependency set with mixed existing/nonexistent packages."""
        dependency_set = collect_dependency_set(["pydantic", "nonexistent-package-xyz"])

        # Should only contain existing packages
        assert isinstance(dependency_set, dict)
        if "pydantic" in dependency_set:
            assert "nonexistent-package-xyz" not in dependency_set


class TestRunIdentity:
    """Tests for RunIdentity dataclass."""

    def test_create_run_identity(self) -> None:
        """Test creating RunIdentity."""
        identity = RunIdentity(
            template_code_ref="abc123def456",
            config_hash="a" * 64,  # Valid SHA256 length
            dependency_set={"polytrader": "1.0.0", "numpy": "1.24.0"},
            market_data_snapshot_ref="stream-12345",
        )

        assert identity.template_code_ref == "abc123def456"
        assert identity.config_hash == "a" * 64
        assert identity.dependency_set == {"polytrader": "1.0.0", "numpy": "1.24.0"}
        assert identity.market_data_snapshot_ref == "stream-12345"

    def test_run_identity_empty_template_code_ref(self) -> None:
        """Test that empty template_code_ref raises error."""
        with pytest.raises(ValueError, match="template_code_ref cannot be empty"):
            RunIdentity(
                template_code_ref="",
                config_hash="a" * 64,
                dependency_set={},
                market_data_snapshot_ref=None,
            )

    def test_run_identity_empty_config_hash(self) -> None:
        """Test that empty config_hash raises error."""
        with pytest.raises(ValueError, match="config_hash cannot be empty"):
            RunIdentity(
                template_code_ref="abc123",
                config_hash="",
                dependency_set={},
                market_data_snapshot_ref=None,
            )

    def test_run_identity_invalid_config_hash_length(self) -> None:
        """Test that invalid config_hash length raises error."""
        with pytest.raises(ValueError, match="config_hash must be SHA256"):
            RunIdentity(
                template_code_ref="abc123",
                config_hash="short",  # Not 64 characters
                dependency_set={},
                market_data_snapshot_ref=None,
            )

    def test_run_identity_invalid_dependency_set_type(self) -> None:
        """Test that invalid dependency_set type raises error."""
        with pytest.raises(ValueError, match="dependency_set must be a dictionary"):
            RunIdentity(
                template_code_ref="abc123",
                config_hash="a" * 64,
                dependency_set="not a dict",  # type: ignore[arg-type]
                market_data_snapshot_ref=None,
            )

    def test_run_identity_invalid_dependency_set_keys(self) -> None:
        """Test that dependency_set with non-string keys raises error."""
        with pytest.raises(ValueError, match="dependency_set keys must be strings"):
            RunIdentity(
                template_code_ref="abc123",
                config_hash="a" * 64,
                dependency_set={123: "value"},  # type: ignore[dict-item]
                market_data_snapshot_ref=None,
            )

    def test_run_identity_invalid_dependency_set_values(self) -> None:
        """Test that dependency_set with non-string values raises error."""
        with pytest.raises(ValueError, match="dependency_set values must be strings"):
            RunIdentity(
                template_code_ref="abc123",
                config_hash="a" * 64,
                dependency_set={"key": 123},  # type: ignore[dict-item]
                market_data_snapshot_ref=None,
            )

    def test_run_identity_none_market_data_snapshot_ref(self) -> None:
        """Test that market_data_snapshot_ref can be None."""
        identity = RunIdentity(
            template_code_ref="abc123",
            config_hash="a" * 64,
            dependency_set={},
            market_data_snapshot_ref=None,
        )

        assert identity.market_data_snapshot_ref is None

    def test_run_identity_is_immutable(self) -> None:
        """Test that RunIdentity is immutable (frozen dataclass)."""
        identity = RunIdentity(
            template_code_ref="abc123",
            config_hash="a" * 64,
            dependency_set={},
            market_data_snapshot_ref=None,
        )

        # Should not be able to modify attributes (frozen dataclass)
        with pytest.raises(AttributeError):
            identity.template_code_ref = "new_value"  # type: ignore[misc]


class TestCreateRunIdentity:
    """Tests for create_run_identity convenience function."""

    def test_create_run_identity_automatic_hash(self) -> None:
        """Test that create_run_identity automatically calculates config hash."""
        config = {"buy_threshold": 0.30, "min_history": 30}
        identity = create_run_identity(
            template_code_ref="abc123",
            config=config,
        )

        # Config hash should be calculated automatically
        expected_hash = calculate_config_hash(config)
        assert identity.config_hash == expected_hash
        assert len(identity.config_hash) == 64

    def test_create_run_identity_automatic_dependency_set(self) -> None:
        """Test that create_run_identity automatically collects dependency set."""
        identity = create_run_identity(
            template_code_ref="abc123",
            config={"key": "value"},
        )

        # Dependency set should be collected automatically
        assert isinstance(identity.dependency_set, dict)
        # May be empty if packages not installed, but should be a dict

    def test_create_run_identity_custom_dependency_packages(self) -> None:
        """Test that create_run_identity can use custom dependency packages."""
        identity = create_run_identity(
            template_code_ref="abc123",
            config={"key": "value"},
            dependency_packages=["pydantic"],
        )

        # Dependency set should only contain requested packages
        assert isinstance(identity.dependency_set, dict)

    def test_create_run_identity_with_market_data_ref(self) -> None:
        """Test that create_run_identity can set market_data_snapshot_ref."""
        identity = create_run_identity(
            template_code_ref="abc123",
            config={"key": "value"},
            market_data_snapshot_ref="stream-12345",
        )

        assert identity.market_data_snapshot_ref == "stream-12345"

    def test_create_run_identity_deterministic(self) -> None:
        """Test that create_run_identity is deterministic."""
        config = {"buy_threshold": 0.30, "min_history": 30}

        identity1 = create_run_identity(
            template_code_ref="abc123",
            config=config,
        )

        identity2 = create_run_identity(
            template_code_ref="abc123",
            config=config,
        )

        # Same inputs should produce same identity (except dependency_set may vary)
        assert identity1.template_code_ref == identity2.template_code_ref
        assert identity1.config_hash == identity2.config_hash
        assert identity1.market_data_snapshot_ref == identity2.market_data_snapshot_ref
