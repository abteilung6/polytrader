from typing import Protocol

from polytrader.types import MarketTick


class ITradingModel(Protocol):
    async def on_tick(self, tick: MarketTick) -> None: ...
