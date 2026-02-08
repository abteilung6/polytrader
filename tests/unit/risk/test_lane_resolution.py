"""Unit tests for lane resolution (paper vs live).

Component: risk/engine.resolve_lane
Stage: Risk (flows.mdc §6)
Contract: lane is paper when execution_control or get_active_strategies is None,
  or when execution is disabled, or when strategy not in active set; else live.
"""

from typing import cast

from polytrader.ops.control import ExecutionControl
from polytrader.risk.engine import resolve_lane
from tests.factories.events import create_order_intent_event


class _MockExecutionControl:
    """Minimal mock for ExecutionControl (is_enabled only)."""

    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled


def _active_s1() -> set[str]:
    return {"s1"}


def _active_s1_s2() -> set[str]:
    return {"s1", "s2"}


def test_resolve_lane_returns_paper_when_execution_control_none() -> None:
    """When execution_control is None, lane is paper."""
    intent = create_order_intent_event(strategy_id="s1")
    assert resolve_lane(intent, None, _active_s1) == "paper"


def test_resolve_lane_returns_paper_when_execution_disabled() -> None:
    """When execution is disabled, lane is paper."""
    intent = create_order_intent_event(strategy_id="s1")
    control = _MockExecutionControl(enabled=False)
    assert resolve_lane(intent, cast(ExecutionControl, control), _active_s1) == "paper"


def test_resolve_lane_returns_paper_when_get_active_strategies_none() -> None:
    """When get_active_strategies is None, lane is paper."""
    intent = create_order_intent_event(strategy_id="s1")
    control = _MockExecutionControl(enabled=True)
    assert resolve_lane(intent, cast(ExecutionControl, control), None) == "paper"


def test_resolve_lane_returns_paper_when_strategy_not_in_active_set() -> None:
    """When strategy_id not in active set, lane is paper."""
    intent = create_order_intent_event(strategy_id="other")
    control = _MockExecutionControl(enabled=True)
    assert resolve_lane(intent, cast(ExecutionControl, control), _active_s1_s2) == "paper"


def test_resolve_lane_returns_live_when_enabled_and_strategy_active() -> None:
    """When execution enabled and strategy in active set, lane is live."""
    intent = create_order_intent_event(strategy_id="s1")
    control = _MockExecutionControl(enabled=True)
    assert resolve_lane(intent, cast(ExecutionControl, control), _active_s1_s2) == "live"
