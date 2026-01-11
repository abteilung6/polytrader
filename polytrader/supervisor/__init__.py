"""Supervisor package: Manages component lifecycle.

Two supervisors:
- SystemSupervisor: Manages global/system-wide services (Portfolio, Risk, OMS, Execution, Position)
- MarketSupervisor: Manages market-specific components (Adapter, Observer, Strategy)
"""

from polytrader.supervisor.market import MarketSupervisor
from polytrader.supervisor.system import SystemSupervisor

__all__ = ["MarketSupervisor", "SystemSupervisor"]
