"""simulation_mode._keyword_fallback 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation_mode import _keyword_fallback


WORKERS = [
    {"name": "cokac", "engine": "claude-code", "description": "코딩, 구현, 리팩토링 전문"},
    {"name": "researcher", "engine": "codex", "description": "분석, 리서치, 데이터 처리"},
]


# ---------------------------------------------------------------------------
# "코딩" 키워드 → cokac 선택
# ---------------------------------------------------------------------------

def test_keyword_coding_selects_cokac():
    result = _keyword_fallback("파이썬 코딩 해줘", WORKERS)
    names = [a["worker_name"] for a in result["assignments"]]
    assert "cokac" in names


# ---------------------------------------------------------------------------
# "리서치" 키워드 → researcher 선택
# ---------------------------------------------------------------------------

def test_keyword_research_selects_researcher():
    result = _keyword_fallback("시장 리서치 부탁해", WORKERS)
    names = [a["worker_name"] for a in result["assignments"]]
    assert "researcher" in names


# ---------------------------------------------------------------------------
# 매칭 없음 → 첫 번째 워커 선택
# ---------------------------------------------------------------------------

def test_no_match_selects_first_worker():
    result = _keyword_fallback("그냥 아무거나 해줘", WORKERS)
    assignments = result["assignments"]
    assert len(assignments) == 1
    assert assignments[0]["worker_name"] == WORKERS[0]["name"]


# ---------------------------------------------------------------------------
# 워커 없음 → 빈 assignments
# ---------------------------------------------------------------------------

def test_no_workers_returns_empty():
    result = _keyword_fallback("뭔가 해줘", [])
    assert result["assignments"] == []


# ---------------------------------------------------------------------------
# 반환 구조 검증
# ---------------------------------------------------------------------------

def test_return_structure():
    result = _keyword_fallback("코딩 작업", WORKERS)
    assert "analysis" in result
    assert "assignments" in result
    assert "completion_criteria" in result
    for a in result["assignments"]:
        assert "worker_name" in a
        assert "instruction" in a
        assert "priority" in a
