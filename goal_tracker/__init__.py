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

임포트 최적화 (Phase 3):
    모든 서브모듈은 직접 import 패턴(`from goal_tracker.state_machine import ...`)을 사용하므로
    __init__.py 수준의 eager re-export가 불필요. __getattr__ 지연 로딩으로 전환하여
    cold-start 임포트 시간 ~65ms 단축 (loguru 초기화 지연 효과).
"""
from __future__ import annotations

# 지연 로딩 맵: 이름 → (서브모듈 경로, 실제 속성 이름)
_LAZY: dict[str, tuple[str, str]] = {
    # state_machine
    "GoalTrackerState": ("goal_tracker.state_machine", "GoalTrackerState"),
    "GoalTrackerStateMachine": ("goal_tracker.state_machine", "GoalTrackerStateMachine"),
    "StateMachineContext": ("goal_tracker.state_machine", "StateMachineContext"),
    "StateTransition": ("goal_tracker.state_machine", "StateTransition"),
    # router
    "DeptRoute": ("goal_tracker.router", "DeptRoute"),
    "DeptRouter": ("goal_tracker.router", "DeptRouter"),
    "DEPT_ROUTES": ("goal_tracker.router", "DEPT_ROUTES"),
    # dispatcher
    "GoalTrackerDispatcher": ("goal_tracker.dispatcher", "GoalTrackerDispatcher"),
    "DispatchResult": ("goal_tracker.dispatcher", "DispatchResult"),
    # meeting_handler
    "MeetingType": ("goal_tracker.meeting_handler", "MeetingType"),
    "MeetingEvent": ("goal_tracker.meeting_handler", "MeetingEvent"),
    "MeetingEventHandler": ("goal_tracker.meeting_handler", "MeetingEventHandler"),
    # action_parser
    "ActionItem": ("goal_tracker.action_parser", "ActionItem"),
    "ActionParser": ("goal_tracker.action_parser", "ActionParser"),
    # registrar
    "MeetingActionRegistrar": ("goal_tracker.registrar", "MeetingActionRegistrar"),
    # report_parser
    "parse_action_items": ("goal_tracker.report_parser", "parse_action_items"),
    "parse_report_metadata": ("goal_tracker.report_parser", "parse_report_metadata"),
    # auto_register
    "auto_register_from_report": ("goal_tracker.auto_register", "auto_register_from_report"),
    "AutoRegisterResult": ("goal_tracker.auto_register", "AutoRegisterResult"),
    # loop_runner
    "AutonomousLoopRunner": ("goal_tracker.loop_runner", "AutonomousLoopRunner"),
    "LoopRunResult": ("goal_tracker.loop_runner", "LoopRunResult"),
    "run_meeting_cycle": ("goal_tracker.loop_runner", "run_meeting_cycle"),
}


def __getattr__(name: str) -> object:
    if name in _LAZY:
        module_path, attr = _LAZY[name]
        import importlib
        mod = importlib.import_module(module_path)
        obj = getattr(mod, attr)
        # 캐시: 다음 접근 시 __getattr__ 호출 생략
        globals()[name] = obj
        return obj
    raise AttributeError(f"module 'goal_tracker' has no attribute {name!r}")


__all__ = list(_LAZY.keys())
