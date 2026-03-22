"""단위 테스트 — LLMFailureDetector.

정상 케이스 3건:
  N1. survival_rate < 0.70 → 불확실 구간 아님 (is_uncertain=False)
  N2. API 키 없음 → fallback 반환 (is_failure=algo 판정)
  N3. apply_hybrid confidence < 0.60 → 알고리즘 판정 유지

실패 케이스 3건:
  F1. survival_rate 0.75 → 불확실 구간 (is_uncertain=True)
  F2. new_count=1, algo_is_failure=True → flaky 불확실 구간 (is_uncertain=True)
  F3. apply_hybrid confidence >= 0.85 + override_algorithm → LLM 채택

추가 케이스:
  E1. 동일 run_id 중복 → fallback (rate limit)
  E2. 로그 너무 짧음 → fallback
  E3. _parse_verdict 유효 JSON → 정상 파싱
  E4. _parse_verdict 손상 JSON → fallback
  E5. apply_hybrid confidence 0.70 AND 조건 (algo T + LLM F = F)
  E6. apply_hybrid confidence 0.70 AND 조건 (algo T + LLM T = T)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.llm_failure_detector import LLMFailureDetector, LLMVerdict


# ---------------------------------------------------------------------------
# 헬퍼 — 테스트용 ScanDiff 유사 객체
# ---------------------------------------------------------------------------

@dataclass
class _FakeDiff:
    run_id: str = "test-run-001"
    baseline_issue_count: int = 10
    post_run_issue_count: int = 8
    resolved_count: int = 2
    new_count: int = 0
    improvement_rate: float = 0.2
    status: str = "improved"
    new_items: list = field(default_factory=list)
    unresolved_items: list = field(default_factory=list)


def _make_detector(api_key: str | None = None) -> LLMFailureDetector:
    """API 키 없이 생성 — 테스트 환경에서 실제 API 호출 방지."""
    with patch.dict("os.environ", {}, clear=False):
        # 환경변수 GOOGLE_API_KEY / GEMINI_API_KEY 를 덮어써서 api key를 비움
        import os
        original_google = os.environ.pop("GOOGLE_API_KEY", None)
        original_gemini = os.environ.pop("GEMINI_API_KEY", None)
        try:
            detector = LLMFailureDetector(api_key=api_key)
        finally:
            if original_google is not None:
                os.environ["GOOGLE_API_KEY"] = original_google
            if original_gemini is not None:
                os.environ["GEMINI_API_KEY"] = original_gemini
    return detector


# ---------------------------------------------------------------------------
# N1. survival_rate < 0.70 → 불확실 구간 아님
# ---------------------------------------------------------------------------

def test_normal_n1_not_uncertain_low_survival():
    """survival_rate 0.60 (< 0.70) → is_uncertain=False."""
    detector = _make_detector()
    diff = _FakeDiff(
        baseline_issue_count=10,
        post_run_issue_count=6,  # survival=0.60
        new_count=0,
        resolved_count=4,
    )
    assert not detector.is_uncertain(diff, algo_is_failure=False)


# ---------------------------------------------------------------------------
# N2. API 키 없음 → fallback 반환
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_normal_n2_no_api_key_returns_fallback():
    """API 키 없으면 check()가 알고리즘 판정 그대로 반환."""
    detector = _make_detector(api_key=None)
    diff = _FakeDiff()
    verdict = await detector.check(diff, algo_is_failure=True, algo_reason="회귀 감지")
    assert verdict.is_failure is True
    assert verdict.confidence == 0.0
    assert "fallback" in verdict.reason


# ---------------------------------------------------------------------------
# N3. apply_hybrid confidence < 0.60 → 알고리즘 판정 유지
# ---------------------------------------------------------------------------

def test_normal_n3_apply_hybrid_low_confidence_keeps_algo():
    """confidence=0.40이면 알고리즘 판정 그대로 유지."""
    detector = _make_detector()
    verdict = LLMVerdict(
        is_failure=False,
        confidence=0.40,
        failure_type="null",
        override_algorithm=True,
        reason="LLM은 실패 아님",
        recommended_action="ignore",
    )
    is_fail, reason = detector.apply_hybrid(
        algo_is_failure=True,
        algo_reason="알고리즘: 회귀",
        verdict=verdict,
    )
    assert is_fail is True       # 알고리즘(True) 유지
    assert "알고리즘" in reason or "회귀" in reason


# ---------------------------------------------------------------------------
# F1. survival_rate 0.75 → 불확실 구간
# ---------------------------------------------------------------------------

def test_failure_f1_uncertain_survival_75():
    """survival_rate 0.75 (0.70~0.85) → is_uncertain=True."""
    detector = _make_detector()
    diff = _FakeDiff(
        baseline_issue_count=20,
        post_run_issue_count=15,  # survival=0.75
        new_count=1,
        resolved_count=5,
    )
    assert detector.is_uncertain(diff, algo_is_failure=False)


# ---------------------------------------------------------------------------
# F2. new_count=1, algo_is_failure=True → flaky 불확실 구간
# ---------------------------------------------------------------------------

def test_failure_f2_uncertain_flaky_new_count():
    """new_count=1 > resolved_count=0, algo=True → is_uncertain=True (flaky 가능성)."""
    detector = _make_detector()
    diff = _FakeDiff(
        baseline_issue_count=5,
        post_run_issue_count=5,
        new_count=1,
        resolved_count=0,
        status="regressed",
    )
    assert detector.is_uncertain(diff, algo_is_failure=True)


# ---------------------------------------------------------------------------
# F3. apply_hybrid confidence >= 0.85 + override → LLM 채택
# ---------------------------------------------------------------------------

def test_failure_f3_apply_hybrid_high_confidence_override():
    """confidence=0.90 + override_algorithm=True → LLM 판정 채택."""
    detector = _make_detector()
    verdict = LLMVerdict(
        is_failure=False,       # LLM은 실패 아님
        confidence=0.90,
        failure_type="flaky",
        override_algorithm=True,
        reason="CI 노이즈로 인한 일시 증가 — flaky 패턴",
        recommended_action="ignore",
    )
    is_fail, reason = detector.apply_hybrid(
        algo_is_failure=True,   # 알고리즘은 실패로 판정
        algo_reason="회귀: new_count > resolved_count",
        verdict=verdict,
    )
    assert is_fail is False      # LLM 판정(False) 채택
    assert "LLM 채택" in reason


# ---------------------------------------------------------------------------
# E1. 동일 run_id 중복 → fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extra_e1_duplicate_run_id_returns_fallback():
    """동일 run_id로 두 번 호출 시 두 번째는 fallback."""
    detector = _make_detector()
    # run_id를 seen 목록에 미리 등록
    detector._seen_run_ids.add("dup-run-id")
    diff = _FakeDiff(run_id="dup-run-id")
    verdict = await detector.check(diff, algo_is_failure=False, algo_reason="OK")
    assert verdict.confidence == 0.0
    assert "fallback" in verdict.reason


# ---------------------------------------------------------------------------
# E2. 로그 너무 짧음 → fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extra_e2_short_logs_returns_fallback():
    """recent_logs 길이 < 200자이면 LLM 생략 후 fallback."""
    detector = _make_detector()
    diff = _FakeDiff()
    verdict = await detector.check(
        diff,
        algo_is_failure=True,
        algo_reason="회귀",
        recent_logs="짧은 로그",  # < 200자
    )
    assert verdict.confidence == 0.0
    assert "fallback" in verdict.reason


# ---------------------------------------------------------------------------
# E3. _parse_verdict 유효 JSON → 정상 파싱
# ---------------------------------------------------------------------------

def test_extra_e3_parse_verdict_valid_json():
    """유효한 JSON 응답 → LLMVerdict 정상 생성."""
    detector = _make_detector()
    raw = '{"is_failure": true, "confidence": 0.88, "failure_type": "regression", "override_algorithm": true, "reason": "명확한 회귀", "recommended_action": "escalate", "evidence": ["신규 5건", "해소 1건"]}'
    verdict = detector._parse_verdict(raw, algo_is_failure=False, algo_reason="")
    assert verdict.is_failure is True
    assert verdict.confidence == 0.88
    assert verdict.failure_type == "regression"
    assert len(verdict.evidence) == 2


# ---------------------------------------------------------------------------
# E4. _parse_verdict 손상 JSON → fallback
# ---------------------------------------------------------------------------

def test_extra_e4_parse_verdict_invalid_json_falls_back():
    """JSON 손상 시 fallback verdict 반환."""
    detector = _make_detector()
    verdict = detector._parse_verdict(
        "이건 JSON이 아님 {broken",
        algo_is_failure=True,
        algo_reason="회귀",
    )
    assert verdict.confidence == 0.0
    assert "fallback" in verdict.reason


# ---------------------------------------------------------------------------
# E5. apply_hybrid mid confidence + algo T + LLM F = F
# ---------------------------------------------------------------------------

def test_extra_e5_apply_hybrid_mid_confidence_and_logic_false():
    """confidence=0.70, algo=True, LLM=False → AND = False."""
    detector = _make_detector()
    verdict = LLMVerdict(
        is_failure=False,
        confidence=0.70,
        failure_type="flaky",
        override_algorithm=False,
        reason="flaky 가능성",
        recommended_action="retry",
    )
    is_fail, reason = detector.apply_hybrid(
        algo_is_failure=True,
        algo_reason="회귀",
        verdict=verdict,
    )
    assert is_fail is False  # True AND False = False


# ---------------------------------------------------------------------------
# E6. apply_hybrid mid confidence + algo T + LLM T = T
# ---------------------------------------------------------------------------

def test_extra_e6_apply_hybrid_mid_confidence_and_logic_true():
    """confidence=0.70, algo=True, LLM=True → AND = True."""
    detector = _make_detector()
    verdict = LLMVerdict(
        is_failure=True,
        confidence=0.72,
        failure_type="regression",
        override_algorithm=False,
        reason="회귀 패턴 확인됨",
        recommended_action="escalate",
    )
    is_fail, reason = detector.apply_hybrid(
        algo_is_failure=True,
        algo_reason="회귀",
        verdict=verdict,
    )
    assert is_fail is True   # True AND True = True
    assert "합산" in reason
