"""비동기 이벤트 버스 — 모듈 간 결합도 감소.

pub/sub 패턴으로 모듈 간 직접 호출을 이벤트 기반 통신으로 전환.
핸들러 에러는 격리되어 버스를 죽이지 않음.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from loguru import logger


class EventType(Enum):
    TASK_CREATED = "task_created"
    TASK_STATE_CHANGED = "task_state_changed"
    TASK_RESULT = "task_result"
    MESSAGE_RECEIVED = "message_received"
    DISPLAY_REQUEST = "display_request"
    HEALTH_UPDATE = "health_update"
    COLLAB_REQUEST = "collab_request"
    MEMORY_UPDATE = "memory_update"
    DISCUSSION_STARTED = "discussion_started"
    DISCUSSION_MESSAGE = "discussion_message"
    DISCUSSION_CONVERGED = "discussion_converged"
    DISCUSSION_DECIDED = "discussion_decided"
    DISCUSSION_TIMED_OUT = "discussion_timed_out"


@dataclass
class Event:
    type: EventType
    source: str
    data: dict
    target: str | None = None


class MessageBus:
    """비동기 pub/sub 이벤트 버스."""

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[Callable]] = defaultdict(list)
        self._running = False

    def subscribe(self, event_type: EventType, handler: Callable) -> None:
        self._subscribers[event_type].append(handler)
        logger.debug(f"Bus 구독: {event_type.value} <- {handler.__name__}")

    async def publish(self, event: Event) -> None:
        for handler in self._subscribers.get(event.type, []):
            try:
                await handler(event)
            except Exception:
                logger.exception(f"Bus 핸들러 에러: {event.type.value} -> {handler.__name__}")

    async def start(self) -> None:
        self._running = True
        logger.info("MessageBus 시작")

    async def stop(self) -> None:
        self._running = False
        logger.info("MessageBus 종료")
