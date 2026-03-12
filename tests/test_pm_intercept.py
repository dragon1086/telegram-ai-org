"""Task 1.5 + 1.6 테스트 — PM Intercept Mechanism + TelegramRelay 통합."""
from __future__ import annotations

import os
import sys
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── PM Intercept: score=999 bid ────────────────────────────────────────────

class TestPMInterceptBid:
    """PM 오케스트레이터 활성 시 PM이 score=999로 입찰하는지 테스트."""

    def test_pm_bids_999_wins_over_dept(self, tmp_path):
        """PM score=999 > dept score=80 → PM 승리."""
        from core.claim_manager import ClaimManager
        cm = ClaimManager()
        # 임시 claims 디렉토리 사용
        cm.CLAIM_FILE_DIR = tmp_path

        text_hash = "abc123"
        cm.submit_bid(text_hash, "aiorg_pm_bot", 999)
        cm.submit_bid(text_hash, "aiorg_engineering_bot", 80)
        cm.submit_bid(text_hash, "aiorg_design_bot", 60)

        winner = cm.get_winner(text_hash)
        assert winner == "aiorg_pm_bot"

    def test_dept_wins_without_pm(self, tmp_path):
        """PM 없을 때 부서 봇 중 최고 점수가 승리."""
        from core.claim_manager import ClaimManager
        cm = ClaimManager()
        cm.CLAIM_FILE_DIR = tmp_path

        text_hash = "def456"
        cm.submit_bid(text_hash, "aiorg_engineering_bot", 80)
        cm.submit_bid(text_hash, "aiorg_design_bot", 60)

        winner = cm.get_winner(text_hash)
        assert winner == "aiorg_engineering_bot"


# ── PM_TASK 파싱 ──────────────────────────────────────────────────────────

class TestPMTaskParsing:
    """[PM_TASK:task_id|dept:org_id] 태그 파싱 테스트."""

    def test_parse_pm_task_tag(self):
        text = "[PM_TASK:T-pm-001|dept:aiorg_engineering_bot] 개발실에 배정: API 구현"
        match = re.search(r'\[PM_TASK:([^|]+)\|dept:([^\]]+)\]', text)
        assert match is not None
        assert match.group(1) == "T-pm-001"
        assert match.group(2) == "aiorg_engineering_bot"

    def test_parse_pm_task_tag_no_match(self):
        text = "일반 메시지입니다"
        match = re.search(r'\[PM_TASK:([^|]+)\|dept:([^\]]+)\]', text)
        assert match is None

    def test_parse_pm_task_with_spaces(self):
        text = "[PM_TASK:T-pm-002|dept:aiorg_design_bot] 디자인 작업"
        match = re.search(r'\[PM_TASK:([^|]+)\|dept:([^\]]+)\]', text)
        assert match is not None
        assert match.group(1).strip() == "T-pm-002"
        assert match.group(2).strip() == "aiorg_design_bot"


# ── ENABLE_PM_ORCHESTRATOR 플래그 ─────────────────────────────────────────

class TestFeatureFlag:
    """ENABLE_PM_ORCHESTRATOR 플래그 동작 테스트."""

    def test_flag_default_off(self):
        """기본값 = 비활성."""
        # 환경변수 없을 때
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENABLE_PM_ORCHESTRATOR", None)
            # 모듈 재로드
            import importlib
            import core.pm_orchestrator as mod
            importlib.reload(mod)
            assert mod.ENABLE_PM_ORCHESTRATOR is False

    def test_flag_on(self):
        """ENABLE_PM_ORCHESTRATOR=1 → True."""
        with patch.dict(os.environ, {"ENABLE_PM_ORCHESTRATOR": "1"}):
            import importlib
            import core.pm_orchestrator as mod
            importlib.reload(mod)
            assert mod.ENABLE_PM_ORCHESTRATOR is True

    def test_flag_off_explicit(self):
        """ENABLE_PM_ORCHESTRATOR=0 → False."""
        with patch.dict(os.environ, {"ENABLE_PM_ORCHESTRATOR": "0"}):
            import importlib
            import core.pm_orchestrator as mod
            importlib.reload(mod)
            assert mod.ENABLE_PM_ORCHESTRATOR is False


# ── TelegramRelay PM/Dept 모드 판정 ──────────────────────────────────────

class TestRelayModeDetection:
    """TelegramRelay의 PM/Dept 모드 판정 테스트."""

    @patch("core.telegram_relay.ENABLE_PM_ORCHESTRATOR", True)
    @patch("core.telegram_relay.KNOWN_DEPTS", {
        "aiorg_engineering_bot": "개발실",
        "aiorg_design_bot": "디자인실",
    })
    def test_pm_org_detected(self):
        """PM org_id (KNOWN_DEPTS에 없음) → _is_pm_org=True."""
        from core.telegram_relay import TelegramRelay
        relay = TelegramRelay(
            token="fake",
            allowed_chat_id=123,
            session_manager=MagicMock(),
            memory_manager=MagicMock(),
            org_id="aiorg_pm_bot",
        )
        assert relay._is_pm_org is True
        assert relay._is_dept_org is False

    @patch("core.telegram_relay.ENABLE_PM_ORCHESTRATOR", True)
    @patch("core.telegram_relay.KNOWN_DEPTS", {
        "aiorg_engineering_bot": "개발실",
        "aiorg_design_bot": "디자인실",
    })
    def test_dept_org_detected(self):
        """Dept org_id (KNOWN_DEPTS에 있음) → _is_dept_org=True."""
        from core.telegram_relay import TelegramRelay
        relay = TelegramRelay(
            token="fake",
            allowed_chat_id=123,
            session_manager=MagicMock(),
            memory_manager=MagicMock(),
            org_id="aiorg_engineering_bot",
        )
        assert relay._is_pm_org is False
        assert relay._is_dept_org is True

    @patch("core.telegram_relay.ENABLE_PM_ORCHESTRATOR", False)
    def test_flag_off_no_mode(self):
        """플래그 off → 둘 다 False."""
        from core.telegram_relay import TelegramRelay
        relay = TelegramRelay(
            token="fake",
            allowed_chat_id=123,
            session_manager=MagicMock(),
            memory_manager=MagicMock(),
            org_id="aiorg_pm_bot",
        )
        assert relay._is_pm_org is False
        assert relay._is_dept_org is False


