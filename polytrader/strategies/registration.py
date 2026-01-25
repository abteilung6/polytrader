"""Explicit strategy registration (not import-time).

Per institutional best practices: Registration happens at explicit composition root,
not at module import time. This avoids:
- Import-order dependencies
- Test flakiness
- Circular imports
- Accidental registration in CLI tools
"""

from polytrader.strategies.registry import StrategyRegistry


def register_all_strategies(registry: StrategyRegistry) -> None:
    """Register all strategy types in the registry.

    This function is called explicitly from orchestrator startup,
    not at module import time. This avoids:
    - Import-order dependencies
    - Test flakiness
    - Circular imports
    - Accidental registration in CLI tools

    Args:
        registry: StrategyRegistry instance to register strategies in

    Note:
        Imports are done inside the function to avoid import-time side effects.
        This ensures registration only happens when explicitly called.
    """
    # Import strategy modules only when registration is called
    from polytrader.strategies.simple_threshold.factory import (
        create_simple_threshold_factory,
    )
    from polytrader.strategies.simple_threshold.schema import (
        SIMPLE_THRESHOLD_SCHEMA,
    )

    # Register simple_threshold strategy
    registry.register(
        type_id="simple_threshold",
        version="1.0.0",
        name="Simple Threshold Strategy",
        description="Generates BUY signals when price is below threshold",
        parameter_schema=SIMPLE_THRESHOLD_SCHEMA,
        factory=create_simple_threshold_factory,
    )

    # Register other strategies as they are implemented...
