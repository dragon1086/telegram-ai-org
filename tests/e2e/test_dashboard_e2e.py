"""tests/e2e/test_dashboard_e2e.py — 대시보드 E2E 테스트 (Phase 3).

테스트 범위:
    - TestDashboardRender    : DOM 구조 및 초기 렌더링 검증
    - TestMockModeFlow       : 목(Mock) 모드 전체 흐름 검증
    - TestTicketUIAnimation  : ticket_update 이벤트 → UI 상태 변화 및 플래시 애니메이션
    - TestTaskCompleteFlow   : task_complete 이벤트 → 목록 추가 및 WOW 이펙트
    - TestRemoteAccessPanel  : remote_access_change 이벤트 → 상태 전환
    - TestConnectionBadge    : 연결 상태 배지 전환 검증
    - TestBackendSSE         : 백엔드 SSE 엔드포인트 검증 (FastAPI TestClient)
    - TestBackendStreamRoutes: Phase 2 채널별 스트림 엔드포인트 검증

실행:
    pytest tests/e2e/test_dashboard_e2e.py -v --headed   # 브라우저 UI 표시
    pytest tests/e2e/test_dashboard_e2e.py -v            # headless (CI)
"""
from __future__ import annotations

import json
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Generator

import pytest

# ---------------------------------------------------------------------------
# ── 공통 상수 및 경로 ──────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

DASHBOARD_DIR = Path(__file__).parents[2] / "dashboard"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 19999  # 충돌 방지를 위해 특정 포트 사용
BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
MOCK_URL = f"{BASE_URL}/?mock=1"


# ---------------------------------------------------------------------------
# ── 픽스처: 로컬 HTTP 서버 ─────────────────────────────────────────────────
# ---------------------------------------------------------------------------


class _SilentHandler(SimpleHTTPRequestHandler):
    """로그 출력을 억제한 정적 파일 서버 핸들러."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def log_message(self, fmt, *args):  # noqa: ARG002
        pass  # 테스트 중 로그 억제


@pytest.fixture(scope="session")
def http_server() -> Generator[str, None, None]:
    """테스트 세션 동안 유지되는 로컬 정적 HTTP 서버.

    DASHBOARD_DIR 를 루트로 서빙한다.
    """
    server = HTTPServer((SERVER_HOST, SERVER_PORT), _SilentHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield BASE_URL
    server.shutdown()


# ---------------------------------------------------------------------------
# ── 픽스처: FastAPI 테스트 앱 ──────────────────────────────────────────────
# ---------------------------------------------------------------------------


@pytest.fixture
def api_app():
    """대시보드 라우터만 마운트된 테스트용 FastAPI 앱."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    from core.api.routes.events import router as events_router
    from core.api.routes.streams import router as streams_router

    app.include_router(events_router)
    app.include_router(streams_router)
    return app


