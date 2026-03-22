"""대화 히스토리 컨텍스트 윈도우 유틸리티.

PM이 작업 배분 판단 시 직전 메시지만 보지 않고 최근 N개 대화를 참고할 수 있도록
히스토리를 수집·정제·직렬화한다.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# ── 환경변수 기반 기본값 ──────────────────────────────────────────────────────
MAX_HISTORY_MESSAGES: int = int(os.environ.get("MAX_HISTORY_MESSAGES", "20"))
MAX_HISTORY_TOKENS: int = int(os.environ.get("MAX_HISTORY_TOKENS", "6000"))


def _estimate_tokens(text: str) -> int:
    """단어 수 기반 토큰 근사치 (1 token ≈ 0.75 words, CJK는 글자당 ~1 token).

    tiktoken 없이도 동작하도록 단순 근사 사용.
    tiktoken 가용 시 더 정확하지만, 의존성 추가 없이 동작해야 함.
    """
    try:
        import tiktoken  # type: ignore[import]
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        pass
    # CJK/한글 문자 비율에 따라 근사치 조정
    # 유니코드 범위: CJK (\u4E00-\u9FFF), 한글 완성형 (\uAC00-\uD7A3), 한글 자모 (\u1100-\u11FF)
    cjk_count = sum(
        1 for ch in text
        if ("\u1100" <= ch <= "\u11FF") or ("\u4E00" <= ch <= "\u9FFF") or ("\uAC00" <= ch <= "\uD7A3")
    )
    # 영문/숫자 단어 토큰 (공백 기준)
    ascii_words = len(text.split()) - sum(
        1 for w in text.split() if all(
            ("\u1100" <= c <= "\u11FF") or ("\u4E00" <= c <= "\u9FFF") or ("\uAC00" <= c <= "\uD7A3")
            for c in w
        )
    )
    ascii_words = max(ascii_words, 0)
    return cjk_count + ascii_words


def build_context_window(
    messages: list[dict],
    *,
    max_messages: int = MAX_HISTORY_MESSAGES,
    max_tokens: int = MAX_HISTORY_TOKENS,
    current_message: str = "",
) -> list[dict]:
    """최근 N개 메시지 슬라이딩 윈도우를 적용하고, 토큰 한도 초과 시 오래된 것부터 제거.

    Args:
        messages: ContextDB.get_conversation_messages() 반환값 (timestamp DESC 정렬).
                  각 dict는 최소 "role", "content", "timestamp" 키를 가짐.
        max_messages: 포함할 최대 메시지 수 (환경변수 MAX_HISTORY_MESSAGES).
        max_tokens: 컨텍스트 전체 토큰 한도 (환경변수 MAX_HISTORY_TOKENS).
        current_message: 현재 처리 중인 메시지 (토큰 예산에서 제외하기 위한 참고용).

    Returns:
        시간순(오래된 것 먼저) 정렬된 메시지 dict 리스트.
        빈 히스토리면 [] 반환.
    """
    if not messages:
        return []

    # ── 중복 제거: 동일 (role, content) 쌍은 최신 1건만 유지 ──
    # 동일 메시지가 여러 봇에 의해 각자의 msg_id로 중복 저장될 수 있으므로,
    # msg_id 대신 (role, content 앞 200자) 기준으로 디덥 후 슬라이딩 윈도우 적용.
    seen_keys: set[tuple] = set()
    deduped: list[dict] = []
    for msg in messages:  # DESC 정렬이므로 최신 우선
        content_snippet = (msg.get("content") or "")[:200]
        role = msg.get("role", "")
        key = (role, content_snippet)
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(msg)

    # DB 반환은 DESC(최신 먼저) — N개 슬라이싱 후 오래된 순으로 재정렬
    recent = deduped[:max_messages]
    # 토큰 한도 적용: 최신 것부터 추가하다가 한도 초과 시 중단
    token_budget = max_tokens - _estimate_tokens(current_message)
    token_budget = max(token_budget, 200)  # 최소 200 토큰 보장

    selected: list[dict] = []
    for msg in recent:  # recent는 최신 우선
        content = msg.get("content", "")
        cost = _estimate_tokens(content)
        if cost > token_budget:
            break
        selected.append(msg)
        token_budget -= cost

    # 시간순(오래된 것 먼저) 재정렬
    selected.sort(key=lambda m: m.get("timestamp", ""))
    return selected


def format_history_for_prompt(messages: list[dict]) -> str:
    """role별 구조화된 메시지 목록을 프롬프트 삽입용 문자열로 직렬화.

    형식:
        [CONTEXT]
        [user] 안녕하세요
        [assistant] 안녕하세요! 무엇을 도와드릴까요?
        ...
        [/CONTEXT]

    Args:
        messages: build_context_window() 반환값 (시간순 정렬).

    Returns:
        직렬화된 문자열. 빈 리스트면 빈 문자열 반환.
    """
    if not messages:
        return ""

    lines: list[str] = ["[CONTEXT]"]
    for msg in messages:
        role = msg.get("role", "user")
        # DB role: "user" | "bot" | "system" — 프롬프트 표준화
        if role == "bot":
            role = "assistant"
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        # 너무 긴 개별 메시지는 잘라냄 (단일 메시지 최대 1500자)
        if len(content) > 1500:
            content = content[:1497] + "..."
        lines.append(f"[{role}] {content}")
    lines.append("[/CONTEXT]")

    # 본문이 [CONTEXT]와 [/CONTEXT]만 있으면(실제 메시지 없음) 빈 문자열 반환
    if len(lines) <= 2:
        return ""
    return "\n".join(lines)
