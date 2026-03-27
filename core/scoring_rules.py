"""
scoring_rules.py — L1/L2/L3 메모리 계층 자동 스코어링 및 레벨 전환 규칙

=== Phase 1: 스코어링 공식 및 임계값 상수 정의 ===

■ 점수 산출 공식 (0–100 스케일):
    score = frequency_norm × 0.5
          + reference_count_norm × 0.3
          + recency_decay × 0.2

  · frequency_norm     = min(frequency / FREQUENCY_SCALE, 1.0) × 100
  · reference_norm     = min(reference_count / REFERENCE_SCALE, 1.0) × 100
  · recency_decay      = max(0, 1 − last_accessed_days_ago / RECENCY_DECAY_DAYS) × 100

■ 레벨 승급 임계값:
    L1 → L2  : score ≥ 70
    L2 → L3  : score ≥ 90

■ 만료 조건:
    · score < 30  (점수 미달)
    · last_accessed_days_ago ≥ 30  (장기 미접근 — 하드 만료)

■ 정상화 스케일:
    · FREQUENCY_SCALE  = 10   (빈도 10 이상 → 만점)
    · REFERENCE_SCALE  = 20   (참조 20 이상 → 만점)
    · RECENCY_DECAY_DAYS = 30 (30일 이상 미접근 → 0점)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

# ──────────────────────────────────────────────
# 입력 정규화 스케일
# ──────────────────────────────────────────────
FREQUENCY_SCALE: float = 10.0     # frequency >= 10 → 만점(100)
REFERENCE_SCALE: float = 20.0     # reference_count >= 20 → 만점(100)
RECENCY_DECAY_DAYS: float = 30.0  # 30일 이상 → 0점

# ──────────────────────────────────────────────
# 가중치 (합 = 1.0)
# ──────────────────────────────────────────────
SCORE_WEIGHTS: dict[str, float] = {
    "frequency": 0.5,
    "reference_count": 0.3,
    "recency": 0.2,
}

# ──────────────────────────────────────────────
# 레벨 승급 임계값
# ──────────────────────────────────────────────
PROMOTION_THRESHOLDS: dict[str, float] = {
    "L1_TO_L2": 70.0,   # L1 → L2: score >= 70
    "L2_TO_L3": 90.0,   # L2 → L3: score >= 90
}

# ──────────────────────────────────────────────
# 만료 조건
# ──────────────────────────────────────────────
EXPIRY_CONDITIONS: dict[str, float] = {
    "min_score": 30.0,               # score < 30 → 만료
    "max_days_without_access": 30.0, # 30일 미접근 → 강제 만료
}

VALID_LEVELS: tuple[str, ...] = ("L1", "L2", "L3")

# ──────────────────────────────────────────────
# 현재 레벨 → 승급 시 다음 레벨 매핑
# ──────────────────────────────────────────────
_PROMOTE_MAP: dict[str, str] = {
    "L1": "L2",
    "L2": "L3",
    "L3": "L3",  # 최상위 — 유지
}


# ============================================================
# 공개 API
# ============================================================


def calculate_score(
    frequency: float,
    reference_count: float,
    last_accessed_days_ago: float,
) -> float:
    """태스크/메모리 항목의 중요도 점수를 0–100 범위로 산출한다.

    Args:
        frequency: 태스크 완료 횟수(빈도). 원시 카운트.
        reference_count: 참조된 횟수. 원시 카운트.
        last_accessed_days_ago: 마지막 접근으로부터 경과 일수 (>= 0).

    Returns:
        float: 가중 합산 점수, 범위 [0.0, 100.0], 소수점 4자리 반올림.

    Examples:
        >>> calculate_score(10, 20, 0)   # 모든 지표 최대
        100.0
        >>> calculate_score(0, 0, 30)    # 모든 지표 최소
        0.0
        >>> calculate_score(10, 0, 30)   # frequency만 기여
        50.0
    """
    if last_accessed_days_ago < 0:
        raise ValueError(f"last_accessed_days_ago must be >= 0, got {last_accessed_days_ago}")

    frequency_score = min(frequency / FREQUENCY_SCALE, 1.0) * 100.0
    reference_score = min(reference_count / REFERENCE_SCALE, 1.0) * 100.0
    recency_score = max(0.0, 1.0 - last_accessed_days_ago / RECENCY_DECAY_DAYS) * 100.0

    score = (
        frequency_score * SCORE_WEIGHTS["frequency"]
        + reference_score * SCORE_WEIGHTS["reference_count"]
        + recency_score * SCORE_WEIGHTS["recency"]
    )
    return round(min(score, 100.0), 4)


def get_level_transition(
    current_level: Literal["L1", "L2", "L3"],
    score: float,
) -> Literal["promote", "stay", "expire"]:
    """현재 레벨과 점수를 바탕으로 레벨 전환 방향을 반환한다.

    승급 규칙:
        L1 → L2  : score >= PROMOTION_THRESHOLDS['L1_TO_L2'] (70)
        L2 → L3  : score >= PROMOTION_THRESHOLDS['L2_TO_L3'] (90)
        L3        : 최상위 레벨이므로 승급 없음 (stay)

    만료 규칙 (승급 판단보다 우선):
        모든 레벨: score < EXPIRY_CONDITIONS['min_score'] (30) → expire

    Args:
        current_level: 현재 메모리 계층 ('L1', 'L2', 'L3').
        score: calculate_score() 반환값 (0–100).

    Returns:
        Literal['promote', 'stay', 'expire']

    Raises:
        ValueError: current_level이 유효하지 않을 때.

    Examples:
        >>> get_level_transition("L1", 70.0)
        'promote'
        >>> get_level_transition("L1", 50.0)
        'stay'
        >>> get_level_transition("L2", 15.0)
        'expire'
    """
    if current_level not in VALID_LEVELS:
        raise ValueError(
            f"current_level must be one of {VALID_LEVELS}, got '{current_level}'"
        )

    # 만료 조건: 점수 미달 (하드 만료는 apply_scoring_rules에서 처리)
    if score < EXPIRY_CONDITIONS["min_score"]:
        return "expire"

    # 승급 조건
    if current_level == "L1" and score >= PROMOTION_THRESHOLDS["L1_TO_L2"]:
        return "promote"
    if current_level == "L2" and score >= PROMOTION_THRESHOLDS["L2_TO_L3"]:
        return "promote"

    return "stay"


def apply_scoring_rules(task_record: dict) -> dict:
    """태스크 레코드 전체에 스코어링 파이프라인을 적용한다.

    task_record 필수 키:
        - frequency (int|float)    : 태스크 완료 빈도
        - reference_count (int|float): 참조 횟수
        - last_accessed (str|date|datetime): ISO 날짜 문자열 또는 date/datetime 객체
        - level (str)              : 현재 레벨 ('L1', 'L2', 'L3')

    하드 만료 규칙 (점수 계산과 무관하게 독립 적용):
        last_accessed 경과일 >= EXPIRY_CONDITIONS['max_days_without_access'] (30일)
        → score=0.0, transition='expire', next_level=None

    Args:
        task_record: 태스크 또는 메모리 항목 딕셔너리.

    Returns:
        dict: 다음 키가 추가/갱신된 레코드 사본.
            - 'score' (float)         : 산출된 중요도 점수 (0–100)
            - 'transition' (str)      : 'promote' | 'stay' | 'expire'
            - 'next_level' (str|None) : 전환 후 레벨 ('L2', 'L3') 또는 None(만료)

    Raises:
        ValueError: last_accessed 파싱 실패 또는 level이 유효하지 않을 때.

    Examples:
        >>> import datetime
        >>> rec = {
        ...     "frequency": 10, "reference_count": 20,
        ...     "last_accessed": datetime.date.today().isoformat(),
        ...     "level": "L2",
        ... }
        >>> result = apply_scoring_rules(rec)
        >>> result["transition"]
        'promote'
        >>> result["next_level"]
        'L3'
    """
    record = dict(task_record)

    # ── last_accessed 파싱 ──
    raw_date = record.get("last_accessed")
    if isinstance(raw_date, datetime):
        last_accessed_date = raw_date.date()
    elif isinstance(raw_date, date):
        last_accessed_date = raw_date
    elif isinstance(raw_date, str):
        try:
            last_accessed_date = datetime.fromisoformat(raw_date).date()
        except ValueError as exc:
            raise ValueError(
                f"Cannot parse last_accessed '{raw_date}' as ISO date: {exc}"
            ) from exc
    else:
        raise ValueError(
            f"last_accessed must be str, date, or datetime — got {type(raw_date).__name__!r}"
        )

    today = date.today()
    days_ago = (today - last_accessed_date).days

    # ── 하드 만료: 장기 미접근 ──
    if days_ago >= EXPIRY_CONDITIONS["max_days_without_access"]:
        record["score"] = 0.0
        record["transition"] = "expire"
        record["next_level"] = None
        return record

    # ── 점수 산출 ──
    score = calculate_score(
        frequency=float(record.get("frequency", 0)),
        reference_count=float(record.get("reference_count", 0)),
        last_accessed_days_ago=float(days_ago),
    )
    record["score"] = score

    # ── 레벨 전환 결정 ──
    current_level: str = record.get("level", "L1")
    transition = get_level_transition(current_level, score)  # type: ignore[arg-type]
    record["transition"] = transition

    # ── next_level 매핑 ──
    if transition == "expire":
        record["next_level"] = None
    elif transition == "promote":
        record["next_level"] = _PROMOTE_MAP.get(current_level, current_level)
    else:  # stay
        record["next_level"] = current_level

    return record
