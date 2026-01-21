"""Database infrastructure module.

This module contains database-related infrastructure:
- Migrations: Schema versioning and migration runner
- Events: CRUD operations for events table
- Future: Connection pooling, query helpers, etc.
"""

from polytrader.db.models import (
    Base,
    ControlCommandRecord,
    EventRecord,
    PlatformStateRecord,
    StrategyRecord,
)
from polytrader.db.repository import (
    ControlCommandRepository,
    EventRepository,
    PlatformStateRepository,
    StrategyRepository,
)
from polytrader.db.session import DatabaseSessionManager

__all__ = [
    "Base",
    "ControlCommandRecord",
    "EventRecord",
    "PlatformStateRecord",
    "StrategyRecord",
    "ControlCommandRepository",
    "EventRepository",
    "PlatformStateRepository",
    "StrategyRepository",
    "DatabaseSessionManager",
]
