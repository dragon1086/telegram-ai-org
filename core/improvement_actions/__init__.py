"""improvement_actions 패키지 — 개선 항목 유형별 실행 액션 모음.

각 액션은 ImprovementItem을 받아 ActionResult를 반환한다.
"""
from core.improvement_actions.base import ActionResult, BaseAction
from core.improvement_actions.fix_error_pattern import FixErrorPatternAction
from core.improvement_actions.split_large_file import SplitLargeFileAction
from core.improvement_actions.log_only import LogOnlyAction

__all__ = [
    "ActionResult",
    "BaseAction",
    "FixErrorPatternAction",
    "SplitLargeFileAction",
    "LogOnlyAction",
]
