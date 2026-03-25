"""_handle_improve_status 메서드 존재 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_improve_status_handler_exists():
    """_handle_improve_status 메서드가 PMOrchestrator에 있어야 한다."""
    from core.pm_orchestrator import PMOrchestrator
    assert hasattr(PMOrchestrator, "_handle_improve_status")


def test_routing_approve_handler_exists():
    from core.pm_orchestrator import PMOrchestrator
    assert hasattr(PMOrchestrator, "_handle_routing_approve")


def test_routing_reject_handler_exists():
    from core.pm_orchestrator import PMOrchestrator
    assert hasattr(PMOrchestrator, "_handle_routing_reject")
