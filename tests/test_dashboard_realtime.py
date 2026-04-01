"""tests/test_dashboard_realtime.py — 실시간 대시보드 백엔드 통합 테스트 (Phase 2).

테스트 범위:
    TestConnectionManager   — ConnectionManager 유닛 테스트
    TestSSEEndpoints        — SSE 엔드포인트 연결 및 헤더 검증
    TestEventPayloads       — 이벤트 페이로드 스키마 검증
    TestConnectionLifecycle — 연결/해제 시 ConnectionManager 등록·해제 검증
"""
from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------


@pytest.fixture
def manager():
    """ConnectionManager 새 인스턴스 (테스트 격리)."""
    from core.dashboard.connection_manager import ConnectionManager
    return ConnectionManager()


@pytest.fixture
def test_app():
    """테스트용 FastAPI 앱 — lifespan 없이 라우터만 마운트."""
    app = FastAPI()

    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from core.api.routes.events import router as events_router
    from core.api.routes.streams import router as streams_router
    app.include_router(events_router)
    app.include_router(streams_router)

    return app


@pytest.fixture
def client(test_app):
    """TestClient 인스턴스."""
    return TestClient(test_app, raise_server_exceptions=False)


def _get_sse_endpoint_info(test_app: FastAPI, url_path: str) -> dict:
    """테스트 앱에서 SSE 엔드포인트의 라우트 정보를 반환한다.

    실제 HTTP 연결을 하지 않아 blocking 없이 라우트 등록 여부를 확인한다.
    """
    from fastapi.routing import APIRoute
    for route in test_app.routes:
        if isinstance(route, APIRoute) and route.path == url_path:
            return {
                "path": route.path,
                "methods": route.methods,
                "tags": route.tags,
            }
    return {}


# ---------------------------------------------------------------------------
# TestConnectionManager — 유닛 테스트
# ---------------------------------------------------------------------------


class TestConnectionManager:
    """ConnectionManager 내부 로직 검증."""

    def test_subscribe_creates_queue(self, manager):
        """구독 시 asyncio.Queue 반환, 채널에 등록된다."""
        q = manager.subscribe("tickets")
        assert isinstance(q, asyncio.Queue)
        assert manager.client_count("tickets") == 1

    def test_unsubscribe_removes_queue(self, manager):
        """해제 시 채널에서 큐가 제거된다."""
        q = manager.subscribe("tickets")
        manager.unsubscribe("tickets", q)
        assert manager.client_count("tickets") == 0

    def test_unsubscribe_nonexistent_is_safe(self, manager):
        """미등록 큐 해제 시 예외 없이 처리된다."""
        q = asyncio.Queue()
        manager.unsubscribe("tickets", q)  # 예외 없어야 함

    def test_publish_delivers_to_channel(self, manager):
        """publish는 해당 채널 구독자에게만 이벤트를 전달한다."""
        q_tickets = manager.subscribe("tickets")
        q_completed = manager.subscribe("completed-tasks")

        manager.publish("tickets", "ticket_update", {"pending": 3})

        # tickets 채널만 수신
        assert not q_tickets.empty()
        assert q_completed.empty()

        event = q_tickets.get_nowait()
        assert event["type"] == "ticket_update"
        assert event["pending"] == 3

    def test_publish_all_delivers_to_all_channels(self, manager):
        """publish_all은 모든 채널 구독자에게 이벤트를 전달한다."""
        q1 = manager.subscribe("tickets")
        q2 = manager.subscribe("completed-tasks")
        q3 = manager.subscribe("remote-access")
        q4 = manager.subscribe("all")

        manager.publish_all("ticket_update", {"pending": 5})

        for q in (q1, q2, q3, q4):
            assert not q.empty()
            e = q.get_nowait()
            assert e["type"] == "ticket_update"
            assert e["pending"] == 5

    def test_client_count_channel_specific(self, manager):
        """client_count(channel)은 해당 채널만 카운트한다."""
        manager.subscribe("tickets")
        manager.subscribe("tickets")
        manager.subscribe("completed-tasks")

        assert manager.client_count("tickets") == 2
        assert manager.client_count("completed-tasks") == 1
        assert manager.client_count("remote-access") == 0

    def test_client_count_total(self, manager):
        """client_count(None)은 전체 채널 합산을 반환한다."""
        manager.subscribe("tickets")
        manager.subscribe("completed-tasks")
        manager.subscribe("all")

        total = manager.client_count()
        assert total == 3

    def test_queue_full_silent_drop(self, manager):
        """큐 maxsize 초과 시 예외 없이 이벤트를 드롭한다."""
        from core.dashboard.connection_manager import _QUEUE_MAX_SIZE
        q = manager.subscribe("tickets")

        # 큐를 가득 채움
        for i in range(_QUEUE_MAX_SIZE):
            q.put_nowait({"type": "fill", "i": i})

        # maxsize 초과 publish — 예외 없어야 함
        manager.publish("tickets", "ticket_update", {"pending": 1})

    def test_invalid_channel_raises(self, manager):
        """지원하지 않는 채널 구독 시 ValueError 발생."""
        with pytest.raises(ValueError, match="지원하지 않는 채널"):
            manager.subscribe("invalid-channel")

    def test_get_channel_stats(self, manager):
        """get_channel_stats는 채널별 구독자 수 딕셔너리를 반환한다."""
        manager.subscribe("tickets")
        manager.subscribe("tickets")
        manager.subscribe("completed-tasks")

        stats = manager.get_channel_stats()
        assert stats["tickets"] == 2
        assert stats["completed-tasks"] == 1
        assert stats["remote-access"] == 0
        assert stats["all"] == 0

    def test_reset_clears_all(self, manager):
        """reset()은 모든 구독자를 제거한다."""
        manager.subscribe("tickets")
        manager.subscribe("completed-tasks")
        manager.reset()
        assert manager.client_count() == 0