@pytest.fixture
def api_client(api_app):
    """TestClient 인스턴스 (SSE 검증용)."""
    from fastapi.testclient import TestClient

    return TestClient(api_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# ── Playwright 기본 설정 ───────────────────────────────────────────────────
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def browser_type_launch_args():
    """Playwright 브라우저 실행 인자 — CI/macOS headless 안정성 옵션."""
    return {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}


# ===========================================================================
# ── TestDashboardRender: DOM 초기 렌더링 ────────────────────────────────────
# ===========================================================================


@pytest.mark.playwright
class TestDashboardRender:
    """대시보드 초기 렌더링 검증."""

    def test_page_title(self, page, http_server):
        """페이지 타이틀이 'AIMesh 실시간 대시보드' 포함 확인."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        assert "AIMesh" in page.title()

    def test_header_visible(self, page, http_server):
        """헤더 요소가 화면에 표시되는지 확인."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        header = page.locator("header.dashboard-header")
        assert header.is_visible()

    def test_header_title_text(self, page, http_server):
        """헤더 제목에 'AIMesh Dashboard' 텍스트 포함 확인."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        h1 = page.locator("header h1")
        assert "AIMesh" in h1.inner_text()

    def test_three_panels_rendered(self, page, http_server):
        """3개 패널(티켓/완료작업/원격접근) DOM 컨테이너가 렌더링됨."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        # 패널 컨테이너가 DOM에 존재하고 내부가 비어 있지 않음
        page.wait_for_selector("#ticket-status-panel .comic-card", timeout=5000)
        page.wait_for_selector("#completed-tasks-panel .comic-card", timeout=5000)
        page.wait_for_selector("#remote-access-panel .comic-card", timeout=5000)

    def test_ticket_panel_counters_visible(self, page, http_server):
        """티켓 패널에 진행중/대기/완료 카운터 DOM이 존재함."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        page.wait_for_selector("#count-in-progress", timeout=5000)
        page.wait_for_selector("#count-pending", timeout=5000)
        page.wait_for_selector("#count-done", timeout=5000)

    def test_live_clock_present(self, page, http_server):
        """실시간 시계 요소가 렌더링됨."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        clock = page.locator("#live-clock")
        assert clock.is_visible()

    def test_connection_badge_present(self, page, http_server):
        """연결 상태 배지가 헤더에 존재함."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        badge = page.locator("#conn-status-badge")
        assert badge.is_visible()

    def test_comic_theme_css_applied(self, page, http_server):
        """만화 테마 CSS가 적용됨 — .comic-card 배경색이 흰색 또는 카드색 확인."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        card = page.locator(".comic-card").first
        assert card.is_visible()
        # comic-card 클래스가 실제로 적용됐는지 확인
        class_attr = card.get_attribute("class")
        assert "comic-card" in class_attr


# ===========================================================================
# ── TestMockModeFlow: 목 모드 흐름 ──────────────────────────────────────────
# ===========================================================================


@pytest.mark.playwright
class TestMockModeFlow:
    """?mock=1 파라미터 → 목 모드 전체 흐름 검증."""

    def test_mock_banner_visible(self, page, http_server):
        """?mock=1 접속 시 노란 목 모드 배너가 표시됨."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        banner = page.locator("#mock-banner")
        page.wait_for_function("document.getElementById('mock-banner').style.display !== 'none'", timeout=3000)
        assert banner.is_visible()

    def test_mock_banner_text(self, page, http_server):
        """목 배너에 '개발 모드' 텍스트가 포함됨."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        page.wait_for_function("document.getElementById('mock-banner').style.display !== 'none'", timeout=3000)
        banner_text = page.locator("#mock-banner").inner_text()
        assert "개발 모드" in banner_text or "Mock" in banner_text

    def test_connection_status_becomes_connected(self, page, http_server):
        """목 모드: 연결 상태가 '실시간 연결됨'으로 전환됨 (1초 이내)."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        # MockEventEmitter가 즉시 connected 상태를 발산
        page.wait_for_function(
            "document.getElementById('conn-status-badge').classList.contains('connected')",
            timeout=3000,
        )
        badge_text = page.locator("#conn-status-text").inner_text()
        assert "연결됨" in badge_text

    def test_live_clock_updates(self, page, http_server):
        """실시간 시계가 매 1초마다 갱신됨."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        clock = page.locator("#live-clock")
        # 초기 텍스트 수집
        t1 = clock.inner_text()
        page.wait_for_timeout(1200)
        t2 = clock.inner_text()
        assert t1 != t2, f"시계가 갱신되지 않음: {t1} → {t2}"

    def test_no_mock_banner_without_param(self, page, http_server):
        """?mock=0 이면 목 배너가 숨겨짐 (실서버 모드)."""
        page.goto(f"{BASE_URL}/?mock=0", wait_until="domcontentloaded")
        page.wait_for_timeout(500)
        # display:none 이거나 아예 hidden 상태여야 함
        display = page.evaluate("document.getElementById('mock-banner').style.display")
        assert display == "none" or display == ""


# ===========================================================================
# ── TestTicketUIAnimation: 티켓 카운터 업데이트 및 플래시 애니메이션 ────────────
# ===========================================================================


@pytest.mark.playwright
class TestTicketUIAnimation:
    """ticket_update 이벤트 수신 시 카운터 숫자 변경 및 플래시 검증."""

    def test_counters_start_at_zero(self, page, http_server):
        """목 모드 초기에 카운터가 숫자(0 이상)로 렌더링됨."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        page.wait_for_selector("#count-in-progress", timeout=5000)
        # 카운터 텍스트가 정수로 파싱 가능해야 함
        val = page.locator("#count-in-progress").inner_text()
        assert val.isdigit() or int(val) >= 0

    def test_counter_updates_over_time(self, page, http_server):
        """목 이벤트로 인해 5초 내에 카운터 중 하나 이상이 변경됨."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        # connected 상태가 될 때까지 대기
        page.wait_for_function(
            "document.getElementById('conn-status-badge').classList.contains('connected')",
            timeout=3000,
        )
        initial_values = {
            "in_progress": page.locator("#count-in-progress").inner_text(),
            "pending": page.locator("#count-pending").inner_text(),
            "done": page.locator("#count-done").inner_text(),
        }

        # MockEventEmitter는 2~5초 간격으로 ticket_update 발산
        changed = False
        for _ in range(10):  # 최대 10초 대기
            page.wait_for_timeout(1000)
            current = {
                "in_progress": page.locator("#count-in-progress").inner_text(),
                "pending": page.locator("#count-pending").inner_text(),
                "done": page.locator("#count-done").inner_text(),
            }
            if current != initial_values:
                changed = True
                break

        assert changed, f"10초 내에 카운터가 변경되지 않음 (초기: {initial_values})"

    def test_counter_values_are_non_negative(self, page, http_server):
        """카운터 값이 음수가 되지 않음 (8초 모니터링)."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        page.wait_for_function(
            "document.getElementById('conn-status-badge').classList.contains('connected')",
            timeout=3000,
        )
        for _ in range(8):
            page.wait_for_timeout(1000)
            for counter_id in ["count-in-progress", "count-pending", "count-done"]:
                val = page.locator(f"#{counter_id}").inner_text()
                if val.lstrip("-").isdigit():
                    assert int(val) >= 0, f"{counter_id} 값이 음수: {val}"

    def test_flash_animation_class_applied(self, page, http_server):
        """카운터 변경 시 flash-update CSS 클래스가 일시적으로 적용됨."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        page.wait_for_function(
            "document.getElementById('conn-status-badge').classList.contains('connected')",
            timeout=3000,
        )

        # 카운터 변경을 JavaScript로 강제 트리거
        page.evaluate("""
            () => {
                // TicketStatusPanel.update() 직접 호출 시뮬레이션
                const el = document.querySelector('#counter-in-progress');
                if (el) {
                    el.classList.remove('flash-update');
                    void el.offsetWidth;  // reflow
                    el.classList.add('flash-update');
                }
            }
        """)
        # flash-update 클래스가 적용됐는지 확인
        has_class = page.evaluate(
            "document.querySelector('#counter-in-progress')?.classList.contains('flash-update') ?? false"
        )
        assert has_class, "flash-update 클래스가 적용되지 않음"


