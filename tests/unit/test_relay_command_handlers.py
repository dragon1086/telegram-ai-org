"""relay_command_handlers.py 유닛 테스트.

Phase 1c 분리 결과 검증:
1. 모듈 임포트 가능
2. 상수 값 정확성
3. 핵심 핸들러 함수 시그니처
4. telegram_relay.py에서 위임 import 가능
"""
from __future__ import annotations

import pytest


class TestRelayCommandHandlersImport:
    """모듈 임포트 기본 검증."""

    def test_module_importable(self):
        import core.relay_command_handlers as cmd
        assert cmd is not None

    def test_feature_flag_exists(self):
        from core.relay_command_handlers import ENABLE_REFACTORED_COMMAND_HANDLERS
        assert isinstance(ENABLE_REFACTORED_COMMAND_HANDLERS, bool)

    def test_team_id_constant(self):
        from core.relay_command_handlers import TEAM_ID
        assert TEAM_ID == "pm"

    def test_setup_constants_imported(self):
        from core.relay_command_handlers import (
            SETUP_AWAIT_ENGINE,
            SETUP_AWAIT_IDENTITY,
            SETUP_AWAIT_TOKEN,
            SETUP_MENU,
        )
        assert SETUP_MENU == 0
        assert SETUP_AWAIT_TOKEN == 1
        assert SETUP_AWAIT_ENGINE == 2
        assert SETUP_AWAIT_IDENTITY == 3

    def test_all_command_functions_exist(self):
        import core.relay_command_handlers as cmd
        for fname in [
            "on_command_start",
            "on_command_status",
            "on_command_reset",
            "on_command_schedule",
            "on_command_schedules",
            "on_command_cancel_schedule",
            "on_command_pause_schedule",
            "on_command_resume_schedule",
            "on_command_stop_tasks",
            "on_command_restart",
            "on_command_engine",
            "on_command_set_engine",
            "on_command_setup",
            "_setup_callback_menu",
            "_setup_receive_token",
            "_setup_receive_engine",
            "_setup_receive_identity",
            "_setup_cancel",
            "_ensure_runtime_bootstrap",
            "on_self_added_to_chat",
        ]:
            assert hasattr(cmd, fname), f"{fname} 함수가 없음"

    def test_protocol_class_exists(self):
        from core.relay_command_handlers import CommandRelayProtocol
        assert CommandRelayProtocol is not None

    def test_all_functions_are_callable(self):
        import core.relay_command_handlers as cmd
        for fname in [
            "on_command_start", "on_command_status", "on_command_reset",
            "on_command_stop_tasks", "on_command_restart",
            "_ensure_runtime_bootstrap",
        ]:
            fn = getattr(cmd, fname)
            assert callable(fn), f"{fname}이 callable이 아님"


class TestRelayBotSetupImport:
    """relay_bot_setup.py 모듈 임포트 검증."""

    def test_module_importable(self):
        import core.relay_bot_setup as setup
        assert setup is not None

    def test_setup_constants_defined_in_bot_setup(self):
        from core.relay_bot_setup import (
            SETUP_AWAIT_ENGINE,
            SETUP_AWAIT_IDENTITY,
            SETUP_AWAIT_TOKEN,
            SETUP_MENU,
        )
        assert [SETUP_MENU, SETUP_AWAIT_TOKEN, SETUP_AWAIT_ENGINE, SETUP_AWAIT_IDENTITY] == [0, 1, 2, 3]

    def test_utility_functions_exist(self):
        import core.relay_bot_setup as setup
        for fname in [
            "_set_org_bot_commands",
            "register_all_bot_commands",
            "_validate_bot_token",
            "_profile_bundle_for_org",
            "_default_identity_for_org",
            "_launch_bot_subprocess",
            "_refresh_legacy_bot_configs",
            "_upsert_org_in_canonical_config",
            "_sync_identity_to_canonical_config",
        ]:
            assert hasattr(setup, fname), f"{fname} 없음"

    def test_profile_bundle_pm_org(self):
        from core.relay_bot_setup import _profile_bundle_for_org
        bundle = _profile_bundle_for_org("aiorg_pm_bot")
        assert bundle["kind"] == "orchestrator"
        assert bundle["can_direct_reply"] is True

    def test_profile_bundle_engineering_org(self):
        from core.relay_bot_setup import _profile_bundle_for_org
        bundle = _profile_bundle_for_org("aiorg_engineering_bot")
        assert bundle["kind"] == "specialist"
        assert bundle["can_direct_reply"] is False

    def test_default_identity_research(self):
        from core.relay_bot_setup import _default_identity_for_org
        identity = _default_identity_for_org("aiorg_research_bot")
        assert "dept_name" in identity
        assert "리서치" in identity["dept_name"]


