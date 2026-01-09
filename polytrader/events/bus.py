"""Event bus for in-process event communication."""

import asyncio
from dataclasses import dataclass
from typing import Any, TypeVar

from polytrader.events.store import IEventStore
from polytrader.events.types import Event
from polytrader.logging_config import logger

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

    If a store is provided, all Event instances published via publish()
    are automatically persisted to the store. This ensures a complete
    audit trail without requiring manual persistence calls.

    Args:
        store: Optional event store for automatic event persistence.
            If provided, all Event instances will be automatically
            persisted when published.
    """

    def __init__(self, store: IEventStore | None = None) -> None:
        """Initialize the event bus.

        Args:
            store: Optional event store for automatic event persistence.
        """
        self._queues: dict[str, list[asyncio.Queue[Any]]] = {}
        self._store = store

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

        If a store is configured and the message is an Event instance,
        it will be automatically persisted to the store before being
        delivered to subscribers.

        Args:
            topic: The topic to publish to
            msg: The message to publish
        """
        # Auto-persist Event instances if store is configured
        if self._store and isinstance(msg, Event):
            try:
                await self._store.append(msg)
            except Exception as e:
                logger.exception(
                    "Failed to persist event to store",
                    event_id=msg.event_id,
                    event_type=type(msg).__name__,
                    error=str(e),
                )
                # Continue publishing even if persistence fails

        # Publish to subscribers
        queues = self._queues.get(topic.name, [])
        for queue in queues:
            await queue.put(msg)
