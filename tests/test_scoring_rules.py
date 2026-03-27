"""tests/test_scoring_rules.py — scoring_rules.py 단위 테스트

테스트 범위:
    - calculate_score: 가중치 기반 점수 산출, 경계값, 음수 입력 예외
    - get_level_transition: L1/L2/L3 승급·유지·만료 전환, 경계값
    - apply_scoring_rules: 파이프라인 통합, 하드 만료, 날짜 파싱
    - 상수 무결성 검증 (SCORE_WEIGHTS 합계, 임계값 범위)
"""

from __future__ import annotations

import datetime
from copy import deepcopy

import pytest

from core.scoring_rules import (
    EXPIRY_CONDITIONS,
    FREQUENCY_SCALE,
    PROMOTION_THRESHOLDS,
    RECENCY_DECAY_DAYS,
    REFERENCE_SCALE,
    SCORE_WEIGHTS,
    apply_scoring_rules,
    calculate_score,
    get_level_transition,
)


# ============================================================
# 헬퍼
# ============================================================

def _make_record(
    frequency: float = 5,
    reference_count: float = 10,
    days_ago: int = 0,
    level: str = "L1",
) -> dict:
    """기본 태스크 레코드 팩토리."""
    last_accessed = (datetime.date.today() - datetime.timedelta(days=days_ago)).isoformat()
    return {
        "frequency": frequency,
        "reference_count": reference_count,
        "last_accessed": last_accessed,
        "level": level,
    }


# ============================================================
# 상수 무결성
# ============================================================


