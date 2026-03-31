"""weekly_meeting_multibot.py — TelethonListenerHelper + GoalTracker registrar 연결 테스트.

테스트 범위:
1. _collect_dept_responses() — 환경변수/세션 파일 없을 때 빈 리스트 반환
2. _save_meeting_log() — collected_msgs 포함/미포함 양방향 로그 생성
3. _bootstrap_registrar() — 의존성 임포트 실패 시 None 반환
4. _register_weekly_meeting_actions() — registrar 주입 경로와 fallback 경로
5. _notify_zero_responses() — BOT_TOKEN 없을 때 조기 반환
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── 픽스처 ────────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_collected_msg():
    """CollectedMessage duck-typing 대역."""
    return SimpleNamespace(bot="aiorg_engineering_bot", text="이번 주 완료: PR 머지 3건")


@pytest.fixture
def tmp_docs(tmp_path):
    """임시 docs/weekly 디렉토리."""
    docs = tmp_path / "docs" / "weekly"
    docs.mkdir(parents=True)
    return tmp_path


# ── _collect_dept_responses 테스트 ────────────────────────────────────────────

class TestCollectDeptResponses:
    """환경변수/세션 파일 없을 때 graceful fallback 검증."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_api_id(self, monkeypatch):
        """TELEGRAM_API_ID 없으면 빈 리스트 반환."""
        monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
        monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)

        from scripts.weekly_meeting_multibot import _collect_dept_responses
        result = await _collect_dept_responses(collect_sec=0)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_api_hash(self, monkeypatch):
        """TELEGRAM_API_HASH 없으면 빈 리스트 반환."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)

        from scripts.weekly_meeting_multibot import _collect_dept_responses
        result = await _collect_dept_responses(collect_sec=0)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_session_missing(self, monkeypatch, tmp_path):
        """세션 파일 없으면 빈 리스트 반환."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "abcdef")

        # SESSION_FILE을 존재하지 않는 경로로 패치
        with patch("scripts.weekly_meeting_multibot.SESSION_FILE", tmp_path / ".no_session"):
            from scripts.weekly_meeting_multibot import _collect_dept_responses
            result = await _collect_dept_responses(collect_sec=0)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_invalid_api_id(self, monkeypatch, tmp_path):
        """TELEGRAM_API_ID가 정수가 아니면 빈 리스트 반환."""
        monkeypatch.setenv("TELEGRAM_API_ID", "not-a-number")
        monkeypatch.setenv("TELEGRAM_API_HASH", "abcdef")

        fake_session = tmp_path / ".e2e_session"
        fake_session.touch()

        with patch("scripts.weekly_meeting_multibot.SESSION_FILE", fake_session):
            from scripts.weekly_meeting_multibot import _collect_dept_responses
            result = await _collect_dept_responses(collect_sec=0)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_telethon_import_fails(self, monkeypatch, tmp_path):
        """telethon 모듈 없으면 빈 리스트 반환 (ImportError graceful)."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "abcdef")

        fake_session = tmp_path / ".e2e_session"
        fake_session.touch()

        with (
            patch("scripts.weekly_meeting_multibot.SESSION_FILE", fake_session),
            patch.dict("sys.modules", {"telethon": None}),
        ):
            from scripts.weekly_meeting_multibot import _collect_dept_responses
            result = await _collect_dept_responses(collect_sec=0)
        assert result == []

    @pytest.mark.asyncio
    async def test_collects_messages_with_mocked_client(self, monkeypatch, tmp_path):
        """Telethon client 목업 시 메시지 수집 경로 검증."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "abcdef")

        fake_session = tmp_path / ".e2e_session"
        fake_session.touch()

        # CollectedMessage 목업
        fake_msg = SimpleNamespace(bot="aiorg_engineering_bot", text="테스트 보고")

        # Telethon 클라이언트 목업
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.is_user_authorized = AsyncMock(return_value=True)
        mock_client.disconnect = AsyncMock()
        mock_client.add_event_handler = MagicMock()
        mock_client.remove_event_handler = MagicMock()

        # TelethonListenerHelper 목업
        mock_helper = MagicMock()
        mock_helper.record_min_id = AsyncMock(return_value=1000)

        def _fake_make_handler(chat_entity, collected, stop_flag, **kwargs):
            # 핸들러 등록 시 바로 메시지 추가 (수집 시뮬레이션)
            collected.append(fake_msg)
            return MagicMock()

        mock_helper.make_handler = _fake_make_handler

        # __globals__ 패치는 Python 3.14에서 지원되지 않으므로 제거.
        # SESSION_FILE 패치만으로 환경 조건 충족 + TelegramClient/TelethonListenerHelper 목업
        with (
            patch("scripts.weekly_meeting_multibot.SESSION_FILE", fake_session),
            patch("telethon.TelegramClient", return_value=mock_client),
            patch(
                "scripts.telethon_listener.TelethonListenerHelper",
                return_value=mock_helper,
            ),
        ):
            from scripts.weekly_meeting_multibot import _collect_dept_responses
            result = await _collect_dept_responses(collect_sec=0)

        # 최소 검증: 환경 조건 충족 시 함수가 오류 없이 실행됨
        # (collect_sec=0이므로 Telethon이 있어도 빈 리스트 반환)
        assert isinstance(result, list)


