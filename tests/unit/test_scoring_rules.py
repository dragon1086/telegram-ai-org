"""
tests/unit/test_scoring_rules.py

scoring_rules.py 단위 테스트:
  - calculate_score(): 가중치·정규화·경계값
  - get_level_transition(): 승급/유지/만료 경계값
  - apply_scoring_rules(): 통합 파이프라인 (승급·유지·점수만료·하드만료)
"""

import sys
import os
from datetime import date, datetime, timedelta

import pytest

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.scoring_rules import (
    EXPIRY_CONDITIONS,
    PROMOTION_THRESHOLDS,
    SCORE_WEIGHTS,
    apply_scoring_rules,
    calculate_score,
    get_level_transition,
)


# ================================================================
# calculate_score 테스트
# ================================================================


class TestCalculateScore:
    """calculate_score() 경계값 및 가중치 검증."""

    def test_all_max_inputs_returns_100(self):
        """모든 지표 최대값 → 100점."""
        assert calculate_score(10, 20, 0) == pytest.approx(100.0)

    def test_all_min_inputs_returns_0(self):
        """모든 지표 최소값(빈도=0, 참조=0, 30일 미접근) → 0점."""
        assert calculate_score(0, 0, 30) == pytest.approx(0.0)

    def test_only_frequency_contributes(self):
        """frequency만 최대, 나머지 0 → 50점 (가중치 0.5)."""
        score = calculate_score(frequency=10, reference_count=0, last_accessed_days_ago=30)
        assert score == pytest.approx(50.0)

    def test_only_reference_count_contributes(self):
        """reference_count만 최대, 나머지 0 → 30점 (가중치 0.3)."""
        score = calculate_score(frequency=0, reference_count=20, last_accessed_days_ago=30)
        assert score == pytest.approx(30.0)

    def test_only_recency_contributes(self):
        """recency만 최대(days=0), 나머지 0 → 20점 (가중치 0.2)."""
        score = calculate_score(frequency=0, reference_count=0, last_accessed_days_ago=0)
        assert score == pytest.approx(20.0)

    def test_frequency_saturation_at_scale(self):
        """frequency가 FREQUENCY_SCALE(10)을 초과해도 점수가 올라가지 않는다."""
        score_at_scale = calculate_score(10, 0, 30)
        score_over_scale = calculate_score(100, 0, 30)
        assert score_at_scale == score_over_scale

    def test_reference_count_saturation(self):
        """reference_count가 REFERENCE_SCALE(20)을 초과해도 포화된다."""
        score_at_scale = calculate_score(0, 20, 30)
        score_over_scale = calculate_score(0, 999, 30)
        assert score_at_scale == score_over_scale

    def test_recency_half_decay(self):
        """15일 경과 → recency = 50% → 0.2×50 = 10점."""
        score = calculate_score(0, 0, 15)
        assert score == pytest.approx(10.0)

    def test_recency_beyond_30_days_clamped_at_zero(self):
        """30일 초과 → recency_score는 음수가 되지 않고 0으로 클램프."""
        score_at_30 = calculate_score(0, 0, 30)
        score_at_60 = calculate_score(0, 0, 60)
        assert score_at_30 == score_at_60 == pytest.approx(0.0)

    def test_score_never_exceeds_100(self):
        """어떤 경우에도 100점을 초과하지 않는다."""
        assert calculate_score(9999, 9999, 0) <= 100.0

    def test_score_never_below_0(self):
        """어떤 경우에도 0점 미만이 되지 않는다."""
        assert calculate_score(0, 0, 9999) >= 0.0

    def test_negative_days_raises(self):
        """last_accessed_days_ago 음수는 ValueError를 발생시킨다."""
        with pytest.raises(ValueError, match="last_accessed_days_ago"):
            calculate_score(5, 5, -1)

    def test_exact_l1_to_l2_promotion_score(self):
        """frequency=10, ref=0, days=0 → score=70 (L1→L2 경계)."""
        # 50×1.0 + 30×0 + 20×1.0 = 70
        score = calculate_score(10, 0, 0)
        assert score == pytest.approx(70.0)

    def test_exact_expiry_boundary_score_30(self):
        """frequency=2, ref=0, days=0 → score=30 (만료 직전 경계)."""
        # 50×0.2 + 0 + 20×1.0 = 10 + 0 + 20 = 30
        score = calculate_score(2, 0, 0)
        assert score == pytest.approx(30.0)

    def test_score_below_expiry_boundary(self):
        """frequency=1, ref=0, days=0 → score=25 (만료 조건 진입)."""
        # 50×0.1 + 0 + 20×1.0 = 5 + 0 + 20 = 25
        score = calculate_score(1, 0, 0)
        assert score == pytest.approx(25.0)

    def test_weights_sum_to_one(self):
        """SCORE_WEIGHTS 합이 정확히 1.0인지 검증."""
        total = sum(SCORE_WEIGHTS.values())
        assert total == pytest.approx(1.0)


