import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from polytrader.types import MarketChangeEvent, MarketTick, Order, TradeProposal

T = TypeVar("T")


@dataclass(frozen=True)
class Topic[T]:
    name: str


class EventBus:
    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[Any]]] = {}

    def subscribe(self, topic: Topic[T]) -> asyncio.Queue[T]:
        queue: asyncio.Queue[Any] = asyncio.Queue()
        self._queues.setdefault(topic.name, []).append(queue)
        return queue

    async def publish(self, topic: Topic[T], msg: T) -> None:
        queues = self._queues.get(topic.name, [])
        for queue in queues:
            await queue.put(msg)


def _create_ticks_topic() -> "Topic[MarketTick]":
    from polytrader.types import MarketTick

    return Topic[MarketTick]("ticks")


def _create_proposals_topic() -> "Topic[TradeProposal]":
    from polytrader.types import TradeProposal

    return Topic[TradeProposal]("proposals")


def _create_orders_topic() -> "Topic[Order]":
    from polytrader.types import Order

    return Topic[Order]("orders")


def _create_market_change_topic() -> "Topic[MarketChangeEvent]":
    from polytrader.types import MarketChangeEvent

    return Topic[MarketChangeEvent]("market_change")


TICKS = _create_ticks_topic()
PROPOSALS = _create_proposals_topic()
ORDERS = _create_orders_topic()
MARKET_CHANGE = _create_market_change_topic()
