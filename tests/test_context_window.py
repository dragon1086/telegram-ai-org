"""context_window.py 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_window import (
    _estimate_tokens,
    build_context_window,
    format_history_for_prompt,
)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _make_msg(content: str, role: str = "user", ts: str = "2026-03-22T00:00:00", msg_id: int = 1) -> dict:
    return {"role": role, "content": content, "timestamp": ts, "msg_id": msg_id, "is_bot": role == "bot"}


# ── _estimate_tokens ──────────────────────────────────────────────────────────

def test_estimate_tokens_empty():
    assert _estimate_tokens("") == 0


def test_estimate_tokens_ascii():
    result = _estimate_tokens("hello world foo bar")
    assert result > 0


def test_estimate_tokens_cjk():
    result = _estimate_tokens("안녕하세요")
    assert result >= 5  # CJK 각 글자 ~1 token


# ── build_context_window ──────────────────────────────────────────────────────

def test_build_context_window_empty():
    assert build_context_window([]) == []


def test_build_context_window_normal():
    msgs = [
        _make_msg("최신 메시지", ts="2026-03-22T10:00:00", msg_id=3),
        _make_msg("중간 메시지", ts="2026-03-22T09:00:00", msg_id=2),
        _make_msg("오래된 메시지", ts="2026-03-22T08:00:00", msg_id=1),
    ]
    result = build_context_window(msgs, max_messages=10, max_tokens=5000)
    assert len(result) == 3
    # 오래된 것 먼저 (시간순)
    assert result[0]["msg_id"] == 1
    assert result[-1]["msg_id"] == 3


def test_build_context_window_max_messages():
    msgs = [
        _make_msg(f"msg{i}", ts=f"2026-03-22T{10-i:02d}:00:00", msg_id=i)
        for i in range(20)
    ]
    result = build_context_window(msgs, max_messages=5, max_tokens=50000)
    assert len(result) <= 5


def test_build_context_window_token_limit():
    """토큰 한도 초과 시 이전 메시지 제외."""
    long_content = "가나다라마바사아자차카타파하" * 50  # ~700 chars
    msgs = [
        _make_msg(long_content, ts=f"2026-03-22T{i:02d}:00:00", msg_id=i)
        for i in range(10)
    ]
    # max_tokens=200으로 제한 — 긴 메시지 최대 1개만 들어갈 것
    result = build_context_window(msgs, max_messages=10, max_tokens=200)
    assert len(result) <= 2  # 토큰 한도로 절단됨


def test_build_context_window_edge_50plus():
    """50턴 이상 히스토리에서도 토큰 한도 초과 방지."""
    msgs = [
        _make_msg(f"message number {i}", ts=f"2026-01-{(i % 28) + 1:02d}T00:00:00", msg_id=i)
        for i in range(60)
    ]
    result = build_context_window(msgs, max_messages=10, max_tokens=2000)
    # max_messages=10 제한 먼저 적용
    assert len(result) <= 10
    # 토큰 합계 추정치 확인
    from core.context_window import _estimate_tokens
    total = sum(_estimate_tokens(m["content"]) for m in result)
    assert total <= 2000 + 50  # 약간의 마진 허용


def test_build_context_window_sorted_ascending():
    """반환값이 시간순(오래된 것 먼저) 정렬인지 확인."""
    msgs = [
        _make_msg("c", ts="2026-03-22T03:00:00", msg_id=3),
        _make_msg("a", ts="2026-03-22T01:00:00", msg_id=1),
        _make_msg("b", ts="2026-03-22T02:00:00", msg_id=2),
    ]
    result = build_context_window(msgs, max_messages=10, max_tokens=9999)
    assert [m["msg_id"] for m in result] == [1, 2, 3]


# ── format_history_for_prompt ─────────────────────────────────────────────────

def test_format_history_empty():
    assert format_history_for_prompt([]) == ""


def test_format_history_basic():
    msgs = [
        _make_msg("안녕하세요", role="user"),
        _make_msg("안녕하세요! 뭘 도와드릴까요?", role="bot"),
    ]
    result = format_history_for_prompt(msgs)
    assert result.startswith("[CONTEXT]")
    assert result.endswith("[/CONTEXT]")
    assert "[user] 안녕하세요" in result
    assert "[assistant] 안녕하세요!" in result


def test_format_history_bot_role_renamed():
    """role=bot 은 assistant 로 변환되는지 확인."""
    msgs = [_make_msg("응답", role="bot")]
    result = format_history_for_prompt(msgs)
    assert "[assistant]" in result
    assert "[bot]" not in result


def test_format_history_long_content_truncated():
    """개별 메시지 500자 초과 시 잘라냄."""
    long = "x" * 600
    msgs = [_make_msg(long)]
    result = format_history_for_prompt(msgs)
    # 잘린 내용이 포함돼야 하고, 500자를 크게 초과해선 안 됨
    assert "..." in result
    # [user] 접두어 포함이므로 504자 이하
    for line in result.split("\n"):
        if line.startswith("[user]"):
            assert len(line) <= 510


def test_format_history_empty_content_skipped():
    """content가 빈 메시지는 건너뜀."""
    msgs = [
        _make_msg("", role="user"),
        _make_msg("실제 메시지", role="user"),
    ]
    result = format_history_for_prompt(msgs)
    # 실제 메시지는 포함
    assert "실제 메시지" in result
    # 빈 메시지 라인 없음
    lines = [l for l in result.split("\n") if l.startswith("[user]")]
    assert all(l.strip() != "[user]" for l in lines)


def test_format_history_only_empty_returns_empty():
    """모든 메시지 content가 비어있으면 빈 문자열 반환."""
    msgs = [_make_msg("", role="user"), _make_msg("   ", role="bot")]
    result = format_history_for_prompt(msgs)
    assert result == ""
