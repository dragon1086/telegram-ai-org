"""CodeImprovementApprovalStore 단위 테스트.

pending → approved → executed 전체 상태 흐름과
reject / expire 경로를 검증한다.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.code_improvement_approval_store import CodeImprovementApprovalStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path: Path) -> CodeImprovementApprovalStore:
    """임시 경로를 사용하는 격리된 Store."""
    return CodeImprovementApprovalStore(path=tmp_path / "approval.json")


SAMPLE_SIGNAL = {
    "kind": "code_smell",
    "priority": 9,
    "target": "code:pm_orchestrator.py",
    "evidence": {"file": "pm_orchestrator.py", "size_kb": 160.0},
    "suggested_action": "pm_orchestrator.py (160KB) — 분리 또는 리팩토링 권장.",
    "created_at": "2026-03-25T00:00:00+00:00",
}


# ---------------------------------------------------------------------------
# 기본 CRUD
# ---------------------------------------------------------------------------

class TestEnqueue:
    def test_enqueue_returns_approval_id(self, store):
        aid = store.enqueue(SAMPLE_SIGNAL)
        assert isinstance(aid, str)
        assert len(aid) == 12  # uuid4().hex[:12]

    def test_enqueue_creates_pending_item(self, store):
        aid = store.enqueue(SAMPLE_SIGNAL)
        pending = store.list_pending()
        assert len(pending) == 1
        assert pending[0]["approval_id"] == aid
        assert pending[0]["status"] == "pending"

    def test_enqueue_multiple_items(self, store):
        aid1 = store.enqueue(SAMPLE_SIGNAL)
        aid2 = store.enqueue(SAMPLE_SIGNAL)
        assert aid1 != aid2
        assert len(store.list_pending()) == 2

    def test_enqueue_persists_signal_dict(self, store):
        aid = store.enqueue(SAMPLE_SIGNAL)
        item = store.list_pending()[0]
        assert item["signal"] == SAMPLE_SIGNAL

    def test_enqueue_records_queued_at(self, store):
        store.enqueue(SAMPLE_SIGNAL)
        item = store.list_pending()[0]
        assert "queued_at" in item
        assert item["queued_at"]  # non-empty ISO timestamp


# ---------------------------------------------------------------------------
# approve / reject
# ---------------------------------------------------------------------------

class TestApproveReject:
    def test_approve_changes_status(self, store):
        aid = store.enqueue(SAMPLE_SIGNAL)
        result = store.approve(aid)
        assert result is True
        assert store.get_status(aid) == "approved"

    def test_approve_records_decided_at(self, store):
        aid = store.enqueue(SAMPLE_SIGNAL)
        store.approve(aid)
        approved = store.list_approved()
        assert len(approved) == 1
        assert "decided_at" in approved[0]

    def test_reject_changes_status(self, store):
        aid = store.enqueue(SAMPLE_SIGNAL)
        result = store.reject(aid)
        assert result is True
        assert store.get_status(aid) == "rejected"

    def test_approve_unknown_id_returns_false(self, store):
        assert store.approve("nonexistent_id") is False

    def test_reject_unknown_id_returns_false(self, store):
        assert store.reject("nonexistent_id") is False

    def test_approved_item_not_in_pending(self, store):
        aid = store.enqueue(SAMPLE_SIGNAL)
        store.approve(aid)
        assert store.list_pending() == []
        assert len(store.list_approved()) == 1

    def test_rejected_item_not_in_pending_or_approved(self, store):
        aid = store.enqueue(SAMPLE_SIGNAL)
        store.reject(aid)
        assert store.list_pending() == []
        assert store.list_approved() == []


# ---------------------------------------------------------------------------
# mark_executed
# ---------------------------------------------------------------------------

class TestMarkExecuted:
    def test_mark_executed_changes_status(self, store):
        aid = store.enqueue(SAMPLE_SIGNAL)
        store.approve(aid)
        store.mark_executed(aid)
        assert store.get_status(aid) == "executed"

    def test_mark_executed_records_executed_at(self, store):
        aid = store.enqueue(SAMPLE_SIGNAL)
        store.approve(aid)
        store.mark_executed(aid)
        items = json.loads((store._path).read_text())
        executed = [i for i in items if i["approval_id"] == aid]
        assert executed[0]["executed_at"]

    def test_clear_executed_removes_executed_items(self, store):
        aid1 = store.enqueue(SAMPLE_SIGNAL)
        aid2 = store.enqueue(SAMPLE_SIGNAL)
        store.approve(aid1)
        store.mark_executed(aid1)
        removed = store.clear_executed()
        assert removed == 1
        assert store.get_status(aid2) == "pending"
        assert store.get_status(aid1) is None  # 삭제됨


# ---------------------------------------------------------------------------
# expire
# ---------------------------------------------------------------------------

class TestExpire:
    def test_expire_old_pending_converts_status(self, store, monkeypatch):
        """queued_at을 과거로 조작해 만료 로직을 검증."""
        aid = store.enqueue(SAMPLE_SIGNAL)

        # queued_at을 충분히 오래된 과거로 덮어쓰기 (시스템 시계와 무관하게 항상 만료)
        items = json.loads(store._path.read_text(encoding="utf-8"))
        items[0]["queued_at"] = "2020-01-01T00:00:00+00:00"
        store._path.write_text(json.dumps(items), encoding="utf-8")

        expired = store.expire_old_pending(hours=24)
        assert len(expired) == 1
        assert expired[0]["approval_id"] == aid
        assert store.get_status(aid) == "expired"

    def test_expire_does_not_affect_recent_pending(self, store):
        store.enqueue(SAMPLE_SIGNAL)  # 방금 생성 — 만료 안 됨
        expired = store.expire_old_pending(hours=24)
        assert expired == []
        assert len(store.list_pending()) == 1

    def test_list_expired_returns_expired_items(self, store):
        aid = store.enqueue(SAMPLE_SIGNAL)
        items = json.loads(store._path.read_text(encoding="utf-8"))
        items[0]["queued_at"] = "2020-01-01T00:00:00+00:00"
        store._path.write_text(json.dumps(items), encoding="utf-8")
        store.expire_old_pending(hours=24)
        assert len(store.list_expired()) == 1


# ---------------------------------------------------------------------------
# 파일 없음 / 손상 복원력
# ---------------------------------------------------------------------------

class TestResilience:
    def test_empty_store_returns_empty_lists(self, store):
        assert store.list_pending() == []
        assert store.list_approved() == []
        assert store.list_expired() == []

    def test_corrupted_json_returns_empty(self, store, tmp_path):
        p = tmp_path / "approval.json"
        p.write_text("NOT JSON {{")
        bad_store = CodeImprovementApprovalStore(path=p)
        assert bad_store.list_pending() == []

    def test_non_list_json_returns_empty(self, store, tmp_path):
        p = tmp_path / "approval.json"
        p.write_text('{"key": "value"}')
        bad_store = CodeImprovementApprovalStore(path=p)
        assert bad_store.list_pending() == []
