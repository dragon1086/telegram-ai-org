"""tests/unit/test_preflight_check.py — scripts/preflight_check.py 단위 테스트.

각 체크 함수를 독립적으로 테스트한다. 실제 외부 의존성(subprocess, DB)은
최소화하고 파일시스템/환경변수 레벨에서만 검증한다.

RETRO-01: pre-flight 체크 자동화 (2026-03-27)
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 모듈 동적 로드 헬퍼
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_PREFLIGHT_PATH = _PROJECT_ROOT / "scripts" / "preflight_check.py"


def _load_preflight() -> ModuleType:
    """scripts/preflight_check.py 를 동적 import 한다."""
    spec = importlib.util.spec_from_file_location("scripts_preflight_check", _PREFLIGHT_PATH)
    assert spec and spec.loader, f"모듈 로드 실패: {_PREFLIGHT_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# 테스트 1: 모듈 로드 및 run_all_checks() 반환 구조
# ---------------------------------------------------------------------------

class TestModuleLoadAndStructure:
    """모듈 import 가능 여부 및 반환 구조 검증."""

    def test_module_loads_without_error(self):
        """scripts/preflight_check.py 가 에러 없이 로드된다."""
        mod = _load_preflight()
        assert mod is not None

    def test_run_all_checks_returns_dict(self):
        """run_all_checks() 가 dict를 반환한다."""
        mod = _load_preflight()
        result = mod.run_all_checks()
        assert isinstance(result, dict), f"dict가 아닌 타입 반환: {type(result)}"

    def test_run_all_checks_has_required_keys(self):
        """run_all_checks() 반환 dict에 필수 키가 있다."""
        mod = _load_preflight()
        result = mod.run_all_checks()
        for key in ("status", "checks", "summary", "timestamp", "baseline_version"):
            assert key in result, f"필수 키 '{key}' 없음"

    def test_status_is_valid_value(self):
        """result['status'] 는 PASS/WARN/FAIL 중 하나여야 한다."""
        mod = _load_preflight()
        result = mod.run_all_checks()
        assert result["status"] in ("PASS", "WARN", "FAIL"), (
            f"유효하지 않은 status 값: {result['status']}"
        )

    def test_checks_is_list(self):
        """result['checks'] 는 list 타입이어야 한다."""
        mod = _load_preflight()
        result = mod.run_all_checks()
        assert isinstance(result["checks"], list)

    def test_each_check_has_required_keys(self):
        """각 check 항목은 name/status/detail 키를 가진다."""
        mod = _load_preflight()
        result = mod.run_all_checks()
        for check in result["checks"]:
            for key in ("name", "status", "detail"):
                assert key in check, f"check 항목에 '{key}' 없음: {check}"

    def test_each_check_status_is_valid(self):
        """각 check 항목의 status는 PASS/WARN/FAIL 중 하나여야 한다."""
        mod = _load_preflight()
        result = mod.run_all_checks()
        for check in result["checks"]:
            assert check["status"] in ("PASS", "WARN", "FAIL"), (
                f"유효하지 않은 check status: {check}"
            )

    def test_summary_is_non_empty_string(self):
        """result['summary'] 는 비어있지 않은 문자열이어야 한다."""
        mod = _load_preflight()
        result = mod.run_all_checks()
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 0

    def test_timestamp_is_string(self):
        """result['timestamp'] 는 문자열이어야 한다."""
        mod = _load_preflight()
        result = mod.run_all_checks()
        assert isinstance(result["timestamp"], str)
        # 형식: YYYY-MM-DD HH:MM:SS
        import re
        assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", result["timestamp"])


# ---------------------------------------------------------------------------
# 테스트 2: check_venv()
# ---------------------------------------------------------------------------

class TestCheckVenv:
    """check_venv() 함수 단위 테스트."""

    def test_venv_missing_returns_fail(self, tmp_path):
        """venv 없으면 FAIL 결과가 포함된다."""
        mod = _load_preflight()
        # _PROJECT_ROOT를 tmp_path로 monkeypatch
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path
        try:
            results = mod.check_venv()
            statuses = {r["name"]: r["status"] for r in results}
            assert statuses.get("venv_exists") == "FAIL", (
                f"venv 없는데 FAIL이 아님: {statuses}"
            )
        finally:
            mod._PROJECT_ROOT = original_root

    def test_venv_exists_returns_pass(self, tmp_path):
        """venv 있으면 PASS 결과가 포함된다."""
        mod = _load_preflight()
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path
        try:
            results = mod.check_venv()
            statuses = {r["name"]: r["status"] for r in results}
            assert statuses.get("venv_exists") == "PASS"
        finally:
            mod._PROJECT_ROOT = original_root

    def test_venv_activated_when_virtual_env_set(self, tmp_path):
        """VIRTUAL_ENV 환경변수 설정 시 activated PASS."""
        mod = _load_preflight()
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path
        try:
            with patch.dict(os.environ, {"VIRTUAL_ENV": str(venv_path)}):
                results = mod.check_venv()
            statuses = {r["name"]: r["status"] for r in results}
            assert statuses.get("venv_activated") == "PASS"
        finally:
            mod._PROJECT_ROOT = original_root

    def test_venv_not_activated_returns_warn(self, tmp_path):
        """VIRTUAL_ENV 미설정 시 activated WARN."""
        mod = _load_preflight()
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path
        try:
            env_without_venv = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
            with patch.dict(os.environ, env_without_venv, clear=True):
                results = mod.check_venv()
            statuses = {r["name"]: r["status"] for r in results}
            assert statuses.get("venv_activated") == "WARN"
        finally:
            mod._PROJECT_ROOT = original_root


# ---------------------------------------------------------------------------
# 테스트 3: check_env_vars()
# ---------------------------------------------------------------------------

class TestCheckEnvVars:
    """check_env_vars() 함수 단위 테스트."""

    def _run_with_env(self, env_vars: dict[str, str], tmp_path: Path) -> list[dict]:
        """지정된 환경변수로 check_env_vars()를 실행한다."""
        mod = _load_preflight()
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path  # .env 없는 경로

        # os.environ을 제어 환경으로 교체
        clean_env = {k: v for k, v in os.environ.items()
                     if k not in mod._REQUIRED_VARS + mod._API_KEY_VARS}
        clean_env.update(env_vars)

        mod._PROJECT_ROOT = tmp_path
        try:
            with patch.dict(os.environ, clean_env, clear=True):
                return mod.check_env_vars()
        finally:
            mod._PROJECT_ROOT = original_root

    def test_required_vars_missing_returns_fail(self, tmp_path):
        """필수 환경변수 누락 시 FAIL 포함."""
        results = self._run_with_env({}, tmp_path)
        fail_names = [r["name"] for r in results if r["status"] == "FAIL"]
        # TELEGRAM_BOT_TOKEN 또는 TELEGRAM_GROUP_CHAT_ID 누락 FAIL
        assert any("env_TELEGRAM" in n for n in fail_names), (
            f"TELEGRAM 관련 FAIL이 없음: {fail_names}"
        )

    def test_required_vars_set_returns_pass(self, tmp_path):
        """필수 환경변수 설정 시 PASS."""
        env = {
            "TELEGRAM_BOT_TOKEN": "1234567890:ABCdef",
            "TELEGRAM_GROUP_CHAT_ID": "-1001234567890",
            "GEMINI_API_KEY": "test-api-key-xyz",
        }
        results = self._run_with_env(env, tmp_path)
        statuses = {r["name"]: r["status"] for r in results}
        assert statuses.get("env_TELEGRAM_BOT_TOKEN") == "PASS"
        assert statuses.get("env_TELEGRAM_GROUP_CHAT_ID") == "PASS"

    def test_api_key_missing_returns_fail(self, tmp_path):
        """API 키 전부 미설정 시 FAIL."""
        env = {
            "TELEGRAM_BOT_TOKEN": "1234567890:ABCdef",
            "TELEGRAM_GROUP_CHAT_ID": "-1001234567890",
        }
        results = self._run_with_env(env, tmp_path)
        statuses = {r["name"]: r["status"] for r in results}
        assert statuses.get("env_api_key") == "FAIL"

    def test_api_key_set_returns_pass(self, tmp_path):
        """API 키 하나라도 설정 시 PASS."""
        env = {
            "TELEGRAM_BOT_TOKEN": "tok",
            "TELEGRAM_GROUP_CHAT_ID": "-123",
            "ANTHROPIC_API_KEY": "sk-ant-test-key",
        }
        results = self._run_with_env(env, tmp_path)
        statuses = {r["name"]: r["status"] for r in results}
        assert statuses.get("env_api_key") == "PASS"

    def test_dotenv_loaded_pass_when_env_exists(self, tmp_path):
        """.env 파일 존재 시 dotenv_loaded PASS."""
        env_file = tmp_path / ".env"
        env_file.write_text("TELEGRAM_BOT_TOKEN=test123\n")

        mod = _load_preflight()
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path
        try:
            with patch.dict(os.environ, {}, clear=False):
                results = mod.check_env_vars()
            statuses = {r["name"]: r["status"] for r in results}
            assert statuses.get("dotenv_loaded") == "PASS"
        finally:
            mod._PROJECT_ROOT = original_root

    def test_dotenv_warn_when_env_missing(self, tmp_path):
        """.env 파일 없으면 dotenv_loaded WARN."""
        mod = _load_preflight()
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path
        try:
            results = mod.check_env_vars()
            statuses = {r["name"]: r["status"] for r in results}
            assert statuses.get("dotenv_loaded") == "WARN"
        finally:
            mod._PROJECT_ROOT = original_root


# ---------------------------------------------------------------------------
# 테스트 4: check_db_files()
# ---------------------------------------------------------------------------

class TestCheckDbFiles:
    """check_db_files() 함수 단위 테스트."""

    def test_db_missing_returns_warn(self, tmp_path):
        """DB 파일 없으면 WARN (자동 생성 예정)."""
        mod = _load_preflight()
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path
        try:
            results = mod.check_db_files()
            # ai_org.db 또는 tasks.db 중 WARN이 있어야 함
            warn_names = [r["name"] for r in results if r["status"] == "WARN"]
            assert len(warn_names) > 0, "DB 없는데 WARN이 없음"
        finally:
            mod._PROJECT_ROOT = original_root

    def test_db_exists_returns_pass(self, tmp_path):
        """DB 파일 있으면 PASS."""
        (tmp_path / "ai_org.db").write_bytes(b"SQLite format 3\x00")
        (tmp_path / "tasks.db").write_bytes(b"SQLite format 3\x00")

        mod = _load_preflight()
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path
        try:
            results = mod.check_db_files()
            statuses = {r["name"]: r["status"] for r in results}
            assert statuses.get("db_ai_org.db") == "PASS"
            assert statuses.get("db_tasks.db") == "PASS"
        finally:
            mod._PROJECT_ROOT = original_root


# ---------------------------------------------------------------------------
# 테스트 5: check_config_files()
# ---------------------------------------------------------------------------

class TestCheckConfigFiles:
    """check_config_files() 함수 단위 테스트."""

    def test_missing_config_returns_fail(self, tmp_path):
        """핵심 설정 파일 없으면 FAIL."""
        mod = _load_preflight()
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path
        try:
            results = mod.check_config_files()
            fail_names = [r["name"] for r in results if r["status"] == "FAIL"]
            # orchestration.yaml 등 최소 1개 FAIL이어야 함
            assert len(fail_names) > 0, "설정 파일 없는데 FAIL이 없음"
        finally:
            mod._PROJECT_ROOT = original_root

    def test_existing_config_returns_pass(self, tmp_path):
        """설정 파일 존재 시 PASS."""
        for f in ["orchestration.yaml", "organizations.yaml", "workers.yaml", "agent_hints.yaml"]:
            (tmp_path / f).write_text("# placeholder\n")

        mod = _load_preflight()
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path
        try:
            results = mod.check_config_files()
            statuses = {r["name"]: r["status"] for r in results}
            assert statuses.get("config_orchestration.yaml") == "PASS"
        finally:
            mod._PROJECT_ROOT = original_root


# ---------------------------------------------------------------------------
# 테스트 6: check_infra_baseline()
# ---------------------------------------------------------------------------

class TestCheckInfraBaseline:
    """check_infra_baseline() 함수 단위 테스트."""

    def test_missing_baseline_returns_fail(self, tmp_path):
        """infra-baseline.yaml 없으면 FAIL."""
        mod = _load_preflight()
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path
        try:
            results = mod.check_infra_baseline()
            assert results[0]["status"] == "FAIL"
        finally:
            mod._PROJECT_ROOT = original_root

    def test_existing_baseline_returns_pass(self, tmp_path):
        """infra-baseline.yaml 있으면 PASS."""
        (tmp_path / "infra-baseline.yaml").write_text(
            "version: v0.4.0\ntimeout: 120\n"
        )
        mod = _load_preflight()
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path
        try:
            results = mod.check_infra_baseline()
            assert results[0]["status"] == "PASS"
        finally:
            mod._PROJECT_ROOT = original_root

    def test_baseline_version_extracted(self, tmp_path):
        """baseline version이 detail에 포함된다."""
        (tmp_path / "infra-baseline.yaml").write_text(
            "version: v1.2.3\ntimeout: 120\n"
        )
        mod = _load_preflight()
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path
        try:
            results = mod.check_infra_baseline()
            assert "v1.2.3" in results[0]["detail"]
        finally:
            mod._PROJECT_ROOT = original_root


# ---------------------------------------------------------------------------
# 테스트 7: check_deprecated_models()
# ---------------------------------------------------------------------------

class TestCheckDeprecatedModels:
    """check_deprecated_models() 함수 단위 테스트."""

    def test_no_deprecated_model_returns_pass(self, tmp_path):
        """deprecated 모델 없으면 PASS."""
        (tmp_path / "core").mkdir()
        (tmp_path / "core" / "example.py").write_text(
            'MODEL = "gemini-2.5-flash"\n'
        )
        mod = _load_preflight()
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path
        try:
            results = mod.check_deprecated_models()
            assert results[0]["status"] == "PASS"
        finally:
            mod._PROJECT_ROOT = original_root

    def test_deprecated_model_in_core_returns_fail(self, tmp_path):
        """core/ 에 gemini-2.0-flash 있으면 FAIL."""
        (tmp_path / "core").mkdir()
        (tmp_path / "core" / "bad_model.py").write_text(
            'MODEL = "gemini-2.0-flash"\n'
        )
        mod = _load_preflight()
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path
        try:
            results = mod.check_deprecated_models()
            assert results[0]["status"] == "FAIL"
            assert "gemini-2.0-flash" in results[0]["detail"]
        finally:
            mod._PROJECT_ROOT = original_root

    def test_deprecated_model_in_scripts_returns_fail(self, tmp_path):
        """scripts/ 에 gemini-2.0-flash 있으면 FAIL."""
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "runner.py").write_text(
            'ENGINE = "gemini-2.0-flash"\n'
        )
        mod = _load_preflight()
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path
        try:
            results = mod.check_deprecated_models()
            assert results[0]["status"] == "FAIL"
        finally:
            mod._PROJECT_ROOT = original_root

    def test_deprecated_model_in_docs_is_ok(self, tmp_path):
        """docs/ 에는 gemini-2.0-flash 있어도 탐지하지 않는다."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "deprecated.md").write_text(
            "# Deprecated: gemini-2.0-flash (2026-06-01 서비스 종료)\n"
        )
        mod = _load_preflight()
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path
        try:
            results = mod.check_deprecated_models()
            assert results[0]["status"] == "PASS", (
                "docs/는 탐지 대상 외이므로 PASS여야 함"
            )
        finally:
            mod._PROJECT_ROOT = original_root


