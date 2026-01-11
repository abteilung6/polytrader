"""Strategy layer per flows.mdc §4.

Strategies produce SignalEvent (probabilistic scores), not orders.
Optimized for fast decision-making in high-frequency trading scenarios.
"""

from polytrader.strategies.base import IStrategy

__all__ = ["IStrategy"]
