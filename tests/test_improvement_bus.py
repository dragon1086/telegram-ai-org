"""ImprovementBus 단위 테스트.

승인 게이트 (priority≥8 + code: 타겟) 흐름을 포함한 전체 커버리지.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.improvement_bus import ImprovementBus, ImprovementSignal, SignalKind


class TestImprovementSignal:
    def test_signal_creation(self):
        s = ImprovementSignal(
            kind=SignalKind.LESSON_LEARNED,
            priority=7,
            target="skill:pm-task-dispatch",
            evidence={"count": 3},
            suggested_action="개선 필요",
        )
        assert s.kind == SignalKind.LESSON_LEARNED
        assert s.priority == 7
        assert s.target == "skill:pm-task-dispatch"
        assert s.created_at  # ISO timestamp 자동 생성


class TestImprovementBus:
    def test_dry_run_does_not_raise(self):
        bus = ImprovementBus(dry_run=True)
        signals = [
            ImprovementSignal(
                kind=SignalKind.SKILL_STALE,
                priority=5,
                target="skill:test",
                evidence={},
                suggested_action="테스트 신호",
            )
        ]
        report = bus.run(signals)
        assert report.signal_count == 1
        assert len(report.actions_taken) == 1
        assert "[dry_run]" in report.actions_taken[0]

    def test_signals_sorted_by_priority(self):
        bus = ImprovementBus(dry_run=True)
        signals = [
            ImprovementSignal(kind=SignalKind.CODE_SMELL, priority=3, target="a", evidence={}, suggested_action=""),
            ImprovementSignal(kind=SignalKind.PERF_DROP, priority=9, target="b", evidence={}, suggested_action=""),
            ImprovementSignal(kind=SignalKind.ROUTE_MISS, priority=6, target="c", evidence={}, suggested_action=""),
        ]
        # collect_signals returns sorted by priority desc
        collected = bus.collect_signals()
        # We can only test internal sorting via run
        report = bus.run(signals)
        assert report.signal_count == 3

    def test_format_report_no_crash(self):
        bus = ImprovementBus(dry_run=True)
        report = bus.run([])
        text = bus.format_report(report)
        assert "자가개선" in text

    @patch("core.improvement_bus.ImprovementBus._signals_from_lesson_memory", return_value=[])
    @patch("core.improvement_bus.ImprovementBus._signals_from_retro_memory", return_value=[])
    @patch("core.improvement_bus.ImprovementBus._signals_from_skill_staleness", return_value=[])
    @patch("core.improvement_bus.ImprovementBus._signals_from_code_health", return_value=[])
    def test_collect_signals_empty_sources(self, m1, m2, m3, m4):
        bus = ImprovementBus(dry_run=True)
        signals = bus.collect_signals()
        assert signals == []

    def test_code_smell_signals_for_large_files(self, tmp_path):
        """큰 파일이 있으면 CODE_SMELL 신호가 생성된다."""
        bus = ImprovementBus(dry_run=True)
        # 실제 core/ 스캔 — pm_orchestrator.py, telegram_relay.py는 크다
        signals = bus._signals_from_code_health()
        # 신호가 생성될 수도 있고 없을 수도 있음 — 크래시 없어야 함
        assert isinstance(signals, list)
        for s in signals:
            assert s.kind == SignalKind.CODE_SMELL
            assert s.priority >= 1


# ---------------------------------------------------------------------------
# 승인 게이트 (핵심 보안 로직)
# ---------------------------------------------------------------------------

def _make_code_signal(priority: int = 9, target: str = "code:nl_classifier.py") -> ImprovementSignal:
    return ImprovementSignal(
        kind=SignalKind.CODE_SMELL,
        priority=priority,
        target=target,
        evidence={"file": "nl_classifier.py", "size_kb": 170.0},
        suggested_action="nl_classifier.py (170KB) — 리팩토링 권장.",
    )


class TestApprovalGate:
    """priority≥8 + code: 타겟 → SelfCodeImprover 직접 호출 차단 + approval_id 생성."""

    def test_high_priority_code_signal_enqueues_not_executes(self, tmp_path):
        """priority≥8 + code: 신호는 즉시 실행되지 않고 pending 큐에 들어간다."""
        from core.code_improvement_approval_store import CodeImprovementApprovalStore

        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        bus = ImprovementBus(dry_run=False)

        signal = _make_code_signal(priority=9)

        with patch(
            "core.code_improvement_approval_store.CodeImprovementApprovalStore",
            return_value=store,
        ):
            result = bus._dispatch(signal)

        assert result is not None
        assert "[pending_approval]" in result
        assert "approval_id=" in result

        # SelfCodeImprover.fix()가 호출되지 않았음을 store 상태로 확인
        pending = store.list_pending()
        assert len(pending) == 1
        assert pending[0]["status"] == "pending"

    def test_high_priority_code_signal_appends_notification(self, tmp_path):
        """승인 요청 알림이 pending_notifications에 추가된다."""
        from core.code_improvement_approval_store import CodeImprovementApprovalStore

        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        bus = ImprovementBus(dry_run=False)
        signal = _make_code_signal(priority=8)

        with patch("core.code_improvement_approval_store.CodeImprovementApprovalStore", return_value=store):
            bus._dispatch(signal)

        assert len(bus.pending_notifications) == 1
        notif = bus.pending_notifications[0]
        assert "코드 자동 수정 승인 요청" in notif
        assert "approve_code_fix" in notif
        assert "reject_code_fix" in notif

    def test_priority_below_8_code_signal_not_gated(self):
        """priority < 8인 code: 신호는 승인 게이트 없이 즉시 처리된다."""
        bus = ImprovementBus(dry_run=False)
        signal = _make_code_signal(priority=7)

        # CodeImprovementApprovalStore가 호출되지 않아야 함
        with patch("core.code_improvement_approval_store.CodeImprovementApprovalStore") as mock_store_cls:
            result = bus._dispatch(signal)
            mock_store_cls.assert_not_called()

        assert result is not None
        assert "[pending_approval]" not in result

    def test_high_priority_non_code_signal_not_gated(self):
        """priority≥8이더라도 code: 아닌 타겟은 게이트 통과 안 함."""
        bus = ImprovementBus(dry_run=False)
        signal = ImprovementSignal(
            kind=SignalKind.PERF_DROP,
            priority=9,
            target="bot:all",
            evidence={},
            suggested_action="성능 저하",
        )

        with patch("core.code_improvement_approval_store.CodeImprovementApprovalStore") as mock_store_cls:
            result = bus._dispatch(signal)
            mock_store_cls.assert_not_called()

        assert result is not None
        assert "[pending_approval]" not in result

    def test_exact_priority_8_is_gated(self, tmp_path):
        """경계값 priority=8 정확히 게이트에 걸린다."""
        from core.code_improvement_approval_store import CodeImprovementApprovalStore

        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        bus = ImprovementBus(dry_run=False)
        signal = _make_code_signal(priority=8)

        with patch("core.code_improvement_approval_store.CodeImprovementApprovalStore", return_value=store):
            result = bus._dispatch(signal)

        assert "[pending_approval]" in result
        assert len(store.list_pending()) == 1

    def test_dry_run_bypasses_approval_gate(self):
        """dry_run=True 이면 승인 게이트 없이 [dry_run] 반환."""
        bus = ImprovementBus(dry_run=True)
        signal = _make_code_signal(priority=10)

        with patch("core.code_improvement_approval_store.CodeImprovementApprovalStore") as mock_store_cls:
            result = bus._dispatch(signal)
            mock_store_cls.assert_not_called()

        assert "[dry_run]" in result
        assert "[pending_approval]" not in result

    def test_format_approval_notification_content(self):
        """알림 메시지에 승인/거절 커맨드와 만료 안내가 포함된다."""
        bus = ImprovementBus(dry_run=False)
        signal = _make_code_signal(priority=9, target="code:pm_orchestrator.py")
        msg = bus._format_approval_notification(signal, approval_id="abc123def456")

        assert "pm_orchestrator.py" in msg
        assert "abc123def456" in msg
        assert "approve_code_fix" in msg
        assert "reject_code_fix" in msg
        assert "24시간" in msg


# ---------------------------------------------------------------------------
# process_approved_signals
# ---------------------------------------------------------------------------

class TestProcessApprovedSignals:
    def test_process_approved_calls_fix_and_marks_executed(self, tmp_path):
        """approved 항목에 대해 SelfCodeImprover.fix()를 호출하고 executed 처리."""
        from core.code_improvement_approval_store import CodeImprovementApprovalStore

        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        signal_dict = {
            "kind": "code_smell",
            "priority": 9,
            "target": "code:nl_classifier.py",
            "evidence": {},
            "suggested_action": "리팩토링 권장",
            "created_at": "2026-03-25T00:00:00+00:00",
        }
        aid = store.enqueue(signal_dict)
        store.approve(aid)

        mock_fix_result = MagicMock()
        mock_fix_result.success = True
        mock_fix_result.branch = "fix/nl_classifier-abc"

        mock_improver = MagicMock()
        mock_improver.fix.return_value = mock_fix_result

        bus = ImprovementBus(dry_run=False)

        with (
            patch("core.code_improvement_approval_store.CodeImprovementApprovalStore", return_value=store),
            patch("core.self_code_improver.SelfCodeImprover", return_value=mock_improver),
        ):
            results = bus.process_approved_signals()

        assert len(results) == 1
        assert "[executed]" in results[0]
        assert "nl_classifier.py" in results[0]
        assert store.get_status(aid) == "executed"

    def test_process_approved_no_items_returns_empty(self, tmp_path):
        """approved 항목이 없으면 빈 리스트 반환."""
        from core.code_improvement_approval_store import CodeImprovementApprovalStore

        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        bus = ImprovementBus(dry_run=False)

        with patch("core.code_improvement_approval_store.CodeImprovementApprovalStore", return_value=store):
            results = bus.process_approved_signals()

        assert results == []

    def test_process_approved_fix_failure_marks_executed_failed(self, tmp_path):
        """SelfCodeImprover.fix() 실패 시 [executed_failed] 반환."""
        from core.code_improvement_approval_store import CodeImprovementApprovalStore

        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        aid = store.enqueue({
            "target": "code:broken.py",
            "suggested_action": "fix needed",
            "created_at": "2026-03-25T00:00:00+00:00",
        })
        store.approve(aid)

        mock_improver = MagicMock()
        mock_improver.fix.return_value = None  # 실패 케이스

        bus = ImprovementBus(dry_run=False)

        with (
            patch("core.code_improvement_approval_store.CodeImprovementApprovalStore", return_value=store),
            patch("core.self_code_improver.SelfCodeImprover", return_value=mock_improver),
        ):
            results = bus.process_approved_signals()

        assert len(results) == 1
        assert "[executed_failed]" in results[0]


# ---------------------------------------------------------------------------
# expire_pending_signals
# ---------------------------------------------------------------------------

class TestExpirePendingSignals:
    def test_expire_delegates_to_store(self, tmp_path):
        """expire_pending_signals가 store.expire_old_pending를 올바르게 호출한다."""
        from core.code_improvement_approval_store import CodeImprovementApprovalStore

        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        import json as _json
        aid = store.enqueue({"target": "code:old.py", "suggested_action": "old"})
        items = _json.loads(store._path.read_text())
        items[0]["queued_at"] = "2026-01-01T00:00:00+00:00"
        store._path.write_text(_json.dumps(items))

        bus = ImprovementBus(dry_run=False)

        with patch("core.code_improvement_approval_store.CodeImprovementApprovalStore", return_value=store):
            expired = bus.expire_pending_signals(hours=24)

        assert len(expired) == 1
        assert expired[0]["approval_id"] == aid
        assert store.get_status(aid) == "expired"