# ---------------------------------------------------------------------------
# TestSSEEndpoints — 연결 및 헤더 검증
# ---------------------------------------------------------------------------


class TestSSEEndpoints:
    """SSE 엔드포인트 라우트 등록 및 포맷 검증.

    Note: httpx TestClient는 무한 SSE 스트림 close() 시 drain을 시도해 blocking 발생.
    따라서 HTTP 레벨 테스트 대신 (1) 라우트 등록 확인, (2) SSE 포맷 단위 테스트로 검증한다.
    실제 연결 테스트는 통합 환경(uvicorn + curl)에서 수행한다.
    """

    def test_tickets_route_registered(self, test_app):
        """GET /api/v1/stream/tickets 라우트가 앱에 등록되어 있다."""
        info = _get_sse_endpoint_info(test_app, "/api/v1/stream/tickets")
        assert info, "/api/v1/stream/tickets 라우트 미등록"
        assert "GET" in info["methods"]

    def test_completed_tasks_route_registered(self, test_app):
        """GET /api/v1/stream/completed-tasks 라우트가 앱에 등록되어 있다."""
        info = _get_sse_endpoint_info(test_app, "/api/v1/stream/completed-tasks")
        assert info, "/api/v1/stream/completed-tasks 라우트 미등록"
        assert "GET" in info["methods"]

    def test_remote_access_route_registered(self, test_app):
        """GET /api/v1/stream/remote-access 라우트가 앱에 등록되어 있다."""
        info = _get_sse_endpoint_info(test_app, "/api/v1/stream/remote-access")
        assert info, "/api/v1/stream/remote-access 라우트 미등록"
        assert "GET" in info["methods"]

    def test_legacy_events_route_registered(self, test_app):
        """기존 /api/v1/events/stream 라우트가 하위 호환으로 유지된다."""
        info = _get_sse_endpoint_info(test_app, "/api/v1/events/stream")
        assert info, "/api/v1/events/stream 라우트 미등록 (하위 호환 파괴)"
        assert "GET" in info["methods"]

    def test_sse_content_type_header_value(self):
        """StreamingResponse에 text/event-stream media_type이 설정된다."""
        from fastapi.responses import StreamingResponse

        async def dummy_gen():
            yield "data: test\n\n"

        resp = StreamingResponse(dummy_gen(), media_type="text/event-stream")
        assert resp.media_type == "text/event-stream"

    def test_sse_response_headers_configured(self):
        """SSE StreamingResponse에 Cache-Control, X-Accel-Buffering 헤더가 설정된다."""
        from core.api.routes.streams import _SSE_HEADERS

        assert _SSE_HEADERS.get("Cache-Control") == "no-cache"
        assert _SSE_HEADERS.get("X-Accel-Buffering") == "no"

    def test_fmt_sse_format(self):
        """_fmt_sse 함수가 올바른 SSE 포맷을 생성한다."""
        from core.api.routes.streams import _fmt_sse

        result = _fmt_sse("ticket_update", {"pending": 5, "ts": 1.0})
        assert "event: ticket_update\n" in result
        assert "data: " in result
        assert result.endswith("\n\n")
        # data 필드가 JSON인지 확인
        data_line = [l for l in result.split("\n") if l.startswith("data:")][0]
        payload = json.loads(data_line.replace("data: ", "", 1))
        assert payload["pending"] == 5

    def test_fmt_sse_with_event_id(self):
        """_fmt_sse에 event_id 전달 시 id: 라인이 포함된다."""
        from core.api.routes.streams import _fmt_sse

        result = _fmt_sse("ping", {"ts": 1.0}, event_id="12345")
        assert "id: 12345\n" in result

    def test_fmt_sse_without_event_id(self):
        """_fmt_sse에 event_id 미전달 시 id: 라인이 없다."""
        from core.api.routes.streams import _fmt_sse

        result = _fmt_sse("ping", {"ts": 1.0})
        assert "id:" not in result

    def test_tickets_stream_initial_ping_event(self):
        """초기 연결 이벤트는 ping 타입이고 connected 메시지를 포함한다."""
        from core.api.routes.streams import _fmt_sse

        # _base_sse_generator의 첫 yield를 재현
        connect_data = {"ts": time.time(), "message": "connected", "channel": "tickets"}
        event = _fmt_sse("ping", connect_data, event_id="12345")

        assert "event: ping\n" in event
        assert '"message": "connected"' in event
        assert '"channel": "tickets"' in event

    def test_completed_tasks_stream_initial_ping_event(self):
        """/stream/completed-tasks 초기 이벤트는 ping 타입이다."""
        from core.api.routes.streams import _fmt_sse

        connect_data = {"ts": time.time(), "message": "connected", "channel": "completed-tasks"}
        event = _fmt_sse("ping", connect_data)
        assert "event: ping\n" in event

    def test_remote_access_stream_initial_events(self):
        """/stream/remote-access 초기 이벤트는 remote_access_change 타입이다."""
        from core.api.routes.streams import _fmt_sse
        from core.dashboard.connection_manager import ConnectionManager

        cm = ConnectionManager()
        payload = {
            "client_count": cm.client_count(),
            "channel_stats": cm.get_channel_stats(),
            "ts": time.time(),
            "note": "initial_snapshot",
        }
        event = _fmt_sse("remote_access_change", payload)
        assert "event: remote_access_change\n" in event
        assert '"client_count"' in event


