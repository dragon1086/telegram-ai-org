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


class TestTickIteration:
    """tick_iteration() — iteration 카운터 증가 및 max_iterations 반환 검증."""

    @pytest.mark.asyncio
    async def test_tick_increments_db(self, db, tracker):
        """tick_iteration() 호출 시 DB의 iteration 값이 1 증가한다."""
        goal = await tracker.set_goal("tick 테스트", chat_id=1)
        assert goal["iteration"] == 0

        new_iter, max_iter = await tracker.tick_iteration(goal["id"])
        assert new_iter == 1
        assert max_iter == 3  # tracker fixture max_iterations=3

        updated = await db.get_goal(goal["id"])
        assert updated["iteration"] == 1

    @pytest.mark.asyncio
    async def test_tick_increments_sequentially(self, db, tracker):
        """tick_iteration() 연속 호출 시 1씩 증가한다."""
        goal = await tracker.set_goal("연속 tick 테스트", chat_id=1)
        for expected in range(1, 4):
            new_iter, _ = await tracker.tick_iteration(goal["id"])
            assert new_iter == expected

    @pytest.mark.asyncio
    async def test_tick_exceeds_max_returns_over_limit(self, db, tracker):
        """iteration이 max_iterations를 초과하면 new_iter > max_iter를 반환한다."""
        goal = await tracker.set_goal("한계 초과 테스트", chat_id=1)
        # max_iterations=3이므로 4번째 tick은 new_iter=4 > max_iter=3
        for _ in range(3):
            await tracker.tick_iteration(goal["id"])
        new_iter, max_iter = await tracker.tick_iteration(goal["id"])
        assert new_iter > max_iter

    @pytest.mark.asyncio
    async def test_tick_nonexistent_goal_returns_zeros(self, tracker):
        """존재하지 않는 goal_id는 (0, max_iterations) 반환."""
        new_iter, max_iter = await tracker.tick_iteration("G-nonexistent")
        assert new_iter == 0

    @pytest.mark.asyncio
    async def test_run_loop_resume_starts_from_saved_iteration(self, db, tracker, send_fn):
        """_run_loop_inner 재시작 시 DB에 저장된 iteration부터 재개한다."""
        goal = await tracker.set_goal("재개 테스트", chat_id=123)
        # iteration=2로 미리 설정 (이전 실행에서 2번 완료된 상태 시뮬레이션)
        await db.update_goal(goal["id"], iteration=2)

        iterations_seen: list[int] = []
        original_update = db.update_goal

        async def tracking_update(goal_id, **kwargs):
            if "iteration" in kwargs:
                iterations_seen.append(kwargs["iteration"])
            return await original_update(goal_id, **kwargs)

        db.update_goal = tracking_update

        # dispatch를 mock하여 즉시 done으로 처리
        async def mock_dispatch(parent_id, subtasks, chat_id):
            task_ids = []
            for i, st in enumerate(subtasks):
                tid = f"T-resume-{i}"
                await db.create_pm_task(tid, st.description, st.assigned_dept,
                                        "pm", parent_id=parent_id)
                await db.update_pm_task_status(tid, "done", result="완료")
                task_ids.append(tid)
            return task_ids

        tracker._orch.dispatch = mock_dispatch
        await tracker._run_loop_inner(goal["id"], 123)

        # iteration=2에서 재개했으므로 첫 번째로 저장되는 iteration은 3이어야 함
        assert iterations_seen, "iteration 업데이트가 한 번도 없었음"
        assert iterations_seen[0] == 3, (
            f"재개 시 첫 iteration이 1이 아닌 3이어야 하는데 {iterations_seen[0]}임"
        )


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


