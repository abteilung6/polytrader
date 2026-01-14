"""Observability module for metrics, logging, and tracing.

Per observability.mdc: Institutional systems are debuggable by design.
"""

from polytrader.obs.metrics import (
    get_metrics_collector,
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
    set_md_book_mid,
    set_md_spread,
    set_metrics_collector,
)

__all__ = [
    "get_metrics_collector",
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
    "set_md_book_mid",
    "set_md_spread",
    "set_metrics_collector",
]
