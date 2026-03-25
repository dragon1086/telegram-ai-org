"""E2E: GoalTracker 조치사항 자동 등록 및 자율 루프 검증.

멀티봇 채팅 입력 → 조치사항 파싱 → GoalTracker 등록 → 루프 완료까지
엔드투엔드 흐름을 실제 Telegram·DB 없이 로컬 컴포넌트만으로 검증한다.

테스트 구성:
    TestActionParser          — 멀티봇 채팅 텍스트에서 조치사항 파싱
    TestGoalTrackerRegistrar  — MeetingActionRegistrar mock 등록 흐름
    TestAutonomousLoopRunner  — idle→evaluate→replan→dispatch 전이 검증
    TestAutoRegisterPipeline  — auto_register_from_report E2E 파이프라인
    TestEdgeCases             — 조치사항 없음·중복·타임아웃 엣지 케이스
    TestStateTransitionLog    — 각 상태 전이 로그/출력 정상 동작 확인
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

# ── 공통 픽스처 ─────────────────────────────────────────────────────────────────


@pytest.fixture
def daily_retro_text() -> str:
    """일일회고 샘플 텍스트 (액션아이템 포함)."""
    return """\
# 작업 회고 — 2026-03-25

## 오늘 완료된 태스크: 3건

- GoalTracker 상태머신 구현 (개발실) ✅
- E2E 테스트 초안 작성 (개발실) ✅
- API 설계 검토 (기획실) ✅

## 실패 태스크: 1건

- 배포 파이프라인 수정 (운영실) ❌

## 조치사항:

- [ ] 배포 파이프라인 버그 수정 담당: 운영실 긴급
- [ ] GoalTracker E2E 테스트 작성 담당: 개발실
- [ ] API 스펙 최종 확정 담당: 기획실 마감: 2026-03-31

---
*자동 생성: 2026-03-25T14:30:00+00:00*
"""


@pytest.fixture
def weekly_meeting_text() -> str:
    """주간회의 샘플 텍스트 (액션아이템 포함)."""
    return """\
# 주간회의 — 2026 W13 (2026-03-25)

## 참석 부서
- 🔧 개발실
- ⚙️ 운영실
- 🎨 디자인실
- 📋 기획실

## 다음 주 계획

- 개발실: GoalTracker 자율 루프 완성 및 배포
- 운영실: 모니터링 대시보드 설정
- 디자인실: 온보딩 화면 프로토타입 제작
- 기획실: PRD 2.0 초안 완성

## 결정 사항

1. GoalTracker v1.0 다음 주 금요일 배포 확정
2. 테스트 커버리지 90% 이상 유지 합의
3. 주간 코드 리뷰 세션 화요일 오전 10시로 고정

## 액션아이템:

- [ ] GoalTracker 배포 스크립트 작성 담당: 운영실 마감: 2026-03-29
- [ ] E2E 테스트 최종 검증 담당: 개발실
- [ ] 온보딩 PRD 업데이트 담당: 기획실
"""


@pytest.fixture
def no_action_text() -> str:
    """조치사항이 없는 일일회고 텍스트."""
    return """\
# 작업 회고 — 2026-03-25

## 오늘 완료된 태스크: 1건

- 코드 리뷰 완료 (개발실) ✅

