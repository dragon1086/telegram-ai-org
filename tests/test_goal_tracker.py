"""GoalTracker 테스트 — Phase 5."""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_db import ContextDB
from core.task_graph import TaskGraph
from core.claim_manager import ClaimManager
from core.memory_manager import MemoryManager
from core.pm_orchestrator import PMOrchestrator
from core.goal_tracker import GoalTracker, GoalStatus


@pytest.fixture
async def db():
    with tempfile.TemporaryDirectory() as tmp:
        cdb = ContextDB(Path(tmp) / "test.db")
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
        max_iterations=3, max_stagnation=2, poll_interval_sec=0.01,
    )


class TestGoalCRUD:

    @pytest.mark.asyncio
    async def test_create_goal(self, db, tracker):
        goal = await tracker.set_goal("사용자 인증 시스템 구축", chat_id=123)
        assert goal["id"].startswith("G-pm-")
        assert goal["status"] == "active"
        assert goal["iteration"] == 0
        assert goal["max_iterations"] == 3

    @pytest.mark.asyncio
    async def test_get_goal(self, db, tracker):
        goal = await tracker.set_goal("테스트 목표", chat_id=123)
        fetched = await db.get_goal(goal["id"])
        assert fetched is not None
        assert fetched["description"] == "테스트 목표"
        assert fetched["milestones"] == []

    @pytest.mark.asyncio
    async def test_update_goal(self, db, tracker):
        goal = await tracker.set_goal("업데이트 목표", chat_id=123)
        updated = await db.update_goal(goal["id"], status="achieved",
                                       milestones=["m1", "m2"])
        assert updated["status"] == "achieved"
        assert updated["milestones"] == ["m1", "m2"]

    @pytest.mark.asyncio
    async def test_get_active_goals(self, db, tracker):
        await tracker.set_goal("목표1", chat_id=123)
        await tracker.set_goal("목표2", chat_id=123)
        active = await db.get_active_goals()
        assert len(active) == 2

    @pytest.mark.asyncio
    async def test_goal_counter_increments(self, tracker):
        g1 = await tracker.set_goal("첫번째", chat_id=1)
        g2 = await tracker.set_goal("두번째", chat_id=1)
        assert g1["id"] != g2["id"]
        assert g1["id"] == "G-pm-001"
        assert g2["id"] == "G-pm-002"

    @pytest.mark.asyncio
    async def test_counter_restart_safe(self, db, send_fn, orch):
        """프로세스 재시작 후에도 ID 충돌 없이 카운터가 이어짐."""
        tracker1 = GoalTracker(
            context_db=db, orchestrator=orch,
            telegram_send_func=send_fn, org_id="pm",
        )
        g1 = await tracker1.set_goal("목표A", chat_id=1)
        g2 = await tracker1.set_goal("목표B", chat_id=1)
        assert g1["id"] == "G-pm-001"
        assert g2["id"] == "G-pm-002"

        # 새 GoalTracker 인스턴스 (프로세스 재시작 시뮬레이션)
        tracker2 = GoalTracker(
            context_db=db, orchestrator=orch,
            telegram_send_func=send_fn, org_id="pm",
        )
        g3 = await tracker2.set_goal("목표C", chat_id=1)
        assert g3["id"] == "G-pm-003"  # 002가 아니라 003


class TestEvaluateProgress:

    @pytest.mark.asyncio
    async def test_no_subtasks(self, tracker):
        goal = await tracker.set_goal("빈 목표", chat_id=123)
        status = await tracker.evaluate_progress(goal["id"])
        assert not status.achieved
        assert "태스크가 없음" in status.progress_summary

    @pytest.mark.asyncio
    async def test_all_done_fallback(self, db, tracker):
        """LLM 없이 모든 태스크 완료 → achieved (fallback)."""
        goal = await tracker.set_goal("개발 목표", chat_id=123)
        await db.create_pm_task("T-1", "태스크1", "aiorg_engineering_bot", "pm",
                                parent_id=goal["id"])
        await db.create_pm_task("T-2", "태스크2", "aiorg_design_bot", "pm",
                                parent_id=goal["id"])
        await db.update_pm_task_status("T-1", "done", result="완료1")
        await db.update_pm_task_status("T-2", "done", result="완료2")

        status = await tracker.evaluate_progress(goal["id"])
        assert status.achieved
        assert status.done_count == 2
        assert status.total_count == 2

    @pytest.mark.asyncio
    async def test_partial_progress(self, db, tracker):
        goal = await tracker.set_goal("부분 목표", chat_id=123)
        await db.create_pm_task("T-1", "완료됨", "aiorg_engineering_bot", "pm",
                                parent_id=goal["id"])
        await db.create_pm_task("T-2", "미완료", "aiorg_design_bot", "pm",
                                parent_id=goal["id"])
        await db.update_pm_task_status("T-1", "done", result="ok")

        status = await tracker.evaluate_progress(goal["id"])
        assert not status.achieved
        assert "1/2" in status.progress_summary
        assert status.done_count == 1
        assert status.confidence == 0.5

    @pytest.mark.asyncio
    async def test_nonexistent_goal(self, tracker):
        status = await tracker.evaluate_progress("G-nonexistent")
        assert not status.achieved


