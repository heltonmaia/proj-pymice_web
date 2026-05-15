"""In-process pub/sub event bus.

Publishers call publish() synchronously (from the LiveExperiment loop thread).
Subscribers iterate via subscribe() in asyncio context. A subscriber whose
queue overflows is marked dropped — the WebSocket handler closes its socket
in that case. The canonical record is always events.jsonl on disk; the bus
is best-effort delivery.
"""

import asyncio
from dataclasses import dataclass, field
from typing import AsyncIterator, List


@dataclass
class _Subscription:
    queue: asyncio.Queue
    dropped: bool = False
    closed: bool = False

    def close(self):
        self.closed = True


class EventBus:
    def __init__(self, maxsize: int = 1024):
        self._maxsize = maxsize
        self._subs: List[_Subscription] = []
        self._lock = asyncio.Lock()

    def _make_subscription(self) -> _Subscription:
        sub = _Subscription(queue=asyncio.Queue(maxsize=self._maxsize))
        self._subs.append(sub)
        return sub

    def publish(self, event: dict) -> None:
        # Iterate over a snapshot to allow concurrent unsubscribe.
        for sub in list(self._subs):
            if sub.closed:
                self._subs.remove(sub)
                continue
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                sub.dropped = True
                sub.close()

    async def subscribe(self) -> AsyncIterator[dict]:
        sub = self._make_subscription()
        try:
            while not sub.closed:
                evt = await sub.queue.get()
                yield evt
                if sub.dropped:
                    return
        finally:
            sub.close()
