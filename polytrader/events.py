import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from polytrader.types import MarketTick

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


TICKS = _create_ticks_topic()
