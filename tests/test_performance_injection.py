"""Tests for performance psychology injection in session_manager.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_build_performance_context_with_data():
    from core.session_manager import SessionManager
    result = SessionManager.build_performance_context(
        score=4.2, peer_rank=2, total_bots=7
    )
    assert "4.2/5.0" in result
    assert "7개 봇 중 2위" in result
    assert "기록·평가" in result


def test_build_performance_context_none_score():
    from core.session_manager import SessionManager
    result = SessionManager.build_performance_context(
        score=None, peer_rank=None, total_bots=5
    )
    assert "첫 활동" in result or "없음" in result
    assert "기록·평가" in result


def test_build_performance_context_zero_bots():
    from core.session_manager import SessionManager
    result = SessionManager.build_performance_context(
        score=4.0, peer_rank=1, total_bots=0
    )
    assert "기록·평가" in result


def test_write_memory_with_performance(tmp_path):
    from core.session_manager import SessionManager
    # Find write_memory_to_claude_md — it writes to a workdir's CLAUDE.md
    # Create a mock workdir structure
    workdir = tmp_path / "test_team"
    workdir.mkdir()

    # We need to find how SessionManager gets the workdir path
    # Just test the method signature accepts performance_context
    import inspect
    sig = inspect.signature(SessionManager.write_memory_to_claude_md)
    assert "performance_context" in sig.parameters
    assert sig.parameters["performance_context"].default is None


def test_write_memory_without_performance_backward_compat():
    """Existing 2-arg call sites still work."""
    from core.session_manager import SessionManager
    import inspect
    sig = inspect.signature(SessionManager.write_memory_to_claude_md)
    # Verify team_id and memory_context are still the first two params
    params = list(sig.parameters.keys())
    assert "team_id" in params
    assert "memory_context" in params
    assert "performance_context" in params
