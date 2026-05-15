"""Tests for the in-process event bus."""

import asyncio
import pytest

from app.services.event_bus import EventBus


@pytest.mark.asyncio
async def test_publish_reaches_subscriber():
    bus = EventBus()
    received = []

    async def consumer():
        async for evt in bus.subscribe():
            received.append(evt)
            if len(received) == 2:
                return

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)  # let consumer subscribe
    bus.publish({"type": "a"})
    bus.publish({"type": "b"})
    await asyncio.wait_for(task, timeout=1.0)

    assert received == [{"type": "a"}, {"type": "b"}]


@pytest.mark.asyncio
async def test_slow_subscriber_overflows_and_is_dropped():
    bus = EventBus(maxsize=2)

    async def slow_consumer():
        # Subscribe but never read
        sub = bus._make_subscription()
        try:
            await asyncio.sleep(10)
        finally:
            sub.close()
        return sub

    # Manually create subscription and don't drain it
    sub = bus._make_subscription()
    bus.publish({"type": "a"})
    bus.publish({"type": "b"})
    bus.publish({"type": "c"})  # should overflow → drop

    assert sub.dropped is True


@pytest.mark.asyncio
async def test_multiple_subscribers_each_receive_all():
    bus = EventBus()
    a_received = []
    b_received = []

    async def consumer(target):
        async for evt in bus.subscribe():
            target.append(evt)
            if len(target) == 1:
                return

    task_a = asyncio.create_task(consumer(a_received))
    task_b = asyncio.create_task(consumer(b_received))
    await asyncio.sleep(0)
    bus.publish({"type": "x"})
    await asyncio.wait_for(asyncio.gather(task_a, task_b), timeout=1.0)

    assert a_received == [{"type": "x"}]
    assert b_received == [{"type": "x"}]
