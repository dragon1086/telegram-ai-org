"""Tests for PM 2-pass delegation: should_delegate_further + aggregate_results."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.pm_orchestrator import (
    _infer_dept_from_text,
    aggregate_results,
    should_delegate_further,
)
from core.result_synthesizer import SynthesisJudgment, SynthesisResult

# ── _infer_dept_from_text ─────────────────────────────────────────────────

def test_infer_dept_ops_keywords():
    assert _infer_dept_from_text("크론 중복 삭제 후 운영실에서 단일 운영") == "aiorg_ops_bot"
    assert _infer_dept_from_text("deploy to production server") == "aiorg_ops_bot"
    assert _infer_dept_from_text("watchdog 상태 확인") == "aiorg_ops_bot"


def test_infer_dept_engineering_keywords():
    assert _infer_dept_from_text("개발실 — 코드 구현 필요") == "aiorg_engineering_bot"
    assert _infer_dept_from_text("fix bug in api handler") == "aiorg_engineering_bot"


def test_infer_dept_research_keywords():
    assert _infer_dept_from_text("시장 조사 및 경쟁사 분석") == "aiorg_research_bot"


def test_infer_dept_no_match_returns_none():
    assert _infer_dept_from_text("날씨가 좋다") is None
    assert _infer_dept_from_text("") is None


# ── should_delegate_further ───────────────────────────────────────────────

def _make_synthesis(follow_up_tasks: list[dict] | None = None) -> SynthesisResult:
    return SynthesisResult(
        judgment=SynthesisJudgment.SUFFICIENT,
        summary="테스트 합성 결과",
        follow_up_tasks=follow_up_tasks or [],
        unified_report="",
    )


def test_should_delegate_further_empty():
    """follow_up_tasks 없고 COLLAB 태그 없으면 빈 리스트."""
    synthesis = _make_synthesis()
    result = should_delegate_further(synthesis, "보고서 내용만 있음")
    assert result == []


def test_should_delegate_further_from_follow_up_tasks():
    """synthesis.follow_up_tasks가 있으면 그대로 포함."""
    synthesis = _make_synthesis([{"dept": "aiorg_ops_bot", "description": "크론 정리"}])
    result = should_delegate_further(synthesis, "")
    assert len(result) == 1
    assert result[0]["dept"] == "aiorg_ops_bot"


def test_should_delegate_further_from_collab_tag():
    """보고서 내 [COLLAB:...] 태그에서 ops 태스크 추출."""
    synthesis = _make_synthesis()
    report = "크론 중복 3b78e2f8 삭제 후 단일 운영 확인 → [COLLAB:운영실에서 크론 중복 삭제 및 단일 운영 확인|맥락: daily_ai_news 중복 크론]"
    result = should_delegate_further(synthesis, report)
    assert len(result) == 1
    assert result[0]["dept"] == "aiorg_ops_bot"
    assert "크론" in result[0]["description"]


def test_should_delegate_further_dedup():
    """follow_up_tasks와 COLLAB 태그가 동일 내용이면 중복 제거."""
    synthesis = _make_synthesis([{"dept": "aiorg_ops_bot", "description": "운영실에서 크론 중복 삭제 및 단일 운영 확인"}])
    report = "[COLLAB:운영실에서 크론 중복 삭제 및 단일 운영 확인|맥락: daily_ai_news 중복 크론]"
    result = should_delegate_further(synthesis, report)
    # 중복 제거: description 앞 80자가 같으므로 1개만 남아야 함
    assert len(result) == 1


def test_should_delegate_further_multiple_depts():
    """서로 다른 부서 COLLAB 태그 2개 → 2개 반환."""
    synthesis = _make_synthesis()
    report = (
        "[COLLAB:운영실에서 cron 정리|맥락: 중복 크론]\n"
        "[COLLAB:개발실에서 코드 fix|맥락: 버그 수정]"
    )
    result = should_delegate_further(synthesis, report)
    depts = {r["dept"] for r in result}
    assert "aiorg_ops_bot" in depts
    assert "aiorg_engineering_bot" in depts


# ── aggregate_results ────────────────────────────────────────────────────

def test_aggregate_results_format():
    first = [{"id": "T-1", "assigned_dept": "aiorg_engineering_bot", "result": "코드 구현 완료"}]
    second = [{"id": "T-2", "assigned_dept": "aiorg_ops_bot", "result": "크론 등록 완료"}]
    out = aggregate_results(first, second, original_request="PM 2-pass 테스트")
    assert "1차 1개 + 2차 1개" in out
    assert "코드 구현 완료" in out
    assert "크론 등록 완료" in out


def test_aggregate_results_empty():
    out = aggregate_results([], [], "빈 요청")
    assert "1차 0개 + 2차 0개" in out


def test_aggregate_results_no_request():
    out = aggregate_results([], [])
    assert "1차 0개 + 2차 0개" in out
