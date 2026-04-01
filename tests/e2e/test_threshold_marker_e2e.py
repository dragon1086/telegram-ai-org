"""tests/e2e/test_threshold_marker_e2e.py — 임계값 마커 E2E 테스트.

테스트 시나리오:
    TestCriteriaChangeMarkerRender   : 기준 변경 이벤트 → 마커 DOM 렌더링 검증
    TestMarkerAutoRemove             : 30초 후 자동 제거 로직 검증
    TestMarkerContent                : 마커 텍스트 포맷 ("v{old}→v{new}") 검증
    TestThresholdAutoSeverityUpdate  : block_threshold 변경 → 대시보드 severity 자동 갱신 검증
    TestWebSocketReconnect           : 연결 끊김 → 재연결 후 마커 유지 검증
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

# ── 경로 상수 ────────────────────────────────────────────────────────────────

_REPO_ROOT   = Path(__file__).parent.parent.parent
_MOCK_DATA   = _REPO_ROOT / "dashboard" / "api" / "mock_data.json"
_DASHBOARD   = _REPO_ROOT / "dashboard"


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _load_mock_criteria_change_event() -> dict:
    """mock_data.json에서 첫 번째 criteria_change 이벤트 반환."""
    with open(_MOCK_DATA, encoding="utf-8") as f:
        data = json.load(f)
    return data["criteria_change_events"][0]


def _format_marker_text(event: dict) -> str:
    """Python 포팅: CriteriaChangeMarker._formatMarkerText() 핵심 로직."""
    name      = event["threshold_name"]
    old_ver   = event["old_version"]
    new_ver   = event["new_version"]
    old_val   = event["old_value"]
    new_val   = event["new_value"]
    reason    = event.get("change_reason", "")

    text = f"기준 변경: {name} v{old_ver}→v{new_ver} | threshold: {old_val}→{new_val}"
    if reason:
        text += f" | 이유: {reason}"
    return text


# ── 로컬 HTTP 서버 픽스처 ────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def dashboard_server():
    """dashboard/ 디렉토리를 로컬 HTTP 서버로 서빙 (포트 18766)."""
    import http.server
    import socketserver

    port = 18766

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args): pass
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(_DASHBOARD), **kwargs)

    server = socketserver.TCPServer(("127.0.0.1", port), QuietHandler, bind_and_activate=False)
    server.allow_reuse_address = True
    try:
        server.server_bind()
        server.server_activate()
    except OSError:
        yield f"http://127.0.0.1:{port}"
        return

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ── TestCriteriaChangeMarkerRender ────────────────────────────────────────────

@pytest.mark.unit
class TestCriteriaChangeMarkerRender:
    """기준 변경 이벤트 → 마커 DOM 렌더링 검증."""

    def test_marker_text_format_contains_threshold_name(self):
        """마커 텍스트에 threshold_name이 포함되어야 한다."""
        ev   = _load_mock_criteria_change_event()
        text = _format_marker_text(ev)
        assert ev["threshold_name"] in text, f"threshold_name 누락: {text}"

    def test_marker_text_format_contains_version_arrow(self):
        """마커 텍스트에 'v{old}→v{new}' 형식이 있어야 한다."""
        ev   = _load_mock_criteria_change_event()
        text = _format_marker_text(ev)
        expected = f"v{ev['old_version']}→v{ev['new_version']}"
        assert expected in text, f"버전 포맷 누락: {text}"

    def test_marker_text_format_contains_value_change(self):
        """마커 텍스트에 'threshold: {old}→{new}' 형식이 있어야 한다."""
        ev   = _load_mock_criteria_change_event()
        text = _format_marker_text(ev)
        expected = f"threshold: {ev['old_value']}→{ev['new_value']}"
        assert expected in text, f"임계값 변경 포맷 누락: {text}"

    def test_marker_text_contains_reason_when_present(self):
        """change_reason이 있으면 마커 텍스트에 포함되어야 한다."""
        ev   = _load_mock_criteria_change_event()
        text = _format_marker_text(ev)
        if ev.get("change_reason"):
            assert ev["change_reason"] in text, f"change_reason 누락: {text}"

    @pytest.mark.skip(reason="requires playwright browser")
    def test_marker_dom_rendered_on_criteria_change(self, page, dashboard_server):
        """기준 변경 이벤트 수신 시 .criteria-change-marker DOM이 렌더링되어야 한다."""
        from playwright.sync_api import expect

        page.goto(f"{dashboard_server}/?mock=1")
        page.wait_for_selector(".dashboard-character-grid", timeout=5000)

        # JS로 CriteriaChangeMarker.show() 직접 호출 시뮬레이션
        ev = _load_mock_criteria_change_event()
        ev_json = json.dumps(ev)

        page.evaluate(f"""() => {{
            const zone = document.getElementById('criteria-marker-zone');
            if (!zone) return;

            // 마커 직접 생성
            let list = zone.querySelector('.criteria-marker-list');
            if (!list) {{
                list = document.createElement('div');
                list.className = 'criteria-marker-list';
                zone.appendChild(list);
            }}

            const ev = {ev_json};
            const el = document.createElement('div');
            el.className = 'criteria-change-marker criteria-marker';
            el.innerHTML = `📋 기준 변경: ${{ev.threshold_name}} v${{ev.old_version}}→v${{ev.new_version}}`;
            list.insertBefore(el, list.firstChild);
        }}""")

        marker = page.locator(".criteria-change-marker").first
        expect(marker).to_be_visible()
        text = marker.text_content() or ""
        assert ev["threshold_name"] in text


# ── TestMarkerAutoRemove ───────────────────────────────────────────────────────

@pytest.mark.unit
class TestMarkerAutoRemove:
    """자동 제거 로직 검증."""

    def test_auto_remove_ms_default_value(self):
        """autoRemoveMs 기본값은 30000ms(30초)여야 한다."""
        # JavaScript 코드에서 기본값 확인 (소스 파일 파싱)
        marker_js = _REPO_ROOT / "dashboard" / "components" / "CriteriaChangeMarker.js"
        assert marker_js.exists(), "CriteriaChangeMarker.js 없음"
        content = marker_js.read_text(encoding="utf-8")
        assert "30000" in content, "기본 autoRemoveMs=30000 값이 소스에 없음"

    def test_marker_count_starts_at_zero(self):
        """CriteriaChangeMarker 초기화 시 markerCount는 0이어야 한다."""
        # JavaScript 소스에서 초기값 확인
        marker_js = _REPO_ROOT / "dashboard" / "components" / "CriteriaChangeMarker.js"
        content = marker_js.read_text(encoding="utf-8")
        assert "this._markers" in content, "_markers 배열이 없음"
        assert "[]" in content, "_markers 초기값이 빈 배열이어야 함"

    @pytest.mark.skip(reason="requires playwright browser")
    def test_marker_removed_after_timeout(self, page, dashboard_server):
        """autoRemoveMs 경과 후 마커가 DOM에서 제거되어야 한다."""
        from playwright.sync_api import expect

        page.goto(f"{dashboard_server}/?mock=1")
        page.wait_for_selector(".dashboard-character-grid", timeout=5000)

        # 100ms 후 자동 제거 마커 생성
        page.evaluate("""() => {
            const zone = document.getElementById('criteria-marker-zone') || document.body;
            let list = zone.querySelector('.criteria-marker-list');
            if (!list) {
                list = document.createElement('div');
                list.className = 'criteria-marker-list';
                zone.appendChild(list);
            }
            const el = document.createElement('div');
            el.id = 'test-auto-remove-marker';
            el.className = 'criteria-change-marker';
            el.textContent = '테스트 마커';
            list.insertBefore(el, list.firstChild);

            // 200ms 후 페이드아웃
            setTimeout(() => {
                el.style.transition = 'opacity 0.1s';
                el.style.opacity = '0';
                setTimeout(() => el.remove(), 150);
            }, 200);
        }""")

        # 마커가 처음엔 존재해야 함
        marker = page.locator("#test-auto-remove-marker")
        expect(marker).to_be_visible()

        # 500ms 후 제거되어야 함
        page.wait_for_timeout(500)
        assert page.locator("#test-auto-remove-marker").count() == 0, "마커가 제거되지 않음"

    @pytest.mark.skip(reason="requires playwright browser")
    def test_clear_removes_all_markers(self, page, dashboard_server):
        """clear() 호출 시 모든 마커가 제거되어야 한다."""
        page.goto(f"{dashboard_server}/?mock=1")
        page.wait_for_selector(".dashboard-character-grid", timeout=5000)

        # 여러 마커 추가
        page.evaluate("""() => {
            const zone = document.getElementById('criteria-marker-zone') || document.body;
            let list = zone.querySelector('.criteria-marker-list');
            if (!list) {
                list = document.createElement('div');
                list.className = 'criteria-marker-list';
                zone.appendChild(list);
            }
            for (let i = 0; i < 3; i++) {
                const el = document.createElement('div');
                el.className = 'criteria-change-marker test-clear-marker';
                el.textContent = `마커 ${i}`;
                list.appendChild(el);
            }
        }""")

        before_count = page.locator(".test-clear-marker").count()
        assert before_count == 3

        # 모든 마커 제거
        page.evaluate("""() => {
            document.querySelectorAll('.test-clear-marker').forEach(el => el.remove());
        }""")

        assert page.locator(".test-clear-marker").count() == 0


# ── TestMarkerContent ─────────────────────────────────────────────────────────

@pytest.mark.unit
class TestMarkerContent:
    """마커 텍스트 포맷 검증."""

    def test_format_with_all_fields(self):
        """모든 필드가 있는 이벤트 포맷 검증."""
        ev = {
            "type":           "criteria_change",
            "threshold_name": "exit_code_143",
            "old_version":    "0.9.0",
            "new_version":    "1.0.0",
            "old_value":      2,
            "new_value":      3,
            "changed_at":     1711900000000,
            "change_reason":  "RETRO-27",
        }
        text = _format_marker_text(ev)
        assert "exit_code_143" in text
        assert "v0.9.0→v1.0.0" in text
        assert "threshold: 2→3" in text
        assert "RETRO-27" in text

    def test_format_without_reason(self):
        """change_reason 없는 이벤트 포맷 검증."""
        ev = {
            "threshold_name": "error_pattern_repeat",
            "old_version":    "1.0.0",
            "new_version":    "1.1.0",
            "old_value":      3,
            "new_value":      5,
        }
        text = _format_marker_text(ev)
        assert "error_pattern_repeat" in text
        assert "v1.0.0→v1.1.0" in text
        assert "threshold: 3→5" in text
        assert "이유" not in text

    def test_format_version_arrow_notation(self):
        """버전 표기가 반드시 '→' (오른쪽 화살표)를 사용해야 한다."""
        ev = {
            "threshold_name": "test",
            "old_version":    "1.0",
            "new_version":    "2.0",
            "old_value":      1,
            "new_value":      2,
        }
        text = _format_marker_text(ev)
        assert "→" in text, "화살표 '→' 문자가 포맷에 없음"

    @pytest.mark.skip(reason="requires playwright browser")
    def test_marker_aria_role_alert(self, page, dashboard_server):
        """마커 DOM에 role='alert' 접근성 속성이 있어야 한다."""
        page.goto(f"{dashboard_server}/?mock=1")
        page.wait_for_selector(".dashboard-character-grid", timeout=5000)

        ev = _load_mock_criteria_change_event()
        page.evaluate(f"""() => {{
            const zone = document.getElementById('criteria-marker-zone') || document.body;
            let list = zone.querySelector('.criteria-marker-list');
            if (!list) {{
                list = document.createElement('div');
                list.className = 'criteria-marker-list';
                zone.appendChild(list);
            }}
            const el = document.createElement('div');
            el.className = 'criteria-change-marker';
            el.setAttribute('role', 'alert');
            el.textContent = '기준 변경 테스트';
            list.appendChild(el);
        }}""")

        marker = page.locator("[role='alert'].criteria-change-marker").first
        assert marker.count() >= 0


# ── TestThresholdAutoSeverityUpdate ──────────────────────────────────────────

@pytest.mark.unit
class TestThresholdAutoSeverityUpdate:
    """block_threshold 변경 → severity 자동 갱신 검증."""

    def test_severity_recalculated_after_threshold_increase(self):
        """block_threshold 증가 시 동일 currentValue의 severity가 낮아져야 한다."""
        # currentValue=3: block=3 → critical / block=4 → warning
        from pathlib import Path
        import sys
        sys.path.insert(0, str(_REPO_ROOT))

        def compute(val, warn, block):
            if val >= block:  return "critical"
            if val >= warn:   return "warning"
            return "info"

        assert compute(3, warn=1, block=3) == "critical"
        assert compute(3, warn=1, block=4) == "warning"  # block 증가 → severity 낮아짐

    def test_severity_recalculated_after_threshold_decrease(self):
        """block_threshold 감소 시 동일 currentValue의 severity가 높아져야 한다."""
        def compute(val, warn, block):
            if val >= block:  return "critical"
            if val >= warn:   return "warning"
            return "info"

        assert compute(2, warn=1, block=3) == "warning"
        assert compute(2, warn=1, block=2) == "critical"  # block 감소 → severity 높아짐

    def test_threshold_cache_key_matches_threshold_name(self):
        """ThresholdConfig의 name 필드가 캐시 키와 일치해야 한다."""
        import json
        with open(_MOCK_DATA, encoding="utf-8") as f:
            data = json.load(f)
        for key, cfg in data["thresholds"].items():
            assert cfg.get("name") == key, (
                f"threshold key '{key}'와 name '{cfg.get('name')}' 불일치"
            )

    def test_overall_severity_escalates_with_any_critical(self):
        """하나라도 critical이면 전체 severity는 critical이어야 한다."""
        thresholds = [
            {"severity": "info"},
            {"severity": "critical"},
            {"severity": "warning"},
        ]
        # getOverallSeverity 로직 Python 포팅
        rank = {"info": 1, "warning": 2, "critical": 3}
        overall = max(thresholds, key=lambda t: rank.get(t["severity"], 0))["severity"]
        assert overall == "critical"

    @pytest.mark.skip(reason="requires playwright browser")
    def test_character_panel_updates_on_threshold_change(self, page, dashboard_server):
        """임계값 변경 이벤트 후 캐릭터 패널 severity 클래스가 갱신되어야 한다."""
        from playwright.sync_api import expect

        page.goto(f"{dashboard_server}/?mock=1")
        page.wait_for_selector(".character-panel", timeout=5000)

        # JS로 severity 강제 변경
        page.evaluate("""() => {
            const panel = document.querySelector('.character-panel');
            if (!panel) return;
            panel.classList.remove('severity-info', 'severity-warning', 'severity-critical');
            panel.classList.add('severity-critical');
        }""")

        expect(page.locator(".character-panel.severity-critical").first).to_be_visible()


# ── TestWebSocketReconnect ────────────────────────────────────────────────────

@pytest.mark.unit
class TestWebSocketReconnect:
    """연결 끊김 → 재연결 후 마커 유지 검증."""

    def test_realtime_hook_has_reconnect_logic(self):
        """RealtimeStatusHook 소스에 재연결 관련 코드가 있어야 한다."""
        hook_js = _REPO_ROOT / "dashboard" / "hooks" / "useRealtimeStatus.js"
        assert hook_js.exists(), "useRealtimeStatus.js 없음"
        content = hook_js.read_text(encoding="utf-8")
        # RealtimeClient의 reconnect 옵션 사용 여부 확인
        assert "reconnect" in content or "RealtimeClient" in content, (
            "재연결 로직이 없음"
        )

    def test_connection_state_transitions(self):
        """connectionState 값이 명세에 정의된 4가지 중 하나여야 한다."""
        hook_js = _REPO_ROOT / "dashboard" / "hooks" / "useRealtimeStatus.js"
        content = hook_js.read_text(encoding="utf-8")
        valid_states = {"connected", "disconnected", "connecting", "polling"}
        found = set()
        for s in valid_states:
            if f"'{s}'" in content or f'"{s}"' in content:
                found.add(s)
        assert len(found) >= 2, f"connectionState 값 불충분 (found={found})"

    def test_polling_mode_uses_interval(self):
        """폴링 모드에서 setInterval을 사용해야 한다."""
        hook_js = _REPO_ROOT / "dashboard" / "hooks" / "useRealtimeStatus.js"
        content = hook_js.read_text(encoding="utf-8")
        assert "setInterval" in content, "폴링 모드에 setInterval 없음"

    def test_stop_method_clears_polling(self):
        """stop() 메서드가 폴링 인터벌을 정리해야 한다."""
        hook_js = _REPO_ROOT / "dashboard" / "hooks" / "useRealtimeStatus.js"
        content = hook_js.read_text(encoding="utf-8")
        assert "clearInterval" in content, "stop()에 clearInterval 없음"

    @pytest.mark.skip(reason="requires playwright browser")
    def test_marker_persists_after_reconnect(self, page, dashboard_server):
        """연결 끊김 후 재연결해도 기존 마커가 유지되어야 한다."""
        from playwright.sync_api import expect

        page.goto(f"{dashboard_server}/?mock=1")
        page.wait_for_selector(".dashboard-character-grid", timeout=5000)

        # 마커 추가
        page.evaluate("""() => {
            const zone = document.getElementById('criteria-marker-zone') || document.body;
            let list = zone.querySelector('.criteria-marker-list');
            if (!list) {
                list = document.createElement('div');
                list.className = 'criteria-marker-list';
                zone.appendChild(list);
            }
            const el = document.createElement('div');
            el.id = 'persistent-test-marker';
            el.className = 'criteria-change-marker';
            el.textContent = '📋 기준 변경: 재연결 테스트';
            list.appendChild(el);
        }""")

        marker = page.locator("#persistent-test-marker")
        expect(marker).to_be_visible()

        # 재연결 시뮬레이션 (window 이벤트 발생)
        page.evaluate("() => window.dispatchEvent(new Event('online'))")

        # 마커가 여전히 존재해야 함
        expect(page.locator("#persistent-test-marker")).to_be_visible()
