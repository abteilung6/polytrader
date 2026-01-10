"""Execution layer: Converts OMS commands to venue-specific actions.

Per flows.mdc §8: Execution applies tactics and routes to venue adapters.
"""

from polytrader.execution.router import ExecutionRouter

__all__ = ["ExecutionRouter"]
