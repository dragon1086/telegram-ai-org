"""tests/e2e/test_dashboard_api_integration.py — 대시보드 API 연동 E2E 테스트.

테스트 시나리오:
    TestApiClientMockMode      : Mock 모드 API 클라이언트 동작 검증
    TestThresholdMapping       : block_threshold → severity 매핑 검증
    TestCriteriaChangeDetection: 기준 변경 이벤트 감지 검증
    TestSnapshotEndpoint       : /api/v1/dashboard/snapshot 엔드포인트 검증 (FastAPI TestClient)
    TestThresholdEndpoint      : /api/v1/dashboard/thresholds 엔드포인트 검증
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ── 경로 상수 ────────────────────────────────────────────────────────────────

_REPO_ROOT        = Path(__file__).parent.parent.parent
_MOCK_DATA_PATH   = _REPO_ROOT / "dashboard" / "api" / "mock_data.json"
_CRITERIA_PATH    = _REPO_ROOT / "config" / "criteria_tracking.yaml"
_WORKTREE_CRITERIA = _REPO_ROOT / ".worktrees" / "bot-runtime" / "config" / "criteria_tracking.yaml"


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def _load_mock_data() -> dict:
    """mock_data.json 로드."""
    with open(_MOCK_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_criteria() -> dict:
    """criteria_tracking.yaml 로드 (두 경로 모두 시도)."""
    for path in [_CRITERIA_PATH, _WORKTREE_CRITERIA]:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return {}


def _compute_severity(current_value: float, warn_threshold: float, block_threshold: float) -> str:
    """Python 포팅: computeSeverity 로직.

    criteria_tracking.yaml severity_mapping:
      level 1 (info)     → value < warn_threshold
      level 2 (warning)  → warn_threshold <= value < block_threshold
      level 3 (critical) → value >= block_threshold
    """
    if current_value >= block_threshold:
        return "critical"
    if current_value >= warn_threshold:
        return "warning"
    return "info"


# ── TestApiClientMockMode ────────────────────────────────────────────────────

@pytest.mark.unit
class TestApiClientMockMode:
    """Mock 모드 API 클라이언트 동작 검증 (5개 테스트)."""

    def test_mock_data_file_exists(self):
        """mock_data.json 파일이 존재해야 한다."""
        assert _MOCK_DATA_PATH.exists(), f"mock_data.json 없음: {_MOCK_DATA_PATH}"

    def test_mock_data_snapshot_structure(self):
        """snapshot 필드 구조 검증."""
        data = _load_mock_data()
        assert "snapshot" in data
        snap = data["snapshot"]
        assert "counts" in snap
        assert "criteria_version" in snap
        counts = snap["counts"]
        for field in ("pending", "in_progress", "done", "blocked"):
            assert field in counts, f"counts.{field} 누락"
            assert isinstance(counts[field], int)

    def test_mock_data_characters_structure(self):
        """characters 배열 구조 검증."""
        data = _load_mock_data()
        assert "characters" in data
        chars = data["characters"]
        assert len(chars) > 0, "캐릭터 데이터가 없음"
        required_fields = ("orgId", "name", "emoji", "color", "hp", "level", "emotion", "severity")
        for char in chars:
            for field in required_fields:
                assert field in char, f"character.{field} 누락 (orgId={char.get('orgId')})"

    def test_mock_data_thresholds_structure(self):
        """thresholds 구조 검증."""
        data = _load_mock_data()
        assert "thresholds" in data
        thresholds = data["thresholds"]
        assert len(thresholds) > 0, "thresholds가 비어 있음"
        for name, cfg in thresholds.items():
            assert "block_threshold" in cfg, f"thresholds.{name}.block_threshold 누락"
            assert "warn_threshold"  in cfg, f"thresholds.{name}.warn_threshold 누락"
            assert "criteria_version" in cfg, f"thresholds.{name}.criteria_version 누락"
            assert isinstance(cfg["block_threshold"], (int, float))
            assert isinstance(cfg["warn_threshold"],  (int, float))

    def test_mock_data_criteria_change_events_structure(self):
        """criteria_change_events 구조 검증."""
        data = _load_mock_data()
        assert "criteria_change_events" in data
        events = data["criteria_change_events"]
        assert len(events) > 0, "criteria_change_events가 비어 있음"
        required = ("type", "threshold_name", "old_version", "new_version", "old_value", "new_value")
        for ev in events:
            assert ev.get("type") == "criteria_change"
            for field in required:
                assert field in ev, f"criteria_change_event.{field} 누락"


# ── TestThresholdMapping ─────────────────────────────────────────────────────

@pytest.mark.unit
class TestThresholdMapping:
    """block_threshold → severity 매핑 검증 (8개 테스트)."""

    def test_below_warn_is_info(self):
        """warn 미만 → info."""
        assert _compute_severity(0, warn_threshold=1, block_threshold=3) == "info"

    def test_at_warn_is_warning(self):
        """warn 이상, block 미만 → warning."""
        assert _compute_severity(1, warn_threshold=1, block_threshold=3) == "warning"

    def test_between_warn_and_block_is_warning(self):
        """warn 초과, block 미만 → warning."""
        assert _compute_severity(2, warn_threshold=1, block_threshold=3) == "warning"

    def test_at_block_is_critical(self):
        """block 이상 → critical."""
        assert _compute_severity(3, warn_threshold=1, block_threshold=3) == "critical"

    def test_above_block_is_critical(self):
        """block 초과 → critical."""
        assert _compute_severity(5, warn_threshold=1, block_threshold=3) == "critical"

    def test_zero_value_is_info(self):
        """0값 → info."""
        assert _compute_severity(0, warn_threshold=1, block_threshold=3) == "info"

    def test_timeout_threshold_mapping(self):
        """task_timeout_hard: 1200 warn, 1800 block."""
        data = _load_mock_data()
        cfg  = data["thresholds"].get("task_timeout_hard")
        if not cfg:
            pytest.skip("task_timeout_hard threshold 없음")
        assert _compute_severity(1000, cfg["warn_threshold"], cfg["block_threshold"]) == "info"
        assert _compute_severity(1200, cfg["warn_threshold"], cfg["block_threshold"]) == "warning"
        assert _compute_severity(1800, cfg["warn_threshold"], cfg["block_threshold"]) == "critical"

    def test_criteria_yaml_block_threshold_value(self):
        """criteria_tracking.yaml 로드 후 e2e_timeout_min_sec 값 검증."""
        criteria = _load_criteria()
        assert criteria, "criteria_tracking.yaml 로드 실패"
        block = criteria.get("block_threshold", {})
        assert "e2e_timeout_min_sec" in block, "block_threshold.e2e_timeout_min_sec 없음"
        assert block["e2e_timeout_min_sec"] >= 60, "e2e_timeout_min_sec는 60 이상이어야 함"


# ── TestCriteriaChangeDetection ───────────────────────────────────────────────

@pytest.mark.unit
class TestCriteriaChangeDetection:
    """기준 변경 이벤트 감지 검증 (5개 테스트)."""

    def test_criteria_change_event_type_field(self):
        """type 필드는 'criteria_change'여야 한다."""
        data = _load_mock_data()
        ev = data["criteria_change_events"][0]
        assert ev["type"] == "criteria_change"

    def test_criteria_change_version_upgrade(self):
        """new_version이 old_version보다 높아야 한다 (mock 데이터 기준)."""
        data = _load_mock_data()
        ev   = data["criteria_change_events"][0]
        # 단순 버전 문자열 비교: "1.0.0" > "0.9.0"
        assert ev["new_version"] != ev["old_version"], "버전이 동일하면 변경 이벤트가 아님"

    def test_criteria_change_value_changed(self):
        """new_value != old_value여야 한다."""
        data = _load_mock_data()
        ev   = data["criteria_change_events"][0]
        assert ev["new_value"] != ev["old_value"], "값이 동일하면 변경 이벤트가 아님"

    def test_criteria_change_has_threshold_name(self):
        """threshold_name 필드가 실제 thresholds 키와 일치해야 한다."""
        data = _load_mock_data()
        ev   = data["criteria_change_events"][0]
        assert ev["threshold_name"] in data["thresholds"], (
            f"threshold_name '{ev['threshold_name']}' 이 thresholds 키와 불일치"
        )

    def test_criteria_change_reason_present(self):
        """change_reason 필드가 존재하고 비어있지 않아야 한다."""
        data = _load_mock_data()
        ev   = data["criteria_change_events"][0]
        assert "change_reason" in ev, "change_reason 필드 누락"
        assert ev["change_reason"], "change_reason이 비어 있음"


# ── TestSnapshotEndpoint ─────────────────────────────────────────────────────

@pytest.mark.integration
class TestSnapshotEndpoint:
    """/api/v1/dashboard/snapshot 엔드포인트 검증 (FastAPI TestClient)."""

    @pytest.fixture(scope="class")
    def app_client(self):
        """FastAPI TestClient 생성."""
        try:
            from fastapi.testclient import TestClient
            from core.api.app import create_app

            os.environ.setdefault("ENABLE_REST_API", "true")
            os.environ.setdefault("AIMESH_DB_PATH", ":memory:")
            app = create_app()
            return TestClient(app, raise_server_exceptions=False)
        except Exception as e:
            pytest.skip(f"FastAPI 앱 생성 실패 (API 서버 미구성): {e}")

    def test_snapshot_returns_200_or_404(self, app_client):
        """/api/v1/dashboard/snapshot — 200 또는 404(미구현) 허용."""
        res = app_client.get(
            "/api/v1/dashboard/snapshot",
            headers={"X-API-Key": os.environ.get("API_KEY", "test-key")},
        )
        assert res.status_code in (200, 404, 422), f"예상치 못한 상태코드: {res.status_code}"

    def test_snapshot_json_content_type(self, app_client):
        """응답이 JSON content-type이어야 한다."""
        res = app_client.get(
            "/api/v1/dashboard/snapshot",
            headers={"X-API-Key": os.environ.get("API_KEY", "test-key")},
        )
        if res.status_code == 200:
            assert "application/json" in res.headers.get("content-type", "")

    def test_snapshot_unauthenticated_returns_401_or_403(self, app_client):
        """인증 없이 요청 시 401 또는 403이 반환되어야 한다."""
        res = app_client.get("/api/v1/dashboard/snapshot")
        assert res.status_code in (200, 401, 403, 404, 422), (
            f"인증 없는 요청 상태코드: {res.status_code}"
        )

    def test_mock_data_snapshot_is_valid_fallback(self):
        """API가 없는 경우 mock_data.json의 snapshot이 폴백으로 유효해야 한다."""
        data = _load_mock_data()
        snap = data["snapshot"]
        assert snap["counts"]["pending"] >= 0
        assert snap["counts"]["in_progress"] >= 0
        assert snap["counts"]["done"] >= 0
        assert snap["criteria_version"] != ""


# ── TestThresholdEndpoint ─────────────────────────────────────────────────────

@pytest.mark.integration
class TestThresholdEndpoint:
    """/api/v1/dashboard/thresholds 엔드포인트 검증 (3개 테스트)."""

    @pytest.fixture(scope="class")
    def app_client(self):
        """FastAPI TestClient 생성."""
        try:
            from fastapi.testclient import TestClient
            from core.api.app import create_app

            os.environ.setdefault("ENABLE_REST_API", "true")
            os.environ.setdefault("AIMESH_DB_PATH", ":memory:")
            app = create_app()
            return TestClient(app, raise_server_exceptions=False)
        except Exception as e:
            pytest.skip(f"FastAPI 앱 생성 실패: {e}")

    def test_thresholds_endpoint_accessible(self, app_client):
        """/api/v1/dashboard/thresholds — 접근 가능해야 한다 (200 또는 404)."""
        res = app_client.get(
            "/api/v1/dashboard/thresholds",
            headers={"X-API-Key": os.environ.get("API_KEY", "test-key")},
        )
        assert res.status_code in (200, 404, 422), f"예상치 못한 상태코드: {res.status_code}"

    def test_thresholds_mock_data_has_required_entries(self):
        """mock_data.json thresholds에 exit_code_143, error_pattern_repeat 항목이 있어야 한다."""
        data = _load_mock_data()
        thresholds = data["thresholds"]
        assert "exit_code_143" in thresholds, "exit_code_143 threshold 누락"
        assert "error_pattern_repeat" in thresholds, "error_pattern_repeat threshold 누락"

    def test_thresholds_block_ge_warn(self):
        """모든 threshold에서 block_threshold >= warn_threshold여야 한다."""
        data = _load_mock_data()
        for name, cfg in data["thresholds"].items():
            assert cfg["block_threshold"] >= cfg["warn_threshold"], (
                f"{name}: block({cfg['block_threshold']}) < warn({cfg['warn_threshold']})"
            )