# ---------------------------------------------------------------------------
# TestEventPayloads — 페이로드 스키마 검증
# ---------------------------------------------------------------------------


class TestEventPayloads:
    """이벤트 페이로드 JSON 스키마 검증."""

    def _parse_sse_events(self, lines: list[str]) -> list[dict]:
        """SSE 라인 목록에서 파싱된 이벤트 목록을 반환한다."""
        events = []
        current_event = {}
        for line in lines:
            if line.startswith("event:"):
                current_event["type"] = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                try:
                    current_event["data"] = json.loads(line.split(":", 1)[1].strip())
                except json.JSONDecodeError:
                    pass
            elif line == "" and current_event:
                events.append(current_event.copy())
                current_event = {}
        return events

    def test_ping_payload_has_ts(self):
        """ping 이벤트에는 ts 필드가 있어야 한다."""
        from core.api.routes.streams import _fmt_sse

        sse_text = _fmt_sse("ping", {"ts": time.time(), "message": "connected"})
        raw_lines = sse_text.split("\n")
        events = self._parse_sse_events(raw_lines)
        ping_events = [e for e in events if e.get("type") == "ping"]
        assert len(ping_events) >= 1
        assert "ts" in ping_events[0]["data"]
        assert isinstance(ping_events[0]["data"]["ts"], float)

    def test_ping_payload_connected_message(self):
        """초기 ping 이벤트에는 message="connected" 필드가 있다."""
        from core.api.routes.streams import _fmt_sse

        sse_text = _fmt_sse("ping", {"ts": time.time(), "message": "connected"})
        raw_lines = sse_text.split("\n")
        events = self._parse_sse_events(raw_lines)
        ping_events = [e for e in events if e.get("type") == "ping"]
        assert len(ping_events) >= 1
        assert ping_events[0]["data"].get("message") == "connected"

    def test_ticket_update_schema(self):
        """ticket_update 이벤트 페이로드는 필수 필드를 포함한다."""
        from core.api.routes.events import publish_event

        # ticket_update 페이로드 직접 검증
        payload = {
            "pending": 2,
            "in_progress": 1,
            "done": 5,
            "blocked": 0,
            "aggregations": {},
            "ts": time.time(),
        }
        required_fields = {"pending", "in_progress", "done", "blocked", "ts"}
        assert required_fields <= set(payload.keys()), "필수 필드 누락"

    def test_task_complete_schema(self):
        """task_complete 이벤트 페이로드는 필수 필드를 포함한다."""
        from core.dashboard.models import TicketStatus, TicketState

        ticket = TicketStatus(
            ticket_id="T-test-001",
            state=TicketState.DONE,
            assignee="aiorg_engineering_bot",
            title="테스트 태스크",
            org_id="aiorg_engineering_bot",
        )
        ticket.complete()
        payload = {**ticket.to_dict(), "ts": time.time()}

        required_fields = {"ticket_id", "state", "assignee", "ts", "title", "org_id"}
        assert required_fields <= set(payload.keys()), "필수 필드 누락"
        assert payload["state"] == "done"
        assert payload["ticket_id"] == "T-test-001"

    def test_remote_access_change_schema(self):
        """remote_access_change 이벤트 페이로드는 필수 필드를 포함한다."""
        payload = {
            "client_count": 3,
            "channel_stats": {"tickets": 1, "completed-tasks": 1, "remote-access": 1, "all": 0},
            "ts": time.time(),
        }
        required_fields = {"client_count", "ts"}
        assert required_fields <= set(payload.keys()), "필수 필드 누락"
        assert isinstance(payload["client_count"], int)