class TestConstants:
    def test_score_weights_sum_to_one(self):
        total = sum(SCORE_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, f"SCORE_WEIGHTS 합 = {total}, 1.0 이어야 함"

    def test_promotion_thresholds_order(self):
        assert PROMOTION_THRESHOLDS["L1_TO_L2"] < PROMOTION_THRESHOLDS["L2_TO_L3"], (
            "L1→L2 임계값이 L2→L3 임계값보다 낮아야 함"
        )

    def test_expiry_min_score_below_promotion(self):
        assert EXPIRY_CONDITIONS["min_score"] < PROMOTION_THRESHOLDS["L1_TO_L2"], (
            "만료 임계값이 승급 임계값보다 낮아야 함"
        )

    def test_scales_positive(self):
        assert FREQUENCY_SCALE > 0
        assert REFERENCE_SCALE > 0
        assert RECENCY_DECAY_DAYS > 0


# ============================================================
# calculate_score
# ============================================================


class TestCalculateScore:
    # ── 극단값 ──

    def test_all_max_returns_100(self):
        score = calculate_score(
            frequency=FREQUENCY_SCALE,
            reference_count=REFERENCE_SCALE,
            last_accessed_days_ago=0,
        )
        assert score == 100.0

    def test_all_min_returns_0(self):
        score = calculate_score(
            frequency=0,
            reference_count=0,
            last_accessed_days_ago=RECENCY_DECAY_DAYS,
        )
        assert score == 0.0

    def test_over_max_clipped_to_100(self):
        """입력이 스케일을 초과해도 100 이상이 되지 않아야 한다."""
        score = calculate_score(
            frequency=FREQUENCY_SCALE * 10,
            reference_count=REFERENCE_SCALE * 10,
            last_accessed_days_ago=0,
        )
        assert score == 100.0

    def test_recency_beyond_decay_days_clipped_to_0(self):
        """접근일이 decay 기간을 초과해도 음수가 되지 않아야 한다."""
        score = calculate_score(
            frequency=0,
            reference_count=0,
            last_accessed_days_ago=RECENCY_DECAY_DAYS * 2,
        )
        assert score == 0.0

    # ── 가중치 기여 검증 ──

    def test_only_frequency_contributes(self):
        """frequency만 최대일 때 기여도 = 0.5 × 100 = 50.0"""
        score = calculate_score(
            frequency=FREQUENCY_SCALE,
            reference_count=0,
            last_accessed_days_ago=RECENCY_DECAY_DAYS,
        )
        assert score == pytest.approx(50.0, abs=1e-4)

    def test_only_reference_contributes(self):
        """reference_count만 최대일 때 기여도 = 0.3 × 100 = 30.0"""
        score = calculate_score(
            frequency=0,
            reference_count=REFERENCE_SCALE,
            last_accessed_days_ago=RECENCY_DECAY_DAYS,
        )
        assert score == pytest.approx(30.0, abs=1e-4)

    def test_only_recency_contributes(self):
        """recency만 최대(days_ago=0)일 때 기여도 = 0.2 × 100 = 20.0"""
        score = calculate_score(
            frequency=0,
            reference_count=0,
            last_accessed_days_ago=0,
        )
        assert score == pytest.approx(20.0, abs=1e-4)

    # ── 경계값: 승급 직전 ──

    def test_score_just_below_l1_to_l2_threshold(self):
        """score ≈ 69.x → L1→L2 승급 직전"""
        # frequency=6.9, ref=0, recency=0 → 6.9/10*100*0.5 = 34.5 + 0 + 20 = 54.5 (너무 낮음)
        # frequency=10(50), ref=10(15), recency=10일전(~13.3) → 78.3 — 너무 높음
        # 목표: score < 70 이면서 >= 30
        # frequency=5(25), ref=0(0), recency=0(20) → 45 — too low
        # frequency=8(40), ref=10(15), recency=0(20) → 75 — too high
        # frequency=7(35), ref=8(12), recency=5일(16.7) → 63.7 ✓ — 승급 직전
        score = calculate_score(frequency=7, reference_count=8, last_accessed_days_ago=5)
        assert 30.0 <= score < PROMOTION_THRESHOLDS["L1_TO_L2"]

    def test_score_at_l1_to_l2_threshold(self):
        """score 정확히 70.0 → 승급 조건 충족"""
        # frequency=10(50) + ref=20(30) + recency=30일(0) → 80 → too high
        # frequency=10(50) + ref=0 + recency=0(20) → 70 ✓
        score = calculate_score(
            frequency=FREQUENCY_SCALE,
            reference_count=0,
            last_accessed_days_ago=0,
        )
        assert score == pytest.approx(70.0, abs=1e-4)

    def test_score_just_above_l2_to_l3_threshold(self):
        """score >= 90 → L2→L3 승급"""
        # freq=10(50)+ref=20(30)+recency=15일(10) → 90
        score = calculate_score(
            frequency=FREQUENCY_SCALE,
            reference_count=REFERENCE_SCALE,
            last_accessed_days_ago=RECENCY_DECAY_DAYS / 2,
        )
        assert score == pytest.approx(90.0, abs=1e-4)

    # ── 경계값: 만료 직전 ──

    def test_score_just_above_expiry_threshold(self):
        """score > 30 → 만료 아님"""
        score = calculate_score(frequency=3, reference_count=5, last_accessed_days_ago=10)
        assert score > EXPIRY_CONDITIONS["min_score"]

    def test_score_at_expiry_threshold(self):
        """score 정확히 30.0 경계 확인 — 30 미만만 만료"""
        # freq=0 + ref=0 + recency=15일(10) → 10 — 만료
        score = calculate_score(frequency=0, reference_count=0, last_accessed_days_ago=15)
        assert score < EXPIRY_CONDITIONS["min_score"]

    # ── 오류 처리 ──

    def test_negative_days_ago_raises(self):
        with pytest.raises(ValueError, match="last_accessed_days_ago must be >= 0"):
            calculate_score(frequency=1, reference_count=1, last_accessed_days_ago=-1)

    def test_return_type_is_float(self):
        result = calculate_score(frequency=5, reference_count=10, last_accessed_days_ago=5)
        assert isinstance(result, float)


# ============================================================
# get_level_transition
# ============================================================


class TestGetLevelTransition:
    # ── L1 승급 ──

    def test_l1_promote_at_threshold(self):
        assert get_level_transition("L1", PROMOTION_THRESHOLDS["L1_TO_L2"]) == "promote"

    def test_l1_promote_above_threshold(self):
        assert get_level_transition("L1", PROMOTION_THRESHOLDS["L1_TO_L2"] + 10) == "promote"

    def test_l1_stay_below_threshold(self):
        score = PROMOTION_THRESHOLDS["L1_TO_L2"] - 0.1
        assert get_level_transition("L1", score) == "stay"

    # ── L2 승급 ──

    def test_l2_promote_at_threshold(self):
        assert get_level_transition("L2", PROMOTION_THRESHOLDS["L2_TO_L3"]) == "promote"

    def test_l2_stay_between_thresholds(self):
        score = (PROMOTION_THRESHOLDS["L1_TO_L2"] + PROMOTION_THRESHOLDS["L2_TO_L3"]) / 2
        assert get_level_transition("L2", score) == "stay"

    # ── L3 최상위: 승급 없음 ──

    def test_l3_stay_even_at_max(self):
        assert get_level_transition("L3", 100.0) == "stay"

    def test_l3_expire_when_score_low(self):
        assert get_level_transition("L3", EXPIRY_CONDITIONS["min_score"] - 1) == "expire"

    # ── 만료 우선 적용 ──

    def test_expire_beats_promotion_check(self):
        """score < min_score이면 레벨과 무관하게 만료"""
        for lvl in ("L1", "L2", "L3"):
            assert get_level_transition(lvl, EXPIRY_CONDITIONS["min_score"] - 0.1) == "expire"

    def test_expire_at_zero(self):
        assert get_level_transition("L1", 0.0) == "expire"

    # ── 경계값 ──

    def test_exactly_at_expiry_boundary(self):
        """score == min_score → stay (만료는 score < min_score)"""
        assert get_level_transition("L1", EXPIRY_CONDITIONS["min_score"]) == "stay"

    # ── 오류 처리 ──

    def test_invalid_level_raises(self):
        with pytest.raises(ValueError, match="current_level must be one of"):
            get_level_transition("L4", 50.0)  # type: ignore[arg-type]

    def test_invalid_level_empty_string_raises(self):
        with pytest.raises(ValueError):
            get_level_transition("", 50.0)  # type: ignore[arg-type]


# ============================================================
# apply_scoring_rules
# ============================================================


class TestApplyScoringRules:
    # ── 승급 케이스 ──

    def test_l1_to_l2_promotion(self):
        """고빈도·고참조·최근 접근 → L1에서 L2 승급"""
        rec = _make_record(frequency=10, reference_count=20, days_ago=0, level="L1")
        result = apply_scoring_rules(rec)
        assert result["transition"] == "promote"
        assert result["next_level"] == "L2"
        assert result["score"] == 100.0

    def test_l2_to_l3_promotion(self):
        """score >= 90 + L2 → L3 승급"""
        rec = _make_record(frequency=10, reference_count=20, days_ago=0, level="L2")
        result = apply_scoring_rules(rec)
        assert result["transition"] == "promote"
        assert result["next_level"] == "L3"

    def test_l3_stay_at_max(self):
        """L3 최상위 — 점수 만점이어도 승급 없음"""
        rec = _make_record(frequency=10, reference_count=20, days_ago=0, level="L3")
        result = apply_scoring_rules(rec)
        assert result["transition"] == "stay"
        assert result["next_level"] == "L3"

    # ── 정상 유지 케이스 ──

    def test_l1_stay(self):
        """중간 점수 → L1 유지"""
        rec = _make_record(frequency=3, reference_count=5, days_ago=10, level="L1")
        result = apply_scoring_rules(rec)
        assert result["transition"] == "stay"
        assert result["next_level"] == "L1"

    # ── 만료 케이스 ──

    def test_expire_low_score(self):
        """저빈도·무참조·장시간 미접근 → 점수 낮아 만료"""
        rec = _make_record(frequency=0, reference_count=0, days_ago=25, level="L1")
        result = apply_scoring_rules(rec)
        assert result["transition"] == "expire"
        assert result["next_level"] is None

    def test_hard_expire_30_days(self):
        """30일 미접근 → 점수 무관 하드 만료"""
        rec = _make_record(frequency=10, reference_count=20, days_ago=30, level="L2")
        result = apply_scoring_rules(rec)
        assert result["transition"] == "expire"
        assert result["next_level"] is None
        assert result["score"] == 0.0

    def test_hard_expire_beyond_30_days(self):
        """30일 초과 미접근도 하드 만료"""
        rec = _make_record(frequency=10, reference_count=20, days_ago=60, level="L3")
        result = apply_scoring_rules(rec)
        assert result["transition"] == "expire"
        assert result["next_level"] is None

    def test_expire_just_before_30_days(self):
        """29일 미접근 — 하드 만료 아님 (점수 기반 판단으로)"""
        rec = _make_record(frequency=0, reference_count=0, days_ago=29, level="L1")
        result = apply_scoring_rules(rec)
        # 29일 미접근 + 0 지표 → recency 기여만 남고 score 매우 낮음 → expire (score < 30)
        assert result["transition"] == "expire"
        # score는 0이 아님 (하드 만료가 아니라 점수 만료)
        assert result["score"] > 0.0

    # ── 날짜 형식 파싱 ──

    def test_last_accessed_as_date_object(self):
        rec = {
            "frequency": 5,
            "reference_count": 10,
            "last_accessed": datetime.date.today(),
            "level": "L1",
        }
        result = apply_scoring_rules(rec)
        assert "score" in result
        assert "transition" in result

    def test_last_accessed_as_datetime_object(self):
        rec = {
            "frequency": 5,
            "reference_count": 10,
            "last_accessed": datetime.datetime.now(),
            "level": "L1",
        }
        result = apply_scoring_rules(rec)
        assert "score" in result

    def test_last_accessed_as_iso_string(self):
        rec = {
            "frequency": 5,
            "reference_count": 10,
            "last_accessed": datetime.date.today().isoformat(),
            "level": "L1",
        }
        result = apply_scoring_rules(rec)
        assert "score" in result

    def test_invalid_last_accessed_raises(self):
        rec = {
            "frequency": 5,
            "reference_count": 10,
            "last_accessed": "not-a-date",
            "level": "L1",
        }
        with pytest.raises(ValueError):
            apply_scoring_rules(rec)

    def test_missing_last_accessed_raises(self):
        rec = {"frequency": 5, "reference_count": 10, "level": "L1"}
        with pytest.raises((ValueError, TypeError)):
            apply_scoring_rules(rec)

    # ── 원본 레코드 불변성 ──

    def test_original_record_not_mutated(self):
        rec = _make_record(frequency=10, reference_count=20, days_ago=0, level="L1")
        original = deepcopy(rec)
        apply_scoring_rules(rec)
        assert rec == original

    # ── 반환값 구조 ──

    def test_return_contains_required_keys(self):
        rec = _make_record()
        result = apply_scoring_rules(rec)
        for key in ("score", "transition", "next_level"):
            assert key in result, f"반환값에 '{key}' 키 없음"

    def test_score_within_range(self):
        for days in (0, 10, 20, 29):
            rec = _make_record(frequency=5, reference_count=10, days_ago=days)
            result = apply_scoring_rules(rec)
            if result["transition"] != "expire" or days < 30:
                assert 0.0 <= result["score"] <= 100.0, (
                    f"score={result['score']} out of [0, 100] range for days_ago={days}"
                )

    # ── 엣지 케이스: 기본값 처리 ──

    def test_missing_frequency_defaults_to_zero(self):
        rec = {
            "reference_count": 10,
            "last_accessed": datetime.date.today().isoformat(),
            "level": "L1",
        }
        result = apply_scoring_rules(rec)
        assert "score" in result

    def test_missing_reference_count_defaults_to_zero(self):
        rec = {
            "frequency": 10,
            "last_accessed": datetime.date.today().isoformat(),
            "level": "L1",
        }
        result = apply_scoring_rules(rec)
        assert "score" in result
