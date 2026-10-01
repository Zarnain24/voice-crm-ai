"""In-process event bus.

Services call `bus.publish(...)` after a successful commit. Each event is:
  1. fanned out to connected browsers (Server-Sent Events) so the UI updates live, and
  2. queued for outbound delivery to n8n (or straight to Slack as a fallback).

`publish` is thread-safe: sync route handlers run in FastAPI's threadpool, so events are
handed to the event loop with `call_soon_threadsafe`.
"""

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger("crm.events")


class EventBus:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._outbox: asyncio.Queue[dict[str, Any]] | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> asyncio.Queue[dict[str, Any]]:
        self._loop = loop
        self._outbox = asyncio.Queue()
        return self._outbox

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        event = {
            "type": event_type,
            "occurred_at": datetime.now(UTC).isoformat(),
            "data": data,
        }
        if self._loop is None or self._loop.is_closed():
            log.debug("Event bus not running; dropped %s", event_type)
            return
        self._loop.call_soon_threadsafe(self._fan_out, event)

    def _fan_out(self, event: dict[str, Any]) -> None:
        message = json.dumps(event, default=str)
        for queue in self._subscribers:
            # A slow client may have a full queue; it resyncs on its next refetch.
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(message)
        if self._outbox is not None:
            self._outbox.put_nowait(event)

    def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self._subscribers.discard(queue)


bus = EventBus()
