"""ImprovementQueue 및 FeedbackLoopRunner 단위 테스트.

커버리지:
  - ImprovementQueue: enqueue, 우선순위 정렬, run_all, 액션 디스패치
  - FeedbackLoopRunner: 초기 파싱, 루프 종료(모두 해소), 미해소 처리, max_iterations
  - QueueRunLog.summary() 포맷
  - FeedbackLoopSummary.format() 포맷
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.health_report_parser import ImprovementItem
from core.improvement_queue import ImprovementQueue, QueueRunLog
from core.improvement_actions.base import ActionResult
from core.feedback_loop_runner import FeedbackLoopRunner, FeedbackLoopSummary


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------

def _make_item(
    issue_type: str = "file_size_warn",
    severity: str = "warn",
    priority: int = 4,
    file_path: str | None = "core/test.py",
    error_pattern: str | None = None,
) -> ImprovementItem:
    return ImprovementItem(
        issue_type=issue_type,
        severity=severity,
        priority=priority,
        file_path=file_path,
        error_pattern=error_pattern,
        suggested_action="테스트 항목",
        detail={"size_kb": 100.0} if file_path else {"count": 5},
    )


def _critical_item() -> ImprovementItem:
    return _make_item(issue_type="file_size_critical", severity="critical", priority=8)


def _error_item() -> ImprovementItem:
    return _make_item(
        issue_type="error_pattern", severity="warn", priority=6,
        file_path=None, error_pattern="approach",
    )


# ------------------------------------------------------------------
# ImprovementQueue 테스트
# ------------------------------------------------------------------

class TestImprovementQueue:
    def test_enqueue_increases_size(self):
        q = ImprovementQueue(dry_run=True)
        q.enqueue([_make_item(), _critical_item()])
        assert q.size() == 2

    def test_peek_all_sorted_by_priority_desc(self):
        q = ImprovementQueue(dry_run=True)
        items = [
            _make_item(priority=3),
            _make_item(priority=8, issue_type="file_size_critical", severity="critical"),
            _make_item(priority=6),
        ]
        q.enqueue(items)
        visible = q.peek_all()
        priorities = [i.priority for i in visible]
        assert priorities == sorted(priorities, reverse=True)

    def test_run_all_executes_in_priority_order(self):
        q = ImprovementQueue(dry_run=True)
        execution_order: list[int] = []

        class TrackingAction:
            name = "log_only"
            def __init__(self, dry_run=False):
                self.dry_run = dry_run
            def run(self, item):
                execution_order.append(item.priority)
                return ActionResult(
                    action_name="log_only", target="x", success=True,
                    dry_run=True, message="ok"
                )

        items = [_make_item(priority=p) for p in [3, 9, 5]]
        q.enqueue(items)

        with patch.object(q, "_build_action", return_value=TrackingAction(dry_run=True)):
            q.run_all()

        assert execution_order == [9, 5, 3]

    def test_run_all_log_only_dry_run_succeeds(self):
        q = ImprovementQueue(dry_run=True)
        q.enqueue([_make_item(issue_type="file_size_warn")])
        log = q.run_all()
        assert log.succeeded == 1
        assert log.failed == 0
        assert q.size() == 0  # 실행 후 큐 비워짐

    def test_run_all_split_large_file_dry_run(self):
        q = ImprovementQueue(dry_run=True)
        q.enqueue([_critical_item()])
        log = q.run_all()
        assert log.total_items == 1
        assert log.succeeded == 1  # dry_run이므로 성공으로 처리

    def test_run_all_error_pattern_dry_run(self):
        q = ImprovementQueue(dry_run=True)
        q.enqueue([_error_item()])
        log = q.run_all()
        assert log.succeeded == 1

    def test_unknown_issue_type_skipped(self):
        q = ImprovementQueue(dry_run=True)
        item = _make_item(issue_type="unknown_future_type")
        q.enqueue([item])
        log = q.run_all()
        assert log.skipped == 1
        assert log.succeeded == 0

    def test_clear_empties_queue(self):
        q = ImprovementQueue(dry_run=True)
        q.enqueue([_make_item(), _make_item()])
        q.clear()
        assert q.size() == 0

    def test_queue_log_summary_contains_counts(self):
        q = ImprovementQueue(dry_run=True)
        q.enqueue([_make_item(), _critical_item()])
        log = q.run_all()
        summary = log.summary()
        assert "개선 큐" in summary
        assert str(log.total_items) in summary

    def test_action_exception_counts_as_failure(self):
        q = ImprovementQueue(dry_run=True)
        q.enqueue([_make_item()])

        class BrokenAction:
            name = "broken"
            def __init__(self, dry_run=False): pass
            def run(self, item):
                raise RuntimeError("broken!")

        with patch.object(q, "_build_action", return_value=BrokenAction()):
            log = q.run_all()
        assert log.failed == 1


# ------------------------------------------------------------------
# ActionResult 테스트
# ------------------------------------------------------------------

class TestActionResult:
    def test_str_success(self):
        r = ActionResult(action_name="log_only", target="core/x.py", success=True, message="ok")
        assert "✅" in str(r)
        assert "log_only" in str(r)

    def test_str_failure(self):
        r = ActionResult(action_name="split", target="core/big.py", success=False, message="err")
        assert "❌" in str(r)

    def test_dry_run_tag(self):
        r = ActionResult(
            action_name="log_only", target="x", success=True,
            dry_run=True, message="ok"
        )
        assert "[dry_run]" in str(r)


# ------------------------------------------------------------------
# FeedbackLoopRunner 테스트
# ------------------------------------------------------------------

class TestFeedbackLoopRunner:
    def test_empty_report_returns_zero_iterations(self):
        runner = FeedbackLoopRunner(dry_run=True)
        summary = runner.run({})   # 빈 dict → 항목 없음
        assert summary.total_iterations == 0
        assert summary.initial_item_count == 0
        assert summary.final_unresolved_count == 0

    def test_all_resolved_after_first_iteration(self):
        runner = FeedbackLoopRunner(dry_run=True)
        runner.rescan_delay = 0  # 테스트에서 대기 없이

        # 초기 리포트: warn 항목 1개
        report_text = (
            "⚠️ 경고:\n  • core/medium.py (90KB)\n\n"
            "📋 반복 에러 패턴:\n  • approach: 5회\n"
        )

        # 재스캔 결과: 아무 문제 없음 (전부 해소)
        with patch.object(runner, "_rescan", return_value=[]):
            summary = runner.run(report_text)

        assert summary.total_iterations >= 1
        assert summary.final_unresolved_count == 0
        # 해소 항목이 있어야 함
        assert len(summary.iteration_results[0].resolved_items) > 0

    def test_max_iterations_respected(self):
        runner = FeedbackLoopRunner(dry_run=True)
        runner.max_iterations = 2
        runner.rescan_delay = 0
        runner.unresolved_alert = False

        # 재스캔해도 항상 같은 항목이 남아있는 상황 시뮬레이션
        # file_path를 파싱 결과와 일치시켜야 _diff가 "미해소"로 판단
        persistent_item = _make_item(
            priority=8, issue_type="file_size_critical", file_path="core/big.py"
        )
        persistent_item.detail["size_kb"] = 200.0
        report_text = "🔴 크리티컬:\n  • core/big.py (200KB)\n"

        with patch.object(runner, "_rescan", return_value=[persistent_item]):
            summary = runner.run(report_text)

        assert summary.total_iterations == 2  # max_iterations=2 에서 종료
        assert summary.final_unresolved_count >= 1

    def test_unresolved_alert_called_when_items_remain(self):
        runner = FeedbackLoopRunner(dry_run=True)
        runner.max_iterations = 1
        runner.rescan_delay = 0
        runner.unresolved_alert = True

        # file_path를 파싱 결과와 일치시켜야 _diff가 "미해소"로 판단
        persistent_item = _make_item(
            priority=8, issue_type="file_size_critical", file_path="core/big.py"
        )
        persistent_item.detail["size_kb"] = 200.0

        with patch.object(runner, "_rescan", return_value=[persistent_item]):
            with patch.object(runner, "_send_unresolved_alert") as mock_alert:
                runner.run("🔴 크리티컬:\n  • core/big.py (200KB)\n")
                mock_alert.assert_called_once()

    def test_summary_format_contains_key_info(self):
        runner = FeedbackLoopRunner(dry_run=True)
        runner.rescan_delay = 0

        with patch.object(runner, "_rescan", return_value=[]):
            summary = runner.run("🔴 크리티컬:\n  • core/big.py (200KB)\n")

        text = summary.format()
        assert "피드백 루프" in text
        assert "이터레이션" in text

    def test_item_key_distinguishes_different_items(self):
        item1 = _make_item(issue_type="file_size_critical", file_path="core/a.py")
        item2 = _make_item(issue_type="file_size_critical", file_path="core/b.py")
        runner = FeedbackLoopRunner(dry_run=True)
        assert runner._item_key(item1) != runner._item_key(item2)

    def test_diff_correctly_separates_resolved_unresolved(self):
        runner = FeedbackLoopRunner(dry_run=True)
        before = [
            _make_item(file_path="core/a.py"),
            _make_item(file_path="core/b.py"),
        ]
        after = [_make_item(file_path="core/b.py")]  # a.py는 해소됨
        resolved, unresolved = runner._diff(before, after)
        assert len(resolved) == 1
        assert resolved[0].file_path == "core/a.py"
        assert resolved[0].resolved is True
        assert len(unresolved) == 1
        assert unresolved[0].file_path == "core/b.py"


# ------------------------------------------------------------------
# FeedbackLoopSummary 포맷 테스트
# ------------------------------------------------------------------

class TestFeedbackLoopSummaryFormat:
    def test_all_resolved_message(self):
        summary = FeedbackLoopSummary(
            started_at="2026-03-22T00:00:00Z",
            finished_at="2026-03-22T00:01:00Z",
            total_iterations=1,
            initial_item_count=2,
            final_unresolved_count=0,
            iteration_results=[],
        )
        text = summary.format()
        assert "모든 항목 해소" in text

    def test_unresolved_warning_shown(self):
        summary = FeedbackLoopSummary(
            started_at="2026-03-22T00:00:00Z",
            finished_at="2026-03-22T00:01:00Z",
            total_iterations=3,
            initial_item_count=2,
            final_unresolved_count=1,
            iteration_results=[],
        )
        text = summary.format()
        assert "미해소" in text
        assert "수동 검토" in text
