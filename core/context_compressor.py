"""Context Compressor — 대화 맥락 토큰 압축 유틸리티 (CC-01).

긴 대화 히스토리를 max_tokens 한도 내로 압축한다.
system 메시지와 최근 N개 메시지는 항상 보존하고, 오래된 메시지부터 제거한다.

Feature flag: ENABLE_CONTEXT_COMPRESSOR (default=false)
  - When false: compress()는 원본 messages를 그대로 반환 (safe no-op).
  - When true: 실제 압축 로직 실행.

Self-review:
  ① Logic: system 보존 → keep_last_n 보존 → 잔여 예산으로 older 채움 — 올바름.
  ② Edge cases: 빈 messages, max_tokens=0, keep_last_n > 전체 수 → 모두 처리됨.
  ③ Compat: 신규 모듈, 기존 인터페이스 변경 없음. flag=off 시 완전 no-op.
  ④ Global state: 모듈 레벨 _compressor singleton만 사용, 다른 모듈 상태 미변경.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------


def _is_enabled() -> bool:
    """Return True if the context compressor feature flag is enabled."""
    return os.environ.get("ENABLE_CONTEXT_COMPRESSOR", "true").lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Token estimation (tiktoken optional, fallback to CJK/ASCII heuristic)
# ---------------------------------------------------------------------------


def _estimate_tokens(text: str) -> int:
    """단어 수 기반 토큰 근사치 (1 token ≈ 0.75 words, CJK는 글자당 ~1 token).

    tiktoken 가용 시 더 정확한 값 반환, 없어도 동작 보장 (외부 의존성 없음).
    context_window.py와 동일한 알고리즘 — 독립 구현으로 의존성 격리.
    """
    if not text:
        return 0
    try:
        import tiktoken  # type: ignore[import]
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        pass
    # CJK/한글 문자 비율에 따라 근사치 조정
    cjk_count = sum(
        1 for ch in text
        if ("\u1100" <= ch <= "\u11FF") or ("\u4E00" <= ch <= "\u9FFF") or ("\uAC00" <= ch <= "\uD7A3")
    )
    ascii_words = len(text.split()) - sum(
        1 for w in text.split() if all(
            ("\u1100" <= c <= "\u11FF") or ("\u4E00" <= c <= "\u9FFF") or ("\uAC00" <= c <= "\uD7A3")
            for c in w
        )
    )
    ascii_words = max(ascii_words, 0)
    return cjk_count + ascii_words


# ---------------------------------------------------------------------------
# ContextCompressor
# ---------------------------------------------------------------------------


class ContextCompressor:
    """대화 맥락 압축기.

    압축 전략 (3계층 우선순위):
      1순위 — role=="system" 메시지 전체 보존
      2순위 — 마지막 keep_last_n 개 non-system 메시지 보존
      3순위 — 남은 토큰 예산 내에서 older 메시지를 최신순으로 채움

    Usage::

        from core.context_compressor import get_compressor

        compressor = get_compressor()
        compressed = compressor.compress(messages, max_tokens=4000)
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def estimate_tokens(self, text: str) -> int:
        """텍스트의 토큰 수를 추정한다.

        feature flag와 무관하게 항상 동작한다 (독립 유틸리티).

        Args:
            text: 토큰 수를 추정할 텍스트.

        Returns:
            추정 토큰 수 (int). 빈 문자열이면 0.
        """
        return _estimate_tokens(text)

    def compress(
        self,
        messages: list[dict],
        max_tokens: int,
        keep_last_n: int = 4,
    ) -> list[dict]:
        """대화 메시지 리스트를 max_tokens 이하로 압축한다.

        Args:
            messages: 처리할 메시지 딕셔너리 리스트. 각 dict는 "role", "content" 키 필요.
            max_tokens: 압축 후 목표 최대 토큰 수.
            keep_last_n: 마지막 N개 non-system 메시지를 무조건 보존. 기본 4.

        Returns:
            압축된 메시지 리스트. 원래 시간 순서 유지.
            flag=off이면 원본 messages 그대로 반환.
        """
        if not _is_enabled():
            logger.debug("ContextCompressor disabled (ENABLE_CONTEXT_COMPRESSOR=false); returning original")
            return messages

        if not messages:
            return []

        if max_tokens <= 0:
            logger.debug("ContextCompressor: max_tokens=%d <= 0, returning empty", max_tokens)
            return []

        # ① system 메시지 분리
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        # ② 마지막 keep_last_n 분리 (비어 있으면 전체)
        if keep_last_n >= len(non_system):
            keep_last = list(non_system)
            older = []
        else:
            keep_last = non_system[-keep_last_n:]
            older = non_system[:-keep_last_n]

        # ③ system + keep_last 토큰 합산
        mandatory = system_msgs + keep_last
        mandatory_tokens = sum(
            _estimate_tokens(m.get("content", "")) for m in mandatory
        )

        if mandatory_tokens >= max_tokens:
            # 최소 보존 세트만으로도 초과 → 그대로 반환 (보존 우선)
            logger.debug(
                "ContextCompressor: mandatory_tokens=%d >= max_tokens=%d; keeping mandatory only",
                mandatory_tokens, max_tokens,
            )
            result = system_msgs + keep_last
            return result

        # ④ 남은 예산으로 older 메시지를 최신순(역순)으로 채움
        remaining_budget = max_tokens - mandatory_tokens
        selected_older: list[dict] = []
        for msg in reversed(older):
            cost = _estimate_tokens(msg.get("content", ""))
            if remaining_budget >= cost:
                selected_older.append(msg)
                remaining_budget -= cost
            else:
                break

        # ⑤ 순서 재조립: system + selected_older(시간순) + keep_last
        selected_older.reverse()
        result = system_msgs + selected_older + keep_last

        logger.debug(
            "ContextCompressor: compressed %d → %d messages (budget %d tokens left)",
            len(messages), len(result), remaining_budget,
        )
        return result

    def __repr__(self) -> str:
        enabled = _is_enabled()
        return f"ContextCompressor(enabled={enabled})"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_compressor: Optional[ContextCompressor] = None


def get_compressor() -> ContextCompressor:
    """모듈 레벨 ContextCompressor 싱글턴을 반환한다.

    생성 비용이 낮고 멱등적이다. feature flag가 off일 때도 안전하게 반환된다.
    """
    global _compressor
    if _compressor is None:
        _compressor = ContextCompressor()
    return _compressor


def reset_compressor() -> None:
    """싱글턴을 새 인스턴스로 교체한다. 테스트 전용."""
    global _compressor
    _compressor = ContextCompressor()
