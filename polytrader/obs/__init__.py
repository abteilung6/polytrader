"""Observability module for metrics, logging, and tracing.

Per observability.mdc: Institutional systems are debuggable by design.
"""

from polytrader.obs.metrics import (
    get_metrics_collector,
    record_projected_exposure,
    record_risk_check,
    record_risk_denial,
    set_metrics_collector,
)

__all__ = [
    "get_metrics_collector",
    "record_projected_exposure",
    "record_risk_check",
    "record_risk_denial",
    "set_metrics_collector",
]