# ================================================================
# get_level_transition 테스트
# ================================================================


class TestGetLevelTransition:
    """get_level_transition() 승급/유지/만료 경계값 검증."""

    # ── L1 테스트 ──

    def test_l1_promotes_at_threshold(self):
        """L1: score=70.0 → promote (경계값 포함)."""
        assert get_level_transition("L1", 70.0) == "promote"

    def test_l1_stays_just_below_promotion(self):
        """L1: score=69.9999 → stay (승급 직전)."""
        assert get_level_transition("L1", 69.9999) == "stay"

    def test_l1_stays_at_min_score(self):
        """L1: score=30.0 → stay (만료 경계 직전, 유지)."""
        assert get_level_transition("L1", 30.0) == "stay"

    def test_l1_expires_just_below_min_score(self):
        """L1: score=29.9999 → expire (만료 경계값)."""
        assert get_level_transition("L1", 29.9999) == "expire"

    def test_l1_expires_at_zero(self):
        """L1: score=0 → expire."""
        assert get_level_transition("L1", 0.0) == "expire"

    # ── L2 테스트 ──

    def test_l2_promotes_at_threshold(self):
        """L2: score=90.0 → promote (경계값 포함)."""
        assert get_level_transition("L2", 90.0) == "promote"

    def test_l2_stays_just_below_promotion(self):
        """L2: score=89.9999 → stay (승급 직전)."""
        assert get_level_transition("L2", 89.9999) == "stay"

    def test_l2_stays_in_middle_range(self):
        """L2: score=60 → stay (정상 범위)."""
        assert get_level_transition("L2", 60.0) == "stay"

    def test_l2_expires_below_min_score(self):
        """L2: score=29.9 → expire."""
        assert get_level_transition("L2", 29.9) == "expire"

    # ── L3 테스트 ──

    def test_l3_stays_at_max_score(self):
        """L3: score=100 → stay (최상위, 승급 없음)."""
        assert get_level_transition("L3", 100.0) == "stay"

    def test_l3_stays_above_threshold(self):
        """L3: score=90 → stay (L2→L3 임계값이어도 L3에서는 stay)."""
        assert get_level_transition("L3", 90.0) == "stay"

    def test_l3_expires_below_min_score(self):
        """L3: score=29.9 → expire."""
        assert get_level_transition("L3", 29.9) == "expire"

    # ── 유효하지 않은 레벨 ──

    def test_invalid_level_raises_value_error(self):
        """유효하지 않은 레벨('L4')은 ValueError를 발생시킨다."""
        with pytest.raises(ValueError, match="current_level"):
            get_level_transition("L4", 80.0)  # type: ignore[arg-type]

    def test_empty_string_level_raises(self):
        """빈 문자열 레벨은 ValueError를 발생시킨다."""
        with pytest.raises(ValueError):
            get_level_transition("", 80.0)  # type: ignore[arg-type]


# ================================================================
# apply_scoring_rules 테스트
# ================================================================


