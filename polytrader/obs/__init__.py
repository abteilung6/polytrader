"""Observability module for metrics, logging, and tracing.

Per observability.mdc: Institutional systems are debuggable by design.
"""

from polytrader.obs.logging import (
    bind_correlation_context,
    bind_order_context,
    bind_strategy_context,
)
from polytrader.obs.metrics import (
    get_metrics_collector,
    record_circuit_breaker,
    record_md_gap,
    record_md_reconnect,
    record_md_staleness,
    record_md_update,
    record_order_intent,
    record_projected_exposure,
    record_risk_check,
    record_risk_denial,
    record_strategy_eval,
    record_strategy_eval_latency,
    set_execution_enabled,
    set_kill_switch,
    set_md_book_mid,
    set_md_spread,
    set_metrics_collector,
)

__all__ = [
    "bind_correlation_context",
    "bind_order_context",
    "bind_strategy_context",
    "get_metrics_collector",
    "record_circuit_breaker",
    "record_md_gap",
    "record_md_reconnect",
    "record_md_staleness",
    "record_md_update",
    "record_order_intent",
    "record_projected_exposure",
    "record_risk_check",
    "record_risk_denial",
    "record_strategy_eval",
    "record_strategy_eval_latency",
    "set_execution_enabled",
    "set_kill_switch",
    "set_md_book_mid",
    "set_md_spread",
    "set_metrics_collector",
]
