"""SelfCodeImprover 승인 게이트 통합 테스트.

Phase 1: pending_notifications 생성, 승인 흐름
Phase 2: expire_old_pending, 거절/만료 처리
"""
from __future__ import annotations

import dataclasses
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.code_improvement_approval_store import CodeImprovementApprovalStore
from core.improvement_bus import ImprovementBus, ImprovementSignal, SignalKind

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _make_code_signal(priority: int = 9) -> ImprovementSignal:
    return ImprovementSignal(
        kind=SignalKind.CODE_SMELL,
        priority=priority,
        target="code:nl_classifier.py",
        evidence={"size_kb": 160},
        suggested_action="nl_classifier.py (160KB) — 분리 또는 리팩토링 권장.",
    )


# ---------------------------------------------------------------------------
# Phase 1: pending_notifications 생성
# ---------------------------------------------------------------------------

class TestPendingNotifications:
    def test_high_priority_enqueue_adds_notification(self):
        """priority >= 8 신호 enqueue 시 pending_notifications에 메시지 추가."""
        bus = ImprovementBus(dry_run=False)
        signal = _make_code_signal(priority=9)

        mock_store = MagicMock()
        mock_store.list_approved.return_value = []
        mock_store.enqueue.return_value = "abc123def456"

        with patch(
            "core.code_improvement_approval_store.CodeImprovementApprovalStore",
            return_value=mock_store,
        ):
            bus._dispatch(signal)

        assert len(bus.pending_notifications) == 1
        msg = bus.pending_notifications[0]
        assert "abc123def456" in msg
        assert "approve_code_fix" in msg
        assert "reject_code_fix" in msg
        assert "24시간" in msg

    def test_notification_contains_approval_id_and_target(self):
        """알림 메시지에 approval_id와 target이 포함된다."""
        bus = ImprovementBus(dry_run=False)
        signal = _make_code_signal(priority=9)

        mock_store = MagicMock()
        mock_store.list_approved.return_value = []
        mock_store.enqueue.return_value = "deadbeef0001"

        with patch(
            "core.code_improvement_approval_store.CodeImprovementApprovalStore",
            return_value=mock_store,
        ):
            bus._dispatch(signal)

        msg = bus.pending_notifications[0]
        assert "deadbeef0001" in msg
        assert "nl_classifier.py" in msg
        assert "9/10" in msg

    def test_low_priority_does_not_add_notification(self):
        """priority < 8 신호는 pending_notifications에 추가되지 않는다."""
        bus = ImprovementBus(dry_run=False)
        signal = _make_code_signal(priority=7)
        bus._dispatch(signal)
        assert bus.pending_notifications == []

    def test_dry_run_does_not_add_notification(self):
        """dry_run 모드에서는 pending_notifications에 추가되지 않는다."""
        bus = ImprovementBus(dry_run=True)
        signal = _make_code_signal(priority=9)
        bus._dispatch(signal)
        assert bus.pending_notifications == []

    def test_multiple_signals_add_multiple_notifications(self):
        """여러 high-priority 신호는 각각 알림을 추가한다."""
        bus = ImprovementBus(dry_run=False)
        signals = [_make_code_signal(priority=9) for _ in range(3)]

        call_count = 0

        def make_id():
            nonlocal call_count
            call_count += 1
            return f"id{call_count:04d}"

        mock_store = MagicMock()
        mock_store.list_approved.return_value = []
        mock_store.enqueue.side_effect = [make_id(), make_id(), make_id()]

        with patch(
            "core.code_improvement_approval_store.CodeImprovementApprovalStore",
            return_value=mock_store,
        ):
            for sig in signals:
                bus._dispatch(sig)

        assert len(bus.pending_notifications) == 3


# ---------------------------------------------------------------------------
# Phase 2: expire_old_pending
# ---------------------------------------------------------------------------

