"""회의/회고 전 조직 참여 구조 통합 테스트.

테스트 대상:
- GroupChatHub.start_meeting() — 전 조직 참여
- OrgScheduler.broadcast_meeting_start() — 브로드캐스트 + 조치사항 등록
- broadcast_meeting_start() → GoalTracker.start_goal() 연동
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.group_chat_hub import GroupChatHub, GroupMessage
from core.context_db import ContextDB
from core.task_graph import TaskGraph
from core.claim_manager import ClaimManager
from core.memory_manager import MemoryManager
from core.pm_orchestrator import PMOrchestrator
from core.goal_tracker import GoalTracker
from core.scheduler import OrgScheduler


# ── 픽스처 ─────────────────────────────────────────────────────────────────────

@pytest.fixture
async def db():
    with tempfile.TemporaryDirectory() as tmp:
        cdb = ContextDB(Path(tmp) / "meeting_test.db")
        await cdb.initialize()
        yield cdb


@pytest.fixture
def send_fn():
    return AsyncMock()


@pytest.fixture
async def orch(db, send_fn):
    return PMOrchestrator(
        context_db=db, task_graph=TaskGraph(db),
        claim_manager=ClaimManager(), memory=MemoryManager("pm"),
        org_id="pm", telegram_send_func=send_fn,
    )


@pytest.fixture
async def tracker(db, orch, send_fn):
    return GoalTracker(
        context_db=db, orchestrator=orch,
        telegram_send_func=send_fn, org_id="pm",
        max_iterations=2, max_stagnation=2, poll_interval_sec=0.01,
    )


@pytest.fixture
def group_hub():
    sent_messages: list[str] = []

    async def _send(text: str) -> None:
        sent_messages.append(text)

    hub = GroupChatHub(send_to_group=_send)
    hub._sent = sent_messages  # 검증용
    return hub


@pytest.fixture
def scheduler(send_fn, db):
    msgs: list[str] = []

    async def _sched_send(text: str) -> None:
        msgs.append(text)

    sched = OrgScheduler(send_text=_sched_send, context_db=db)
    sched._sent = msgs
    return sched


# ── GroupChatHub 참가자 등록 & 회의 테스트 ───────────────────────────────────────

class TestGroupChatHubMeeting:

    @pytest.mark.asyncio
    async def test_register_participant(self, group_hub):
        """register_participant()가 참가자를 등록한다."""
        async def speak(topic, ctx):
            return "안녕하세요!"

        group_hub.register_participant("engineering", speak, domain_keywords=["코드"])
        assert "engineering" in group_hub.participant_ids

    @pytest.mark.asyncio
    async def test_start_meeting_all_participants_speak(self, group_hub):
        """start_meeting()이 등록된 모든 참가자를 순서대로 호출한다."""
        spoke_orgs: list[str] = []

        async def make_speak(org_id: str):
            async def speak(topic, ctx):
                spoke_orgs.append(org_id)
                return f"[{org_id}] 보고합니다."
            return speak

        for org in ["engineering", "product", "design"]:
            group_hub.register_participant(org, await make_speak(org))

        await group_hub.start_meeting(topic="일일 회고")

        assert spoke_orgs == ["engineering", "product", "design"]

    @pytest.mark.asyncio
    async def test_start_meeting_messages_sent_to_group(self, group_hub):
        """start_meeting()이 각 봇 발언을 그룹에 전송한다."""
        async def speak(topic, ctx):
            return "오늘 작업 보고: 완료 3건"

        group_hub.register_participant("pm", speak)
        await group_hub.start_meeting(topic="일일 회고")

        assert any("오늘 작업 보고" in m for m in group_hub._sent)

    @pytest.mark.asyncio
    async def test_start_meeting_participant_timeout_skipped(self, group_hub):
        """타임아웃 발생한 봇은 건너뛰고 회의는 계속 진행된다."""
        async def slow_speak(topic, ctx):
            await asyncio.sleep(100)  # 타임아웃 유발
            return "절대 도달 안 함"

        async def fast_speak(topic, ctx):
            return "빠른 보고"

        group_hub.register_participant("slow_bot", slow_speak)
        group_hub.register_participant("fast_bot", fast_speak)

        # 타임아웃을 짧게 설정
        from core import group_chat_hub as ghm
        original = ghm.TURN_TIMEOUT_SEC
        ghm.TURN_TIMEOUT_SEC = 0.05
        try:
            await group_hub.start_meeting(topic="테스트 회의")
        finally:
            ghm.TURN_TIMEOUT_SEC = original

        # fast_bot은 발언했어야 함
        assert any("빠른 보고" in m for m in group_hub._sent)

    @pytest.mark.asyncio
    async def test_meeting_context_shared_between_participants(self, group_hub):
        """앞 봇 발언이 뒷 봇의 컨텍스트에 포함된다."""
        contexts_received: list[int] = []

        async def first_speak(topic, ctx):
            return "첫 번째 발언"

        async def second_speak(topic, ctx):
            # 첫 번째 봇 발언이 ctx에 있어야 함
            contexts_received.append(len(ctx))
            return "두 번째 발언"

        group_hub.register_participant("first", first_speak)
        group_hub.register_participant("second", second_speak)

        await group_hub.start_meeting(topic="컨텍스트 테스트")
        # second_speak 호출 시 컨텍스트에 첫 번째 발언이 있어야 함
        assert contexts_received and contexts_received[0] >= 1


# ── broadcast_meeting_start + GoalTracker 연동 ──────────────────────────────────

class TestMeetingActionItems:

    @pytest.mark.asyncio
    async def test_broadcast_meeting_start_without_participants(self, scheduler):
        """참가자 없는 GroupChatHub에서도 오류 없이 실행된다."""
        hub = GroupChatHub(send_to_group=AsyncMock())
        scheduler._group_chat_hub = hub
        # 예외 없이 실행되어야 함
        await scheduler.broadcast_meeting_start("daily_retro")

    @pytest.mark.asyncio
    async def test_register_retro_action_items_no_tracker(self, scheduler):
        """GoalTracker 없이 _register_retro_action_items() 호출 — 조용히 종료."""
        # goal_tracker가 None이면 아무것도 안 해야 함
        await scheduler._register_retro_action_items("daily_retro")
        # 예외가 없으면 성공

    @pytest.mark.asyncio
    async def test_register_action_items_with_failed_tasks(self, db, scheduler, tracker):
        """실패 태스크가 있으면 GoalTracker에 목표가 등록된다."""
        # failed 태스크 2건 생성
        await db.create_pm_task("T-fail-1", "실패 태스크1", "aiorg_engineering_bot", "pm")
        await db.create_pm_task("T-fail-2", "실패 태스크2", "aiorg_engineering_bot", "pm")
        await db.update_pm_task_status("T-fail-1", "failed")
        await db.update_pm_task_status("T-fail-2", "failed")

        scheduler.set_goal_tracker(tracker)
        await scheduler._register_retro_action_items("daily_retro")

        # GoalTracker에 목표가 등록됐는지 확인
        active_goals = await tracker.get_active_goals(org_id="pm")
        assert len(active_goals) >= 1
        # 생성된 목표의 메타데이터 확인 (meta_json은 문자열로 저장됨)
        import json as _json
        def _get_meta(g):
            raw = g.get("meta_json", "{}")
            if isinstance(raw, str):
                try:
                    return _json.loads(raw)
                except Exception:
                    return {}
            return raw or {}

        action_goals = [g for g in active_goals if _get_meta(g).get("source") == "daily_retro"]
        assert len(action_goals) >= 1

    @pytest.mark.asyncio
    async def test_register_action_items_no_failed_tasks(self, db, scheduler, tracker):
        """실패 태스크 없으면 아무 목표도 등록되지 않는다."""
        # 완료된 태스크만 존재
        await db.create_pm_task("T-done-1", "완료 태스크", "aiorg_engineering_bot", "pm")
        await db.update_pm_task_status("T-done-1", "done", result="성공")

        scheduler.set_goal_tracker(tracker)
        initial_goals = await tracker.get_active_goals()
        await scheduler._register_retro_action_items("daily_retro")
        final_goals = await tracker.get_active_goals()

        assert len(final_goals) == len(initial_goals)


# ── OrgScheduler.set_goal_tracker() 주입 ──────────────────────────────────────

class TestSchedulerGoalTrackerInjection:

    def test_set_goal_tracker(self, scheduler):
        """set_goal_tracker()가 내부 참조를 업데이트한다."""
        mock_tracker = MagicMock()
        scheduler.set_goal_tracker(mock_tracker)
        assert scheduler._goal_tracker is mock_tracker

    def test_goal_tracker_initially_none(self, scheduler):
        """OrgScheduler 초기화 시 goal_tracker는 None이다."""
        assert scheduler._goal_tracker is None


# ── broadcast_meeting_start + _register_action_items 직접 테스트 ──────────────


class TestBroadcastMeetingStart:
    """OrgScheduler.broadcast_meeting_start() — pm_orchestrator 미연결 시 동작."""

    @pytest.mark.asyncio
    async def test_broadcast_without_orchestrator_sends_message(self, send_fn):
        """pm_orchestrator 없으면 수동 브로드캐스트 안내 메시지 전송."""
        sched = OrgScheduler(send_text=send_fn)
        responses = await sched.broadcast_meeting_start(
            meeting_type="daily_retro",
            topic="오늘 회고",
            collect_timeout_sec=0.5,
        )
        assert isinstance(responses, list)
        send_fn.assert_called()

    @pytest.mark.asyncio
    async def test_register_action_items_with_goal_tracker(self, send_fn):
        """ACTION: 라인이 있으면 GoalTracker.start_goal() 호출된다."""
        mock_tracker = AsyncMock()
        mock_tracker.start_goal = AsyncMock(return_value="G-pm-999")

        sched = OrgScheduler(
            send_text=send_fn,
            goal_tracker=mock_tracker,
            pm_chat_id=0,
        )
        responses = [
            {
                "org_id": "aiorg_engineering_bot",
                "report": "## 완료\n- API 구현\n\nACTION: E2E 테스트 추가\nACTION: 문서 업데이트",
                "status": "done",
            }
        ]
        await sched._register_action_items(responses, "daily_retro")
        assert mock_tracker.start_goal.call_count == 2

    @pytest.mark.asyncio
    async def test_register_action_items_no_actions(self, send_fn):
        """ACTION: 없는 보고에서는 start_goal 미호출."""
        mock_tracker = AsyncMock()
        mock_tracker.start_goal = AsyncMock(return_value="G-pm-001")

        sched = OrgScheduler(
            send_text=send_fn,
            goal_tracker=mock_tracker,
            pm_chat_id=0,
        )
        responses = [
            {
                "org_id": "aiorg_product_bot",
                "report": "## 완료\n- PRD 작성\n## 진행 중\n- 스펙 검토",
                "status": "done",
            }
        ]
        await sched._register_action_items(responses, "weekly_standup")
        mock_tracker.start_goal.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_dept_bot_with_hub(self, send_fn):
        """register_dept_bot_with_hub()가 GroupChatHub에 참가자를 등록한다."""
        from core.group_chat_hub import GroupChatHub

        hub = GroupChatHub(send_to_group=send_fn)
        sched = OrgScheduler(
            send_text=send_fn,
            group_chat_hub=hub,
        )
        callback = AsyncMock(return_value="테스트 응답")
        sched.register_dept_bot_with_hub(
            org_id="aiorg_engineering_bot",
            speak_callback=callback,
            domain_keywords=["코드", "버그"],
        )
        assert "aiorg_engineering_bot" in hub.participant_ids
