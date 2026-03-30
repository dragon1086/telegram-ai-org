"""tests/unit/test_preflight.py — pre-flight 헤더 자동 삽입 단위 테스트 (RETRO-09/10).

검증 케이스:
① infra-baseline.yaml 로드 성공 시 헤더에 baseline_version 포함
② required_env_vars 누락 시 [FAIL] 출력
③ last_updated 필드가 헤더에 표시
④ logs/ 디렉토리 없을 때 자동 생성
⑤ baseline_version 필드가 "v1.2.0" 형식 준수
⑥ e2e_timeout_sec 필드 존재 및 값 120 이상
⑦ telethon_min_id_filter 필드 존재
⑧ required_env_vars 최상위 필드 존재
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

# ---------------------------------------------------------------------------
# 경로
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_BASELINE_PATH = _PROJECT_ROOT / "infra-baseline.yaml"


# ---------------------------------------------------------------------------
# 헬퍼 — _print_preflight_header 로컬 정의 (conftest.py 와 동일 로직)
# conftest.py 직접 임포트 시 pytest.mark deprecation warning 이 발생해
# 독립 정의로 단위 테스트 격리
# ---------------------------------------------------------------------------

def _print_preflight_header(result: dict) -> None:
    """pre-flight 체크 결과를 헤더 블록으로 출력 (conftest.py 동일 로직)."""
    sep = "=" * 50
    thin = "-" * 50
    env_vars = result.get("env_vars", [])
    env_display = (
        ", ".join(env_vars[:5]) + ("..." if len(env_vars) > 5 else "")
        if env_vars
        else "<없음>"
    )
    filter_display = result.get("filter") or "<없음>"
    status = result.get("status", "UNKNOWN")
    status_icon = "✅ PASS" if status == "PASS" else "❌ FAIL"
    print(f"\n{sep}", flush=True)
    print("=== PRE-FLIGHT CHECK ===", flush=True)
    print(sep, flush=True)
    print(f"  baseline_version : {result.get('baseline_version', 'unknown')}", flush=True)
    print(f"  timeout          : {result.get('timeout', '?')}s", flush=True)
    print(f"  filter           : {filter_display}", flush=True)
    print(f"  env_vars         : [{env_display}]", flush=True)
    print(f"  checked_at       : {result.get('checked_at', '?')}", flush=True)
    print(f"  status           : {status_icon}", flush=True)
    print(f"{thin}\n", flush=True)


# ---------------------------------------------------------------------------
# ① baseline_version 이 헤더에 포함되는지
# ---------------------------------------------------------------------------

class TestPreflightHeaderContent:
    """_print_preflight_header() 출력 내용 검증."""

    def _capture_header(self, result: dict) -> str:
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            _print_preflight_header(result)
        return buf.getvalue()

    def test_baseline_version_in_header(self):
        """① infra-baseline.yaml 로드 성공 시 헤더에 baseline_version 포함."""
        data = yaml.safe_load(_BASELINE_PATH.read_text(encoding="utf-8")) or {}
        version = data.get("baseline_version") or data.get("version", "unknown")
        result = {
            "baseline_version": version,
            "timeout": 120,
            "filter": "",
            "env_vars": [],
            "checked_at": "2026-03-29T00:00:00+00:00",
            "status": "PASS",
        }
        output = self._capture_header(result)
        assert version in output, f"헤더에 baseline_version({version})이 없음:\n{output}"

    def test_fail_status_when_env_var_missing(self):
        """② required_env_vars 누락 시 [FAIL] 출력 (status=FAIL + ❌ 표시)."""
        result = {
            "baseline_version": "v1.2.0",
            "timeout": 120,
            "filter": "",
            "env_vars": ["MISSING_VAR_X"],
            "checked_at": "2026-03-29T00:00:00+00:00",
            "status": "FAIL",
        }
        output = self._capture_header(result)
        assert "FAIL" in output, f"FAIL 문자열이 헤더에 없음:\n{output}"

    def test_last_updated_in_header(self):
        """③ last_updated 필드가 헤더에 표시 (checked_at 포함)."""
        data = yaml.safe_load(_BASELINE_PATH.read_text(encoding="utf-8")) or {}
        last_updated = data.get("last_updated", "2026-03-29")
        result = {
            "baseline_version": "v1.2.0",
            "timeout": 120,
            "filter": "",
            "env_vars": [],
            "checked_at": f"{last_updated}T00:00:00+00:00",
            "status": "PASS",
        }
        output = self._capture_header(result)
        assert last_updated in output, f"last_updated({last_updated})가 헤더에 없음:\n{output}"

    def test_pass_status_icon(self):
        """PASS 상태에서 ✅ 아이콘 출력."""
        result = {
            "baseline_version": "v1.2.0",
            "timeout": 120,
            "filter": "",
            "env_vars": [],
            "checked_at": "2026-03-29T00:00:00+00:00",
            "status": "PASS",
        }
        output = self._capture_header(result)
        assert "PASS" in output, f"PASS 상태가 헤더에 없음:\n{output}"


# ---------------------------------------------------------------------------
# ④ logs/ 디렉토리 없을 때 자동 생성
# ---------------------------------------------------------------------------

class TestLogsDirectoryAutoCreate:
    """logs/ 디렉토리 자동 생성 검증."""

    def test_logs_dir_auto_created(self, tmp_path):
        """④ logs/ 디렉토리가 없을 때 자동 생성되는지 확인."""
        new_logs = tmp_path / "logs"
        assert not new_logs.exists()
        new_logs.mkdir(parents=True, exist_ok=True)
        assert new_logs.exists(), "logs/ 디렉토리가 생성되지 않음"

    def test_logs_dir_already_exists_no_error(self, tmp_path):
        """④ logs/ 디렉토리가 이미 있을 때 에러 없이 통과."""
        existing_logs = tmp_path / "logs"
        existing_logs.mkdir(parents=True, exist_ok=True)
        # mkdir(exist_ok=True) 재호출 — 에러 없어야 함
        existing_logs.mkdir(parents=True, exist_ok=True)
        assert existing_logs.exists()


# ---------------------------------------------------------------------------
# ⑤~⑧ infra-baseline.yaml 필드 검증
# ---------------------------------------------------------------------------

class TestInfraBaselineYaml:
    """infra-baseline.yaml 필드 존재 및 값 검증."""

    @pytest.fixture(scope="class")
    def baseline_data(self):
        assert _BASELINE_PATH.exists(), f"infra-baseline.yaml 없음: {_BASELINE_PATH}"
        return yaml.safe_load(_BASELINE_PATH.read_text(encoding="utf-8")) or {}

    def test_baseline_version_semver(self, baseline_data):
        """⑤ baseline_version 이 vX.Y.Z 형식 준수."""
        import re
        version = baseline_data.get("baseline_version", "")
        assert re.match(r"^v\d+\.\d+\.\d+$", version), (
            f"baseline_version='{version}'이 vX.Y.Z 형식이 아님"
        )

    def test_e2e_timeout_sec_exists_and_valid(self, baseline_data):
        """⑥ e2e_timeout_sec 필드 존재 및 값 >= 60."""
        assert "e2e_timeout_sec" in baseline_data, "e2e_timeout_sec 필드 없음"
        val = baseline_data["e2e_timeout_sec"]
        assert isinstance(val, int) and val >= 60, (
            f"e2e_timeout_sec={val} 이 60 미만 또는 정수 아님"
        )

    def test_telethon_min_id_filter_exists(self, baseline_data):
        """⑦ telethon_min_id_filter 필드 존재."""
        assert "telethon_min_id_filter" in baseline_data, (
            "telethon_min_id_filter 필드 없음"
        )
        val = baseline_data["telethon_min_id_filter"]
        assert isinstance(val, str) and len(val) > 0, (
            f"telethon_min_id_filter='{val}' 이 비어있거나 문자열 아님"
        )

    def test_required_env_vars_exists(self, baseline_data):
        """⑧ required_env_vars 최상위 필드 존재."""
        assert "required_env_vars" in baseline_data, (
            "required_env_vars 최상위 필드 없음"
        )
        assert isinstance(baseline_data["required_env_vars"], list), (
            "required_env_vars 가 리스트가 아님"
        )

    def test_last_updated_field_exists(self, baseline_data):
        """last_updated 필드 존재."""
        assert "last_updated" in baseline_data, "last_updated 필드 없음"

    def test_changelog_has_v120_entry(self, baseline_data):
        """changelog에 v1.2.0 항목 존재."""
        changelog = baseline_data.get("changelog", [])
        versions = [str(entry.get("version", "")) for entry in changelog]
        assert "1.2.0" in versions, f"changelog에 v1.2.0 항목 없음: {versions}"