# ---------------------------------------------------------------------------
# 테스트 8: check_ruff() 유연성 테스트
# ---------------------------------------------------------------------------

class TestCheckRuff:
    """check_ruff() 함수 단위 테스트."""

    def test_ruff_returns_valid_status(self):
        """check_ruff()가 유효한 status dict를 반환한다."""
        mod = _load_preflight()
        results = mod.check_ruff()
        assert len(results) > 0
        for r in results:
            assert r["status"] in ("PASS", "WARN", "FAIL")
            assert "ruff" in r["name"]

    def test_ruff_without_venv_returns_warn(self, tmp_path):
        """venv 없으면 WARN을 반환한다."""
        mod = _load_preflight()
        original_root = mod._PROJECT_ROOT
        mod._PROJECT_ROOT = tmp_path
        # core 디렉토리만 만들고 venv 없음
        (tmp_path / "core").mkdir()
        try:
            results = mod.check_ruff()
            assert results[0]["status"] == "WARN"
        finally:
            mod._PROJECT_ROOT = original_root


# ---------------------------------------------------------------------------
# 테스트 9: _check_result() 헬퍼 구조
# ---------------------------------------------------------------------------

class TestCheckResultHelper:
    """_check_result() 반환 구조 검증."""

    def test_check_result_returns_dict_with_three_keys(self):
        """_check_result()는 name/status/detail 3키 dict를 반환한다."""
        mod = _load_preflight()
        r = mod._check_result("test_name", "PASS", "test detail")
        assert r == {"name": "test_name", "status": "PASS", "detail": "test detail"}

    def test_check_result_fail_status(self):
        """FAIL status도 동일한 구조를 가진다."""
        mod = _load_preflight()
        r = mod._check_result("check_x", "FAIL", "something went wrong")
        assert r["status"] == "FAIL"
        assert r["name"] == "check_x"

    def test_check_result_warn_status(self):
        """WARN status도 동일한 구조를 가진다."""
        mod = _load_preflight()
        r = mod._check_result("check_y", "WARN", "minor issue")
        assert r["status"] == "WARN"


