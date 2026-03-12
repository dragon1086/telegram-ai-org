"""MessageBus 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.message_bus import MessageBus, Event, EventType


@pytest.mark.asyncio
async def test_publish_calls_subscriber():
    bus = MessageBus()
    handler = AsyncMock()
    bus.subscribe(EventType.TASK_CREATED, handler)
    event = Event(type=EventType.TASK_CREATED, source="test", data={"id": "T001"})
    await bus.publish(event)
    handler.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_multiple_subscribers():
    bus = MessageBus()
    h1 = AsyncMock()
    h2 = AsyncMock()
    bus.subscribe(EventType.TASK_RESULT, h1)
    bus.subscribe(EventType.TASK_RESULT, h2)
    event = Event(type=EventType.TASK_RESULT, source="test", data={})
    await bus.publish(event)
    h1.assert_awaited_once()
    h2.assert_awaited_once()


@pytest.mark.asyncio
async def test_event_type_isolation():
    bus = MessageBus()
    task_handler = AsyncMock()
    health_handler = AsyncMock()
    bus.subscribe(EventType.TASK_CREATED, task_handler)
    bus.subscribe(EventType.HEALTH_UPDATE, health_handler)
    event = Event(type=EventType.TASK_CREATED, source="test", data={})
    await bus.publish(event)
    task_handler.assert_awaited_once()
    health_handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_handler_error_does_not_affect_others():
    bus = MessageBus()
    failing = AsyncMock(side_effect=Exception("boom"))
    passing = AsyncMock()
    bus.subscribe(EventType.TASK_RESULT, failing)
    bus.subscribe(EventType.TASK_RESULT, passing)
    event = Event(type=EventType.TASK_RESULT, source="test", data={})
    await bus.publish(event)
    failing.assert_awaited_once()
    passing.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_no_subscribers():
    bus = MessageBus()
    event = Event(type=EventType.MEMORY_UPDATE, source="test", data={})
    await bus.publish(event)


@pytest.mark.asyncio
async def test_start_stop_lifecycle():
    bus = MessageBus()
    await bus.start()
    assert bus._running is True
    await bus.stop()
    assert bus._running is False
