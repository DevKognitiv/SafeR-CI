"""In-process async event bus used for realtime updates, automations and messages."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("safer.hub.events")

Subscriber = Callable[["HubEvent"], Awaitable[None]]

# Event types published on the bus (mirrored 1:1 on the WebSocket)
DEVICE_STATE = "device.state"
DEVICE_EVENT = "device.event"
DEVICE_ADDED = "device.added"
DEVICE_REMOVED = "device.removed"
MESSAGE_NEW = "message.new"
SECURITY_MODE = "security.mode"
SECURITY_ALARM = "security.alarm"
SCENE_RAN = "scene.ran"
SOS_RAISED = "sos.raised"
TICK = "tick"


@dataclass
class HubEvent:
    """A single event. ``payload`` is JSON serialisable."""

    type: str
    home_id: Optional[str] = None
    device_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_ws(self) -> Dict[str, Any]:
        """Wire representation sent to WebSocket clients."""
        data: Dict[str, Any] = {"type": self.type, "home_id": self.home_id}
        if self.device_id:
            data["device_id"] = self.device_id
        data.update(self.payload)
        return data


class EventBus:
    """Very small pub/sub. Subscribers are awaited sequentially and isolated from each other."""

    def __init__(self) -> None:
        self._subscribers: List[Subscriber] = []
        self._lock = asyncio.Lock()

    def subscribe(self, callback: Subscriber) -> Callable[[], None]:
        """Register a subscriber; returns an unsubscribe function."""
        self._subscribers.append(callback)

        def _unsubscribe() -> None:
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass

        return _unsubscribe

    async def publish(self, event: HubEvent) -> None:
        """Deliver an event to every subscriber."""
        for callback in list(self._subscribers):
            try:
                await callback(event)
            except Exception:  # pylint: disable=broad-except
                logger.exception("Event subscriber failed for %s", event.type)

    def publish_nowait(self, event: HubEvent) -> None:
        """Schedule delivery from sync code / other tasks."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.publish(event))

    @property
    def subscriber_count(self) -> int:
        """Number of active subscribers."""
        return len(self._subscribers)