내일도 화이팅! 💪
"""


@pytest.fixture
def mock_goal_tracker():
    """GoalTracker 목 인스턴스 (start_goal 반환값 자동 생성)."""
    tracker = AsyncMock()
    _counter = {"n": 0}

    async def _start_goal(title, description, meta=None, chat_id=0, org_id=None):
        _counter["n"] += 1
        return f"G-pm-{_counter['n']:03d}"

    tracker.start_goal.side_effect = _start_goal
    tracker.get_goals_by_title = AsyncMock(return_value=[])
    tracker.get_active_goals = AsyncMock(return_value=[])
    tracker.get_goals_by_status = AsyncMock(return_value=[])
    return tracker


# ── TestActionParser ────────────────────────────────────────────────────────────


class TestActionParser:
    """멀티봇 채팅 텍스트에서 조치사항 파싱 테스트."""

    def test_parse_daily_retro_action_items(self, daily_retro_text: str) -> None:
        """일일회고에서 액션아이템 3개 파싱."""
        from goal_tracker.action_parser import ActionParser

        parser = ActionParser()
        items = parser.parse(daily_retro_text)
        assert len(items) >= 3, f"기대: 3개 이상, 실제: {len(items)}개"

    def test_parse_weekly_meeting_action_items(self, weekly_meeting_text: str) -> None:
        """주간회의에서 액션아이템 3개 파싱."""
        from goal_tracker.action_parser import ActionParser

        parser = ActionParser()
        items = parser.parse(weekly_meeting_text)
        assert len(items) >= 3, f"기대: 3개 이상, 실제: {len(items)}개"

    def test_assigned_dept_extracted(self, daily_retro_text: str) -> None:
        """담당 부서가 올바르게 추출된다."""
        from goal_tracker.action_parser import ActionParser

        parser = ActionParser()
        items = parser.parse(daily_retro_text)
        depts = {item.assigned_dept for item in items if item.assigned_dept}
        assert len(depts) > 0, "담당 부서 추출 실패"

    def test_priority_high_extracted(self, daily_retro_text: str) -> None:
        """'긴급' 키워드가 있는 항목은 priority=high로 파싱된다."""
        from goal_tracker.action_parser import ActionParser

        parser = ActionParser()
        items = parser.parse(daily_retro_text)
        high_priority = [i for i in items if i.priority == "high"]
        assert len(high_priority) >= 1, "priority=high 항목 없음"

    def test_due_date_extracted(self, daily_retro_text: str) -> None:
        """마감일이 있는 항목은 due_date가 파싱된다."""
        from goal_tracker.action_parser import ActionParser

        parser = ActionParser()
        items = parser.parse(daily_retro_text)
        with_due = [i for i in items if i.due_date]
        assert len(with_due) >= 1, "due_date 있는 항목 없음"

    def test_no_action_items_returns_empty(self, no_action_text: str) -> None:
        """조치사항 섹션 없는 텍스트는 빈 리스트 반환."""
        from goal_tracker.action_parser import ActionParser

        parser = ActionParser()
        # 섹션 없는 경우 불릿 라인도 파싱될 수 있으므로 has_action_items로 검사
        has = parser.has_action_items(no_action_text)
        assert not has, "조치사항 헤더가 없어야 함"

    def test_meeting_type_detection_daily(self, daily_retro_text: str) -> None:
        """일일회고 텍스트에서 meeting type이 올바르게 감지된다."""
        from goal_tracker.meeting_handler import MeetingType, detect_meeting_type

        # 일일회고 키워드 포함 텍스트
        retro_trigger = "일일회고 — 2026-03-25\n" + daily_retro_text
        detected = detect_meeting_type(retro_trigger)
        assert detected == MeetingType.DAILY_RETRO

    def test_meeting_type_detection_weekly(self, weekly_meeting_text: str) -> None:
        """주간회의 텍스트에서 meeting type이 올바르게 감지된다."""
        from goal_tracker.meeting_handler import MeetingType, detect_meeting_type

        weekly_trigger = "주간회의 시작 — 2026 W13\n" + weekly_meeting_text
        detected = detect_meeting_type(weekly_trigger)
        assert detected == MeetingType.WEEKLY_MEETING


# ── TestGoalTrackerRegistrar ────────────────────────────────────────────────────


class TestGoalTrackerRegistrar:
    """MeetingActionRegistrar mock 등록 흐름 테스트."""

    @pytest.mark.asyncio
    async def test_register_from_event_returns_ids(
        self,
        daily_retro_text: str,
        mock_goal_tracker,
    ) -> None:
        """MeetingEvent → register_from_event → goal_id 목록 반환."""
        from goal_tracker.action_parser import ActionParser
        from goal_tracker.meeting_handler import MeetingEvent, MeetingType
        from goal_tracker.registrar import MeetingActionRegistrar

        parser = ActionParser()
        action_items = parser.parse(daily_retro_text)
        assert len(action_items) > 0

        event = MeetingEvent(
            meeting_type=MeetingType.DAILY_RETRO,
            chat_id=0,
            message_text=daily_retro_text,
            sender_org="aiorg_pm_bot",
            action_items=action_items,
        )

        registrar = MeetingActionRegistrar(
            goal_tracker=mock_goal_tracker,
            org_id="aiorg_pm_bot",
        )
        ids = await registrar.register_from_event(event)
        assert len(ids) == len(action_items), (
            f"등록된 ID 수({len(ids)}) ≠ 액션아이템 수({len(action_items)})"
        )
        assert all(id_.startswith("G-pm-") for id_ in ids)

    @pytest.mark.asyncio
    async def test_duplicate_items_filtered(
        self,
        daily_retro_text: str,
        mock_goal_tracker,
    ) -> None:
        """동일 텍스트 2회 등록 시 두 번째는 중복으로 필터링된다."""
        from goal_tracker.action_parser import ActionParser
        from goal_tracker.meeting_handler import MeetingEvent, MeetingType
        from goal_tracker.registrar import MeetingActionRegistrar

        parser = ActionParser()
        action_items = parser.parse(daily_retro_text)
        event = MeetingEvent(
            meeting_type=MeetingType.DAILY_RETRO,
            chat_id=0,
            message_text=daily_retro_text,
            sender_org="aiorg_pm_bot",
            action_items=action_items,
        )

        registrar = MeetingActionRegistrar(
            goal_tracker=mock_goal_tracker,
            org_id="aiorg_pm_bot",
            dedup_ttl_sec=3600.0,
        )
        ids_first = await registrar.register_from_event(event)
        ids_second = await registrar.register_from_event(event)

        assert len(ids_first) > 0, "첫 번째 등록 실패"
        assert len(ids_second) == 0, f"중복 등록이 필터링되지 않음: {ids_second}"

    @pytest.mark.asyncio
    async def test_register_single_item(self, mock_goal_tracker) -> None:
        """단일 조치사항 직접 등록."""
        from goal_tracker.registrar import MeetingActionRegistrar

        registrar = MeetingActionRegistrar(
            goal_tracker=mock_goal_tracker,
            org_id="aiorg_pm_bot",
        )
        goal_id = await registrar.register_single(
            description="GoalTracker 배포 스크립트 작성",
            assigned_dept="aiorg_ops_bot",
            priority="high",
        )
        assert goal_id is not None
        assert goal_id.startswith("G-pm-")


# ── TestAutonomousLoopRunner ────────────────────────────────────────────────────


class TestAutonomousLoopRunner:
    """idle→evaluate→replan→dispatch 상태 전이 E2E 검증."""

    @pytest.mark.asyncio
    async def test_full_cycle_with_tasks(self) -> None:
        """task_ids 있을 때 idle→evaluate→replan→dispatch→idle 전 사이클 통과."""
        from goal_tracker.loop_runner import AutonomousLoopRunner

        dispatched_tasks: list[str] = []

        async def capture_dispatch(task_ids: list[str]) -> None:
            dispatched_tasks.extend(task_ids)

        runner = AutonomousLoopRunner(
            goal_id="G-test-001",
            dispatch_func=capture_dispatch,
        )
        result = await runner.run_cycle(
            registered_ids=["G-pm-001", "G-pm-002", "G-pm-003"]
        )

        assert result.success, f"오류 발생: {result.error}"
        assert result.dispatched, "dispatch 미실행"
        assert result.dispatched_count == 3
        assert dispatched_tasks == ["G-pm-001", "G-pm-002", "G-pm-003"]
        assert "evaluate" in result.states_visited
        assert "replan" in result.states_visited
        assert "dispatch" in result.states_visited
        # 마지막 상태는 idle
        assert result.states_visited[-1] == "idle"

    @pytest.mark.asyncio
    async def test_state_machine_transitions_logged(self) -> None:
        """상태 전이가 GoalTrackerStateMachine history에 기록된다."""
        from goal_tracker.loop_runner import AutonomousLoopRunner
        from goal_tracker.state_machine import GoalTrackerStateMachine

        sm = GoalTrackerStateMachine("G-test-002", max_iterations=5)
        runner = AutonomousLoopRunner(goal_id="G-test-002", state_machine=sm)
        await runner.run_cycle(registered_ids=["G-pm-001"])

        assert len(sm.ctx.history) >= 3, (
            f"전이 이력 {len(sm.ctx.history)}개 — 최소 3개 기대"
        )
        transition_pairs = [
            (t.from_state.value, t.to_state.value)
            for t in sm.ctx.history
        ]
        assert ("idle", "evaluate") in transition_pairs
        assert ("evaluate", "replan") in transition_pairs
        assert ("replan", "dispatch") in transition_pairs
        assert ("dispatch", "idle") in transition_pairs

    @pytest.mark.asyncio
    async def test_idle_state_after_completion(self) -> None:
        """사이클 완료 후 상태머신이 IDLE로 복귀한다."""
        from goal_tracker.loop_runner import AutonomousLoopRunner
        from goal_tracker.state_machine import GoalTrackerState, GoalTrackerStateMachine

        sm = GoalTrackerStateMachine("G-test-003")
        runner = AutonomousLoopRunner(goal_id="G-test-003", state_machine=sm)
        await runner.run_cycle(registered_ids=["G-pm-001"])

        assert sm.state == GoalTrackerState.IDLE, (
            f"최종 상태가 IDLE이 아님: {sm.state}"
        )

    @pytest.mark.asyncio
    async def test_iteration_counter_incremented(self) -> None:
        """사이클 실행 후 iteration 카운터가 1 증가한다."""
        from goal_tracker.loop_runner import AutonomousLoopRunner
        from goal_tracker.state_machine import GoalTrackerStateMachine

        sm = GoalTrackerStateMachine("G-test-004", max_iterations=10)
        runner = AutonomousLoopRunner(goal_id="G-test-004", state_machine=sm)
        assert sm.ctx.iteration == 0
        await runner.run_cycle(registered_ids=["G-pm-001"])
        assert sm.ctx.iteration == 1, f"iteration 카운터 오류: {sm.ctx.iteration}"

    @pytest.mark.asyncio
    async def test_dispatch_with_action_items(self) -> None:
        """ActionItem이 있으면 담당 부서 정보가 DispatchRecord에 기록된다."""
        from goal_tracker.action_parser import ActionItem
        from goal_tracker.loop_runner import AutonomousLoopRunner

        action_items = [
            ActionItem(
                description="배포 파이프라인 버그 수정",
                assigned_dept="aiorg_ops_bot",
                priority="high",
            ),
            ActionItem(
                description="GoalTracker E2E 테스트 작성",
                assigned_dept="aiorg_engineering_bot",
            ),
        ]

        runner = AutonomousLoopRunner(goal_id="G-test-005")
        result = await runner.run_cycle(
            registered_ids=["G-pm-001", "G-pm-002"],
            action_items=action_items,
        )

        assert result.dispatched
        assert len(result.dispatch_records) == 2
        depts = {r.assigned_dept for r in result.dispatch_records}
        assert "aiorg_ops_bot" in depts
        assert "aiorg_engineering_bot" in depts


# ── TestAutoRegisterPipeline ────────────────────────────────────────────────────


class TestAutoRegisterPipeline:
    """auto_register_from_report() E2E 파이프라인 전체 흐름 테스트."""

    @pytest.mark.asyncio
    async def test_daily_retro_full_pipeline(
        self,
        daily_retro_text: str,
        mock_goal_tracker,
    ) -> None:
        """일일회고 텍스트 → 파싱 → 등록 → 상태머신 트리거 전체 흐름."""
        from goal_tracker.auto_register import auto_register_from_report
        from goal_tracker.state_machine import GoalTrackerStateMachine

        sm = GoalTrackerStateMachine("G-daily-pipeline-001", max_iterations=5)

        result = await auto_register_from_report(
            report_text=daily_retro_text,
            report_type="daily_retro",
            goal_tracker=mock_goal_tracker,
            state_machine=sm,
            chat_id=0,
            org_id="aiorg_pm_bot",
        )

        assert result.action_items_found >= 3, (
            f"파싱된 조치사항이 3개 미만: {result.action_items_found}"
        )
        assert result.registered_count > 0, "등록된 항목 없음"
        assert result.state_machine_triggered, "상태머신 트리거 안 됨"
        assert result.success

    @pytest.mark.asyncio
    async def test_weekly_meeting_full_pipeline(
        self,
        weekly_meeting_text: str,
        mock_goal_tracker,
    ) -> None:
        """주간회의 텍스트 → 파싱 → 등록 → 상태머신 트리거 전체 흐름."""
        from goal_tracker.auto_register import auto_register_from_report
        from goal_tracker.state_machine import GoalTrackerStateMachine

        sm = GoalTrackerStateMachine("G-weekly-pipeline-001", max_iterations=5)

        result = await auto_register_from_report(
            report_text=weekly_meeting_text,
            report_type="weekly_meeting",
            goal_tracker=mock_goal_tracker,
            state_machine=sm,
            chat_id=0,
            org_id="aiorg_pm_bot",
        )

        assert result.action_items_found >= 3
        assert result.registered_count > 0
        assert result.state_machine_triggered

    @pytest.mark.asyncio
    async def test_run_meeting_cycle_convenience(self) -> None:
        """run_meeting_cycle() 편의 함수 — 전체 사이클 완료."""
        from goal_tracker.loop_runner import run_meeting_cycle

        result = await run_meeting_cycle(
            meeting_type="daily_retro",
            registered_ids=["G-pm-001", "G-pm-002"],
        )

        assert result.success
        assert result.dispatched
        assert result.goal_id.startswith("G-daily_retro-")

    @pytest.mark.asyncio
    async def test_pipeline_with_send_func(
        self,
        daily_retro_text: str,
        mock_goal_tracker,
    ) -> None:
        """send_func 콜백이 등록 완료 시 호출된다."""
        from goal_tracker.auto_register import auto_register_from_report

        sent_messages: list[str] = []

        async def capture_send(chat_id: int, text: str) -> None:
            sent_messages.append(text)

        result = await auto_register_from_report(
            report_text=daily_retro_text,
            report_type="daily_retro",
            goal_tracker=mock_goal_tracker,
            chat_id=12345,
            org_id="aiorg_pm_bot",
            send_func=capture_send,
        )

        assert result.registered_count > 0
        assert len(sent_messages) >= 1, "send_func 미호출"
        assert any("일일회고" in msg or "GoalTracker" in msg for msg in sent_messages)


# ── TestEdgeCases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    """엣지 케이스: 조치사항 없음·중복 등록·타임아웃 처리."""

    @pytest.mark.asyncio
    async def test_empty_text_returns_zero_items(self) -> None:
        """빈 텍스트는 0개 파싱·0개 등록을 반환한다."""
        from goal_tracker.auto_register import auto_register_from_report

        result = await auto_register_from_report(
            report_text="",
            report_type="daily_retro",
        )
        assert result.action_items_found == 0
        assert result.registered_count == 0
        assert result.success

    @pytest.mark.asyncio
    async def test_no_action_section_text(self, no_action_text: str) -> None:
        """조치사항 섹션 없는 텍스트 — 등록 없이 성공 반환."""
        from goal_tracker.auto_register import auto_register_from_report

        result = await auto_register_from_report(
            report_text=no_action_text,
            report_type="daily_retro",
        )
        # has_action_items=False → action_items_found=0
        assert result.success
        assert not result.state_machine_triggered

    @pytest.mark.asyncio
    async def test_no_task_ids_skips_dispatch(self) -> None:
        """등록 task_ids 없을 때 dispatch 생략 후 성공 반환."""
        from goal_tracker.loop_runner import AutonomousLoopRunner
        from goal_tracker.state_machine import GoalTrackerState

        dispatched = []

        async def _dispatch(ids):
            dispatched.extend(ids)

        runner = AutonomousLoopRunner(goal_id="G-edge-001", dispatch_func=_dispatch)
        result = await runner.run_cycle(registered_ids=[])

        assert result.success
        assert not result.dispatched, "빈 task_ids로 dispatch 실행 시도됨"
        assert len(dispatched) == 0
        # 상태머신 최종 상태는 IDLE이어야 함 (빈 목록 → 즉시 달성 처리 → IDLE)
        assert runner.current_state == GoalTrackerState.IDLE

    @pytest.mark.asyncio
    async def test_dispatch_func_error_handled(self) -> None:
        """dispatch_func가 예외를 던지면 LoopRunResult.error에 기록된다."""
        from goal_tracker.loop_runner import AutonomousLoopRunner

        async def _failing_dispatch(ids: list[str]) -> None:
            raise RuntimeError("dispatch 서버 타임아웃")

        runner = AutonomousLoopRunner(
            goal_id="G-edge-002",
            dispatch_func=_failing_dispatch,
        )
        result = await runner.run_cycle(registered_ids=["G-pm-001"])

        assert not result.success, "오류가 발생했어야 함"
        assert result.error is not None
        assert "타임아웃" in result.error or "dispatch" in result.error

    @pytest.mark.asyncio
    async def test_duplicate_registration_same_ttl(
        self, daily_retro_text: str, mock_goal_tracker
    ) -> None:
        """동일 텍스트를 TTL 내 2회 auto_register 시 두 번째는 0건 등록."""
        from goal_tracker.action_parser import ActionParser
        from goal_tracker.meeting_handler import MeetingEvent, MeetingType
        from goal_tracker.registrar import MeetingActionRegistrar

        parser = ActionParser()
        items = parser.parse(daily_retro_text)
        event = MeetingEvent(
            meeting_type=MeetingType.DAILY_RETRO,
            chat_id=0,
            message_text=daily_retro_text,
            sender_org="aiorg_pm_bot",
            action_items=items,
        )
        registrar = MeetingActionRegistrar(
            goal_tracker=mock_goal_tracker,
            dedup_ttl_sec=3600.0,
        )
        ids1 = await registrar.register_from_event(event)
        ids2 = await registrar.register_from_event(event)

        assert len(ids1) > 0
        assert len(ids2) == 0, f"중복 등록이 허용됨: {ids2}"

    @pytest.mark.asyncio
    async def test_max_iterations_terminal(self) -> None:
        """max_iterations 도달 시 추가 EVALUATE 진입이 차단된다."""
        from goal_tracker.loop_runner import AutonomousLoopRunner
        from goal_tracker.state_machine import GoalTrackerStateMachine

        sm = GoalTrackerStateMachine("G-edge-003", max_iterations=1)
        runner = AutonomousLoopRunner(goal_id="G-edge-003", state_machine=sm)

        # 첫 번째 사이클
        result1 = await runner.run_cycle(registered_ids=["G-pm-001"])
        assert result1.success
        assert sm.ctx.iteration == 1

        # 두 번째 사이클 — max_iterations 초과로 EVALUATE 진입 불가
        result2 = await runner.run_cycle(registered_ids=["G-pm-002"])
        assert not result2.dispatched, "max_iterations 초과 후 dispatch 실행됨"
        assert result2.error is not None


# ── TestStateTransitionLog ──────────────────────────────────────────────────────


class TestStateTransitionLog:
    """각 상태 전이가 정상 동작하는지 로그/출력으로 확인."""

    @pytest.mark.asyncio
    async def test_state_history_order(self) -> None:
        """전이 이력이 IDLE→EVALUATE→REPLAN→DISPATCH→IDLE 순서인지 확인."""
        from goal_tracker.loop_runner import AutonomousLoopRunner
        from goal_tracker.state_machine import GoalTrackerState, GoalTrackerStateMachine

        sm = GoalTrackerStateMachine("G-log-001")
        runner = AutonomousLoopRunner(goal_id="G-log-001", state_machine=sm)
        await runner.run_cycle(registered_ids=["G-pm-001"])

        states = [(t.from_state, t.to_state) for t in sm.ctx.history]
        expected_sequence = [
            (GoalTrackerState.IDLE, GoalTrackerState.EVALUATE),
            (GoalTrackerState.EVALUATE, GoalTrackerState.REPLAN),
            (GoalTrackerState.REPLAN, GoalTrackerState.DISPATCH),
            (GoalTrackerState.DISPATCH, GoalTrackerState.IDLE),
        ]
        for pair in expected_sequence:
            assert pair in states, f"전이 {pair} 미발생 — 실제: {states}"

    @pytest.mark.asyncio
    async def test_sm_to_dict_reflects_final_state(self) -> None:
        """사이클 완료 후 state_machine.to_dict()가 올바른 상태를 반환한다."""
        from goal_tracker.loop_runner import AutonomousLoopRunner
        from goal_tracker.state_machine import GoalTrackerStateMachine

        sm = GoalTrackerStateMachine("G-log-002")
        runner = AutonomousLoopRunner(goal_id="G-log-002", state_machine=sm)
        await runner.run_cycle(registered_ids=["G-pm-001", "G-pm-002"])

        snapshot = sm.to_dict()
        assert snapshot["state"] == "idle", f"최종 state 오류: {snapshot['state']}"
        assert snapshot["iteration"] == 1
        assert snapshot["history_length"] >= 4
        assert snapshot["dispatched_tasks"] == 2

    def test_state_machine_repr(self) -> None:
        """GoalTrackerStateMachine.__repr__이 정보를 포함한다."""
        from goal_tracker.state_machine import GoalTrackerStateMachine

        sm = GoalTrackerStateMachine("G-log-003")
        repr_str = repr(sm)
        assert "G-log-003" in repr_str
        assert "idle" in repr_str

    @pytest.mark.asyncio
    async def test_loop_runner_repr(self) -> None:
        """AutonomousLoopRunner.__repr__이 goal_id와 state를 포함한다."""
        from goal_tracker.loop_runner import AutonomousLoopRunner

        runner = AutonomousLoopRunner(goal_id="G-log-004")
        repr_str = repr(runner)
        assert "G-log-004" in repr_str

    @pytest.mark.asyncio
    async def test_result_str_representation(self) -> None:
        """LoopRunResult.__str__이 요약 정보를 포함한다."""
        from goal_tracker.loop_runner import AutonomousLoopRunner

        runner = AutonomousLoopRunner(goal_id="G-log-005")
        result = await runner.run_cycle(registered_ids=["G-pm-001"])
        result_str = str(result)

        assert "G-log-005" in result_str
        assert "states" in result_str

    @pytest.mark.asyncio
    async def test_meeting_handler_on_message_triggers_registration(
        self, mock_goal_tracker
    ) -> None:
        """MeetingEventHandler.on_message()가 회의 트리거 감지 시 registrar 호출."""
        from goal_tracker.meeting_handler import MeetingEventHandler, MeetingType
        from goal_tracker.registrar import MeetingActionRegistrar

        registrar = MeetingActionRegistrar(
            goal_tracker=mock_goal_tracker,
            org_id="aiorg_pm_bot",
        )
        handler = MeetingEventHandler(
            org_id="aiorg_pm_bot",
            registrar=registrar,
        )

        message_with_action = (
            "일일회고 — 2026-03-25\n"
            "조치사항:\n"
            "- [ ] GoalTracker 배포 확인 담당: 운영실\n"
            "- [ ] 테스트 커버리지 확인 담당: 개발실\n"
        )
        event = await handler.on_message(
            chat_id=0,
            text=message_with_action,
        )

        assert event is not None, "회의 이벤트 감지 실패"
        assert event.meeting_type == MeetingType.DAILY_RETRO
        assert event.has_action_items, "액션아이템 미파싱"


# ── TestDispatchConfirmCallback ──────────────────────────────────────────────────


class TestDispatchConfirmCallback:
    """dispatch 완료 후 확인 콜백(on_dispatch_complete) 처리 테스트."""

    @pytest.mark.asyncio
    async def test_callback_called_on_successful_dispatch(self) -> None:
        """dispatch 성공 시 on_dispatch_complete 콜백이 호출된다."""
        from goal_tracker.loop_runner import AutonomousLoopRunner, LoopRunResult

        callback_results: list[LoopRunResult] = []

        async def confirm_callback(result: LoopRunResult) -> None:
            callback_results.append(result)

        runner = AutonomousLoopRunner(goal_id="G-cb-001")
        result = await runner.run_cycle(
            registered_ids=["G-pm-001", "G-pm-002"],
            on_dispatch_complete=confirm_callback,
        )

        assert result.dispatched, "dispatch 미실행"
        assert len(callback_results) == 1, "콜백 미호출"
        assert callback_results[0] is result, "콜백에 전달된 result가 다름"
        assert callback_results[0].dispatched_count == 2

    @pytest.mark.asyncio
    async def test_callback_not_called_when_no_dispatch(self) -> None:
        """dispatch 없을 때 on_dispatch_complete 콜백은 호출되지 않는다."""
        from goal_tracker.loop_runner import AutonomousLoopRunner, LoopRunResult

        callback_results: list[LoopRunResult] = []

        async def confirm_callback(result: LoopRunResult) -> None:
            callback_results.append(result)

        runner = AutonomousLoopRunner(goal_id="G-cb-002")
        result = await runner.run_cycle(
            registered_ids=[],  # 등록 없음 → dispatch 없음
            on_dispatch_complete=confirm_callback,
        )

        assert not result.dispatched, "빈 목록에서 dispatch 실행됨"
        assert len(callback_results) == 0, "dispatch 없는데 콜백 호출됨"

    @pytest.mark.asyncio
    async def test_constructor_callback_used_when_no_call_callback(self) -> None:
        """run_cycle()에 콜백 없으면 생성자의 on_dispatch_complete가 사용된다."""
        from goal_tracker.loop_runner import AutonomousLoopRunner, LoopRunResult

        constructor_calls: list[LoopRunResult] = []

        async def ctor_callback(result: LoopRunResult) -> None:
            constructor_calls.append(result)

        runner = AutonomousLoopRunner(
            goal_id="G-cb-003",
            on_dispatch_complete=ctor_callback,
        )
        await runner.run_cycle(registered_ids=["G-pm-001"])

        assert len(constructor_calls) == 1, "생성자 콜백 미호출"
        assert constructor_calls[0].dispatched

    @pytest.mark.asyncio
    async def test_call_callback_overrides_constructor_callback(self) -> None:
        """run_cycle()의 콜백이 생성자 콜백보다 우선 적용된다."""
        from goal_tracker.loop_runner import AutonomousLoopRunner, LoopRunResult

        ctor_calls: list[str] = []
        call_calls: list[str] = []

        async def ctor_callback(result: LoopRunResult) -> None:
            ctor_calls.append("ctor")

        async def call_callback(result: LoopRunResult) -> None:
            call_calls.append("call")

        runner = AutonomousLoopRunner(
            goal_id="G-cb-004",
            on_dispatch_complete=ctor_callback,
        )
        await runner.run_cycle(
            registered_ids=["G-pm-001"],
            on_dispatch_complete=call_callback,
        )

        assert len(call_calls) == 1, "run_cycle() 콜백 미호출"
        assert len(ctor_calls) == 0, "생성자 콜백이 우선 적용됨 (오류)"

    @pytest.mark.asyncio
    async def test_callback_error_does_not_fail_result(self) -> None:
        """on_dispatch_complete 콜백에서 예외가 발생해도 LoopRunResult는 성공 상태다."""
        from goal_tracker.loop_runner import AutonomousLoopRunner, LoopRunResult

        async def failing_callback(result: LoopRunResult) -> None:
            raise RuntimeError("콜백 내부 오류")

        runner = AutonomousLoopRunner(goal_id="G-cb-005")
        result = await runner.run_cycle(
            registered_ids=["G-pm-001"],
            on_dispatch_complete=failing_callback,
        )

        # 콜백 오류는 비치명적 — result는 성공이어야 함
        assert result.success, "콜백 오류로 result.success=False됨"
        assert result.dispatched, "dispatch는 정상 수행됐어야 함"

    @pytest.mark.asyncio
    async def test_run_meeting_cycle_with_callback(self) -> None:
        """run_meeting_cycle() 편의 함수도 on_dispatch_complete를 지원한다."""
        from goal_tracker.loop_runner import LoopRunResult, run_meeting_cycle

        confirmed: list[LoopRunResult] = []

        async def on_done(r: LoopRunResult) -> None:
            confirmed.append(r)

        result = await run_meeting_cycle(
            meeting_type="daily_retro",
            registered_ids=["G-pm-001", "G-pm-002", "G-pm-003"],
            on_dispatch_complete=on_done,
        )

        assert result.dispatched
        assert len(confirmed) == 1
        assert confirmed[0].dispatched_count == 3


# ── TestScriptIntegration ────────────────────────────────────────────────────────


class TestScriptIntegration:
    """scripts/daily_retro.py, scripts/weekly_meeting_multibot.py 통합 테스트.

    실제 DB·Telegram 없이 조치사항 파싱 → GoalTracker 등록 → 자율 루프 전체
    E2E 흐름을 모킹으로 검증한다.
    """

    @pytest.mark.asyncio
    async def test_daily_retro_register_flow(
        self,
        daily_retro_text: str,
        mock_goal_tracker,
    ) -> None:
        """일일회고 스크립트 통합 흐름: 파싱 → GoalTracker 등록 → 루프 완료."""
        from goal_tracker.auto_register import auto_register_from_report
        from goal_tracker.loop_runner import run_meeting_cycle
        from goal_tracker.state_machine import GoalTrackerStateMachine

        sm = GoalTrackerStateMachine("G-script-daily-001", max_iterations=3)
        dispatched_ids: list[str] = []

        async def capture_dispatch(ids: list[str]) -> None:
            dispatched_ids.extend(ids)

        confirmed_results: list = []

        async def on_complete(result) -> None:
            confirmed_results.append(result)

        # Step 1: 파싱 및 GoalTracker 등록 (스크립트 내부 흐름 재현)
        register_result = await auto_register_from_report(
            report_text=daily_retro_text,
            report_type="daily_retro",
            goal_tracker=mock_goal_tracker,
            state_machine=sm,
            chat_id=0,
            org_id="aiorg_pm_bot",
        )

        assert register_result.action_items_found >= 3
        assert register_result.registered_count > 0
        assert register_result.state_machine_triggered

        # Step 2: 자율 루프 사이클 (스크립트에서 run_meeting_cycle 호출 패턴)
        loop_result = await run_meeting_cycle(
            meeting_type="daily_retro",
            registered_ids=register_result.registered_ids,
            dispatch_func=capture_dispatch,
            on_dispatch_complete=on_complete,
        )

        assert loop_result.success, f"루프 오류: {loop_result.error}"
        assert loop_result.dispatched, "dispatch 미실행"
        assert len(dispatched_ids) > 0, "dispatch 콜백 미호출"
        assert len(confirmed_results) == 1, "dispatch 확인 콜백 미호출"
        assert "daily_retro" in loop_result.goal_id

    @pytest.mark.asyncio
    async def test_weekly_meeting_register_flow(
        self,
        weekly_meeting_text: str,
        mock_goal_tracker,
    ) -> None:
        """주간회의 스크립트 통합 흐름: 파싱 → GoalTracker 등록 → 루프 완료."""
        from goal_tracker.auto_register import auto_register_from_report
        from goal_tracker.loop_runner import run_meeting_cycle

        dispatched_ids: list[str] = []

        async def capture_dispatch(ids: list[str]) -> None:
            dispatched_ids.extend(ids)

        register_result = await auto_register_from_report(
            report_text=weekly_meeting_text,
            report_type="weekly_meeting",
            goal_tracker=mock_goal_tracker,
            chat_id=0,
            org_id="aiorg_pm_bot",
        )

        assert register_result.action_items_found >= 3
        assert register_result.registered_count > 0

        loop_result = await run_meeting_cycle(
            meeting_type="weekly_meeting",
            registered_ids=register_result.registered_ids,
            dispatch_func=capture_dispatch,
        )

        assert loop_result.success
        assert loop_result.dispatched
        assert len(dispatched_ids) == len(register_result.registered_ids)

    @pytest.mark.asyncio
    async def test_meeting_handler_daily_retro_start_integration(
        self,
        daily_retro_text: str,
        mock_goal_tracker,
    ) -> None:
        """MeetingEventHandler.on_daily_retro_start() → registrar 자동 등록 통합."""
        from goal_tracker.meeting_handler import MeetingEventHandler, MeetingType
        from goal_tracker.registrar import MeetingActionRegistrar

        registered_ids: list[str] = []
        original_start_goal = mock_goal_tracker.start_goal.side_effect

        async def tracking_start_goal(title, description, meta=None, chat_id=0, org_id=None):
            goal_id = await original_start_goal(title, description, meta=meta, chat_id=chat_id, org_id=org_id)
            registered_ids.append(goal_id)
            return goal_id

        mock_goal_tracker.start_goal.side_effect = tracking_start_goal

        registrar = MeetingActionRegistrar(
            goal_tracker=mock_goal_tracker,
            org_id="aiorg_pm_bot",
        )
        handler = MeetingEventHandler(
            org_id="aiorg_pm_bot",
            registrar=registrar,
        )

        event = await handler.on_daily_retro_start(
            chat_id=0,
            summary_text=daily_retro_text,
        )

        assert event.meeting_type == MeetingType.DAILY_RETRO
        assert event.has_action_items
        assert len(registered_ids) > 0, "GoalTracker 등록이 발생하지 않음"

    @pytest.mark.asyncio
    async def test_meeting_handler_weekly_start_integration(
        self,
        weekly_meeting_text: str,
        mock_goal_tracker,
    ) -> None:
        """MeetingEventHandler.on_weekly_meeting_start() → registrar 자동 등록 통합."""
        from goal_tracker.meeting_handler import MeetingEventHandler, MeetingType
        from goal_tracker.registrar import MeetingActionRegistrar

        registered_ids: list[str] = []
        original_start_goal = mock_goal_tracker.start_goal.side_effect

        async def tracking_start_goal(title, description, meta=None, chat_id=0, org_id=None):
            goal_id = await original_start_goal(title, description, meta=meta, chat_id=chat_id, org_id=org_id)
            registered_ids.append(goal_id)
            return goal_id

        mock_goal_tracker.start_goal.side_effect = tracking_start_goal

        registrar = MeetingActionRegistrar(
            goal_tracker=mock_goal_tracker,
            org_id="aiorg_pm_bot",
        )
        handler = MeetingEventHandler(
            org_id="aiorg_pm_bot",
            registrar=registrar,
        )

        event = await handler.on_weekly_meeting_start(
            chat_id=0,
            summary_text=weekly_meeting_text,
        )

        assert event.meeting_type == MeetingType.WEEKLY_MEETING
        assert event.has_action_items
        assert len(registered_ids) > 0

    @pytest.mark.asyncio
    async def test_script_parse_only_mode_no_goal_tracker(
        self,
        daily_retro_text: str,
    ) -> None:
        """goal_tracker 없는 parse-only 모드: 파싱은 되지만 등록 없이 성공."""
        from goal_tracker.auto_register import auto_register_from_report

        # scripts/daily_retro.py의 실제 호출 패턴 (goal_tracker 미전달)
        result = await auto_register_from_report(
            report_text=daily_retro_text,
            report_type="daily_retro",
            org_id="aiorg_pm_bot",
        )

        # 파싱은 성공
        assert result.action_items_found >= 3
        # 등록은 없음 (parse-only)
        assert result.registered_count == 0
        # 상태머신 미트리거
        assert not result.state_machine_triggered
        # 오류 없음
        assert result.success

    @pytest.mark.asyncio
    async def test_script_fallback_synthetic_ids_flow(
        self,
        daily_retro_text: str,
    ) -> None:
        """parse-only 결과로 가상 ID 생성 후 루프 실행 — scripts/daily_retro.py 패턴."""
        from goal_tracker.auto_register import auto_register_from_report
        from goal_tracker.loop_runner import run_meeting_cycle

        register_result = await auto_register_from_report(
            report_text=daily_retro_text,
            report_type="daily_retro",
            org_id="aiorg_pm_bot",
        )

        # scripts/daily_retro.py의 fallback 패턴 재현
        synthetic_ids = register_result.registered_ids or [
            f"G-daily-{i:03d}"
            for i in range(register_result.action_items_found)
        ]

        assert len(synthetic_ids) >= 3, "가상 ID 생성 실패"

        loop_result = await run_meeting_cycle(
            meeting_type="daily_retro",
            registered_ids=synthetic_ids,
        )

        assert loop_result.success, f"루프 오류: {loop_result.error}"
        assert loop_result.dispatched
        assert loop_result.dispatched_count == len(synthetic_ids)
        # 전체 상태 전이 확인
        assert "evaluate" in loop_result.states_visited
        assert "replan" in loop_result.states_visited
        assert "dispatch" in loop_result.states_visited
        assert loop_result.states_visited[-1] == "idle"