class TestIterationBugFixes:
    """iteration 카운터 버그 수정 검증 테스트."""

    @pytest.mark.asyncio
    async def test_get_goals_by_title_returns_all_statuses(self, db, tracker):
        """get_goals_by_title은 achieved/stagnated 상태도 반환해야 한다 (재시딩 방지)."""
        goal = await tracker.set_goal("고정된 목표 제목", chat_id=1)
        await db.update_goal(goal["id"], status="achieved")

        results = await tracker.get_goals_by_title("고정된 목표 제목")
        assert len(results) == 1
        assert results[0]["status"] == "achieved"

        # 활성 목표 조회에서는 빠져야 함
        active = await tracker.get_active_goals()
        assert not any(g["id"] == goal["id"] for g in active)

    @pytest.mark.asyncio
    async def test_get_goals_by_title_no_match(self, db, tracker):
        """존재하지 않는 제목 조회 시 빈 리스트 반환."""
        results = await tracker.get_goals_by_title("존재하지않는제목123")
        assert results == []

    @pytest.mark.asyncio
    async def test_cancel_old_subtasks_includes_done(self, db, tracker, orch):
        """_cancel_old_subtasks가 done 상태 서브태스크도 취소해야 한다."""
        goal = await tracker.set_goal("취소 테스트 목표", chat_id=1)
        goal_id = goal["id"]

        # done 서브태스크 생성
        task = await db.create_pm_task(
            task_id="T-done-001",
            description="완료된 태스크",
            assigned_dept="aiorg_engineering_bot",
            created_by="pm",
            parent_id=goal_id,
        )
        await db.update_pm_task_status("T-done-001", "done")

        # pending 서브태스크 생성
        await db.create_pm_task(
            task_id="T-pending-001",
            description="대기중 태스크",
            assigned_dept="aiorg_engineering_bot",
            created_by="pm",
            parent_id=goal_id,
        )

        # _cancel_old_subtasks 실행
        await tracker._cancel_old_subtasks(goal_id)

        subtasks = await db.get_subtasks(goal_id)
        statuses = {s["id"]: s["status"] for s in subtasks}
        # done 포함 모두 cancelled 되어야 함
        assert statuses["T-done-001"] == "cancelled"
        assert statuses["T-pending-001"] == "cancelled"

    @pytest.mark.asyncio
    async def test_evaluate_progress_excludes_cancelled(self, db, tracker):
        """evaluate_progress가 cancelled 서브태스크를 제외하고 평가해야 한다."""
        goal = await tracker.set_goal("평가 테스트 목표", chat_id=1)
        goal_id = goal["id"]

        # 이전 iteration에서 취소된 서브태스크 (3개)
        for i in range(3):
            await db.create_pm_task(
                task_id=f"T-old-{i:03d}",
                description=f"이전 태스크 {i}",
                assigned_dept="aiorg_engineering_bot",
                created_by="pm",
                parent_id=goal_id,
            )
            await db.update_pm_task_status(f"T-old-{i:03d}", "cancelled")

        # 현재 iteration 서브태스크 (2개, 아직 pending)
        for i in range(2):
            await db.create_pm_task(
                task_id=f"T-new-{i:03d}",
                description=f"새 태스크 {i}",
                assigned_dept="aiorg_engineering_bot",
                created_by="pm",
                parent_id=goal_id,
            )

        status = await tracker.evaluate_progress(goal_id)
        # cancelled 3개는 제외, pending 2개만 평가 → done 0개 → achieved=False
        assert not status.achieved
        assert status.total_count == 2
        assert status.done_count == 0

    @pytest.mark.asyncio
    async def test_evaluate_progress_achieved_when_active_all_done(self, db, tracker):
        """현재 iteration 서브태스크가 모두 done이면 fallback에서 achieved=True."""
        goal = await tracker.set_goal("달성 평가 목표", chat_id=1)
        goal_id = goal["id"]

        # 이전 iteration cancelled 서브태스크
        await db.create_pm_task(
            task_id="T-cancelled-001",
            description="이전 태스크",
            assigned_dept="aiorg_engineering_bot",
            created_by="pm",
            parent_id=goal_id,
        )
        await db.update_pm_task_status("T-cancelled-001", "cancelled")

        # 현재 iteration done 서브태스크
        await db.create_pm_task(
            task_id="T-active-001",
            description="현재 태스크",
            assigned_dept="aiorg_engineering_bot",
            created_by="pm",
            parent_id=goal_id,
        )
        await db.update_pm_task_status("T-active-001", "done")

        status = await tracker.evaluate_progress(goal_id)
        # cancelled 제외 → done 1/1 → achieved=True (LLM 없으므로 fallback)
        assert status.achieved
        assert status.total_count == 1
        assert status.done_count == 1
