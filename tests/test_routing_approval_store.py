"""RoutingApprovalStore 테스트."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.routing_approval_store import RoutingApprovalStore


def test_save_and_load(tmp_path):
    store = RoutingApprovalStore(tmp_path / "approvals.json")
    store.save({"dept": "engineering", "keywords": ["버그"]})
    pending = store.load_pending()
    assert pending is not None
    assert pending["dept"] == "engineering"


def test_clear_after_decision(tmp_path):
    store = RoutingApprovalStore(tmp_path / "approvals.json")
    store.save({"keywords": ["test"]})
    store.clear()
    assert store.load_pending() is None


def test_load_returns_none_when_empty(tmp_path):
    store = RoutingApprovalStore(tmp_path / "approvals.json")
    assert store.load_pending() is None
