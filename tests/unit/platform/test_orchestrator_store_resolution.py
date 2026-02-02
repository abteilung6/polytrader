"""Unit tests for orchestrator store resolution (slug vs pattern view per template).

Per unit_testing_technical.mdc: Tests are deterministic, no DB, no network.
Verifies create_strategy_factory_from_config passes the correct IMarketDataStore
view (slug_store or pattern_store) based on StrategyTemplate.use_pattern_history.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from polytrader.db.models import StrategyRecord
from polytrader.platform.orchestrator import create_strategy_factory_from_config
from polytrader.store import (
    DualViewMarketDataStore,
    IMarketDataStore,
    MemoryMarketDataStore,
)
from polytrader.strategies.lifecycle_models import StrategyLifecycleState
from polytrader.strategies.registry import StrategyRegistry
from polytrader.strategies.schema import ParameterDefinition, ParameterSchema

if TYPE_CHECKING:
    from polytrader.strategies.base import IStrategy


def _minimal_schema() -> ParameterSchema:
    """Schema with one optional param so validation accepts empty config."""
    return ParameterSchema(
        parameters={
            "dummy": ParameterDefinition(
                name="dummy",
                type=float,
                required=False,
                default=0.0,
                description="Unused",
                validation=None,
                min_value=0.0,
                max_value=1.0,
            ),
        }
    )


def _recording_factory(
    received_store: list[IMarketDataStore | None],
) -> Callable[[dict[str, object], IMarketDataStore], Callable[[str], IStrategy]]:
    """Returns a factory that records the store it receives."""

    def factory(config: dict[str, object], store: IMarketDataStore) -> Callable[[str], IStrategy]:
        received_store.append(store)
        # Return a no-op strategy factory; we only assert on store passed to factory
        return cast("Callable[[str], IStrategy]", lambda slug: None)

    return factory


def _strategy_record(
    strategy_id: str,
    template_type_id: str,
    template_version: str,
    config: dict[str, object] | None = None,
) -> StrategyRecord:
    return StrategyRecord(
        strategy_id=strategy_id,
        name="Test",
        description="Test",
        config=config or {},
        template_type_id=template_type_id,
        template_version=template_version,
        config_hash="test_hash",
        desired_state=StrategyLifecycleState.RUNNING,
        actual_state=StrategyLifecycleState.RUNNING,
    )


def test_create_strategy_factory_from_config_dual_view_use_pattern_passes_pattern_store() -> None:
    """Dual-view + use_pattern_history=True: factory receives pattern_store."""
    dual = DualViewMarketDataStore()
    received: list[IMarketDataStore | None] = []

    registry = StrategyRegistry()
    registry.register(
        type_id="test_pattern",
        version="1.0.0",
        name="Test Pattern",
        description="Uses pattern store",
        parameter_schema=_minimal_schema(),
        factory=_recording_factory(received),
        use_pattern_history=True,
    )

    record = _strategy_record("s1", "test_pattern", "1.0.0", {})
    create_strategy_factory_from_config(record, registry, dual)

    assert len(received) == 1
    assert received[0] is dual.pattern_store


def test_create_strategy_factory_from_config_dual_view_no_pattern_passes_slug_store() -> None:
    """Dual-view + use_pattern_history=False: factory receives slug_store."""
    dual = DualViewMarketDataStore()
    received: list[IMarketDataStore | None] = []

    registry = StrategyRegistry()
    registry.register(
        type_id="test_slug",
        version="1.0.0",
        name="Test Slug",
        description="Uses slug store",
        parameter_schema=_minimal_schema(),
        factory=_recording_factory(received),
        use_pattern_history=False,
    )

    record = _strategy_record("s2", "test_slug", "1.0.0", {})
    create_strategy_factory_from_config(record, registry, dual)

    assert len(received) == 1
    assert received[0] is dual.slug_store


def test_create_strategy_factory_from_config_plain_store_passes_unchanged() -> None:
    """Plain store: factory receives same store regardless of use_pattern_history."""
    plain = MemoryMarketDataStore()
    received: list[IMarketDataStore | None] = []

    registry = StrategyRegistry()
    registry.register(
        type_id="test_plain",
        version="1.0.0",
        name="Test Plain",
        description="Plain store",
        parameter_schema=_minimal_schema(),
        factory=_recording_factory(received),
        use_pattern_history=True,
    )

    record = _strategy_record("s3", "test_plain", "1.0.0", {})
    create_strategy_factory_from_config(record, registry, plain)

    assert len(received) == 1
    assert received[0] is plain