# ── PMOrchestrator 인스턴스 생성 ──────────────────────────────────────────

class TestPMOrchestratorWiring:
    """TelegramRelay에 context_db 전달 시 PMOrchestrator 생성 테스트."""

    @patch("core.telegram_relay.ENABLE_PM_ORCHESTRATOR", True)
    @patch("core.telegram_relay.KNOWN_DEPTS", {
        "aiorg_engineering_bot": "개발실",
    })
    def test_pm_orchestrator_created_with_context_db(self):
        """context_db 제공 + PM org → PMOrchestrator 생성."""
        from core.telegram_relay import TelegramRelay
        mock_db = MagicMock()
        relay = TelegramRelay(
            token="fake",
            allowed_chat_id=123,
            session_manager=MagicMock(),
            memory_manager=MagicMock(),
            org_id="aiorg_pm_bot",
            context_db=mock_db,
        )
        assert relay._pm_orchestrator is not None

    @patch("core.telegram_relay.ENABLE_PM_ORCHESTRATOR", True)
    @patch("core.telegram_relay.KNOWN_DEPTS", {
        "aiorg_engineering_bot": "개발실",
    })
    def test_pm_orchestrator_none_without_context_db(self):
        """context_db 없음 → PMOrchestrator None."""
        from core.telegram_relay import TelegramRelay
        relay = TelegramRelay(
            token="fake",
            allowed_chat_id=123,
            session_manager=MagicMock(),
            memory_manager=MagicMock(),
            org_id="aiorg_pm_bot",
        )
        assert relay._pm_orchestrator is None

    @patch("core.telegram_relay.ENABLE_PM_ORCHESTRATOR", True)
    @patch("core.telegram_relay.KNOWN_DEPTS", {
        "aiorg_engineering_bot": "개발실",
    })
    def test_dept_bot_no_orchestrator(self):
        """Dept org → PMOrchestrator 생성 안함."""
        from core.telegram_relay import TelegramRelay
        mock_db = MagicMock()
        relay = TelegramRelay(
            token="fake",
            allowed_chat_id=123,
            session_manager=MagicMock(),
            memory_manager=MagicMock(),
            org_id="aiorg_engineering_bot",
            context_db=mock_db,
        )
        assert relay._pm_orchestrator is None
        assert relay._is_dept_org is True


# ── _handle_pm_task 단위 테스트 ───────────────────────────────────────────

class TestHandlePMTask:
    """Dept 봇의 _handle_pm_task 메서드 테스트."""

    @pytest.mark.asyncio
    @patch("core.telegram_relay.ENABLE_PM_ORCHESTRATOR", True)
    @patch("core.telegram_relay.KNOWN_DEPTS", {
        "aiorg_engineering_bot": "개발실",
    })
    async def test_handle_pm_task_wrong_dept_ignored(self):
        """다른 부서에 배정된 태스크는 무시."""
        from core.telegram_relay import TelegramRelay
        mock_db = MagicMock()
        relay = TelegramRelay(
            token="fake",
            allowed_chat_id=123,
            session_manager=MagicMock(),
            memory_manager=MagicMock(),
            org_id="aiorg_engineering_bot",
            context_db=mock_db,
        )
        # dept:aiorg_design_bot → engineering 봇은 무시해야 함
        text = "[PM_TASK:T-pm-001|dept:aiorg_design_bot] 디자인 작업"
        await relay._handle_pm_task(text, MagicMock(), MagicMock())
        mock_db.get_pm_task.assert_not_called()

    @pytest.mark.asyncio
    @patch("core.telegram_relay.ENABLE_PM_ORCHESTRATOR", True)
    @patch("core.telegram_relay.KNOWN_DEPTS", {
        "aiorg_engineering_bot": "개발실",
    })
    async def test_handle_pm_task_no_context_db(self):
        """context_db 없으면 처리 불가."""
        from core.telegram_relay import TelegramRelay
        relay = TelegramRelay(
            token="fake",
            allowed_chat_id=123,
            session_manager=MagicMock(),
            memory_manager=MagicMock(),
            org_id="aiorg_engineering_bot",
            context_db=None,
        )
        text = "[PM_TASK:T-pm-001|dept:aiorg_engineering_bot] 개발 작업"
        # 에러 없이 무시되어야 함
        await relay._handle_pm_task(text, MagicMock(), MagicMock())
