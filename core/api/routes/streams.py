"""core.api.routes.streams — 채널별 SSE 실시간 스트림 엔드포인트 (Phase 2).

채널별 전용 SSE 엔드포인트 3종:
    GET /api/v1/stream/tickets          — 티켓 처리 현황 실시간 스트림
    GET /api/v1/stream/completed-tasks  — 완료 작업 목록 실시간 업데이트
    GET /api/v1/stream/remote-access    — 원격 접근 현황 스트림

이벤트 페이로드 스키마:
    ticket_update:
        { "type": "ticket_update", "pending": int, "in_progress": int,
          "done": int, "blocked": int, "aggregations": {...}, "ts": float }

    task_complete:
        { "type": "task_complete", "ticket_id": str, "state": str,
          "assignee": str, "title": str, "org_id": str,
          "completed_at": float, "ts": float }

    remote_access_change:
        { "type": "remote_access_change", "client_count": int,
          "channel_stats": {...}, "ts": float }

인증:
    ENABLE_API_AUTH 와 무관하게 대시보드 스트리밍은 공개 접근 허용.
    (대시보드 UI가 인증 없이 실시간 업데이트를 수신할 수 있도록 설계)

재연결:
    Last-Event-ID 헤더를 지원한다. 서버는 헤더를 수신하면 로그에 기록하고
    연결 확인 이벤트에 last_id 필드를 포함한다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from core.dashboard.connection_manager import connection_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/stream", tags=["stream"])

# SSE 응답 헤더
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",  # nginx 프록시 버퍼링 비활성화
    "Connection": "keep-alive",
}

# ping 간격 (초)
_PING_INTERVAL = 30.0


# ---------------------------------------------------------------------------
# SSE 유틸리티
# ---------------------------------------------------------------------------


def _fmt_sse(event: str, data: dict, event_id: str | None = None) -> str:
    """SSE 포맷 직렬화.

    Args:
        event:    이벤트 타입
        data:     페이로드 딕셔너리
        event_id: 이벤트 ID (Last-Event-ID 재연결용, 선택)

    Returns:
        "event: {type}\ndata: {json}\n\n" 형식 문자열
    """
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    lines.append("")  # 이벤트 구분 빈 줄
    lines.append("")
    return "\n".join(lines)


async def _base_sse_generator(
    request: Request,
    channel: str,
    initial_event_fn=None,
    last_event_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """채널별 SSE 생성기 공통 구현.

    Args:
        request:          FastAPI Request (연결 끊김 감지용)
        channel:          ConnectionManager 채널명
        initial_event_fn: 연결 시 초기 이벤트 생성 함수 (없으면 ping만 발송)
        last_event_id:    클라이언트 재연결 시 전달된 마지막 이벤트 ID
    """
    queue = connection_manager.subscribe(channel)
    if last_event_id:
        logger.info("채널 %s 재연결: Last-Event-ID=%s", channel, last_event_id)

    # 원격 접근 현황 업데이트 (채널 구독자 수 변경 시)
    _notify_remote_access()

    try:
        # 초기 연결 확인 이벤트
        connect_data: dict = {"ts": time.time(), "message": "connected", "channel": channel}
        if last_event_id:
            connect_data["last_id"] = last_event_id
        yield _fmt_sse("ping", connect_data, event_id=str(int(time.time() * 1000)))

        # 초기 상태 이벤트 (채널별 다름)
        if initial_event_fn is not None:
            try:
                initial_events = initial_event_fn()
                for ev_type, ev_data in initial_events:
                    yield _fmt_sse(ev_type, ev_data)
            except Exception as exc:
                logger.warning("초기 이벤트 생성 오류: %s", exc)

        # 이벤트 루프
        deadline = time.time() + _PING_INTERVAL
        while True:
            if await request.is_disconnected():
                logger.debug("채널 %s: 클라이언트 연결 끊김", channel)
                break

            remaining = deadline - time.time()
            if remaining <= 0:
                # ping 발송 후 타이머 리셋
                yield _fmt_sse("ping", {"ts": time.time()})
                deadline = time.time() + _PING_INTERVAL
                continue

            try:
                # 최대 1초씩 짧게 대기 — 연결 끊김을 빠르게 감지
                event_data = await asyncio.wait_for(queue.get(), timeout=min(1.0, remaining))
                ev_type = event_data.pop("type", "message")
                ev_id = str(int(time.time() * 1000))
                yield _fmt_sse(ev_type, event_data, event_id=ev_id)
                # 이벤트 수신 시 ping 타이머 리셋
                deadline = time.time() + _PING_INTERVAL
            except asyncio.TimeoutError:
                # 1초 후 재시도 (ping 타이머 또는 다음 이벤트 대기)
                pass

    finally:
        connection_manager.unsubscribe(channel, queue)
        _notify_remote_access()
        logger.debug("채널 %s: 구독 해제 완료", channel)


def _notify_remote_access() -> None:
    """원격 접근 현황 이벤트를 remote-access 채널에 발행."""
    try:
        connection_manager.publish(
            "remote-access",
            "remote_access_change",
            {
                "client_count": connection_manager.client_count(),
                "channel_stats": connection_manager.get_channel_stats(),
                "ts": time.time(),
            },
        )
    except Exception as exc:
        logger.debug("원격 접근 알림 오류: %s", exc)


# ---------------------------------------------------------------------------
# 엔드포인트 (a): 티켓 처리 현황 스트림
# ---------------------------------------------------------------------------


@router.get(
    "/tickets",
    summary="티켓 처리 현황 실시간 SSE 스트림",
    description=(
        "티켓 상태 변경 이벤트(ticket_update)를 실시간으로 스트리밍한다. "
        "연결 즉시 현재 카운트 스냅샷을 발송하고, 이후 변경 발생 시 push한다."
    ),
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def stream_tickets(
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """티켓 처리 현황 SSE 스트림."""

    def _initial_events():
        """연결 시 현재 티켓 카운트 스냅샷 즉시 발송."""
        try:
            from core.dashboard.aggregator import aggregate_all_periods, count_by_state
            from core.dashboard.adapter import DataSourceAdapter

            # DashboardPusher에서 마지막 캐시 재사용 시도
            try:
                from core.api.routes.events import _get_pusher_snapshot
                snapshot = _get_pusher_snapshot()
                if snapshot:
                    yield ("ticket_update", {**snapshot.get("counts", {}), "ts": time.time()})
                    return
            except Exception:
                pass

            # 폴백: 빈 스냅샷 발송
            yield ("ticket_update", {
                "pending": 0, "in_progress": 0, "done": 0, "blocked": 0,
                "ts": time.time(), "note": "initial_snapshot"
            })
        except Exception as exc:
            logger.debug("티켓 초기 스냅샷 오류: %s", exc)

    return StreamingResponse(
        _base_sse_generator(request, "tickets", _initial_events, last_event_id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# ---------------------------------------------------------------------------
# 엔드포인트 (b): 완료 작업 스트림
# ---------------------------------------------------------------------------


@router.get(
    "/completed-tasks",
    summary="완료 작업 목록 실시간 SSE 스트림",
    description=(
        "작업 완료 이벤트(task_complete)를 실시간으로 스트리밍한다. "
        "연결 즉시 최근 완료 작업 20건을 초기 발송한다."
    ),
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def stream_completed_tasks(
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """완료 작업 SSE 스트림."""

    def _initial_events():
        """연결 시 최근 완료 작업 20건 초기 발송."""
        try:
            from core.api.routes.events import _get_pusher_snapshot
            snapshot = _get_pusher_snapshot()
            if snapshot:
                for task in snapshot.get("recent_completed", []):
                    yield ("task_complete", {**task, "ts": time.time(), "note": "initial_batch"})
        except Exception as exc:
            logger.debug("완료 작업 초기 발송 오류: %s", exc)

    return StreamingResponse(
        _base_sse_generator(request, "completed-tasks", _initial_events, last_event_id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# ---------------------------------------------------------------------------
# 엔드포인트 (c): 원격 접근 현황 스트림
# ---------------------------------------------------------------------------


@router.get(
    "/remote-access",
    summary="원격 접근 현황 실시간 SSE 스트림",
    description=(
        "원격 접근 상태 변경 이벤트(remote_access_change)를 실시간으로 스트리밍한다. "
        "클라이언트 접속/해제 시 자동으로 현황이 업데이트된다."
    ),
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def stream_remote_access(
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """원격 접근 현황 SSE 스트림."""

    def _initial_events():
        """연결 시 현재 접속 현황 즉시 발송."""
        yield ("remote_access_change", {
            "client_count": connection_manager.client_count(),
            "channel_stats": connection_manager.get_channel_stats(),
            "ts": time.time(),
            "note": "initial_snapshot",
        })

    return StreamingResponse(
        _base_sse_generator(request, "remote-access", _initial_events, last_event_id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