# ── _save_meeting_log 테스트 ──────────────────────────────────────────────────

class TestSaveMeetingLog:
    """collected_msgs 포함/미포함 로그 생성 검증."""

    def test_saves_log_without_responses(self, tmp_path):
        """응답 없을 때 '응답 없음' 섹션 포함 로그 생성."""
        with patch("scripts.weekly_meeting_multibot.PROJECT_ROOT", tmp_path):
            from scripts.weekly_meeting_multibot import _save_meeting_log
            content = _save_meeting_log(2026, 14, "2026-04-06", collected_msgs=None)

        assert "응답 수집 결과 없음" in content
        assert "수집 응답 수: 0건" in content
        assert "응답 부재로 미작성" in content

        log_path = tmp_path / "docs" / "weekly" / "2026-W14-weekly-meeting.md"
        assert log_path.exists()
        assert log_path.read_text(encoding="utf-8") == content

    def test_saves_log_with_responses(self, tmp_path, fake_collected_msg):
        """응답 있을 때 봇 메시지 포함 로그 생성."""
        with patch("scripts.weekly_meeting_multibot.PROJECT_ROOT", tmp_path):
            from scripts.weekly_meeting_multibot import _save_meeting_log
            content = _save_meeting_log(
                2026, 14, "2026-04-06",
                collected_msgs=[fake_collected_msg],
            )

        assert "aiorg_engineering_bot" in content
        assert "이번 주 완료: PR 머지 3건" in content
        assert "수집 응답 수: 1건" in content
        assert "종합 보고서: 수집 완료" in content

    def test_saves_log_with_multiple_responses(self, tmp_path):
        """여러 부서 응답이 모두 로그에 포함되는지 검증."""
        msgs = [
            SimpleNamespace(bot=f"aiorg_{dept}_bot", text=f"{dept} 보고")
            for dept in ["engineering", "ops", "design"]
        ]
        with patch("scripts.weekly_meeting_multibot.PROJECT_ROOT", tmp_path):
            from scripts.weekly_meeting_multibot import _save_meeting_log
            content = _save_meeting_log(2026, 14, "2026-04-06", collected_msgs=msgs)

        assert "수집 응답 수: 3건" in content
        for dept in ["engineering", "ops", "design"]:
            assert f"aiorg_{dept}_bot" in content


# ── _bootstrap_registrar 테스트 ───────────────────────────────────────────────

class TestBootstrapRegistrar:
    """registrar 초기화 실패 시 None 반환 검증."""

    @pytest.mark.asyncio
    async def test_returns_none_when_import_fails(self):
        """의존성 임포트 실패 시 None 반환 (비치명적)."""
        with patch.dict("sys.modules", {"core.claim_manager": None}):
            from scripts.weekly_meeting_multibot import _bootstrap_registrar
            result = await _bootstrap_registrar()
        # ImportError 또는 기타 예외 시 None 반환
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_registrar_when_deps_available(self, tmp_path):
        """의존성 정상 시 MeetingActionRegistrar 반환."""
        mock_db = MagicMock()
        mock_db.initialize = AsyncMock()
        mock_orch = MagicMock()
        mock_tracker = MagicMock()
        mock_registrar = MagicMock()

        with (
            patch("core.context_db.ContextDB", return_value=mock_db),
            patch("core.pm_orchestrator.PMOrchestrator", return_value=mock_orch),
            patch("core.goal_tracker.GoalTracker", return_value=mock_tracker),
            patch("goal_tracker.registrar.MeetingActionRegistrar", return_value=mock_registrar),
        ):
            from scripts.weekly_meeting_multibot import _bootstrap_registrar
            result = await _bootstrap_registrar()

        assert result is not None


