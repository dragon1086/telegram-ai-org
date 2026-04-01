"""tests/test_dashboard_server.py — dashboard.py 서버 임포트 및 라우트 검증.

테스트 범위:
    TestDashboardImport     — dashboard.py 임포트 + FastAPI 앱 속성 검증
    TestDashboardRoutes     — 필수 라우트 등록 여부 확인
    TestSnapshotEndpoint    — /api/v1/dashboard/snapshot 응답 구조 검증
    TestCharactersEndpoint  — /api/v1/dashboard/characters 응답 검증
    TestStaticMounts        — 정적 파일 마운트 경로 존재 여부 확인
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _route_paths(app: FastAPI) -> set[str]:
    """앱에 등록된 APIRoute 경로 집합을 반환한다."""
    return {r.path for r in app.routes if isinstance(r, APIRoute)}


def _get_route(app: FastAPI, path: str) -> APIRoute | None:
    """특정 경로의 APIRoute를 반환. 없으면 None."""
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path == path:
            return r
    return None


# ---------------------------------------------------------------------------
# TestDashboardImport — 임포트 및 기본 속성
# ---------------------------------------------------------------------------


class TestDashboardImport:
    """dashboard.py 를 임포트할 수 있고 FastAPI 인스턴스를 노출한다."""

    def test_dashboard_module_importable(self):
        """dashboard 모듈을 임포트해도 예외가 발생하지 않는다."""
        import dashboard  # noqa: F401 — 임포트 자체가 목적

    def test_app_is_fastapi_instance(self):
        """dashboard.app 은 FastAPI 인스턴스다."""
        import dashboard
        assert isinstance(dashboard.app, FastAPI)

    def test_app_title(self):
        """dashboard.app 타이틀이 설정되어 있다."""
        import dashboard
        assert dashboard.app.title  # 비어 있지 않으면 통과

    def test_app_version(self):
        """dashboard.app 버전이 설정되어 있다."""
        import dashboard
        assert dashboard.app.version  # 비어 있지 않으면 통과

    def test_dashboard_dir_constant(self):
        """DASHBOARD_DIR 상수가 dashboard/ 디렉토리를 가리킨다."""
        import dashboard
        assert dashboard.DASHBOARD_DIR.name == "dashboard"


# ---------------------------------------------------------------------------
# TestDashboardRoutes — 라우트 등록 여부
# ---------------------------------------------------------------------------


class TestDashboardRoutes:
    """필수 API 라우트가 dashboard.app 에 등록되어 있다."""

    @pytest.fixture(autouse=True)
    def _import_app(self):
        import dashboard
        self.app = dashboard.app

    def test_snapshot_route_registered(self):
        """/api/v1/dashboard/snapshot 라우트가 등록되어 있다."""
        route = _get_route(self.app, "/api/v1/dashboard/snapshot")
        assert route is not None, "/api/v1/dashboard/snapshot 라우트 미등록"
        assert "GET" in route.methods

    def test_characters_route_registered(self):
        """/api/v1/dashboard/characters 라우트가 등록되어 있다."""
        route = _get_route(self.app, "/api/v1/dashboard/characters")
        assert route is not None, "/api/v1/dashboard/characters 라우트 미등록"
        assert "GET" in route.methods

    def test_events_stream_route_registered(self):
        """/api/v1/events/stream SSE 라우트가 등록되어 있다."""
        route = _get_route(self.app, "/api/v1/events/stream")
        assert route is not None, "/api/v1/events/stream 라우트 미등록"

    def test_health_route_registered(self):
        """헬스체크 라우트가 하나 이상 등록되어 있다."""
        paths = _route_paths(self.app)
        health_routes = [p for p in paths if "health" in p]
        assert len(health_routes) >= 1, "헬스체크 라우트 미등록"

    def test_root_route_registered(self):
        """루트 경로(/) 가 등록되어 있다."""
        route = _get_route(self.app, "/")
        assert route is not None, "/ 라우트 미등록"
        assert "GET" in route.methods


# ---------------------------------------------------------------------------
# TestSnapshotEndpoint — 스냅샷 응답 구조
# ---------------------------------------------------------------------------


class TestSnapshotEndpoint:
    """/api/v1/dashboard/snapshot 응답 스키마 검증."""

    @pytest.fixture
    def mock_pusher(self):
        """DashboardPusher 목 객체 — get_snapshot()이 고정 데이터 반환."""
        pusher = MagicMock()
        pusher.get_snapshot.return_value = {
            "counts": {
                "pending":     2,
                "in_progress": 1,
                "done":        10,
                "blocked":     0,
            },
            "aggregations": {
                "1h": {"throughput": 5.0, "completed": 3, "avg_duration": 120.0},
            },
            "recent_completed": [],
            "ts": 1_700_000_000.0,
        }
        return pusher

    @pytest.fixture
    def test_client(self, mock_pusher):
        """pusher가 주입된 TestClient."""
        import dashboard
        app = dashboard.app

        # lifespan 없이 pusher를 직접 state에 주입
        app.state.pusher = mock_pusher
        return TestClient(app, raise_server_exceptions=True)

    def test_snapshot_returns_200(self, test_client):
        """/api/v1/dashboard/snapshot 은 HTTP 200을 반환한다."""
        resp = test_client.get("/api/v1/dashboard/snapshot")
        assert resp.status_code == 200

    def test_snapshot_has_counts_key(self, test_client):
        """스냅샷 응답에 counts 키가 있다."""
        resp = test_client.get("/api/v1/dashboard/snapshot")
        data = resp.json()
        assert "counts" in data, f"counts 키 없음: {data}"

    def test_snapshot_counts_has_required_fields(self, test_client):
        """counts 딕셔너리에 pending/in_progress/done/blocked 필드가 있다."""
        resp  = test_client.get("/api/v1/dashboard/snapshot")
        counts = resp.json().get("counts", {})
        for field in ("pending", "in_progress", "done", "blocked"):
            assert field in counts, f"counts.{field} 누락"

    def test_snapshot_has_aggregations_key(self, test_client):
        """스냅샷 응답에 aggregations 키가 있다."""
        resp = test_client.get("/api/v1/dashboard/snapshot")
        data = resp.json()
        assert "aggregations" in data, f"aggregations 키 없음: {data}"

    def test_snapshot_aggregations_1h(self, test_client):
        """aggregations['1h'] 에 throughput/completed 필드가 있다."""
        resp    = test_client.get("/api/v1/dashboard/snapshot")
        agg_1h  = resp.json().get("aggregations", {}).get("1h", {})
        assert "throughput" in agg_1h, "aggregations.1h.throughput 누락"
        assert "completed"  in agg_1h, "aggregations.1h.completed 누락"

    def test_snapshot_recent_completed_is_list(self, test_client):
        """recent_completed 필드가 리스트다."""
        resp = test_client.get("/api/v1/dashboard/snapshot")
        data = resp.json()
        assert isinstance(data.get("recent_completed", []), list)

    def test_snapshot_without_pusher_returns_error(self):
        """pusher가 초기화되지 않으면 error 키를 반환한다."""
        import dashboard
        app = dashboard.app
        # pusher 제거
        if hasattr(app.state, "pusher"):
            del app.state.pusher

        client = TestClient(app, raise_server_exceptions=True)
        resp   = client.get("/api/v1/dashboard/snapshot")
        assert resp.status_code == 200
        data   = resp.json()
        assert "error" in data, "pusher 미초기화 시 error 키 없음"


# ---------------------------------------------------------------------------
# TestCharactersEndpoint — 캐릭터 응답 검증
# ---------------------------------------------------------------------------


class TestCharactersEndpoint:
    """/api/v1/dashboard/characters 응답 검증."""

    @pytest.fixture
    def test_client(self):
        import dashboard
        return TestClient(dashboard.app, raise_server_exceptions=True)

    def test_characters_returns_200(self, test_client):
        """/api/v1/dashboard/characters 는 HTTP 200을 반환한다."""
        resp = test_client.get("/api/v1/dashboard/characters")
        assert resp.status_code == 200

    def test_characters_is_dict(self, test_client):
        """응답이 딕셔너리(오브젝트) 형태다."""
        resp = test_client.get("/api/v1/dashboard/characters")
        data = resp.json()
        assert isinstance(data, dict), f"dict 아님: {type(data)}"

    def test_characters_not_empty(self, test_client):
        """캐릭터 데이터가 비어 있지 않다."""
        resp = test_client.get("/api/v1/dashboard/characters")
        data = resp.json()
        assert len(data) > 0, "캐릭터 데이터 비어 있음"

    def test_characters_each_has_required_fields(self, test_client):
        """각 캐릭터 항목에 emoji/name/color 필드가 있다."""
        resp = test_client.get("/api/v1/dashboard/characters")
        data = resp.json()
        for org_id, char in data.items():
            for field in ("emoji", "name", "color"):
                assert field in char, f"{org_id} 캐릭터에 {field} 필드 없음"

    def test_pm_bot_character_present(self, test_client):
        """PM 봇(aiorg_pm_bot) 캐릭터가 포함되어 있다."""
        resp = test_client.get("/api/v1/dashboard/characters")
        data = resp.json()
        assert "aiorg_pm_bot" in data, "aiorg_pm_bot 캐릭터 없음"

    def test_engineering_bot_character_present(self, test_client):
        """개발실 봇(aiorg_engineering_bot) 캐릭터가 포함되어 있다."""
        resp = test_client.get("/api/v1/dashboard/characters")
        data = resp.json()
        assert "aiorg_engineering_bot" in data, "aiorg_engineering_bot 캐릭터 없음"


# ---------------------------------------------------------------------------
# TestStaticMounts — 정적 파일 마운트 경로 존재 여부
# ---------------------------------------------------------------------------


class TestStaticMounts:
    """대시보드 정적 파일 디렉토리가 존재하고 마운트된다."""

    def test_dashboard_dir_exists(self):
        """dashboard/ 디렉토리가 존재한다."""
        import dashboard
        assert dashboard.DASHBOARD_DIR.exists(), \
            f"dashboard/ 디렉토리 없음: {dashboard.DASHBOARD_DIR}"

    def test_dashboard_index_html_exists(self):
        """dashboard/index.html 파일이 존재한다."""
        import dashboard
        index = dashboard.DASHBOARD_DIR / "index.html"
        assert index.exists(), f"index.html 없음: {index}"

    def test_dashboard_styles_dir_exists(self):
        """dashboard/styles/ 디렉토리가 존재한다."""
        import dashboard
        styles = dashboard.DASHBOARD_DIR / "styles"
        assert styles.exists(), f"styles/ 디렉토리 없음: {styles}"

    def test_dashboard_components_dir_exists(self):
        """dashboard/components/ 디렉토리가 존재한다."""
        import dashboard
        components = dashboard.DASHBOARD_DIR / "components"
        assert components.exists(), f"components/ 디렉토리 없음: {components}"

    def test_dashboard_services_dir_exists(self):
        """dashboard/services/ 디렉토리가 존재하고 client.js가 있다."""
        import dashboard
        services   = dashboard.DASHBOARD_DIR / "services"
        client_js  = services / "client.js"
        assert services.exists(),   f"services/ 디렉토리 없음: {services}"
        assert client_js.exists(),  f"client.js 없음: {client_js}"

    def test_root_serves_html(self):
        """루트(/) 에 GET 요청 시 HTML 응답을 반환한다."""
        import dashboard
        client = TestClient(dashboard.app, raise_server_exceptions=True)
        resp   = client.get("/")
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "text/html" in content_type, f"content-type 이 text/html 아님: {content_type}"
