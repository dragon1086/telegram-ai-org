"""GoalTracker 패키지 — idle→evaluate→replan→dispatch 상태머신 및 회의 자동 등록 모듈.

패키지 구조:
    state_machine.py  — GoalTrackerState Enum + 전이 로직 (transition/get_state/reset 포함)
    router.py         — 부서별 라우팅 테이블
    dispatcher.py     — dispatch 라우팅 모듈
    meeting_handler.py — 회의 이벤트 핸들러
    action_parser.py  — 조치사항 파서
    registrar.py      — GoalTracker 자동 등록 클래스
    report_parser.py  — 일일회고/주간회의 보고 파서 (parse_action_items)
    auto_register.py  — 보고 → GoalTracker 자동 등록 파이프라인
"""
from goal_tracker.action_parser import ActionItem, ActionParser
from goal_tracker.auto_register import AutoRegisterResult, auto_register_from_report
from goal_tracker.dispatcher import DispatchResult, GoalTrackerDispatcher
from goal_tracker.loop_runner import AutonomousLoopRunner, LoopRunResult, run_meeting_cycle
from goal_tracker.meeting_handler import MeetingEvent, MeetingEventHandler, MeetingType
from goal_tracker.registrar import MeetingActionRegistrar
from goal_tracker.report_parser import parse_action_items, parse_report_metadata
from goal_tracker.router import DEPT_ROUTES, DeptRoute, DeptRouter
from goal_tracker.state_machine import (
    GoalTrackerState,
    GoalTrackerStateMachine,
    StateMachineContext,
    StateTransition,
)

__all__ = [
    # state_machine
    "GoalTrackerState",
    "StateMachineContext",
    "StateTransition",
    "GoalTrackerStateMachine",
    # router
    "DeptRoute",
    "DeptRouter",
    "DEPT_ROUTES",
    # dispatcher
    "GoalTrackerDispatcher",
    "DispatchResult",
    # meeting_handler
    "MeetingType",
    "MeetingEvent",
    "MeetingEventHandler",
    # action_parser
    "ActionItem",
    "ActionParser",
    # registrar
    "MeetingActionRegistrar",
    # report_parser
    "parse_action_items",
    "parse_report_metadata",
    # auto_register
    "auto_register_from_report",
    "AutoRegisterResult",
    # loop_runner
    "AutonomousLoopRunner",
    "LoopRunResult",
    "run_meeting_cycle",
]