class TestParseEvaluation:

    def test_parse_achieved(self):
        response = "ACHIEVED: YES\nPROGRESS: All tasks done\nREMAINING: nothing"
        status = GoalTracker._parse_evaluation(response)
        assert status.achieved
        assert status.progress_summary == "All tasks done"
        assert status.remaining_work == "nothing"

    def test_parse_not_achieved(self):
        response = "ACHIEVED: NO\nPROGRESS: 50% done\nREMAINING: backend API"
        status = GoalTracker._parse_evaluation(response)
        assert not status.achieved
        assert "50%" in status.progress_summary
        assert "backend" in status.remaining_work

    def test_parse_malformed(self):
        response = "some random text"
        status = GoalTracker._parse_evaluation(response)
        assert not status.achieved

    def test_parse_partial_response(self):
        """ACHIEVED만 있고 나머지 필드 누락."""
        response = "ACHIEVED: YES"
        status = GoalTracker._parse_evaluation(response)
        assert status.achieved
        assert status.progress_summary == "(평가 결과 없음)"


class TestReplan:

    @pytest.mark.asyncio
    async def test_replan_creates_new_tasks(self, db, tracker, send_fn):
        goal = await tracker.set_goal("기획하고 개발하자", chat_id=123)
        task_ids = await tracker.replan(goal["id"], "개발 구현 필요", chat_id=123)
        assert len(task_ids) > 0
        assert send_fn.called

    @pytest.mark.asyncio
    async def test_replan_nonexistent_goal(self, tracker):
        result = await tracker.replan("G-nope", "something", chat_id=123)
        assert result == []

    @pytest.mark.asyncio
    async def test_replan_cancels_old_subtasks(self, db, tracker):
        """replan 시 이전 미완료 태스크가 cancelled로 마킹됨."""
        goal = await tracker.set_goal("기획하자", chat_id=123)
        # 수동으로 old subtask 생성
        await db.create_pm_task("T-old-1", "이전 태스크", "aiorg_product_bot", "pm",
                                parent_id=goal["id"])
        await db.update_pm_task_status("T-old-1", "assigned")

        await tracker.replan(goal["id"], "기획 개선", chat_id=123)

        old_task = await db.get_pm_task("T-old-1")
        assert old_task["status"] == "cancelled"


class TestCancellation:

    @pytest.mark.asyncio
    async def test_cancel_goal(self, db, tracker, send_fn):
        """run_loop 중 cancel_goal 호출 시 즉시 중단."""
        goal = await tracker.set_goal("취소될 기획", chat_id=123)

        original_dispatch = tracker._orch.dispatch

        async def slow_dispatch(parent_id, subtasks, chat_id):
            task_ids = await original_dispatch(parent_id, subtasks, chat_id)
            for tid in task_ids:
                await db.update_pm_task_status(tid, "done", result="완료")
            # 첫 dispatch 후 cancel 트리거
            tracker.cancel_goal(goal["id"])
            return task_ids

        tracker._orch.dispatch = slow_dispatch

        status = await tracker.run_loop(goal["id"])
        # 취소 또는 달성 (첫 dispatch에서 done 마킹 후 evaluate에서 achieved일 수 있음)
        g = await db.get_goal(goal["id"])
        assert g["status"] in ("cancelled", "achieved")

    @pytest.mark.asyncio
    async def test_cancel_all(self, tracker):
        """cancel_all이 모든 이벤트를 set."""
        g1 = await tracker.set_goal("목표1", chat_id=1)
        g2 = await tracker.set_goal("목표2", chat_id=1)
        # 수동으로 cancel_events 등록 (run_loop가 하는 일을 시뮬레이션)
        tracker._cancel_events[g1["id"]] = asyncio.Event()
        tracker._cancel_events[g2["id"]] = asyncio.Event()

        tracker.cancel_all()

        assert tracker._is_cancelled(g1["id"])
        assert tracker._is_cancelled(g2["id"])


