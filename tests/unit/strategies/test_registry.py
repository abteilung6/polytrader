"""Unit tests for strategy registry.

Per testing.mdc: Unit tests must be deterministic, fast, and isolated.
Registry operations are pure (no side effects, no I/O).
"""

from collections.abc import Callable

import pytest

from polytrader.strategies.base import IStrategy
from polytrader.strategies.registry import StrategyRegistry, StrategyTemplate
from polytrader.strategies.schema import ParameterDefinition, ParameterSchema


class TestStrategyTemplate:
    """Tests for StrategyTemplate dataclass."""

    def test_create_template(self) -> None:
        """Test creating a strategy template."""
        schema = ParameterSchema(
            parameters={
                "buy_threshold": ParameterDefinition(
                    name="buy_threshold",
                    type=float,
                    required=True,
                    default=None,
                    description="Price threshold",
                    min_value=0.0,
                    max_value=1.0,
                ),
            }
        )

        def dummy_factory(config: dict[str, object], store: object) -> Callable[[str], IStrategy]:
            def factory(market_slug: str) -> IStrategy:
                # Dummy implementation for testing
                from polytrader.strategies.simple_threshold import (
                    SimpleThresholdStrategy,
                )

                buy_threshold = config.get("buy_threshold", 0.30)
                return SimpleThresholdStrategy(
                    market_slug=market_slug,
                    store=store,  # type: ignore[arg-type]
                    buy_threshold=float(buy_threshold)
                    if isinstance(buy_threshold, (int, float))
                    else 0.30,
                )

            return factory

        template = StrategyTemplate(
            type_id="test_strategy",
            version="1.0.0",
            name="Test Strategy",
            description="A test strategy",
            parameter_schema=schema,
            factory=dummy_factory,
        )

        assert template.type_id == "test_strategy"
        assert template.version == "1.0.0"
        assert template.name == "Test Strategy"
        assert template.description == "A test strategy"
        assert template.parameter_schema is schema
        assert template.factory is dummy_factory

    def test_template_validation_empty_type_id(self) -> None:
        """Test that template validation fails with empty type_id."""
        schema = ParameterSchema(
            parameters={
                "param": ParameterDefinition(
                    name="param",
                    type=float,
                    required=True,
                    default=None,
                    description="Test param",
                ),
            }
        )

        def dummy_factory(config: dict[str, object], store: object) -> Callable[[str], IStrategy]:
            def factory(market_slug: str) -> IStrategy:
                raise NotImplementedError

            return factory

        with pytest.raises(ValueError, match="type_id cannot be empty"):
            StrategyTemplate(
                type_id="",
                version="1.0.0",
                name="Test",
                description="Test",
                parameter_schema=schema,
                factory=dummy_factory,
            )

    def test_template_validation_empty_version(self) -> None:
        """Test that template validation fails with empty version."""
        schema = ParameterSchema(
            parameters={
                "param": ParameterDefinition(
                    name="param",
                    type=float,
                    required=True,
                    default=None,
                    description="Test param",
                ),
            }
        )

        def dummy_factory(config: dict[str, object], store: object) -> Callable[[str], IStrategy]:
            def factory(market_slug: str) -> IStrategy:
                raise NotImplementedError

            return factory

        with pytest.raises(ValueError, match="version cannot be empty"):
            StrategyTemplate(
                type_id="test",
                version="",
                name="Test",
                description="Test",
                parameter_schema=schema,
                factory=dummy_factory,
            )

    def test_template_validation_empty_name(self) -> None:
        """Test that template validation fails with empty name."""
        schema = ParameterSchema(
            parameters={
                "param": ParameterDefinition(
                    name="param",
                    type=float,
                    required=True,
                    default=None,
                    description="Test param",
                ),
            }
        )

        def dummy_factory(config: dict[str, object], store: object) -> Callable[[str], IStrategy]:
            def factory(market_slug: str) -> IStrategy:
                raise NotImplementedError

            return factory

        with pytest.raises(ValueError, match="name cannot be empty"):
            StrategyTemplate(
                type_id="test",
                version="1.0.0",
                name="",
                description="Test",
                parameter_schema=schema,
                factory=dummy_factory,
            )