class TestApplyScoringRules:
    """apply_scoring_rules() 통합 파이프라인 검증."""

    def _today(self) -> str:
        return date.today().isoformat()

    def _days_ago(self, n: int) -> str:
        return (date.today() - timedelta(days=n)).isoformat()

    # ── 승급 케이스 ──

    def test_l1_promotes_to_l2(self):
        """L1 + score=70 → promote, next_level='L2'."""
        record = {
            "frequency": 10,      # 50×1.0 = 50
            "reference_count": 0, # 0
            "last_accessed": self._today(),  # recency = 20
            "level": "L1",
        }
        result = apply_scoring_rules(record)
        assert result["score"] == pytest.approx(70.0)
        assert result["transition"] == "promote"
        assert result["next_level"] == "L2"

    def test_l2_promotes_to_l3(self):
        """L2 + score=100 → promote, next_level='L3'."""
        record = {
            "frequency": 10,
            "reference_count": 20,
            "last_accessed": self._today(),
            "level": "L2",
        }
        result = apply_scoring_rules(record)
        assert result["score"] == pytest.approx(100.0)
        assert result["transition"] == "promote"
        assert result["next_level"] == "L3"

    def test_l3_stays_at_top(self):
        """L3 + 높은 점수 → stay, next_level='L3' (최상위 유지)."""
        record = {
            "frequency": 10,
            "reference_count": 20,
            "last_accessed": self._today(),
            "level": "L3",
        }
        result = apply_scoring_rules(record)
        assert result["transition"] == "stay"
        assert result["next_level"] == "L3"

    # ── 유지(stay) 케이스 ──

    def test_l1_stays_in_normal_range(self):
        """L1 + score 30~70 범위 → stay, next_level='L1'."""
        record = {
            "frequency": 2,       # score = 10 + 0 + 20 = 30 (최소 유지)
            "reference_count": 0,
            "last_accessed": self._today(),
            "level": "L1",
        }
        result = apply_scoring_rules(record)
        assert result["score"] == pytest.approx(30.0)
        assert result["transition"] == "stay"
        assert result["next_level"] == "L1"

    def test_l2_stays_in_normal_range(self):
        """L2 + score 30~90 범위 → stay."""
        record = {
            "frequency": 5,
            "reference_count": 5,
            "last_accessed": self._today(),
            "level": "L2",
        }
        result = apply_scoring_rules(record)
        # score = 50×0.5 + 25×0.3 + 100×0.2 = 25 + 7.5 + 20 = 52.5
        assert result["score"] == pytest.approx(52.5)
        assert result["transition"] == "stay"
        assert result["next_level"] == "L2"

    # ── 점수 기반 만료 케이스 ──

    def test_expires_by_low_score(self):
        """최근 접근이지만 활동 없음 → score=20 → expire."""
        record = {
            "frequency": 0,
            "reference_count": 0,
            "last_accessed": self._today(),  # recency만 = 20
            "level": "L2",
        }
        result = apply_scoring_rules(record)
        assert result["score"] == pytest.approx(20.0)
        assert result["transition"] == "expire"
        assert result["next_level"] is None

    def test_expires_just_below_min_score(self):
        """L1: score 29.9 → expire."""
        record = {
            "frequency": 1,       # 50×0.1 = 5
            "reference_count": 0,
            "last_accessed": self._today(),  # 20
            "level": "L1",        # score = 5 + 0 + 20 = 25 < 30 → expire
        }
        result = apply_scoring_rules(record)
        assert result["score"] == pytest.approx(25.0)
        assert result["transition"] == "expire"
        assert result["next_level"] is None

    # ── 하드 만료 케이스 (장기 미접근) ──

    def test_hard_expiry_at_30_days(self):
        """정확히 30일 미접근 → 하드 만료 (점수 무관)."""
        record = {
            "frequency": 10,
            "reference_count": 20,
            "last_accessed": self._days_ago(30),
            "level": "L2",
        }
        result = apply_scoring_rules(record)
        assert result["score"] == 0.0
        assert result["transition"] == "expire"
        assert result["next_level"] is None

    def test_hard_expiry_beyond_30_days(self):
        """31일 이상 미접근도 하드 만료."""
        record = {
            "frequency": 10,
            "reference_count": 20,
            "last_accessed": self._days_ago(60),
            "level": "L3",
        }
        result = apply_scoring_rules(record)
        assert result["transition"] == "expire"
        assert result["score"] == 0.0

    def test_no_hard_expiry_at_29_days(self):
        """29일 미접근 → 하드 만료 미적용 (점수 기반 판단)."""
        record = {
            "frequency": 10,
            "reference_count": 20,
            "last_accessed": self._days_ago(29),
            "level": "L1",
        }
        result = apply_scoring_rules(record)
        assert result["score"] > 0.0
        assert result["transition"] != "expire" or result["score"] < EXPIRY_CONDITIONS["min_score"]

    # ── last_accessed 형식 테스트 ──

    def test_last_accessed_as_date_object(self):
        """last_accessed가 date 객체일 때도 정상 동작."""
        record = {
            "frequency": 5,
            "reference_count": 5,
            "last_accessed": date.today(),
            "level": "L1",
        }
        result = apply_scoring_rules(record)
        assert "score" in result
        assert "transition" in result

    def test_last_accessed_as_datetime_object(self):
        """last_accessed가 datetime 객체일 때도 정상 동작."""
        record = {
            "frequency": 5,
            "reference_count": 5,
            "last_accessed": datetime.now(),
            "level": "L1",
        }
        result = apply_scoring_rules(record)
        assert "score" in result

    def test_last_accessed_invalid_type_raises(self):
        """last_accessed가 int 등 파싱 불가한 타입이면 ValueError."""
        record = {
            "frequency": 5,
            "reference_count": 5,
            "last_accessed": 12345,
            "level": "L1",
        }
        with pytest.raises(ValueError):
            apply_scoring_rules(record)

    # ── 레코드 불변성 테스트 ──

    def test_original_record_not_mutated(self):
        """apply_scoring_rules는 원본 딕셔너리를 변경하지 않는다."""
        record = {
            "frequency": 5,
            "reference_count": 5,
            "last_accessed": self._today(),
            "level": "L1",
        }
        original_keys = set(record.keys())
        apply_scoring_rules(record)
        assert set(record.keys()) == original_keys
        assert "score" not in record

    # ── 기본값 처리 ──

    def test_missing_frequency_defaults_to_zero(self):
        """frequency 키 없을 때 0으로 기본 처리."""
        record = {
            "reference_count": 10,
            "last_accessed": self._today(),
            "level": "L1",
        }
        result = apply_scoring_rules(record)
        assert result["score"] is not None

    def test_missing_level_defaults_to_l1(self):
        """level 키 없을 때 L1로 기본 처리."""
        record = {
            "frequency": 5,
            "reference_count": 5,
            "last_accessed": self._today(),
        }
        result = apply_scoring_rules(record)
        assert result["next_level"] in ("L1", "L2", None)


# ================================================================
# 상수 정합성 테스트
# ================================================================


class TestConstants:
    """상수 정의 정합성 검증."""

    def test_promotion_threshold_l1_lt_l2(self):
        """L1→L2 임계값이 L2→L3 임계값보다 낮아야 한다."""
        assert PROMOTION_THRESHOLDS["L1_TO_L2"] < PROMOTION_THRESHOLDS["L2_TO_L3"]

    def test_expiry_min_score_below_l1_threshold(self):
        """만료 min_score가 L1→L2 승급 임계값보다 낮아야 한다."""
        assert EXPIRY_CONDITIONS["min_score"] < PROMOTION_THRESHOLDS["L1_TO_L2"]

    def test_score_weights_sum_to_one(self):
        """가중치 합계 = 1.0."""
        assert sum(SCORE_WEIGHTS.values()) == pytest.approx(1.0)