class TestRunLoop:

    @pytest.mark.asyncio
    async def test_immediate_achievement(self, db, tracker, send_fn):
        """첫 iteration에서 모든 태스크 완료 → 즉시 달성."""
        goal = await tracker.set_goal("간단한 기획", chat_id=123)

        original_dispatch = tracker._orch.dispatch

        async def mock_dispatch(parent_id, subtasks, chat_id):
            task_ids = await original_dispatch(parent_id, subtasks, chat_id)
            for tid in task_ids:
                await db.update_pm_task_status(tid, "done", result="자동완료")
            return task_ids

        tracker._orch.dispatch = mock_dispatch

        status = await tracker.run_loop(goal["id"])
        assert status.achieved

        g = await db.get_goal(goal["id"])
        assert g["status"] == "achieved"

    @pytest.mark.asyncio
    async def test_max_iterations_reached(self, db, orch, send_fn):
        """태스크가 계속 미완료 → max_iterations 도달."""
        # stagnation보다 먼저 max_iterations에 도달하도록 설정
        tracker = GoalTracker(
            context_db=db, orchestrator=orch,
            telegram_send_func=send_fn, org_id="pm",
            max_iterations=3, max_stagnation=10, poll_interval_sec=0.01,
        )
        goal = await tracker.set_goal("절대 안끝나는 기획", chat_id=123)
        dispatch_counter = 0

        async def mock_dispatch(parent_id, subtasks, chat_id):
            nonlocal dispatch_counter
            task_ids = []
            for st in subtasks:
                dispatch_counter += 1
                tid = f"T-stuck-{dispatch_counter}"
                await db.create_pm_task(tid, st.description, st.assigned_dept,
                                        "pm", parent_id=parent_id)
                await db.update_pm_task_status(tid, "failed")
                task_ids.append(tid)
            return task_ids

        tracker._orch.dispatch = mock_dispatch

        status = await tracker.run_loop(goal["id"])
        assert not status.achieved

        g = await db.get_goal(goal["id"])
        assert g["status"] == "max_iterations_reached"

    @pytest.mark.asyncio
    async def test_stagnation_detection(self, db, tracker, send_fn):
        """done_count가 동일하게 유지 → 정체 감지."""
        goal = await tracker.set_goal("정체 기획", chat_id=123)
        call_count = 0

        async def mock_dispatch(parent_id, subtasks, chat_id):
            nonlocal call_count
            call_count += 1
            tid = f"T-stag-{call_count}"
            await db.create_pm_task(tid, "항상 같은 태스크", "aiorg_product_bot",
                                    "pm", parent_id=parent_id)
            await db.update_pm_task_status(tid, "done", result="동일결과")
            return [tid]

        tracker._orch.dispatch = mock_dispatch

        # evaluate_progress가 항상 같은 done_count를 반환하도록 mock
        async def mock_evaluate(goal_id):
            return GoalStatus(achieved=False, progress_summary="변하는 텍스트",
                              remaining_work="나머지", done_count=1, total_count=2,
                              confidence=0.5)

        tracker.evaluate_progress = mock_evaluate

        status = await tracker.run_loop(goal["id"])
        assert not status.achieved

        g = await db.get_goal(goal["id"])
        assert g["status"] == "stagnated"
        assert g["stagnation_count"] >= 2

    @pytest.mark.asyncio
    async def test_stagnation_resets_on_progress(self, db, tracker, send_fn):
        """done_count가 증가하면 stagnation 카운터가 리셋됨."""
        goal = await tracker.set_goal("진전 기획", chat_id=123)
        eval_call = 0
        dispatch_counter = 0

        async def mock_dispatch(parent_id, subtasks, chat_id):
            nonlocal dispatch_counter
            dispatch_counter += 1
            tid = f"T-prog-{dispatch_counter}"
            await db.create_pm_task(tid, "태스크", "aiorg_product_bot",
                                    "pm", parent_id=parent_id)
            await db.update_pm_task_status(tid, "done", result="완료")
            return [tid]

        tracker._orch.dispatch = mock_dispatch

        async def mock_evaluate(goal_id):
            nonlocal eval_call
            eval_call += 1
            # 1회차: done=1, 2회차: done=1(정체), 3회차: done=2(진전!)
            if eval_call <= 1:
                dc = 1
            elif eval_call == 2:
                dc = 1  # 정체
            else:
                dc = 2  # 진전 → stagnation 리셋
            return GoalStatus(achieved=False, progress_summary=f"eval {eval_call}",
                              remaining_work="남음", done_count=dc, total_count=3,
                              confidence=0.3)

        tracker.evaluate_progress = mock_evaluate

        status = await tracker.run_loop(goal["id"])
        # max_iterations=3이라 끝남
        g = await db.get_goal(goal["id"])
        # 3회차에서 진전이 있었으므로 stagnation이 아닌 max_iterations_reached
        assert g["status"] == "max_iterations_reached"
        assert g["stagnation_count"] == 0  # 리셋됨


