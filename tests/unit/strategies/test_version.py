"""Unit tests for version selector system.

Per testing.mdc: Unit tests must be deterministic, fast, and isolated.
All version resolution is pure (no side effects, no I/O).
"""

import pytest

from polytrader.strategies.version import (
    VersionResolutionError,
    VersionSelector,
)


class TestVersionSelector:
    """Tests for VersionSelector dataclass."""

    def test_create_exact_version(self) -> None:
        """Test creating selector with exact version."""
        selector = VersionSelector(exact="1.2.3")
        assert selector.exact == "1.2.3"
        assert selector.channel is None
        assert selector.major is None

    def test_create_channel_selector(self) -> None:
        """Test creating selector with channel."""
        selector = VersionSelector(channel="stable")
        assert selector.exact is None
        assert selector.channel == "stable"
        assert selector.major is None

    def test_create_channel_with_major(self) -> None:
        """Test creating selector with channel and major version."""
        selector = VersionSelector(channel="stable", major=1)
        assert selector.exact is None
        assert selector.channel == "stable"
        assert selector.major == 1

    def test_selector_must_have_exact_or_channel(self) -> None:
        """Test that selector must have either exact or channel."""
        with pytest.raises(ValueError, match="must have either"):
            VersionSelector()

    def test_selector_cannot_have_both_exact_and_channel(self) -> None:
        """Test that selector cannot have both exact and channel."""
        with pytest.raises(ValueError, match="cannot have both"):
            VersionSelector(exact="1.2.3", channel="stable")

    def test_invalid_channel(self) -> None:
        """Test that invalid channel raises error."""
        with pytest.raises(ValueError, match="Invalid channel"):
            VersionSelector(channel="invalid")

    def test_major_requires_channel(self) -> None:
        """Test that major can only be specified with channel."""
        with pytest.raises(ValueError, match="can only be specified with 'channel'"):
            VersionSelector(exact="1.2.3", major=1)

    def test_valid_channels(self) -> None:
        """Test that valid channels are accepted."""
        for channel in ["stable", "beta", "dev"]:
            selector = VersionSelector(channel=channel)
            assert selector.channel == channel


class TestVersionResolution:
    """Tests for version resolution."""

    def test_resolve_exact_version(self) -> None:
        """Test resolving exact version."""
        selector = VersionSelector(exact="1.2.3")
        available = ["1.0.0", "1.2.3", "2.0.0"]

        result = selector.resolve(available)
        assert result == "1.2.3"

    def test_resolve_exact_version_not_available(self) -> None:
        """Test that exact version not available raises error."""
        selector = VersionSelector(exact="1.2.3")
        available = ["1.0.0", "2.0.0"]

        with pytest.raises(VersionResolutionError) as exc_info:
            selector.resolve(available)

        assert "Version 1.2.3 not available" in str(exc_info.value)
        assert exc_info.value.selector == selector
        assert exc_info.value.available_versions == available

    def test_resolve_stable_channel(self) -> None:
        """Test resolving stable channel (latest version)."""
        selector = VersionSelector(channel="stable")
        available = ["1.0.0", "1.1.0", "2.0.0"]

        result = selector.resolve(available)
        assert result == "2.0.0"  # Latest by string sort

    def test_resolve_beta_channel(self) -> None:
        """Test resolving beta channel (latest version)."""
        selector = VersionSelector(channel="beta")
        available = ["1.0.0", "1.1.0", "2.0.0"]

        result = selector.resolve(available)
        assert result == "2.0.0"  # Latest by string sort

    def test_resolve_dev_channel(self) -> None:
        """Test resolving dev channel (latest version)."""
        selector = VersionSelector(channel="dev")
        available = ["1.0.0", "1.1.0", "2.0.0"]

        result = selector.resolve(available)
        assert result == "2.0.0"  # Latest by string sort

    def test_resolve_channel_with_major_version(self) -> None:
        """Test resolving channel with major version constraint."""
        selector = VersionSelector(channel="stable", major=1)
        available = ["1.0.0", "1.1.0", "2.0.0", "2.1.0"]

        result = selector.resolve(available)
        assert result == "1.1.0"  # Latest with major=1

    def test_resolve_channel_with_major_version_no_matches(self) -> None:
        """Test that channel with major version constraint fails if no matches."""
        selector = VersionSelector(channel="stable", major=3)
        available = ["1.0.0", "1.1.0", "2.0.0"]

        with pytest.raises(VersionResolutionError) as exc_info:
            selector.resolve(available)

        assert "No versions available for channel 'stable' with major version 3" in str(
            exc_info.value
        )

    def test_resolve_channel_no_versions_available(self) -> None:
        """Test that channel resolution fails if no versions available."""
        selector = VersionSelector(channel="stable")
        available: list[str] = []

        with pytest.raises(VersionResolutionError) as exc_info:
            selector.resolve(available)

        assert "No versions available" in str(exc_info.value)

    def test_resolve_deterministic(self) -> None:
        """Test that resolution is deterministic (same input = same output)."""
        selector = VersionSelector(channel="stable")
        available = ["1.0.0", "1.1.0", "2.0.0"]

        result1 = selector.resolve(available)
        result2 = selector.resolve(available)

        assert result1 == result2

    def test_resolve_single_version(self) -> None:
        """Test resolving with single available version."""
        selector = VersionSelector(channel="stable")
        available = ["1.0.0"]

        result = selector.resolve(available)
        assert result == "1.0.0"

    def test_resolve_exact_version_single_available(self) -> None:
        """Test resolving exact version when only one version available."""
        selector = VersionSelector(exact="1.0.0")
        available = ["1.0.0"]

        result = selector.resolve(available)
        assert result == "1.0.0"


class TestVersionResolutionError:
    """Tests for VersionResolutionError exception."""

    def test_error_message_includes_reason(self) -> None:
        """Test that error message includes reason."""
        selector = VersionSelector(exact="1.2.3")
        available = ["1.0.0", "2.0.0"]

        error = VersionResolutionError(
            selector=selector,
            available_versions=available,
            reason="Version 1.2.3 not available",
        )

        assert "Version resolution failed" in str(error)
        assert "Version 1.2.3 not available" in str(error)
        assert "available: 1.0.0, 2.0.0" in str(error)

    def test_error_message_no_available_versions(self) -> None:
        """Test error message when no versions available."""
        selector = VersionSelector(channel="stable")
        available: list[str] = []

        error = VersionResolutionError(
            selector=selector,
            available_versions=available,
            reason="No versions available",
        )

        assert "No versions available" in str(error)
        # Should not include "available:" when list is empty
        assert "available:" not in str(error)


class TestGetMajorVersion:
    """Tests for _get_major_version helper function."""

    def test_get_major_version_semantic(self) -> None:
        """Test extracting major version from semantic version."""
        from polytrader.strategies.version import _get_major_version

        assert _get_major_version("1.2.3") == 1
        assert _get_major_version("2.0.0") == 2
        assert _get_major_version("10.5.2") == 10

    def test_get_major_version_invalid(self) -> None:
        """Test that invalid version returns None."""
        from polytrader.strategies.version import _get_major_version

        assert _get_major_version("invalid") is None
        assert _get_major_version("") is None
        assert _get_major_version("abc.def.ghi") is None
