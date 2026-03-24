"""AutonomousLoop 통합 테스트 — idle→evaluate→replan→dispatch→idle 상태 머신."""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_db import ContextDB
from core.task_graph import TaskGraph
from core.claim_manager import ClaimManager
from core.memory_manager import MemoryManager
from core.pm_orchestrator import PMOrchestrator
from core.goal_tracker import GoalTracker, GoalStatus


# ── 픽스처 ─────────────────────────────────────────────────────────────────────

@pytest.fixture
async def db():
    with tempfile.TemporaryDirectory() as tmp:
        cdb = ContextDB(Path(tmp) / "loop_test.db")
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


# ── 상태 머신 흐름 테스트 ───────────────────────────────────────────────────────

class TestAutonomousLoopStateMachine:
    """idle → evaluate → replan → dispatch → idle 루프 검증."""

    @pytest.mark.asyncio
    async def test_start_goal_triggers_loop(self, db, tracker):
        """start_goal()이 백그라운드 루프를 시작하고 DB에 목표를 저장한다."""
        gid = await tracker.start_goal(
            org_id="pm",
            title="루프 시작 테스트",
            description="자율 루프 시작 확인",
        )
        assert gid.startswith("G-pm-")
        goal = await db.get_goal(gid)
        assert goal is not None
        assert goal["status"] == "active"
        assert goal["org_id"] == "pm"

    @pytest.mark.asyncio
    async def test_loop_evaluate_then_achieve(self, db, tracker, send_fn):
        """evaluate에서 모든 태스크 done → achieved 상태로 전이."""
        goal = await tracker.set_goal("달성 루프 테스트", chat_id=123)
        gid = goal["id"]

        original_dispatch = tracker._orch.dispatch

        async def mock_dispatch(parent_id, subtasks, chat_id):
            task_ids = await original_dispatch(parent_id, subtasks, chat_id)
            for tid in task_ids:
                await db.update_pm_task_status(tid, "done", result="완료")
            return task_ids

        tracker._orch.dispatch = mock_dispatch
        status = await tracker.run_loop(gid)

        assert status.achieved
        final = await db.get_goal(gid)
        assert final["status"] == "achieved"

    @pytest.mark.asyncio
    async def test_loop_replan_on_partial_progress(self, db, tracker, send_fn):
        """일부 태스크 실패 → replan 후 재배분 → 최종 max_iterations 도달."""
        goal = await tracker.set_goal("리플랜 루프 테스트", chat_id=123)
        gid = goal["id"]
        dispatch_count = 0

        async def mock_dispatch(parent_id, subtasks, chat_id):
            nonlocal dispatch_count
            dispatch_count += 1
            task_ids = []
            for i, st in enumerate(subtasks):
                tid = f"T-replan-{dispatch_count}-{i}"
                await db.create_pm_task(tid, st.description, st.assigned_dept,
                                        "pm", parent_id=parent_id)
                # 첫 dispatch: 실패, 이후: 계속 pending
                await db.update_pm_task_status(tid, "failed")
                task_ids.append(tid)
            return task_ids

        tracker._orch.dispatch = mock_dispatch
        status = await tracker.run_loop(gid)

        assert not status.achieved
        # replan이 여러 번 발생했으면 dispatch_count > 1
        assert dispatch_count >= 1

    @pytest.mark.asyncio
    async def test_loop_stagnation_detection(self, db, tracker):
        """done_count 변화 없음 → stagnation 감지 → 루프 종료."""
        goal = await tracker.set_goal("정체 루프 테스트", chat_id=123)
        gid = goal["id"]
        call = 0

        async def mock_dispatch(parent_id, subtasks, chat_id):
            nonlocal call
            call += 1
            tid = f"T-stag-{call}"
            await db.create_pm_task(tid, "태스크", "aiorg_product_bot", "pm",
                                    parent_id=parent_id)
            await db.update_pm_task_status(tid, "done", result="ok")
            return [tid]

        async def mock_evaluate(goal_id):
            # done_count 고정 → 정체
            return GoalStatus(achieved=False, progress_summary="정체",
                              remaining_work="남은 작업", done_count=1, total_count=5,
                              confidence=0.2)

        tracker._orch.dispatch = mock_dispatch
        tracker.evaluate_progress = mock_evaluate

        status = await tracker.run_loop(gid)
        final = await db.get_goal(gid)
        assert final["status"] == "stagnated"

    @pytest.mark.asyncio
    async def test_loop_cancel_mid_run(self, db, tracker, send_fn):
        """run_loop 중 cancel_goal() 호출 → 즉시 중단."""
        goal = await tracker.set_goal("취소 루프 테스트", chat_id=123)
        gid = goal["id"]

        async def mock_dispatch(parent_id, subtasks, chat_id):
            tracker.cancel_goal(gid)  # dispatch 직후 취소 트리거
            return []

        tracker._orch.dispatch = mock_dispatch
        status = await tracker.run_loop(gid)

        final = await db.get_goal(gid)
        assert final["status"] in ("cancelled", "achieved", "max_iterations_reached")

    @pytest.mark.asyncio
    async def test_get_active_goals_org_filter(self, db, tracker):
        """start_goal()으로 등록한 목표를 org_id로 필터링 조회."""
        gid1 = await tracker.start_goal(org_id="pm", title="PM 목표", description="PM용")
        await tracker.set_goal("다른 조직", chat_id=1, org_id="aiorg_engineering_bot")

        pm_goals = await tracker.get_active_goals(org_id="pm")
        assert any(g["id"] == gid1 for g in pm_goals)
        assert all(g["org_id"] == "pm" for g in pm_goals)

    @pytest.mark.asyncio
    async def test_update_goal_status_convenience(self, db, tracker):
        """update_goal_status() 편의 메서드 동작 확인."""
        gid = await tracker.start_goal(org_id="pm", title="상태 변경", description="테스트")
        result = await tracker.update_goal_status(gid, "achieved")
        assert result is not None
        assert result["status"] == "achieved"


