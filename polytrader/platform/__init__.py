"""Platform module: Control plane, strategy registry, and orchestrator.

Per Platform_Proposal.md: Platform module provides control plane services
for managing execution state, strategy activation, and multi-strategy orchestration.
"""

from polytrader.platform.control import (
    ExecutionControlRepository,
    LiveStrategyRepository,
)
from polytrader.platform.control_plane import ControlPlaneService
from polytrader.platform.orchestrator import (
    PlatformOrchestrator,
    create_strategy_factory_from_config,
)
from polytrader.platform.performance import PerStrategyPerformanceTracker
from polytrader.platform.registry import StrategyRegistry
from polytrader.platform.strategy_runner import StrategyRunner

__all__ = [
    "ControlPlaneService",
    "ExecutionControlRepository",
    "LiveStrategyRepository",
    "PerStrategyPerformanceTracker",
    "PlatformOrchestrator",
    "StrategyRunner",
    "StrategyRegistry",
    "create_strategy_factory_from_config",
]
