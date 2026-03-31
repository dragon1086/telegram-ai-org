"""core.eval_context — 평가 컨텍스트 세션 주입 모듈.

봇이 자신이 평가받는 중임을 인지하도록 세션 프롬프트에 평가 컨텍스트를 주입합니다.

Feature flag: ENABLE_EVAL_CONTEXT (default=1 — .env 기준)
  - true/1 : 세션 프롬프트에 평가 컨텍스트 문구를 주입합니다.
  - false/0 : no-op (빈 문자열 반환).

평가 활성화 조건 (둘 다 충족 필요):
  1. ENABLE_EVAL_CONTEXT=1
  2. 아래 중 하나:
     - EVAL_SESSION=1   : 특정 세션만 평가 활성화
     - IS_EVAL_RUN=1    : CI/eval 러너에서 명시적 활성화
     - EVAL_ALWAYS=1    : 세션 구분 없이 항상 평가 인지 주입 (상시 운영용)

Self-review:
  ① Logic: feature flag + 3-way 세션 조건 → 어느 하나 충족 시 주입.
  ② Edge cases: 플래그 비활성화/환경변수 없음 → 빈 문자열, 부작용 없음.
  ③ Compat: EVAL_ALWAYS 추가 — 기존 EVAL_SESSION/IS_EVAL_RUN 동작 그대로.
  ④ Global state: 없음.
"""
from __future__ import annotations

import os

from loguru import logger

# ---------------------------------------------------------------------------
# 피처 플래그
# ---------------------------------------------------------------------------

ENABLE_EVAL_CONTEXT: bool = (
    os.environ.get("ENABLE_EVAL_CONTEXT", "false").lower() in ("true", "1", "yes")
)
"""True일 때 평가 컨텍스트 주입이 활성화됩니다."""

# ---------------------------------------------------------------------------
# 평가 인지 문구
# ---------------------------------------------------------------------------

_EVAL_NOTICE = """\
[평가 모드] 현재 세션은 품질 평가 중입니다.
응답 품질·정확도·완결성이 측정됩니다.
평소와 동일한 방식으로 응답하되, 평가 기준을 인지한 상태로 최선을 다하세요."""


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------


def is_eval_session() -> bool:
    """현재 세션이 평가 세션인지 확인합니다.

    아래 조건 중 하나라도 충족되면 True:
    - EVAL_SESSION=1   : 특정 세션 평가 활성화
    - IS_EVAL_RUN=1    : CI/eval 러너 명시 활성화
    - EVAL_ALWAYS=1    : 세션 구분 없이 상시 평가 인지 주입
    """
    _true_vals = ("1", "true", "yes")
    return (
        os.environ.get("EVAL_SESSION", "").strip() in _true_vals
        or os.environ.get("IS_EVAL_RUN", "").strip() in _true_vals
        or os.environ.get("EVAL_ALWAYS", "").strip() in _true_vals
    )


def inject_eval_context(extra_notice: str = "") -> str:
    """평가 컨텍스트 문구를 반환합니다.

    ENABLE_EVAL_CONTEXT=true 이고 is_eval_session()이 True인 경우에만 문구를 반환합니다.
    그 외에는 빈 문자열을 반환합니다.

    Args:
        extra_notice: 추가로 붙일 사용자 정의 공지 (선택).

    Returns:
        주입할 컨텍스트 문자열. 비활성화 시 "".
    """
    if not ENABLE_EVAL_CONTEXT:
        logger.debug("eval_context: ENABLE_EVAL_CONTEXT=false → no-op")
        return ""

    if not is_eval_session():
        logger.debug("eval_context: EVAL_SESSION/IS_EVAL_RUN/EVAL_ALWAYS 미설정 → no-op")
        return ""

    notice = _EVAL_NOTICE
    if extra_notice:
        notice = notice + "\n" + extra_notice.strip()

    logger.info("eval_context: 평가 모드 컨텍스트 주입")
    return notice