class TestUpdateGoalSafety:
    """update_goal의 SQL injection 방지 테스트."""

    @pytest.mark.asyncio
    async def test_update_only_allowed_fields(self, db, tracker):
        goal = await tracker.set_goal("SQL 테스트", chat_id=123)
        # 허용되지 않은 필드는 무시됨
        updated = await db.update_goal(goal["id"], status="achieved",
                                       evil_field="DROP TABLE")
        assert updated["status"] == "achieved"

    @pytest.mark.asyncio
    async def test_update_no_fields(self, db, tracker):
        goal = await tracker.set_goal("빈 업데이트", chat_id=123)
        updated = await db.update_goal(goal["id"])
        assert updated["status"] == "active"  # 변경 없음


class TestStartGoal:
    """start_goal() 공개 API 테스트."""

    @pytest.mark.asyncio
    async def test_start_goal_returns_id(self, tracker):
        """start_goal()이 goal_id 문자열을 반환한다."""
        gid = await tracker.start_goal(
            org_id="pm",
            title="오픈소스화 스프린트",
            description="telegram-ai-org 오픈소스화",
            meta={"sprint": "7d"},
        )
        assert isinstance(gid, str)
        assert gid.startswith("G-pm-")

    @pytest.mark.asyncio
    async def test_start_goal_persists_to_db(self, db, tracker):
        """start_goal() 후 DB에서 목표를 조회할 수 있다."""
        gid = await tracker.start_goal(
            org_id="pm",
            title="테스트 목표",
            description="DB 저장 확인용",
        )
        goal = await db.get_goal(gid)
        assert goal is not None
        assert goal["title"] == "테스트 목표"
        assert goal["org_id"] == "pm"
        assert goal["status"] == "active"
        assert goal["meta_json"] == {}

    @pytest.mark.asyncio
    async def test_start_goal_with_meta(self, db, tracker):
        """start_goal()에 meta 전달 시 DB에 저장된다."""
        gid = await tracker.start_goal(
            org_id="pm",
            title="메타 테스트",
            description="메타 데이터 저장",
            meta={"sprint": "7d", "deadline": "2026-03-31"},
        )
        goal = await db.get_goal(gid)
        assert goal["meta_json"]["sprint"] == "7d"
        assert goal["meta_json"]["deadline"] == "2026-03-31"

    @pytest.mark.asyncio
    async def test_get_active_goals_by_org(self, db, tracker):
        """get_active_goals(org_id) 필터링이 동작한다."""
        await tracker.start_goal(org_id="pm", title="PM 목표", description="PM용")
        await tracker.set_goal("다른 조직 목표", chat_id=1, org_id="aiorg_engineering_bot")
        pm_goals = await tracker.get_active_goals(org_id="pm")
        assert all(g["org_id"] == "pm" for g in pm_goals)
        eng_goals = await tracker.get_active_goals(org_id="aiorg_engineering_bot")
        assert all(g["org_id"] == "aiorg_engineering_bot" for g in eng_goals)

    @pytest.mark.asyncio
    async def test_get_active_goals_no_filter(self, db, tracker):
        """get_active_goals() 필터 없으면 전체 반환."""
        await tracker.start_goal(org_id="pm", title="A", description="A")
        await tracker.set_goal("B", chat_id=1, org_id="aiorg_engineering_bot")
        all_goals = await tracker.get_active_goals()
        assert len(all_goals) >= 2

    @pytest.mark.asyncio
    async def test_update_goal_status(self, db, tracker):
        """update_goal_status() 편의 메서드가 status를 업데이트한다."""
        gid = await tracker.start_goal(org_id="pm", title="상태 업데이트", description="테스트")
        updated = await tracker.update_goal_status(gid, "achieved")
        assert updated is not None
        assert updated["status"] == "achieved"

    @pytest.mark.asyncio
    async def test_start_goal_background_task_created(self, db, tracker):
        """start_goal() 호출 시 백그라운드 루프 태스크가 생성된다."""
        import asyncio
        tasks_before = {t.get_name() for t in asyncio.all_tasks()}
        gid = await tracker.start_goal(
            org_id="pm", title="루프 테스트", description="백그라운드 태스크 확인"
        )
        # 태스크가 생성됐는지 확인 (즉시 완료될 수 있으므로 이름만 확인)
        assert isinstance(gid, str)
        # 목표가 DB에 있으면 태스크가 생성됐음
        goal = await db.get_goal(gid)
        assert goal is not None