# ---------------------------------------------------------------------------
# 테스트 10: _load_dotenv() 함수
# ---------------------------------------------------------------------------

class TestLoadDotenv:
    """_load_dotenv() 간이 .env 파서 테스트."""

    def test_parses_key_value_pairs(self, tmp_path):
        """KEY=VALUE 형태의 .env 파일을 파싱한다."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "FOO=bar\nBAZ=qux\n"
        )
        mod = _load_preflight()
        result = mod._load_dotenv(env_file)
        assert result.get("FOO") == "bar"
        assert result.get("BAZ") == "qux"

    def test_ignores_comments(self, tmp_path):
        """# 주석 행을 무시한다."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# comment\nFOO=bar\n# another comment\n"
        )
        mod = _load_preflight()
        result = mod._load_dotenv(env_file)
        assert "# comment" not in result
        assert result.get("FOO") == "bar"

    def test_ignores_empty_values(self, tmp_path):
        """값이 없는 변수는 파싱 결과에서 제외된다."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "EMPTY_VAR=\nSET_VAR=hello\n"
        )
        mod = _load_preflight()
        result = mod._load_dotenv(env_file)
        assert "EMPTY_VAR" not in result
        assert result.get("SET_VAR") == "hello"

    def test_strips_quotes(self, tmp_path):
        """따옴표로 감싼 값도 올바르게 파싱한다."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            'QUOTED="hello world"\nSINGLE=\'foo bar\'\n'
        )
        mod = _load_preflight()
        result = mod._load_dotenv(env_file)
        assert result.get("QUOTED") == "hello world"
        assert result.get("SINGLE") == "foo bar"

    def test_missing_file_returns_empty_dict(self, tmp_path):
        """존재하지 않는 파일이면 빈 dict를 반환한다."""
        mod = _load_preflight()
        result = mod._load_dotenv(tmp_path / "nonexistent.env")
        assert result == {}
