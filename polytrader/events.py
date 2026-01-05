import asyncio
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[Any]]] = {}

    def subscribe(self, topic: str) -> asyncio.Queue[Any]:
        queue: asyncio.Queue[Any] = asyncio.Queue()
        self._queues.setdefault(topic, []).append(queue)
        return queue

    async def publish(self, topic: str, msg: Any) -> None:
        queues = self._queues.get(topic, [])
        for queue in queues:
            await queue.put(msg)
