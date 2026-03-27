"""tests/unit/test_preflight_guards.py — 방어 코드 단위 테스트.

다음 3가지 방어 코드 경로를 커버한다:
1. timeout 기본값 사용 시 경고 로그 (core/env_guard.py)
2. 필수 환경변수 누락 시 ValueError (core/env_guard.py)
3. Telethon listener min_id 필터 누락 시 경고 로그 (scripts/telethon_listener.py)
4. tests/e2e/preflight_check.py run_preflight_checks() dict 반환 구조 검증
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ===========================================================================
# 1. core/env_guard.py — warn_default_timeout
# ===========================================================================
class TestWarnDefaultTimeout:
    """warn_default_timeout() 경고 로그 방어 코드 테스트."""

    def test_warns_when_using_default_value(self, caplog):
        """timeout이 기본값(120)과 동일하면 WARNING 로그를 출력한다."""
        from core.env_guard import warn_default_timeout

        with caplog.at_level(logging.WARNING, logger="core.env_guard"):
            warn_default_timeout(120, default=120, param_name="e2e_timeout")

        assert any("120" in r.message and "기본값" in r.message for r in caplog.records), (
            "기본값 사용 시 WARNING 로그가 출력되지 않았습니다"
        )

    def test_no_warning_when_custom_value(self, caplog):
        """timeout이 기본값과 다르면 WARNING 로그가 없어야 한다."""
        from core.env_guard import warn_default_timeout

        with caplog.at_level(logging.WARNING, logger="core.env_guard"):
            warn_default_timeout(300, default=120, param_name="e2e_timeout")

        timeout_warns = [r for r in caplog.records if "기본값" in r.message]
        assert len(timeout_warns) == 0, "기본값과 다른 timeout인데 경고가 출력되었습니다"

    def test_warns_when_timeout_is_none(self, caplog):
        """timeout이 None이면 WARNING 로그를 출력한다."""
        from core.env_guard import warn_default_timeout

        with caplog.at_level(logging.WARNING, logger="core.env_guard"):
            warn_default_timeout(None, default=120, param_name="e2e_timeout")

        assert any("None" in r.message or "미설정" in r.message for r in caplog.records)


# ===========================================================================
# 2. core/env_guard.py — require_env
# ===========================================================================
class TestRequireEnv:
    """require_env() 환경변수 누락 시 ValueError 방어 코드 테스트."""

    def test_raises_value_error_when_missing(self):
        """환경변수가 없으면 ValueError가 발생한다."""
        from core.env_guard import require_env

        non_existent = "_TEST_GUARD_VAR_NEVER_SET_12345"
        os.environ.pop(non_existent, None)

        with pytest.raises(ValueError, match=non_existent):
            require_env(non_existent)

    def test_raises_value_error_when_empty(self):
        """환경변수가 빈 문자열이면 ValueError가 발생한다."""
        from core.env_guard import require_env

        test_var = "_TEST_GUARD_EMPTY_VAR_99999"
        os.environ[test_var] = ""
        try:
            with pytest.raises(ValueError, match=test_var):
                require_env(test_var)
        finally:
            os.environ.pop(test_var, None)

    def test_returns_value_when_set(self):
        """환경변수가 설정되어 있으면 값을 반환한다."""
        from core.env_guard import require_env

        test_var = "_TEST_GUARD_SET_VAR_77777"
        os.environ[test_var] = "hello_world"
        try:
            result = require_env(test_var)
            assert result == "hello_world"
        finally:
            os.environ.pop(test_var, None)

    def test_error_message_includes_var_name(self):
        """ValueError 메시지에 환경변수 이름이 포함된다."""
        from core.env_guard import require_env

        test_var = "_TEST_GUARD_MSG_VAR_55555"
        os.environ.pop(test_var, None)

        with pytest.raises(ValueError) as exc_info:
            require_env(test_var, context="테스트 컨텍스트")

        assert test_var in str(exc_info.value)

    def test_get_env_or_warn_returns_default_and_logs(self, caplog):
        """get_env_or_warn()는 없는 변수에 대해 default 반환 + 경고 로그."""
        from core.env_guard import get_env_or_warn

        test_var = "_TEST_GUARD_WARN_VAR_33333"
        os.environ.pop(test_var, None)

        with caplog.at_level(logging.WARNING, logger="core.env_guard"):
            result = get_env_or_warn(test_var, default="fallback_value")

        assert result == "fallback_value"
        assert any(test_var in r.message for r in caplog.records)


# ===========================================================================
# 3. scripts/telethon_listener.py — min_id guard
# ===========================================================================
class TestTelethonMinIdGuard:
    """make_handler() min_id 필터 누락 시 경고 로그 방어 코드 테스트."""

    def _make_helper(self):
        """TelethonListenerHelper 인스턴스를 mock client로 생성."""
        from scripts.telethon_listener import TelethonListenerHelper

        client = MagicMock()
        return TelethonListenerHelper(client)

    def test_warns_when_record_min_id_not_called(self, caplog):
        """record_min_id() 없이 make_handler() 호출 시 WARNING 로그가 출력된다."""
        helper = self._make_helper()
        collected: list = []
        stop_flag = [False]
        chat_entity = 12345678  # int chat_id

        with caplog.at_level(logging.WARNING, logger="scripts.telethon_listener"):
            helper.make_handler(chat_entity, collected, stop_flag)

        assert any(
            "record_min_id" in r.message or "cross-contamination" in r.message
            for r in caplog.records
        ), "record_min_id 미호출 경고가 출력되지 않았습니다"

    def test_no_warning_when_record_min_id_called(self, caplog):
        """record_min_id()가 호출된 후 make_handler() 호출 시 경고가 없어야 한다."""
        from scripts.telethon_listener import TelethonListenerHelper

        client = MagicMock()
        helper = TelethonListenerHelper(client)

        # record_min_id를 직접 호출하지 않고 내부 dict에 값을 직접 주입
        chat_entity = 99887766
        helper._min_ids[chat_entity] = 0  # 0이지만 명시적으로 기록된 상태

        collected: list = []
        stop_flag = [False]

        with caplog.at_level(logging.WARNING, logger="scripts.telethon_listener"):
            helper.make_handler(chat_entity, collected, stop_flag)

        cross_warn = [
            r for r in caplog.records if "cross-contamination" in r.message
        ]
        assert len(cross_warn) == 0, "이미 record_min_id가 호출됐는데 경고가 출력되었습니다"

    def test_handler_skips_old_messages(self):
        """반환된 핸들러가 min_id 이하 메시지를 skip한다."""
        import asyncio
        from scripts.telethon_listener import CollectedMessage, TelethonListenerHelper

        client = MagicMock()
        helper = TelethonListenerHelper(client)

        chat_entity = 11223344
        helper._min_ids[chat_entity] = 100  # min_id = 100

        collected: list[CollectedMessage] = []
        stop_flag = [False]

        handler = helper.make_handler(chat_entity, collected, stop_flag)

        # min_id 이하 메시지 이벤트 mock
        old_event = MagicMock()
        old_event.message.id = 50  # <= min_id=100 이므로 skip

        asyncio.get_event_loop().run_until_complete(handler(old_event))
        assert len(collected) == 0, "min_id 이하 메시지가 수집되어서는 안 됩니다"


# ===========================================================================
# 4. tests/e2e/preflight_check.py — dict 반환 구조 검증
# ===========================================================================
class TestPreflightChecksModule:
    """tests/e2e/preflight_check.py run_preflight_checks() 구조 검증."""

    def _import_module(self):
        """tests/e2e/preflight_check.py 를 동적 import."""
        import importlib.util

        mod_path = Path(__file__).parent.parent / "e2e" / "preflight_check.py"
        spec = importlib.util.spec_from_file_location("e2e_preflight_check", mod_path)
        assert spec and spec.loader, f"모듈 로드 실패: {mod_path}"
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def test_returns_dict_with_required_keys(self):
        """run_preflight_checks()가 필수 키를 포함한 dict를 반환한다."""
        mod = self._import_module()
        result = mod.run_preflight_checks(exit_on_fail=False)

        assert isinstance(result, dict), f"dict가 아닌 타입 반환: {type(result)}"
        for key in ("passed", "timeout", "filter", "env", "errors"):
            assert key in result, f"필수 키 '{key}' 가 결과 dict에 없습니다"

    def test_passed_is_bool(self):
        """result['passed'] 는 bool 타입이어야 한다."""
        mod = self._import_module()
        result = mod.run_preflight_checks(exit_on_fail=False)
        assert isinstance(result["passed"], bool)

    def test_errors_is_list(self):
        """result['errors'] 는 list 타입이어야 한다."""
        mod = self._import_module()
        result = mod.run_preflight_checks(exit_on_fail=False)
        assert isinstance(result["errors"], list)

    def test_check_timeout_returns_dict(self):
        """_check_timeout() 이 ok/msg/value 키를 포함한 dict를 반환한다."""
        mod = self._import_module()
        result = mod._check_timeout(120)
        assert "ok" in result
        assert "msg" in result
        assert "value" in result

    def test_check_timeout_fails_on_zero(self):
        """_check_timeout(0) 은 ok=False를 반환한다."""
        mod = self._import_module()
        result = mod._check_timeout(0)
        assert result["ok"] is False

    def test_check_timeout_fails_on_negative(self):
        """_check_timeout(-1) 은 ok=False를 반환한다."""
        mod = self._import_module()
        result = mod._check_timeout(-1)
        assert result["ok"] is False

    def test_check_env_detects_missing_required(self):
        """_check_env()는 누락된 required 변수를 missing_required에 넣는다."""
        mod = self._import_module()
        non_existent = "_PREFLIGHT_TEST_NEVER_SET_98765"
        os.environ.pop(non_existent, None)

        result = mod._check_env([non_existent], [])
        assert result["ok"] is False
        assert non_existent in result["missing_required"]

    def test_check_filter_rejects_shell_injection(self):
        """_check_filter()는 ; | & 등 shell 특수문자를 거부한다."""
        mod = self._import_module()
        for bad in ["foo;bar", "a|b", "x&y", "$(cmd)", "`cmd`"]:
            result = mod._check_filter(bad)
            assert result["ok"] is False, f"위험한 filter 패턴이 통과됨: {bad!r}"