class TestExpireOldPending:
    def test_fresh_pending_not_expired(self, tmp_path):
        """방금 추가된 pending 항목은 만료되지 않는다."""
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        signal = _make_code_signal()
        store.enqueue(dataclasses.asdict(signal))
        expired = store.expire_old_pending(hours=24)
        assert expired == []

    def test_old_pending_is_expired(self, tmp_path):
        """25시간 전 queued_at을 가진 pending 항목은 만료된다."""
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        signal = _make_code_signal()
        approval_id = store.enqueue(dataclasses.asdict(signal))

        # queued_at을 25시간 전으로 강제 설정
        items = store._load()
        for item in items:
            if item["approval_id"] == approval_id:
                old_time = (
                    datetime.now(timezone.utc) - timedelta(hours=25)
                ).isoformat()
                item["queued_at"] = old_time
        store._save(items)

        expired = store.expire_old_pending(hours=24)
        assert len(expired) == 1
        assert expired[0]["approval_id"] == approval_id
        assert store.get_status(approval_id) == "expired"

    def test_expired_not_in_pending(self, tmp_path):
        """만료된 항목은 list_pending()에 포함되지 않는다."""
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        signal = _make_code_signal()
        approval_id = store.enqueue(dataclasses.asdict(signal))

        items = store._load()
        for item in items:
            if item["approval_id"] == approval_id:
                item["queued_at"] = (
                    datetime.now(timezone.utc) - timedelta(hours=25)
                ).isoformat()
        store._save(items)

        store.expire_old_pending(hours=24)
        assert store.list_pending() == []

    def test_list_expired_returns_expired_items(self, tmp_path):
        """list_expired()는 expired 상태 항목을 반환한다."""
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        signal = _make_code_signal()
        approval_id = store.enqueue(dataclasses.asdict(signal))

        items = store._load()
        for item in items:
            if item["approval_id"] == approval_id:
                item["queued_at"] = (
                    datetime.now(timezone.utc) - timedelta(hours=30)
                ).isoformat()
        store._save(items)

        store.expire_old_pending(hours=24)
        expired_list = store.list_expired()
        assert len(expired_list) == 1
        assert expired_list[0]["approval_id"] == approval_id

    def test_approved_not_expired(self, tmp_path):
        """approved 상태 항목은 expire_old_pending의 영향을 받지 않는다."""
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        signal = _make_code_signal()
        approval_id = store.enqueue(dataclasses.asdict(signal))
        store.approve(approval_id)

        # queued_at을 오래 전으로 설정해도 approved는 만료되지 않는다
        items = store._load()
        for item in items:
            if item["approval_id"] == approval_id:
                item["queued_at"] = (
                    datetime.now(timezone.utc) - timedelta(hours=48)
                ).isoformat()
        store._save(items)

        expired = store.expire_old_pending(hours=24)
        assert expired == []
        assert store.get_status(approval_id) == "approved"


# ---------------------------------------------------------------------------
# Phase 2: 거절 흐름
# ---------------------------------------------------------------------------

class TestRejectFlow:
    def test_reject_changes_status(self, tmp_path):
        """reject() 호출 후 상태가 rejected로 전환된다."""
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        signal = _make_code_signal()
        approval_id = store.enqueue(dataclasses.asdict(signal))
        assert store.reject(approval_id) is True
        assert store.get_status(approval_id) == "rejected"

    def test_reject_nonexistent_returns_false(self, tmp_path):
        """존재하지 않는 ID 거절 시 False 반환."""
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        assert store.reject("nonexistent") is False

    def test_rejected_not_in_approved_list(self, tmp_path):
        """거절된 항목은 list_approved()에 포함되지 않는다."""
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        signal = _make_code_signal()
        approval_id = store.enqueue(dataclasses.asdict(signal))
        store.reject(approval_id)
        assert store.list_approved() == []


# ---------------------------------------------------------------------------
# Phase 2: 전체 승인 → 실행 흐름 (모킹)
# ---------------------------------------------------------------------------

class TestApproveAndExecuteFlow:
    def test_approve_then_mark_executed(self, tmp_path):
        """approve → mark_executed 순서가 정상 작동한다."""
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        signal = _make_code_signal()
        approval_id = store.enqueue(dataclasses.asdict(signal))
        store.approve(approval_id)
        assert store.get_status(approval_id) == "approved"
        store.mark_executed(approval_id)
        assert store.get_status(approval_id) == "executed"

    def test_format_approval_notification(self):
        """_format_approval_notification 결과에 필수 필드가 포함된다."""
        bus = ImprovementBus(dry_run=False)
        signal = _make_code_signal(priority=9)
        msg = bus._format_approval_notification(signal, "testid1234")
        assert "testid1234" in msg
        assert "approve_code_fix testid1234" in msg
        assert "reject_code_fix testid1234" in msg
        assert "nl_classifier.py" in msg
        assert "9/10" in msg
        assert "코드 자동 수정 승인 요청" in msg
