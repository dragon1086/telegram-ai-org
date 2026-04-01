"""core.api.routes.events — SSE 실시간 이벤트 스트림 엔드포인트.

클라이언트(대시보드)가 Server-Sent Events(SSE)로 실시간 업데이트를 수신한다.

이벤트 타입:
    - ticket_update         : 티켓 카운터 변경
    - task_complete         : 작업 완료
    - remote_access_change  : 원격 접근 상태 변경
    - ping                  : 연결 유지 (30초 간격)

하위 호환:
    기존 /api/v1/events/stream 엔드포인트는 유지된다.
    Phase 2 채널별 전용 엔드포인트는 core.api.routes.streams 모듈에 구현됨.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any, AsyncGenerator, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/v1/events", tags=["events"])

# DashboardPusher 참조 (앱 초기화 후 주입)
_pusher_ref: Optional[Any] = None


def _set_pusher(pusher: Any) -> None:
    """DashboardPusher 참조를 등록한다 (lifespan 초기화 시 호출)."""
    global _pusher_ref
    _pusher_ref = pusher


def _get_pusher_snapshot() -> Optional[dict]:
    """DashboardPusher 스냅샷을 반환한다. 초기화 전이면 None."""
    if _pusher_ref is None:
        return None
    try:
        return _pusher_ref.get_snapshot()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 글로벌 구독자 관리 (in-memory pub/sub) — 하위 호환 유지
# ---------------------------------------------------------------------------

_subscribers: list[asyncio.Queue] = []


def publish_event(event_type: str, data: dict) -> None:
    """백엔드 코드에서 이벤트를 발행한다.

    기존 _subscribers 큐 + ConnectionManager 채널 양쪽에 동시 발행한다.

    사용 예::

        from core.api.routes.events import publish_event
        publish_event("ticket_update", {"in_progress": 3, "pending": 5, "done": 12})
    """
    payload = {"type": event_type, **data}

    # 1) 기존 글로벌 구독자 (하위 호환)
    for q in list(_subscribers):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass  # 느린 클라이언트는 이벤트 드롭

    # 2) Phase 2 ConnectionManager — "all" 채널 구독자에게 브로드캐스트
    try:
        from core.dashboard.connection_manager import connection_manager
        connection_manager.publish("all", event_type, data)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# SSE 스트림 생성기
# ---------------------------------------------------------------------------


async def _sse_generator(request: Request) -> AsyncGenerator[str, None]:
    """SSE 메시지 생성기 — 클라이언트 연결당 1개 생성."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.append(queue)

    try:
        # 초기 연결 확인 이벤트
        yield _format_sse("ping", {"ts": time.time(), "message": "connected"})

        while True:
            # 연결 끊김 감지
            if await request.is_disconnected():
                break

            try:
                # 최대 30초 대기 (ping 간격)
                event_data = await asyncio.wait_for(queue.get(), timeout=30.0)
                event_type = event_data.pop("type", "message")
                yield _format_sse(event_type, event_data)
            except asyncio.TimeoutError:
                # ping 전송 (연결 유지)
                yield _format_sse("ping", {"ts": time.time()})

    finally:
        try:
            _subscribers.remove(queue)
        except ValueError:
            pass


def _format_sse(event: str, data: dict) -> str:
    """SSE 포맷으로 직렬화."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# 라우터 엔드포인트
# ---------------------------------------------------------------------------


@router.get(
    "/stream",
    summary="SSE 실시간 이벤트 스트림",
    description=(
        "대시보드 클라이언트가 연결하는 SSE 엔드포인트. "
        "ticket_update / task_complete / remote_access_change 이벤트를 스트리밍한다."
    ),
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def sse_stream(request: Request) -> StreamingResponse:
    return StreamingResponse(
        _sse_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx 버퍼링 비활성화
        },
    )