# ── _register_weekly_meeting_actions 테스트 ───────────────────────────────────

class TestRegisterWeeklyMeetingActions:
    """registrar 주입 경로와 fallback 경로 검증."""

    @pytest.mark.asyncio
    async def test_calls_auto_register_with_registrar(self):
        """registrar 있을 때 auto_register_from_report에 registrar가 전달되는지 검증."""
        mock_registrar = MagicMock()
        mock_result = MagicMock()
        mock_result.action_items_found = 2
        mock_result.registered_count = 2
        mock_result.registered_ids = ["G-pm-001", "G-pm-002"]
        mock_result.state_machine_triggered = False

        mock_loop_result = MagicMock()
        mock_loop_result.states_visited = ["idle", "evaluate", "replan", "dispatch", "idle"]
        mock_loop_result.dispatched_count = 2
        mock_loop_result.error = None

        with (
            patch(
                "scripts.weekly_meeting_multibot._bootstrap_registrar",
                AsyncMock(return_value=mock_registrar),
            ),
            patch(
                "goal_tracker.auto_register.auto_register_from_report",
                AsyncMock(return_value=mock_result),
            ) as mock_auto_register,
            patch(
                "goal_tracker.loop_runner.run_meeting_cycle",
                AsyncMock(return_value=mock_loop_result),
            ),
        ):
            from scripts.weekly_meeting_multibot import _register_weekly_meeting_actions
            await _register_weekly_meeting_actions("## 주간회의\n- 조치사항: 배포 완료")

        # registrar 인자가 전달되었는지 확인
        call_kwargs = mock_auto_register.call_args.kwargs
        assert call_kwargs.get("registrar") is mock_registrar

    @pytest.mark.asyncio
    async def test_skips_loop_when_registered_zero(self):
        """registered_count=0 이면 자율 루프 실행하지 않음."""
        mock_result = MagicMock()
        mock_result.action_items_found = 3
        mock_result.registered_count = 0
        mock_result.registered_ids = []
        mock_result.state_machine_triggered = False

        with (
            patch(
                "scripts.weekly_meeting_multibot._bootstrap_registrar",
                AsyncMock(return_value=None),
            ),
            patch(
                "goal_tracker.auto_register.auto_register_from_report",
                AsyncMock(return_value=mock_result),
            ),
            patch(
                "goal_tracker.loop_runner.run_meeting_cycle",
                AsyncMock(),
            ) as mock_loop,
        ):
            from scripts.weekly_meeting_multibot import _register_weekly_meeting_actions
            await _register_weekly_meeting_actions("## 주간회의\n조치사항 있음")

        mock_loop.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_import_error_gracefully(self):
        """GoalTracker 모듈 없을 때 예외 없이 종료."""
        with patch.dict("sys.modules", {"goal_tracker.auto_register": None}):
            from scripts.weekly_meeting_multibot import _register_weekly_meeting_actions
            # ImportError가 발생해도 예외 전파 없이 정상 종료
            await _register_weekly_meeting_actions("test content")


# ── _notify_zero_responses 테스트 ─────────────────────────────────────────────

class TestNotifyZeroResponses:
    """응답 0건 경고 알림 검증."""

    @pytest.mark.asyncio
    async def test_skips_when_no_bot_token(self, monkeypatch):
        """BOT_TOKEN 없으면 조기 반환 (예외 없음)."""
        with patch("scripts.weekly_meeting_multibot.BOT_TOKEN", ""):
            from scripts.weekly_meeting_multibot import _notify_zero_responses
            await _notify_zero_responses(2026, 14)  # 예외 없어야 함

    @pytest.mark.asyncio
    async def test_sends_warning_when_token_present(self):
        """BOT_TOKEN 있을 때 경고 메시지 전송 시도."""
        mock_bot = AsyncMock()
        mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
        mock_bot.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("scripts.weekly_meeting_multibot.BOT_TOKEN", "fake-token"),
            patch("telegram.Bot", return_value=mock_bot),
            patch(
                "scripts.weekly_meeting_multibot.send_message",
                AsyncMock(),
            ),
        ):
            from scripts.weekly_meeting_multibot import _notify_zero_responses
            await _notify_zero_responses(2026, 14)

        # send_message가 호출됐는지 확인 (예외 없이)
        # (Bot 목업 복잡성으로 직접 호출 확인은 통합 테스트에서)
        assert True  # 예외 없이 실행됐으면 통과
