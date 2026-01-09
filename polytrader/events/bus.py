"""Event bus for in-process event communication."""

import asyncio
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Topic[T]:
    """Topic for event bus subscriptions."""

    name: str


class EventBus:
    """In-process event bus for publishing and subscribing to events.

    The EventBus provides a simple pub/sub mechanism for components
    to communicate via typed topics. Events are delivered asynchronously
    to all subscribers of a topic.
    """

    def __init__(self) -> None:
        """Initialize the event bus."""
        self._queues: dict[str, list[asyncio.Queue[Any]]] = {}

    def subscribe(self, topic: Topic[T]) -> asyncio.Queue[T]:
        """Subscribe to a topic and receive a queue for messages.

        Args:
            topic: The topic to subscribe to

        Returns:
            An asyncio.Queue that will receive messages published to this topic
        """
        queue: asyncio.Queue[Any] = asyncio.Queue()
        self._queues.setdefault(topic.name, []).append(queue)
        return queue

    async def publish(self, topic: Topic[T], msg: T) -> None:
        """Publish a message to a topic.

        Args:
            topic: The topic to publish to
            msg: The message to publish
        """
        queues = self._queues.get(topic.name, [])
        for queue in queues:
            await queue.put(msg)