class TestStrategyRegistry:
    """Tests for StrategyRegistry class."""

    def test_register_template(self) -> None:
        """Test registering a strategy template."""
        registry = StrategyRegistry()

        schema = ParameterSchema(
            parameters={
                "buy_threshold": ParameterDefinition(
                    name="buy_threshold",
                    type=float,
                    required=True,
                    default=None,
                    description="Price threshold",
                ),
            }
        )

        def dummy_factory(config: dict[str, object], store: object) -> Callable[[str], IStrategy]:
            def factory(market_slug: str) -> IStrategy:
                raise NotImplementedError

            return factory

        registry.register(
            type_id="test_strategy",
            version="1.0.0",
            name="Test Strategy",
            description="A test strategy",
            parameter_schema=schema,
            factory=dummy_factory,
        )

        assert registry.has_template("test_strategy", "1.0.0")

    def test_register_duplicate_raises_error(self) -> None:
        """Test that registering duplicate template raises error."""
        registry = StrategyRegistry()

        schema = ParameterSchema(
            parameters={
                "param": ParameterDefinition(
                    name="param",
                    type=float,
                    required=True,
                    default=None,
                    description="Test param",
                ),
            }
        )

        def dummy_factory(config: dict[str, object], store: object) -> Callable[[str], IStrategy]:
            def factory(market_slug: str) -> IStrategy:
                raise NotImplementedError

            return factory

        registry.register(
            type_id="test",
            version="1.0.0",
            name="Test",
            description="Test",
            parameter_schema=schema,
            factory=dummy_factory,
        )

        with pytest.raises(ValueError, match="already registered"):
            registry.register(
                type_id="test",
                version="1.0.0",
                name="Test",
                description="Test",
                parameter_schema=schema,
                factory=dummy_factory,
            )

    def test_get_template(self) -> None:
        """Test getting a registered template."""
        registry = StrategyRegistry()

        schema = ParameterSchema(
            parameters={
                "param": ParameterDefinition(
                    name="param",
                    type=float,
                    required=True,
                    default=None,
                    description="Test param",
                ),
            }
        )

        def dummy_factory(config: dict[str, object], store: object) -> Callable[[str], IStrategy]:
            def factory(market_slug: str) -> IStrategy:
                raise NotImplementedError

            return factory

        registry.register(
            type_id="test",
            version="1.0.0",
            name="Test",
            description="Test",
            parameter_schema=schema,
            factory=dummy_factory,
        )

        template = registry.get("test", "1.0.0")
        assert template.type_id == "test"
        assert template.version == "1.0.0"
        assert template.name == "Test"

    def test_get_nonexistent_template_raises_error(self) -> None:
        """Test that getting nonexistent template raises error."""
        registry = StrategyRegistry()

        with pytest.raises(ValueError, match="not found"):
            registry.get("nonexistent", "1.0.0")

    def test_list_templates(self) -> None:
        """Test listing all registered templates."""
        registry = StrategyRegistry()

        schema = ParameterSchema(
            parameters={
                "param": ParameterDefinition(
                    name="param",
                    type=float,
                    required=True,
                    default=None,
                    description="Test param",
                ),
            }
        )

        def dummy_factory(config: dict[str, object], store: object) -> Callable[[str], IStrategy]:
            def factory(market_slug: str) -> IStrategy:
                raise NotImplementedError

            return factory

        # Register multiple templates
        registry.register(
            type_id="strategy1",
            version="1.0.0",
            name="Strategy 1",
            description="First strategy",
            parameter_schema=schema,
            factory=dummy_factory,
        )

        registry.register(
            type_id="strategy2",
            version="1.0.0",
            name="Strategy 2",
            description="Second strategy",
            parameter_schema=schema,
            factory=dummy_factory,
        )

        templates = registry.list_templates()
        assert len(templates) == 2
        assert {t.type_id for t in templates} == {"strategy1", "strategy2"}

    def test_list_versions(self) -> None:
        """Test listing versions for a type_id."""
        registry = StrategyRegistry()

        schema = ParameterSchema(
            parameters={
                "param": ParameterDefinition(
                    name="param",
                    type=float,
                    required=True,
                    default=None,
                    description="Test param",
                ),
            }
        )

        def dummy_factory(config: dict[str, object], store: object) -> Callable[[str], IStrategy]:
            def factory(market_slug: str) -> IStrategy:
                raise NotImplementedError

            return factory

        # Register multiple versions
        registry.register(
            type_id="test",
            version="1.0.0",
            name="Test",
            description="Test",
            parameter_schema=schema,
            factory=dummy_factory,
        )

        registry.register(
            type_id="test",
            version="1.1.0",
            name="Test",
            description="Test",
            parameter_schema=schema,
            factory=dummy_factory,
        )

        registry.register(
            type_id="test",
            version="2.0.0",
            name="Test",
            description="Test",
            parameter_schema=schema,
            factory=dummy_factory,
        )

        versions = registry.list_versions("test")
        assert versions == ["1.0.0", "1.1.0", "2.0.0"]

    def test_list_versions_nonexistent_type_id(self) -> None:
        """Test listing versions for nonexistent type_id."""
        registry = StrategyRegistry()

        versions = registry.list_versions("nonexistent")
        assert versions == []

    def test_get_latest_version(self) -> None:
        """Test getting latest version for a type_id."""
        registry = StrategyRegistry()

        schema = ParameterSchema(
            parameters={
                "param": ParameterDefinition(
                    name="param",
                    type=float,
                    required=True,
                    default=None,
                    description="Test param",
                ),
            }
        )

        def dummy_factory(config: dict[str, object], store: object) -> Callable[[str], IStrategy]:
            def factory(market_slug: str) -> IStrategy:
                raise NotImplementedError

            return factory

        # Register multiple versions
        registry.register(
            type_id="test",
            version="1.0.0",
            name="Test",
            description="Test",
            parameter_schema=schema,
            factory=dummy_factory,
        )

        registry.register(
            type_id="test",
            version="1.1.0",
            name="Test",
            description="Test",
            parameter_schema=schema,
            factory=dummy_factory,
        )

        registry.register(
            type_id="test",
            version="2.0.0",
            name="Test",
            description="Test",
            parameter_schema=schema,
            factory=dummy_factory,
        )

        latest = registry.get_latest_version("test")
        assert latest == "2.0.0"

    def test_get_latest_version_nonexistent_type_id(self) -> None:
        """Test getting latest version for nonexistent type_id."""
        registry = StrategyRegistry()

        latest = registry.get_latest_version("nonexistent")
        assert latest is None

    def test_validate_config(self) -> None:
        """Test validating configuration against template schema."""
        registry = StrategyRegistry()

        schema = ParameterSchema(
            parameters={
                "buy_threshold": ParameterDefinition(
                    name="buy_threshold",
                    type=float,
                    required=True,
                    default=None,
                    description="Price threshold",
                    min_value=0.0,
                    max_value=1.0,
                ),
            }
        )

        def dummy_factory(config: dict[str, object], store: object) -> Callable[[str], IStrategy]:
            def factory(market_slug: str) -> IStrategy:
                raise NotImplementedError

            return factory

        registry.register(
            type_id="test",
            version="1.0.0",
            name="Test",
            description="Test",
            parameter_schema=schema,
            factory=dummy_factory,
        )

        # Valid config
        errors = registry.validate_config("test", "1.0.0", {"buy_threshold": 0.5})
        assert errors == []

        # Invalid config (missing required parameter)
        errors = registry.validate_config("test", "1.0.0", {})
        assert len(errors) == 1
        assert "buy_threshold: required parameter missing" in errors[0]

        # Invalid config (out of bounds)
        errors = registry.validate_config("test", "1.0.0", {"buy_threshold": 1.5})
        assert len(errors) == 1
        assert "greater than maximum" in errors[0]

    def test_validate_config_nonexistent_template(self) -> None:
        """Test that validating config for nonexistent template raises error."""
        registry = StrategyRegistry()

        with pytest.raises(ValueError, match="not found"):
            registry.validate_config("nonexistent", "1.0.0", {})

    def test_has_template(self) -> None:
        """Test checking if template exists."""
        registry = StrategyRegistry()

        schema = ParameterSchema(
            parameters={
                "param": ParameterDefinition(
                    name="param",
                    type=float,
                    required=True,
                    default=None,
                    description="Test param",
                ),
            }
        )

        def dummy_factory(config: dict[str, object], store: object) -> Callable[[str], IStrategy]:
            def factory(market_slug: str) -> IStrategy:
                raise NotImplementedError

            return factory

        assert registry.has_template("test", "1.0.0") is False

        registry.register(
            type_id="test",
            version="1.0.0",
            name="Test",
            description="Test",
            parameter_schema=schema,
            factory=dummy_factory,
        )

        assert registry.has_template("test", "1.0.0") is True
        assert registry.has_template("test", "1.1.0") is False
        assert registry.has_template("other", "1.0.0") is False