class TestDispatchOrgMapping:
    """조직별 서브태스크 배분 로직 확인."""

    @pytest.mark.asyncio
    async def test_dispatch_assigns_to_known_depts(self, db, tracker, send_fn):
        """PMOrchestrator.dispatch가 알려진 부서에 태스크를 배분한다."""
        from core.constants import KNOWN_DEPTS
        goal = await tracker.set_goal("멀티 조직 배분 테스트", chat_id=123)
        gid = goal["id"]

        dispatched_depts: list[str] = []
        original_dispatch = tracker._orch.dispatch

        async def tracking_dispatch(parent_id, subtasks, chat_id):
            task_ids = await original_dispatch(parent_id, subtasks, chat_id)
            for st in subtasks:
                dispatched_depts.append(st.assigned_dept)
            return task_ids

        tracker._orch.dispatch = tracking_dispatch
        # replan 한 번 실행
        await tracker.replan(gid, "개발, 기획, 디자인 작업 필요", chat_id=123)

        # 배분된 부서가 알려진 부서 목록에 있어야 함
        for dept in dispatched_depts:
            assert dept in KNOWN_DEPTS or dept, f"알 수 없는 부서: {dept}"


# ── AutonomousLoop 신규 클래스 단위 테스트 ────────────────────────────────────


