"""core.dashboard.connection_manager — 채널별 SSE 연결 관리자 (Phase 2).

채널별 독립 구독자 큐를 관리하고, 이벤트를 채널 단위로 브로드캐스트한다.

지원 채널:
    - tickets          : 티켓 처리 현황 (ticket_update 이벤트)
    - completed-tasks  : 완료 작업 목록 (task_complete 이벤트)
    - remote-access    : 원격 접근 현황 (remote_access_change 이벤트)
    - all              : 전체 이벤트 통합 스트림 (하위 호환)

사용 예::

    from core.dashboard.connection_manager import connection_manager

    # 구독
    queue = connection_manager.subscribe("tickets")
    try:
        event = await asyncio.wait_for(queue.get(), timeout=30)
    finally:
        connection_manager.unsubscribe("tickets", queue)

    # 발행
    connection_manager.publish("tickets", "ticket_update", {"pending": 5, "ts": 1234})
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 지원 채널 목록
CHANNELS = ("tickets", "completed-tasks", "remote-access", "all")

# 구독자 큐 최대 크기 (초과 시 silent drop)
_QUEUE_MAX_SIZE = 100


class ConnectionManager:
    """채널별 SSE 연결 관리자.

    Attributes:
        _channels: 채널명 → 구독자 큐 리스트 매핑

    Thread-safety:
        asyncio 이벤트 루프 단일 스레드 내에서만 사용한다.
        멀티스레드 환경에서는 별도 동기화가 필요하다.
    """

    def __init__(self) -> None:
        self._channels: dict[str, list[asyncio.Queue]] = {ch: [] for ch in CHANNELS}

    # ------------------------------------------------------------------
    # 구독 관리
    # ------------------------------------------------------------------

    def subscribe(self, channel: str) -> asyncio.Queue:
        """채널에 구독자 큐를 생성하고 등록한다.

        Args:
            channel: 구독할 채널명 (tickets / completed-tasks / remote-access / all)

        Returns:
            생성된 asyncio.Queue (이벤트 수신용)

        Raises:
            ValueError: 지원하지 않는 채널명
        """
        if channel not in self._channels:
            raise ValueError(f"지원하지 않는 채널: {channel!r}. 지원 채널: {CHANNELS}")

        queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX_SIZE)
        self._channels[channel].append(queue)
        logger.debug("채널 구독 등록: channel=%s, 구독자 수=%d", channel, len(self._channels[channel]))
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        """채널에서 구독자 큐를 안전하게 제거한다.

        큐가 목록에 없어도 예외를 발생시키지 않는다 (연결 끊김 안전 처리).

        Args:
            channel: 채널명
            queue:   제거할 큐
        """
        if channel not in self._channels:
            return
        try:
            self._channels[channel].remove(queue)
            logger.debug("채널 구독 해제: channel=%s, 잔여 구독자=%d", channel, len(self._channels[channel]))
        except ValueError:
            pass  # 이미 제거된 큐 — 무시

    # ------------------------------------------------------------------
    # 이벤트 발행
    # ------------------------------------------------------------------

    def publish(self, channel: str, event_type: str, data: dict) -> None:
        """특정 채널 구독자에게만 이벤트를 발행한다.

        큐가 가득 찬 경우 이벤트를 드롭한다 (느린 클라이언트 보호).

        Args:
            channel:    대상 채널명
            event_type: 이벤트 타입 문자열 (예: "ticket_update")
            data:       페이로드 딕셔너리
        """
        if channel not in self._channels:
            logger.warning("publish: 알 수 없는 채널 %r — 스킵", channel)
            return

        payload = {"type": event_type, **data}
        dropped = 0
        for q in list(self._channels[channel]):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dropped += 1

        if dropped:
            logger.debug("채널 %s: %d개 이벤트 드롭 (큐 가득)", channel, dropped)

    def publish_all(self, event_type: str, data: dict) -> None:
        """전체 채널(all 포함)에 이벤트를 브로드캐스트한다.

        Args:
            event_type: 이벤트 타입
            data:       페이로드 딕셔너리
        """
        payload = {"type": event_type, **data}
        dropped = 0
        for ch_queues in self._channels.values():
            for q in list(ch_queues):
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    dropped += 1

        if dropped:
            logger.debug("publish_all: %d개 이벤트 드롭 (큐 가득)", dropped)

    # ------------------------------------------------------------------
    # 상태 조회
    # ------------------------------------------------------------------

    def client_count(self, channel: Optional[str] = None) -> int:
        """연결된 클라이언트 수를 반환한다.

        Args:
            channel: 채널명 지정 시 해당 채널만 카운트.
                     None이면 전체 채널 합산 (중복 포함).

        Returns:
            정수형 클라이언트 수
        """
        if channel is not None:
            return len(self._channels.get(channel, []))
        return sum(len(q_list) for q_list in self._channels.values())

    def get_channel_stats(self) -> dict[str, int]:
        """채널별 구독자 수 통계를 반환한다.

        Returns:
            {"tickets": N, "completed-tasks": N, "remote-access": N, "all": N}
        """
        return {ch: len(q_list) for ch, q_list in self._channels.items()}

    def reset(self) -> None:
        """모든 채널 구독자를 초기화한다. 테스트용."""
        self._channels = {ch: [] for ch in CHANNELS}


# ---------------------------------------------------------------------------
# 싱글톤 인스턴스
# ---------------------------------------------------------------------------

connection_manager = ConnectionManager()
"""전역 ConnectionManager 싱글톤."""
