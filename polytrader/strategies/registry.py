"""Strategy registry for central template management.

Per architecture.mdc: Strategy templates must be discoverable and validated.
Registry provides single source of truth for template definitions.

Per flows.mdc §4: Strategy templates are immutable and versioned.
Registry maps (type_id, version) to factory functions and schemas.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from polytrader.strategies.base import IStrategy
from polytrader.strategies.schema import ParameterSchema

if TYPE_CHECKING:
    from polytrader.store import IMarketDataStore


@dataclass(frozen=True)
class StrategyTemplate:
    """Definition of a strategy template (immutable, versioned code).

    Per architecture.mdc: Strategy templates are immutable and versioned.
    This class represents a single version of a strategy template.

    Attributes:
        type_id: Template identifier (e.g., "simple_threshold")
        version: Template version (e.g., "1.0.0")
        name: Human-readable name
        description: Human-readable description
        parameter_schema: Parameter schema for validation
        factory: Factory function that creates strategy factories
    """

    type_id: str
    version: str
    name: str
    description: str
    parameter_schema: ParameterSchema
    factory: Callable[
        [dict[str, object], IMarketDataStore],
        Callable[[str], IStrategy],
    ]

    def __post_init__(self) -> None:
        """Validate StrategyTemplate itself."""
        if not self.type_id:
            raise ValueError("type_id cannot be empty")

        if not self.version:
            raise ValueError("version cannot be empty")

        if not self.name:
            raise ValueError("name cannot be empty")


class StrategyRegistry:
    """Central registry for strategy templates.

    Per architecture.mdc: Strategy templates must be discoverable and validated.
    Registry provides single source of truth for template definitions.

    Registry maps (type_id, version) tuples to StrategyTemplate instances.
    All operations are thread-safe (read-only after registration).
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._registry: dict[tuple[str, str], StrategyTemplate] = {}

    def register(
        self,
        type_id: str,
        version: str,
        name: str,
        description: str,
        parameter_schema: ParameterSchema,
        factory: Callable[
            [dict[str, object], IMarketDataStore],
            Callable[[str], IStrategy],
        ],
    ) -> None:
        """Register a strategy template.

        Args:
            type_id: Template identifier (e.g., "simple_threshold")
            version: Template version (e.g., "1.0.0")
            name: Human-readable name
            description: Human-readable description
            parameter_schema: Parameter schema for validation
            factory: Factory function that creates strategy factories

        Raises:
            ValueError: If template is already registered
        """
        key = (type_id, version)
        if key in self._registry:
            raise ValueError(f"Strategy template {type_id} version {version} already registered")

        template = StrategyTemplate(
            type_id=type_id,
            version=version,
            name=name,
            description=description,
            parameter_schema=parameter_schema,
            factory=factory,
        )

        self._registry[key] = template

    def get(self, type_id: str, version: str) -> StrategyTemplate:
        """Get strategy template definition.

        Args:
            type_id: Template identifier
            version: Template version

        Returns:
            StrategyTemplate instance

        Raises:
            ValueError: If template not found
        """
        key = (type_id, version)
        if key not in self._registry:
            raise ValueError(f"Strategy template {type_id} version {version} not found")

        return self._registry[key]

    def list_templates(self) -> list[StrategyTemplate]:
        """List all registered strategy templates.

        Returns:
            List of all StrategyTemplate instances
        """
        return list(self._registry.values())

    def list_versions(self, type_id: str) -> list[str]:
        """List all versions for a given type_id.

        Args:
            type_id: Template identifier

        Returns:
            List of version strings (sorted)
        """
        versions = [version for (t_id, version) in self._registry.keys() if t_id == type_id]
        return sorted(versions)

    def get_latest_version(self, type_id: str) -> str | None:
        """Get latest version for a given type_id.

        Uses semantic versioning comparison (simple string sort for now).

        Args:
            type_id: Template identifier

        Returns:
            Latest version string, or None if type_id not found
        """
        versions = self.list_versions(type_id)
        if not versions:
            return None
        return versions[-1]  # Last in sorted list (highest version)

    def validate_config(self, type_id: str, version: str, config: dict[str, object]) -> list[str]:
        """Validate configuration against template schema.

        Args:
            type_id: Template identifier
            version: Template version
            config: Configuration dictionary to validate

        Returns:
            List of error messages (empty if valid)

        Raises:
            ValueError: If template not found
        """
        template = self.get(type_id, version)
        return template.parameter_schema.validate(config)

    def has_template(self, type_id: str, version: str) -> bool:
        """Check if template is registered.

        Args:
            type_id: Template identifier
            version: Template version

        Returns:
            True if template is registered, False otherwise
        """
        return (type_id, version) in self._registry