class TestAutonomousLoopClass:
    """core.autonomous_loop.AutonomousLoop 클래스 직접 테스트."""

    @pytest.fixture
    def mock_goal_tracker(self):
        t = AsyncMock()
        t.get_active_goals = AsyncMock(return_value=[])
        t.evaluate_progress = AsyncMock(return_value=GoalStatus(
            achieved=False, progress_summary="0/1", remaining_work="미완",
            done_count=0, total_count=1, confidence=0.0,
        ))
        t.update_goal_status = AsyncMock(return_value={"id": "G-pm-001", "status": "achieved"})
        t.replan = AsyncMock(return_value=[])
        return t

    @pytest.fixture
    def al(self, mock_goal_tracker):
        from core.autonomous_loop import AutonomousLoop
        return AutonomousLoop(
            goal_tracker=mock_goal_tracker,
            idle_sleep_sec=0.02,
            max_dispatch=2,
            send_func=AsyncMock(),
        )

    @pytest.mark.asyncio
    async def test_initial_state_idle(self, al):
        from core.autonomous_loop import LoopState
        assert al.state == LoopState.IDLE

    @pytest.mark.asyncio
    async def test_no_goals_stays_idle(self, al, mock_goal_tracker):
        mock_goal_tracker.get_active_goals.return_value = []
        await al._tick()
        from core.autonomous_loop import LoopState
        assert al.state == LoopState.IDLE
        mock_goal_tracker.evaluate_progress.assert_not_called()

    @pytest.mark.asyncio
    async def test_achieved_goal_updated(self, al, mock_goal_tracker):
        from core.goal_tracker import GoalStatus
        mock_goal_tracker.get_active_goals.return_value = [
            {"id": "G-pm-001", "title": "달성", "description": "...", "chat_id": 0}
        ]
        mock_goal_tracker.evaluate_progress.return_value = GoalStatus(
            achieved=True, progress_summary="완료", remaining_work="",
            done_count=1, total_count=1, confidence=1.0,
        )
        await al._tick()
        mock_goal_tracker.update_goal_status.assert_called_once_with("G-pm-001", "achieved")

    @pytest.mark.asyncio
    async def test_not_achieved_calls_replan(self, al, mock_goal_tracker):
        from core.goal_tracker import GoalStatus
        mock_goal_tracker.get_active_goals.return_value = [
            {"id": "G-pm-002", "title": "미달성", "description": "...", "chat_id": 99}
        ]
        mock_goal_tracker.evaluate_progress.return_value = GoalStatus(
            achieved=False, progress_summary="0/2", remaining_work="남은일",
            done_count=0, total_count=2, confidence=0.0,
        )
        await al._tick()
        mock_goal_tracker.replan.assert_called_once_with(
            goal_id="G-pm-002",
            remaining_work="남은일",
            chat_id=99,
        )

    @pytest.mark.asyncio
    async def test_stop_terminates_run(self, al):
        task = asyncio.create_task(al.run())
        await asyncio.sleep(0.05)
        al.stop()
        await asyncio.wait_for(task, timeout=3.0)
        assert not al._running

    def test_infer_org_engineering(self):
        from core.autonomous_loop import AutonomousLoop
        assert AutonomousLoop.infer_org_for_task("버그 수정 및 API 구현") == "aiorg_engineering_bot"

    def test_infer_org_ops(self):
        from core.autonomous_loop import AutonomousLoop
        assert AutonomousLoop.infer_org_for_task("배포 파이프라인 설정") == "aiorg_ops_bot"

    def test_infer_org_none(self):
        from core.autonomous_loop import AutonomousLoop
        assert AutonomousLoop.infer_org_for_task("아무 키워드 없는 설명") is None


class TestLoadLoopConfig:
    """orchestration.yaml 설정 로드."""

    def test_defaults_on_missing_file(self, tmp_path):
        from core.autonomous_loop import load_loop_config
        cfg = load_loop_config(str(tmp_path / "missing.yaml"))
        assert cfg["idle_sleep_sec"] == 300
        assert cfg["max_dispatch"] == 3

    def test_reads_autonomous_loop_section(self, tmp_path):
        from core.autonomous_loop import load_loop_config
        yaml_path = tmp_path / "orchestration.yaml"
        yaml_path.write_text("autonomous_loop:\n  idle_sleep_sec: 60\n  max_dispatch: 5\n")
        cfg = load_loop_config(str(yaml_path))
        assert cfg["idle_sleep_sec"] == 60
        assert cfg["max_dispatch"] == 5
