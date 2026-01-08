from collections import deque
from typing import Protocol

from polytrader.types import MarketTick, Outcome


class ITickStore(Protocol):
    def add(self, tick: MarketTick) -> None: ...

    def latest(self, market_slug: str, outcome: Outcome) -> MarketTick | None: ...

    def history(self, market_slug: str, outcome: Outcome) -> list[MarketTick]: ...


class MemoryTickStore(ITickStore):
    def __init__(self, window: int = 3000) -> None:
        self.window = window
        self._ticks: dict[tuple[str, Outcome], deque[MarketTick]] = {}

    def add(self, tick: MarketTick) -> None:
        key = (tick.market_slug, tick.outcome)
        self._ticks.setdefault(key, deque(maxlen=self.window)).append(tick)

    def latest(self, market_slug: str, outcome: Outcome) -> MarketTick | None:
        key = (market_slug, outcome)
        d = self._ticks.get(key)
        return d[-1] if d else None

    def history(self, market_slug: str, outcome: Outcome) -> list[MarketTick]:
        key = (market_slug, outcome)
        return list(self._ticks.get(key, []))
