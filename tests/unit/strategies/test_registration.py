"""Unit tests for explicit strategy registration.

Per testing.mdc: Unit tests must be deterministic, fast, and isolated.
Registration function is pure (no side effects, no I/O).
"""

import pytest

from polytrader.strategies.registration import register_all_strategies
from polytrader.strategies.registry import StrategyRegistry


class TestRegisterAllStrategies:
    """Tests for register_all_strategies function."""

    def test_register_all_strategies_registers_simple_threshold(self) -> None:
        """Test that register_all_strategies registers simple_threshold."""
        registry = StrategyRegistry()

        # Initially empty
        templates = registry.list_templates()
        assert len(templates) == 0

        # Register all strategies
        register_all_strategies(registry)

        # Should have registered simple_threshold and volatility_filtered_mean_reversion
        templates = registry.list_templates()
        assert len(templates) == 2

        type_ids = {t.type_id for t in templates}
        assert "simple_threshold" in type_ids
        assert "volatility_filtered_mean_reversion" in type_ids

        simple = next(t for t in templates if t.type_id == "simple_threshold")
        assert simple.version == "1.0.0"
        assert simple.name == "Simple Threshold Strategy"

        vfmr = next(t for t in templates if t.type_id == "volatility_filtered_mean_reversion")
        assert vfmr.version == "1.0.0"
        assert vfmr.name == "Volatility-Filtered Mean Reversion"

    def test_register_all_strategies_can_get_template(self) -> None:
        """Test that registered template can be retrieved."""
        registry = StrategyRegistry()
        register_all_strategies(registry)

        template = registry.get("simple_threshold", "1.0.0")
        assert template.type_id == "simple_threshold"
        assert template.version == "1.0.0"
        assert template.name == "Simple Threshold Strategy"
        assert "BUY signals" in template.description

    def test_register_all_strategies_can_get_vfmr_template(self) -> None:
        """Test that volatility_filtered_mean_reversion template can be retrieved."""
        registry = StrategyRegistry()
        register_all_strategies(registry)

        template = registry.get("volatility_filtered_mean_reversion", "1.0.0")
        assert template.type_id == "volatility_filtered_mean_reversion"
        assert template.version == "1.0.0"
        assert template.name == "Volatility-Filtered Mean Reversion"
        assert "Mean reversion" in template.description or "trend" in template.description

    def test_register_all_strategies_has_parameter_schema(self) -> None:
        """Test that registered template has parameter schema."""
        registry = StrategyRegistry()
        register_all_strategies(registry)

        template = registry.get("simple_threshold", "1.0.0")
        assert template.parameter_schema is not None
        assert "buy_threshold" in template.parameter_schema.parameters
        assert "min_history" in template.parameter_schema.parameters

    def test_register_all_strategies_has_factory(self) -> None:
        """Test that registered template has factory function."""
        registry = StrategyRegistry()
        register_all_strategies(registry)

        template = registry.get("simple_threshold", "1.0.0")
        assert template.factory is not None
        assert callable(template.factory)

    def test_register_all_strategies_idempotent(self) -> None:
        """Test that calling register_all_strategies multiple times raises error."""
        registry = StrategyRegistry()

        # Register once
        register_all_strategies(registry)
        templates1 = registry.list_templates()
        assert len(templates1) == 2

        # Register again (should raise error for duplicate)
        # This is expected behavior - registration should only happen once
        # Second registration should fail (duplicate)
        with pytest.raises(ValueError, match="already registered"):
            register_all_strategies(registry)

    def test_register_all_strategies_no_import_time_side_effects(self) -> None:
        """Test that importing registration module doesn't cause side effects."""
        # Import the module
        import polytrader.strategies.registration

        # Create a fresh registry
        registry = StrategyRegistry()

        # Registry should be empty (no import-time registration)
        templates = registry.list_templates()
        assert len(templates) == 0

        # Only after explicit call should strategies be registered
        polytrader.strategies.registration.register_all_strategies(registry)
        templates = registry.list_templates()
        assert len(templates) == 2