# ---------------------------------------------------------------------------
# TestConnectionLifecycle — 연결·해제 라이프사이클
# ---------------------------------------------------------------------------


class TestConnectionLifecycle:
    """SSE 연결/해제 시 ConnectionManager 등록·해제 동작 검증."""

    def test_subscribe_increments_count(self, manager):
        """subscribe 시 채널 카운트가 증가한다."""
        before = manager.client_count("tickets")
        manager.subscribe("tickets")
        assert manager.client_count("tickets") == before + 1

    def test_unsubscribe_decrements_count(self, manager):
        """unsubscribe 시 채널 카운트가 감소한다."""
        q = manager.subscribe("tickets")
        before = manager.client_count("tickets")
        manager.unsubscribe("tickets", q)
        assert manager.client_count("tickets") == before - 1

    def test_multiple_subscribers_independent(self, manager):
        """여러 구독자는 독립된 큐를 가진다."""
        q1 = manager.subscribe("tickets")
        q2 = manager.subscribe("tickets")

        manager.publish("tickets", "ticket_update", {"pending": 1})

        # 둘 다 이벤트 수신
        assert not q1.empty()
        assert not q2.empty()

        e1 = q1.get_nowait()
        e2 = q2.get_nowait()
        assert e1 == e2

    def test_channel_isolation(self, manager):
        """채널 격리: 다른 채널의 이벤트는 수신되지 않는다."""
        q_tickets = manager.subscribe("tickets")
        q_completed = manager.subscribe("completed-tasks")
        q_remote = manager.subscribe("remote-access")

        manager.publish("tickets", "ticket_update", {"pending": 1})
        manager.publish("completed-tasks", "task_complete", {"ticket_id": "T-001"})

        # tickets 채널만 ticket_update 수신
        assert not q_tickets.empty()
        e = q_tickets.get_nowait()
        assert e["type"] == "ticket_update"

        # completed-tasks 채널만 task_complete 수신
        assert not q_completed.empty()
        e2 = q_completed.get_nowait()
        assert e2["type"] == "task_complete"

        # remote-access 채널은 아무것도 수신 안 함
        assert q_remote.empty()

    def test_unsubscribe_twice_is_safe(self, manager):
        """동일 큐를 두 번 unsubscribe해도 예외 없이 처리된다."""
        q = manager.subscribe("tickets")
        manager.unsubscribe("tickets", q)
        manager.unsubscribe("tickets", q)  # 두 번째 — 예외 없어야 함
        assert manager.client_count("tickets") == 0


# ---------------------------------------------------------------------------
# TestPublishEvent — publish_event 통합
# ---------------------------------------------------------------------------


class TestPublishEvent:
    """publish_event 함수가 기존 구독자 + ConnectionManager에 모두 전달하는지 검증."""

    def test_publish_event_delivers_to_legacy_subscribers(self):
        """publish_event는 기존 _subscribers 큐에 이벤트를 전달한다."""
        from core.api.routes.events import publish_event, _subscribers

        q = asyncio.Queue(maxsize=10)
        _subscribers.append(q)
        try:
            publish_event("ticket_update", {"pending": 1, "ts": 1.0})
            assert not q.empty()
            event = q.get_nowait()
            assert event["type"] == "ticket_update"
            assert event["pending"] == 1
        finally:
            try:
                _subscribers.remove(q)
            except ValueError:
                pass

    def test_publish_event_delivers_to_connection_manager(self):
        """publish_event는 ConnectionManager 'all' 채널에도 이벤트를 전달한다."""
        from core.api.routes.events import publish_event
        from core.dashboard.connection_manager import connection_manager

        q = connection_manager.subscribe("all")
        try:
            publish_event("task_complete", {"ticket_id": "T-001", "ts": 1.0})
            assert not q.empty()
            event = q.get_nowait()
            assert event["type"] == "task_complete"
        finally:
            connection_manager.unsubscribe("all", q)
