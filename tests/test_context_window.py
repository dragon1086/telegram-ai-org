"""core/context_window.py 단위 테스트."""
from __future__ import annotations

import pytest

from core.context_window import (
    MAX_HISTORY_MESSAGES,
    MAX_HISTORY_TOKENS,
    build_context_window,
    estimate_tokens,
    format_history_for_prompt,
)


# ── estimate_tokens ──────────────────────────────────────────────────────────

def test_estimate_tokens_basic():
    assert estimate_tokens("hello") >= 1


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 1  # max(1, 0//4)


def test_estimate_tokens_long():
    text = "a" * 400
    assert estimate_tokens(text) == 100


def test_estimate_tokens_korean():
    # 한글 4글자 → 1 token
    assert estimate_tokens("가나다라") == 1


# ── build_context_window ─────────────────────────────────────────────────────

def _make_msgs(count: int, content_len: int = 20) -> list[dict]:
    """최신 순(DESC) 메시지 리스트 생성 헬퍼."""
    return [
        {
            "content": f"{'x' * content_len} msg{i}",
            "role": "user" if i % 2 == 0 else "bot",
            "is_bot": i % 2 != 0,
            "timestamp": f"2026-01-01T00:{i:02d}:00",
        }
        for i in range(count - 1, -1, -1)  # 최신 → 오래된 순
    ]


def test_build_context_window_empty():
    result = build_context_window([])
    assert result == []


def test_build_context_window_normal():
    msgs = _make_msgs(5)
    result = build_context_window(msgs, max_messages=10, max_tokens=5000)
    assert len(result) == 5
    # 반환 결과는 시간 오름차순이어야 함
    timestamps = [r["timestamp"] for r in result]
    assert timestamps == sorted(timestamps)


def test_build_context_window_max_messages_limit():
    msgs = _make_msgs(20)
    result = build_context_window(msgs, max_messages=5, max_tokens=50000)
    assert len(result) <= 5


def test_build_context_window_token_limit():
    # 각 메시지 400자 → 100 tokens
    msgs = _make_msgs(10, content_len=400)
    result = build_context_window(msgs, max_messages=10, max_tokens=250)
    # 100 tokens/msg → 최대 2개 포함 가능
    assert len(result) <= 2


def test_build_context_window_token_limit_zero():
    # 토큰 한도가 극히 작으면 한 개도 안 들어갈 수 있음
    msgs = _make_msgs(5, content_len=400)
    result = build_context_window(msgs, max_messages=5, max_tokens=10)
    assert len(result) == 0


def test_build_context_window_single_message():
    msgs = _make_msgs(1)
    result = build_context_window(msgs, max_messages=10, max_tokens=5000)
    assert len(result) == 1


def test_build_context_window_50_turns():
    """50턴 이상에서 토큰 한도 초과 방지 엣지 케이스."""
    msgs = _make_msgs(50, content_len=100)
    result = build_context_window(msgs, max_messages=10, max_tokens=2000)
    # max_messages 상한으로 10개 이하
    assert len(result) <= 10
    # 총 토큰이 2000 이하인지 검증
    total = sum(estimate_tokens(str(m.get("content", ""))) for m in result)
    assert total <= 2000


# ── format_history_for_prompt ────────────────────────────────────────────────

def test_format_history_empty():
    result = format_history_for_prompt([])
    assert result == ""


def test_format_history_wraps_context_tags():
    msgs = _make_msgs(3)
    result = format_history_for_prompt(msgs, max_messages=10, max_tokens=5000)
    assert result.startswith("[CONTEXT]")
    assert result.strip().endswith("[/CONTEXT]")


def test_format_history_role_labels():
    msgs = [
        {"content": "안녕하세요", "role": "user", "is_bot": False, "timestamp": "2026-01-01T10:00:00"},
        {"content": "반갑습니다", "role": "bot", "is_bot": True, "timestamp": "2026-01-01T10:01:00"},
    ]
    result = format_history_for_prompt(msgs, max_messages=10, max_tokens=5000)
    assert "사용자:" in result
    assert "PM:" in result


def test_format_history_chronological_order():
    msgs = _make_msgs(5)
    result = format_history_for_prompt(msgs, max_messages=10, max_tokens=5000)
    lines = [ln for ln in result.splitlines() if ln.startswith("[2026")]
    timestamps_in_output = [ln[1:17] for ln in lines]
    assert timestamps_in_output == sorted(timestamps_in_output)


def test_format_history_graceful_fallback_no_content():
    # content 키가 없는 메시지도 crash 없이 처리
    msgs = [{"role": "user", "is_bot": False, "timestamp": "2026-01-01T10:00:00"}]
    result = format_history_for_prompt(msgs, max_messages=10, max_tokens=5000)
    assert "[CONTEXT]" in result


def test_format_history_token_overflow_not_crash():
    """토큰 초과 케이스에서 빈 문자열 반환 (crash 없음)."""
    msgs = _make_msgs(5, content_len=400)
    result = format_history_for_prompt(msgs, max_messages=5, max_tokens=10)
    # 토큰 초과로 빈 윈도우 → 빈 문자열
    assert result == ""


def test_format_history_content_truncated_at_300():
    msgs = [
        {
            "content": "A" * 500,
            "role": "user",
            "is_bot": False,
            "timestamp": "2026-01-01T10:00:00",
        }
    ]
    result = format_history_for_prompt(msgs, max_messages=10, max_tokens=5000)
    # 각 메시지 내용이 300자로 잘려야 함
    assert "A" * 301 not in result
    assert "A" * 300 in result


# ── 환경변수 기본값 확인 ────────────────────────────────────────────────────

def test_defaults_are_reasonable():
    assert MAX_HISTORY_MESSAGES >= 5
    assert MAX_HISTORY_TOKENS >= 500
