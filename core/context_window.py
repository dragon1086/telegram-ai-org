"""대화 히스토리 컨텍스트 창 유틸리티 — PM 작업 배분 판단에 prior context 주입."""
from __future__ import annotations

import os
from typing import Sequence

# 환경변수로 튜닝 가능한 기본값
MAX_HISTORY_MESSAGES: int = int(os.environ.get("MAX_HISTORY_MESSAGES", "10"))
MAX_HISTORY_TOKENS: int = int(os.environ.get("MAX_HISTORY_TOKENS", "2000"))


def estimate_tokens(text: str) -> int:
    """단어 수 기반 토큰 근사치 (영/한 혼합 고려).

    영어 기준 ~0.75 words/token, 한국어는 글자당 ~0.5 token.
    단순 근사: len(text) // 4 를 사용 (문자 수 / 4 ≈ 토큰 수).
    """
    return max(1, len(text) // 4)


def build_context_window(
    messages: Sequence[dict],
    *,
    max_messages: int = MAX_HISTORY_MESSAGES,
    max_tokens: int = MAX_HISTORY_TOKENS,
) -> list[dict]:
    """최근 N개 메시지 중 토큰 합산이 max_tokens 이하인 슬라이딩 윈도우를 반환.

    Args:
        messages: 최신 메시지가 앞에 오는 리스트 (get_conversation_messages 기본 정렬과 동일).
                  각 dict는 최소 'content', 'role', 'timestamp' 키를 포함해야 한다.
        max_messages: 포함할 최대 메시지 수.
        max_tokens: 전체 토큰 합산 상한선.

    Returns:
        시간순(오래된 것 먼저) 정렬된 메시지 리스트.
    """
    if not messages:
        return []

    # max_messages 슬라이스 먼저 적용 (최신 N개 선택)
    candidates = list(messages[:max_messages])

    # 토큰 합산 초과 시 오래된 것부터 제거
    total_tokens = 0
    selected: list[dict] = []
    for msg in candidates:
        content = str(msg.get("content", ""))
        t = estimate_tokens(content)
        if total_tokens + t > max_tokens:
            break
        selected.append(msg)
        total_tokens += t

    # get_conversation_messages는 DESC 정렬이므로 시간순(ASC)으로 뒤집어 반환
    selected.reverse()
    return selected


def format_history_for_prompt(
    messages: Sequence[dict],
    *,
    max_messages: int = MAX_HISTORY_MESSAGES,
    max_tokens: int = MAX_HISTORY_TOKENS,
) -> str:
    """대화 이력을 [CONTEXT]...[/CONTEXT] 블록 문자열로 직렬화.

    빈 이력이면 빈 문자열 반환 (graceful fallback).
    role이 'user'이면 '사용자', 'bot'/'assistant'이면 'PM'으로 표시.
    """
    windowed = build_context_window(messages, max_messages=max_messages, max_tokens=max_tokens)
    if not windowed:
        return ""

    lines: list[str] = []
    for msg in windowed:
        role_raw = str(msg.get("role", "user")).lower()
        is_bot = bool(msg.get("is_bot", False))
        if is_bot or role_raw in {"bot", "assistant"}:
            speaker = "PM"
        else:
            speaker = "사용자"
        ts = str(msg.get("timestamp", ""))[:16]  # YYYY-MM-DDTHH:MM
        content = str(msg.get("content", "")).strip().replace("\n", " ")
        lines.append(f"[{ts}] {speaker}: {content[:300]}")

    body = "\n".join(lines)
    return f"[CONTEXT]\n{body}\n[/CONTEXT]"
