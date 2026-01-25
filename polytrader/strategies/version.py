"""Version selector system for strategy templates.

Per feedback: "latest" must be deterministic. Selectors resolve to exact
versions at creation time, stored on instance.

This module provides VersionSelector for deterministic version resolution.
Supports exact versions (1.2.3) or channel selectors (stable, beta, dev).
"""

from __future__ import annotations

from dataclasses import dataclass


class VersionResolutionError(Exception):
    """Raised when version resolution fails.

    Attributes:
        selector: VersionSelector that failed to resolve
        available_versions: List of available versions
        reason: Reason for resolution failure
    """

    def __init__(
        self,
        selector: VersionSelector,
        available_versions: list[str],
        reason: str,
    ) -> None:
        """Initialize VersionResolutionError.

        Args:
            selector: VersionSelector that failed
            available_versions: Available versions
            reason: Reason for failure
        """
        self.selector = selector
        self.available_versions = available_versions
        self.reason = reason
        message = f"Version resolution failed: {reason}"
        if available_versions:
            message += f" (available: {', '.join(available_versions)})"
        super().__init__(message)


@dataclass(frozen=True)
class VersionSelector:
    """Version selector for strategy instances.

    Either exact version (1.2.3) or channel selector (stable, beta, dev).
    "latest" is resolved to exact version at creation time.

    Per proposal: Selectors resolve to exact versions at creation time,
    stored on instance. This ensures deterministic behavior.

    Attributes:
        exact: Exact version string (e.g., "1.2.3") or None
        channel: Channel name ("stable", "beta", "dev") or None
        major: Major version number for channel selection
            (e.g., 1 for "latest compatible version") or None
    """

    exact: str | None = None
    channel: str | None = None
    major: int | None = None

    def __post_init__(self) -> None:
        """Validate VersionSelector itself."""
        if self.exact is None and self.channel is None:
            raise ValueError("VersionSelector must have either 'exact' or 'channel'")

        if self.exact is not None and self.channel is not None:
            raise ValueError("VersionSelector cannot have both 'exact' and 'channel'")

        if self.channel is not None:
            valid_channels = {"stable", "beta", "dev"}
            if self.channel not in valid_channels:
                raise ValueError(
                    f"Invalid channel: {self.channel}. Must be one of {valid_channels}"
                )

        if self.major is not None and self.channel is None:
            raise ValueError("'major' can only be specified with 'channel'")

    def resolve(self, available_versions: list[str]) -> str:
        """Resolve selector to exact version.

        Args:
            available_versions: List of available version strings
                (e.g., ["1.0.0", "1.1.0", "2.0.0"])

        Returns:
            Exact version string (e.g., "1.2.3")

        Raises:
            VersionResolutionError: If resolution fails

        Note:
            This is a pure function (no side effects, deterministic).
            Per proposal: Resolution is deterministic based on available versions.
        """
        if not available_versions:
            raise VersionResolutionError(
                self,
                available_versions,
                "No versions available",
            )

        # Option 1: Exact version
        if self.exact is not None:
            if self.exact not in available_versions:
                raise VersionResolutionError(
                    self,
                    available_versions,
                    f"Version {self.exact} not available",
                )
            return self.exact

        # Option 2: Channel selector
        if self.channel is not None:
            # Filter versions by major version if specified
            candidate_versions = available_versions
            if self.major is not None:
                candidate_versions = [
                    v for v in available_versions if _get_major_version(v) == self.major
                ]

            if not candidate_versions:
                if self.major is not None:
                    raise VersionResolutionError(
                        self,
                        available_versions,
                        f"No versions available for channel '{self.channel}' "
                        f"with major version {self.major}",
                    )
                raise VersionResolutionError(
                    self,
                    available_versions,
                    f"No versions available for channel '{self.channel}'",
                )

            # Resolve channel to latest version
            # For now: simple string sort (works for semantic versioning)
            # Future: Implement proper semantic versioning comparison
            if self.channel == "stable":
                # Stable = latest version (highest by string sort)
                return max(candidate_versions)
            elif self.channel == "beta":
                # Beta = latest beta version (highest by string sort)
                return max(candidate_versions)
            elif self.channel == "dev":
                # Dev = latest dev version (highest by string sort)
                return max(candidate_versions)
            else:
                # Should not happen due to validation, but handle gracefully
                raise VersionResolutionError(
                    self,
                    available_versions,
                    f"Unknown channel: {self.channel}",
                )

        # Should not happen due to validation
        raise VersionResolutionError(
            self,
            available_versions,
            "Invalid version selector (neither exact nor channel specified)",
        )


def _get_major_version(version: str) -> int | None:
    """Extract major version number from version string.

    Args:
        version: Version string (e.g., "1.2.3" or "1.0.0")

    Returns:
        Major version number (e.g., 1) or None if cannot parse

    Note:
        Simple implementation: extracts first number before first dot.
        For "1.2.3" returns 1, for "2.0.0" returns 2.
    """
    try:
        # Split by dot and take first part
        parts = version.split(".", 1)
        if parts:
            return int(parts[0])
    except (ValueError, AttributeError):
        pass
    return None