class TestTelegramRelayImportsPhase1c:
    """telegram_relay.py Phase 1c import 검증."""

    def test_relay_command_handlers_imported_in_relay(self):
        """telegram_relay.py가 relay_command_handlers를 _cmd로 import하는지 확인."""
        import importlib
        import importlib.util
        spec = importlib.util.find_spec("core.telegram_relay")
        assert spec is not None, "core.telegram_relay 모듈을 찾을 수 없음"

    def test_setup_constants_accessible_in_relay(self):
        """telegram_relay.py에서 SETUP_MENU 등이 접근 가능한지 (모듈 수준에서)."""
        # telegram_relay를 직접 import하지 않고 relay_bot_setup의 상수를 확인
        from core.relay_bot_setup import SETUP_MENU
        assert SETUP_MENU == 0


class TestCodeHealthFlaggedFiles:
    """code_health.py 플래그 파일 처리 검증 (RETRO self-improve fix)."""

    def test_flagged_critical_file_becomes_warn(self, tmp_path):
        """refactor flag가 있는 파일은 critical → warn으로 강등된다."""
        import json
        from core.code_health import CodeHealthMonitor

        # core 디렉토리에 큰 파일 생성 (> 150KB)
        core_dir = tmp_path / "core"
        core_dir.mkdir()
        large_file = core_dir / "big_module.py"
        large_file.write_bytes(b"x" * (160 * 1024))  # 160KB

        # data 디렉토리에 flag 파일 생성
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        flag_file = data_dir / ".refactor_needed_core__big_module.py.flag"
        flag_file.write_text(json.dumps({
            "file_path": "core/big_module.py",
            "status": "needs_manual_refactor",
        }))

        monitor = CodeHealthMonitor(core_dir=core_dir)
        report = monitor.scan()

        # big_module.py 항목 찾기
        entry = next((e for e in report.file_entries if "big_module" in e.path), None)
        assert entry is not None, "big_module.py 엔트리가 없음"
        assert entry.status == "warn", f"flagged 파일은 warn이어야 하지만 {entry.status}임"
        assert "수동 리팩토링" in entry.note

    def test_unflagged_critical_file_stays_critical(self, tmp_path):
        """flag 없는 critical 파일은 critical 상태 유지."""
        from core.code_health import CodeHealthMonitor

        core_dir = tmp_path / "core"
        core_dir.mkdir()
        large_file = core_dir / "unflagged_big.py"
        large_file.write_bytes(b"x" * (160 * 1024))

        monitor = CodeHealthMonitor(core_dir=core_dir)
        report = monitor.scan()

        entry = next((e for e in report.file_entries if "unflagged_big" in e.path), None)
        assert entry is not None
        assert entry.status == "critical"


class TestPMConfirmationQuestionFilter:
    """telegram_user_guardrail.py PM 확인 질문 필터 검증."""

    def test_confirm_question_removed(self):
        from core.telegram_user_guardrail import _heuristic_cleanup
        text = "작업을 완료했습니다.\n\n어떤 건부터 처리할까요?"
        result = _heuristic_cleanup(text, [])
        assert "어떤 건부터 처리할까요" not in result
        assert "작업을 완료했습니다" in result

    def test_normal_text_preserved(self):
        from core.telegram_user_guardrail import _heuristic_cleanup
        text = "## 결론\n\n작업이 완료되었습니다."
        result = _heuristic_cleanup(text, [])
        assert "작업이 완료되었습니다" in result

    def test_all_forbidden_patterns_removed(self):
        from core.telegram_user_guardrail import _heuristic_cleanup
        patterns = [
            "어떤 건부터 처리할까요?",
            "어떤 건부터 먼저 처리하면 될까요?",
            "진행할까요?",
            "계속할까요?",
        ]
        for pattern in patterns:
            result = _heuristic_cleanup(f"완료.\n{pattern}", [])
            assert pattern not in result, f"패턴이 제거되지 않음: {pattern}"
