"""Platform module for strategy registry and control plane.

This module provides:
- StrategyRegistry: CRUD operations for strategy registry
- ExecutionControlRepository: Execution control state management
- LiveStrategyRepository: Live strategy activation management
- ControlCommandRepository: Control command queue operations

Per Platform_Proposal.md: These repositories provide the data access layer
for the platform control plane.
"""