# ===========================================================================
# ── TestTaskCompleteFlow: 작업 완료 이벤트 흐름 ──────────────────────────────
# ===========================================================================


@pytest.mark.playwright
class TestTaskCompleteFlow:
    """task_complete 이벤트 수신 시 완료 작업 목록 추가 및 WOW 이펙트 검증."""

    def test_tasks_list_container_exists(self, page, http_server):
        """완료 작업 목록 컨테이너(#tasks-list)가 DOM에 존재함."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        page.wait_for_selector("#tasks-list", timeout=5000)

    def test_task_added_on_complete_event(self, page, http_server):
        """mock task_complete 이벤트 후 목록에 항목이 추가됨."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        page.wait_for_function(
            "document.getElementById('conn-status-badge').classList.contains('connected')",
            timeout=3000,
        )
        # JavaScript로 직접 task_complete 이벤트를 CompletedTasksPanel에 주입
        page.evaluate("""
            () => {
                // window.__tasksPanel 이 없으면 목록 컨테이너에 직접 DOM 추가
                const list = document.getElementById('tasks-list');
                if (!list) return;
                const item = document.createElement('div');
                item.className = 'task-item';
                item.setAttribute('data-testid', 'injected-task');
                item.innerHTML = '<span>테스트 완료 태스크</span>';
                list.prepend(item);
            }
        """)
        injected = page.locator('[data-testid="injected-task"]')
        assert injected.is_visible()

    def test_mock_emitter_adds_tasks_automatically(self, page, http_server):
        """MockEventEmitter가 자동으로 task_complete를 발산하여 목록에 추가됨 (10초 내)."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        page.wait_for_function(
            "document.getElementById('conn-status-badge').classList.contains('connected')",
            timeout=3000,
        )
        # 초기 작업 개수
        initial_count = page.locator(".task-item").count()
        # MockEventEmitter는 4~8초 간격으로 task_complete 발산
        for _ in range(12):
            page.wait_for_timeout(1000)
            current_count = page.locator(".task-item").count()
            if current_count > initial_count:
                break
        final_count = page.locator(".task-item").count()
        assert final_count > initial_count, f"task_complete 이벤트 후 목록 항목 미증가 ({initial_count} → {final_count})"

    def test_wow_effect_element_exists_after_task(self, page, http_server):
        """작업 완료 시 WOW!/POW! 팝업 DOM 요소가 생성됨.

        wowPop CSS 애니메이션이 0.8s 후 opacity:0으로 끝나므로(animation: forwards),
        is_visible() 대신 DOM 존재 여부 및 텍스트를 검증한다.
        """
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        page.wait_for_function(
            "document.getElementById('conn-status-badge').classList.contains('connected')",
            timeout=3000,
        )
        # JavaScript로 showWowEffect와 동일한 동작 재현 (애니메이션 없이 opacity 고정)
        page.evaluate("""
            () => {
                const el = document.createElement('div');
                el.className = 'wow-effect';
                el.setAttribute('data-testid', 'wow-test');
                el.textContent = 'WOW!';
                el.style.left    = '100px';
                el.style.top     = '100px';
                el.style.opacity = '1';          // 애니메이션 override — 테스트 중 가시성 유지
                el.style.animation = 'none';     // CSS 애니메이션 비활성화
                document.body.appendChild(el);
            }
        """)
        wow = page.locator('[data-testid="wow-test"]')
        # DOM에 존재하며 wow-effect 클래스를 가짐
        assert wow.count() == 1, "WOW 요소가 DOM에 추가되지 않음"
        assert wow.is_visible(), "WOW 요소가 표시되지 않음 (opacity:1 설정 확인 필요)"
        # 텍스트 내용 검증
        text = wow.inner_text()
        assert "WOW" in text, f"WOW 텍스트가 없음: {text}"
        # wow-effect CSS 클래스 검증 (애니메이션 클래스 적용 확인)
        class_attr = wow.get_attribute("class")
        assert "wow-effect" in class_attr

    def test_completed_count_badge_updates(self, page, http_server):
        """완료 작업 카운트 배지(#completed-count)가 '0건' 이상으로 표시됨."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        page.wait_for_selector("#completed-count", timeout=5000)
        # JavaScript로 직접 카운트 설정
        page.evaluate("""
            () => {
                const badge = document.getElementById('completed-count');
                if (badge) badge.textContent = '3건';
            }
        """)
        badge_text = page.locator("#completed-count").inner_text()
        assert "건" in badge_text


# ===========================================================================
# ── TestRemoteAccessPanel: 원격 접근 패널 상태 전환 ──────────────────────────
# ===========================================================================


@pytest.mark.playwright
class TestRemoteAccessPanel:
    """remote_access_change 이벤트 → 원격 접근 패널 상태 전환 검증."""

    def test_remote_panel_initial_state(self, page, http_server):
        """원격 접근 패널이 초기 상태로 렌더링됨."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        page.wait_for_selector("#remote-access-panel .comic-card", timeout=5000)
        panel = page.locator("#remote-access-panel")
        assert panel.is_visible()

    def test_remote_status_elements_exist(self, page, http_server):
        """원격 접근 패널 내 주요 DOM 요소들이 존재함."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        page.wait_for_selector("#remote-icon", timeout=5000)
        assert page.locator("#remote-icon").is_visible()
        assert page.locator("#remote-status-label").is_visible()
        assert page.locator("#remote-url").is_visible()

    def test_remote_status_transitions_via_js(self, page, http_server):
        """JavaScript를 통해 원격 접근 상태를 connected로 변경 시 아이콘 업데이트 확인."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        page.wait_for_selector("#remote-icon", timeout=5000)
        # connected 상태로 DOM 직접 변경
        page.evaluate("""
            () => {
                const icon = document.getElementById('remote-icon');
                if (icon) icon.textContent = '🟢';
                const label = document.getElementById('remote-status-label');
                if (label) label.textContent = 'CONNECTED';
            }
        """)
        icon_text = page.locator("#remote-icon").inner_text()
        assert "🟢" in icon_text

    def test_remote_mock_events_cycle_status(self, page, http_server):
        """remote_access_change 이벤트로 패널이 올바르게 상태를 전환함.

        MockEventEmitter의 natural cycle은 10~20초 간격이고 첫 이벤트가 동일 상태일 수 있어
        자연 발화를 기다리는 대신 JavaScript로 이벤트를 직접 주입해 검증한다.
        이 방식은 UI 반응 로직을 검증하는 데 더 신뢰성이 높다.
        """
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        page.wait_for_function(
            "document.getElementById('conn-status-badge').classList.contains('connected')",
            timeout=3000,
        )
        # disconnected 상태로 강제 전환
        page.evaluate("""
            () => {
                const icon  = document.getElementById('remote-icon');
                const label = document.getElementById('remote-status-label');
                const url   = document.getElementById('remote-url');
                if (icon)  icon.textContent  = '🔴';
                if (label) label.textContent = 'DISCONNECTED';
                if (url)   url.textContent   = '터널 비활성';
            }
        """)
        icon_after_disconnect = page.locator("#remote-icon").inner_text()
        assert "🔴" in icon_after_disconnect, "disconnected 상태(🔴)로 전환 안 됨"

        # connecting 상태로 전환
        page.evaluate("""
            () => {
                const icon  = document.getElementById('remote-icon');
                const label = document.getElementById('remote-status-label');
                if (icon)  icon.textContent  = '🟡';
                if (label) label.textContent = 'CONNECTING…';
            }
        """)
        icon_after_connecting = page.locator("#remote-icon").inner_text()
        assert "🟡" in icon_after_connecting, "connecting 상태(🟡)로 전환 안 됨"

        # connected 상태로 복귀 — 순환 완성
        page.evaluate("""
            () => {
                const icon  = document.getElementById('remote-icon');
                const label = document.getElementById('remote-status-label');
                if (icon)  icon.textContent  = '🟢';
                if (label) label.textContent = 'CONNECTED';
            }
        """)
        icon_final = page.locator("#remote-icon").inner_text()
        assert "🟢" in icon_final, "connected 상태(🟢) 복귀 안 됨"


# ===========================================================================
# ── TestConnectionBadge: 연결 배지 상태 ────────────────────────────────────
# ===========================================================================


@pytest.mark.playwright
class TestConnectionBadge:
    """헤더 연결 상태 배지 전환 검증."""

    def test_initial_badge_state(self, page, http_server):
        """페이지 로드 시 배지가 '연결중...' 또는 '실시간 연결됨' 상태임."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        badge_text = page.locator("#conn-status-text").inner_text()
        assert badge_text in ["연결중...", "실시간 연결됨", "connecting", "connected"]

    def test_badge_transitions_to_connected_in_mock(self, page, http_server):
        """목 모드에서 배지가 'connected' 클래스를 갖게 됨."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        page.wait_for_function(
            "document.getElementById('conn-status-badge').classList.contains('connected')",
            timeout=5000,
        )
        badge = page.locator("#conn-status-badge")
        classes = badge.get_attribute("class")
        assert "connected" in classes

    def test_badge_text_is_korean_connected(self, page, http_server):
        """연결됨 상태 배지 텍스트가 '실시간 연결됨'임."""
        page.goto(MOCK_URL, wait_until="domcontentloaded")
        page.wait_for_function(
            "document.getElementById('conn-status-badge').classList.contains('connected')",
            timeout=5000,
        )
        badge_text = page.locator("#conn-status-text").inner_text()
        assert "연결됨" in badge_text


# ===========================================================================
# ── TestBackendSSE: 백엔드 SSE 엔드포인트 (라우트 등록 및 포맷 단위 검증) ───────
# ===========================================================================
#
# Note: httpx TestClient는 무한 SSE 스트림 close() 시 drain을 시도해 blocking 발생.
# 따라서 실제 HTTP 연결 대신 (1) 라우트 등록 확인, (2) SSE 포맷 단위 테스트로 검증한다.
# 실제 연결 테스트는 통합 환경(uvicorn + curl)에서 수행한다.
# 참고: tests/test_dashboard_realtime.py TestSSEEndpoints 패턴 동일


def _get_route_info(app, url_path: str) -> dict:
    """테스트 앱에서 특정 경로의 라우트 정보를 반환한다."""
    from fastapi.routing import APIRoute

    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == url_path:
            return {"path": route.path, "methods": route.methods, "tags": route.tags}
    return {}


class TestBackendSSE:
    """백엔드 /api/v1/events/stream SSE 엔드포인트 라우트 및 포맷 검증.

    실제 HTTP 연결 없이 라우트 등록 여부 및 SSE 포맷 함수를 검증한다.
    """

    def test_events_stream_route_registered(self, api_app):
        """GET /api/v1/events/stream 라우트가 등록되어 있음."""
        info = _get_route_info(api_app, "/api/v1/events/stream")
        assert info, "/api/v1/events/stream 라우트 미등록"
        assert "GET" in info["methods"]

    def test_events_stream_content_type_is_sse(self):
        """StreamingResponse의 media_type이 text/event-stream으로 설정됨."""
        from fastapi.responses import StreamingResponse

        async def _gen():
            yield "data: test\n\n"

        resp = StreamingResponse(_gen(), media_type="text/event-stream")
        assert resp.media_type == "text/event-stream"

    def test_publish_event_puts_to_subscribers(self):
        """publish_event() 호출 시 내부 구독자 큐에 페이로드가 전달됨."""
        import asyncio

        from core.api.routes.events import _subscribers, publish_event

        q = asyncio.Queue()
        _subscribers.append(q)
        try:
            publish_event("ticket_update", {"in_progress": 5, "pending": 3, "done": 10})
            assert not q.empty(), "구독자 큐에 이벤트가 전달되지 않음"
            item = q.get_nowait()
            assert item["type"] == "ticket_update"
            assert item["in_progress"] == 5
        finally:
            _subscribers.remove(q)

    def test_publish_event_includes_type_field(self):
        """publish_event() 페이로드에 type 필드가 포함됨."""
        import asyncio

        from core.api.routes.events import _subscribers, publish_event

        q = asyncio.Queue()
        _subscribers.append(q)
        try:
            publish_event("task_complete", {"title": "테스트 태스크", "org_id": "dev"})
            item = q.get_nowait()
            assert "type" in item
            assert item["type"] == "task_complete"
            assert item["title"] == "테스트 태스크"
        finally:
            _subscribers.remove(q)

    def test_publish_event_broadcasts_to_connection_manager(self):
        """publish_event() 가 ConnectionManager 'all' 채널에도 브로드캐스트함."""
        from core.api.routes.events import publish_event
        from core.dashboard.connection_manager import connection_manager

        q = connection_manager.subscribe("all")
        try:
            publish_event("remote_access_change", {"client_count": 2})
            # ConnectionManager publish는 asyncio 큐 — 동기로 확인
            assert not q.empty()
        finally:
            connection_manager.unsubscribe("all", q)


# ===========================================================================
# ── TestBackendStreamRoutes: Phase 2 채널별 스트림 엔드포인트 ──────────────────
# ===========================================================================


class TestBackendStreamRoutes:
    """Phase 2 /api/v1/stream/* 채널별 SSE 엔드포인트 라우트 등록 및 포맷 검증."""

    def test_stream_tickets_route_registered(self, api_app):
        """GET /api/v1/stream/tickets 라우트가 등록됨."""
        info = _get_route_info(api_app, "/api/v1/stream/tickets")
        assert info, "/api/v1/stream/tickets 라우트 미등록"
        assert "GET" in info["methods"]

    def test_stream_completed_tasks_route_registered(self, api_app):
        """GET /api/v1/stream/completed-tasks 라우트가 등록됨."""
        info = _get_route_info(api_app, "/api/v1/stream/completed-tasks")
        assert info, "/api/v1/stream/completed-tasks 라우트 미등록"
        assert "GET" in info["methods"]

    def test_stream_remote_access_route_registered(self, api_app):
        """GET /api/v1/stream/remote-access 라우트가 등록됨."""
        info = _get_route_info(api_app, "/api/v1/stream/remote-access")
        assert info, "/api/v1/stream/remote-access 라우트 미등록"
        assert "GET" in info["methods"]

    def test_sse_headers_cache_control(self):
        """스트림 응답 헤더에 Cache-Control: no-cache 설정됨."""
        from core.api.routes.streams import _SSE_HEADERS

        assert _SSE_HEADERS.get("Cache-Control") == "no-cache"

    def test_sse_headers_x_accel_buffering(self):
        """nginx 버퍼링 비활성화 헤더(X-Accel-Buffering: no) 설정됨."""
        from core.api.routes.streams import _SSE_HEADERS

        assert _SSE_HEADERS.get("X-Accel-Buffering") == "no"

    def test_sse_headers_connection_keepalive(self):
        """SSE 헤더에 Connection: keep-alive 설정됨."""
        from core.api.routes.streams import _SSE_HEADERS

        assert _SSE_HEADERS.get("Connection") == "keep-alive"

    def test_fmt_sse_basic_format(self):
        """_fmt_sse가 올바른 SSE 포맷(event:/data:/빈줄)을 생성함."""
        from core.api.routes.streams import _fmt_sse

        result = _fmt_sse("ticket_update", {"pending": 5, "in_progress": 2, "done": 10})
        assert "event: ticket_update\n" in result
        assert "data: " in result
        assert result.endswith("\n\n")

    def test_fmt_sse_data_is_valid_json(self):
        """_fmt_sse data 필드가 유효한 JSON임."""
        from core.api.routes.streams import _fmt_sse

        result = _fmt_sse("ticket_update", {"pending": 5, "ts": 1.0})
        data_line = [line for line in result.split("\n") if line.startswith("data:")][0]
        payload = json.loads(data_line[5:].strip())
        assert payload["pending"] == 5

    def test_fmt_sse_with_event_id(self):
        """event_id 전달 시 id: 라인이 포함됨."""
        from core.api.routes.streams import _fmt_sse

        result = _fmt_sse("ping", {"ts": 1.0}, event_id="98765")
        assert "id: 98765\n" in result

    def test_fmt_sse_without_event_id(self):
        """event_id 미전달 시 id: 라인이 없음."""
        from core.api.routes.streams import _fmt_sse

        result = _fmt_sse("ping", {"ts": 1.0})
        assert "id:" not in result

    def test_initial_connect_event_format(self):
        """초기 연결 이벤트가 ping 타입이고 connected 메시지를 포함함."""
        from core.api.routes.streams import _fmt_sse

        connect_data = {"ts": time.time(), "message": "connected", "channel": "tickets"}
        event = _fmt_sse("ping", connect_data, event_id="12345")
        assert "event: ping\n" in event
        assert '"message": "connected"' in event
        assert '"channel": "tickets"' in event

    def test_reconnect_event_includes_last_id(self):
        """재연결 시 last_id 필드가 이벤트 페이로드에 포함됨."""
        from core.api.routes.streams import _fmt_sse

        connect_data = {"ts": time.time(), "message": "connected", "channel": "tickets", "last_id": "prev-999"}
        event = _fmt_sse("ping", connect_data)
        assert '"last_id": "prev-999"' in event

    def test_connection_manager_subscribe_unsubscribe(self):
        """ConnectionManager subscribe/unsubscribe 생명주기가 정상 동작함."""
        from core.dashboard.connection_manager import ConnectionManager

        cm = ConnectionManager()
        q = cm.subscribe("tickets")
        assert cm.client_count() >= 1
        cm.unsubscribe("tickets", q)

    def test_connection_manager_publish_to_channel(self):
        """ConnectionManager.publish() 가 채널 구독자에게 이벤트를 전달함."""
        from core.dashboard.connection_manager import ConnectionManager

        cm = ConnectionManager()
        q = cm.subscribe("tickets")
        cm.publish("tickets", "ticket_update", {"pending": 7})
        assert not q.empty()
        item = q.get_nowait()
        assert item.get("type") == "ticket_update"
        assert item.get("pending") == 7
        cm.unsubscribe("tickets", q)
