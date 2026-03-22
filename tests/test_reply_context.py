"""reply_to_message 컨텍스트 주입 로직 테스트.

두 시나리오 검증:
1. reply가 있는 메시지 → 발신자 정보 + message_id + 전문이 _replied_context에 포함
2. reply가 없는 일반 메시지 → _replied_context가 빈 문자열
"""

from __future__ import annotations

import pytest


# ------------------------------------------------------------------
# 헬퍼: telegram_relay.py 의 컨텍스트 조립 로직 단위 테스트용 함수
# (실제 Update 객체를 직접 임포트하는 대신, 동일 로직을 분리 검증)
# ------------------------------------------------------------------

def _build_replied_context(
    replied_text: str | None,
    sender_first_name: str | None,
    sender_username: str | None,
    message_id: int | None,
) -> str:
    """telegram_relay.py on_message() 내 _replied_context 조립 로직 재현."""
    if not replied_text:
        return ""
    _reply_from = sender_first_name or sender_username or "bot"
    _reply_msg_id = message_id
    return (
        f"\n\n[답장 대상 메시지]\n"
        f"발신자: {_reply_from} | message_id: {_reply_msg_id}\n"
        f"{replied_text[:2000]}"
    )


def _build_route_replied_to(
    replied_text: str | None,
    sender_first_name: str | None,
    sender_username: str | None,
) -> str | None:
    """telegram_relay.py _route_ctx['replied_to'] 조립 로직 재현."""
    if not replied_text:
        return None
    _reply_sender = sender_first_name or sender_username or "bot"
    return f"[{_reply_sender}] {replied_text[:500]}"


# ------------------------------------------------------------------
# 테스트 케이스
# ------------------------------------------------------------------

class TestRepliedContext:
    def test_reply_with_sender_first_name(self):
        """발신자 first_name이 있으면 포함되어야 함."""
        ctx = _build_replied_context(
            replied_text="안녕하세요, 이것은 봇 답변입니다.",
            sender_first_name="aiorg_pm_bot",
            sender_username=None,
            message_id=12345,
        )
        assert "[답장 대상 메시지]" in ctx
        assert "발신자: aiorg_pm_bot" in ctx
        assert "message_id: 12345" in ctx
        assert "안녕하세요, 이것은 봇 답변입니다." in ctx

    def test_reply_with_username_fallback(self):
        """first_name이 없으면 username으로 fallback."""
        ctx = _build_replied_context(
            replied_text="봇 응답 텍스트",
            sender_first_name=None,
            sender_username="pm_bot_user",
            message_id=999,
        )
        assert "발신자: pm_bot_user" in ctx
        assert "message_id: 999" in ctx

    def test_reply_with_no_sender_info(self):
        """발신자 정보 없으면 'bot' 기본값 사용."""
        ctx = _build_replied_context(
            replied_text="텍스트",
            sender_first_name=None,
            sender_username=None,
            message_id=1,
        )
        assert "발신자: bot" in ctx

    def test_no_reply_returns_empty(self):
        """reply가 없으면 빈 문자열."""
        ctx = _build_replied_context(
            replied_text=None,
            sender_first_name="bot",
            sender_username=None,
            message_id=1,
        )
        assert ctx == ""

    def test_empty_reply_text_returns_empty(self):
        """빈 텍스트이면 빈 문자열."""
        ctx = _build_replied_context(
            replied_text="",
            sender_first_name="bot",
            sender_username=None,
            message_id=1,
        )
        assert ctx == ""

    def test_long_reply_truncated_at_2000(self):
        """2000자 초과 원문은 2000자로 잘려야 함."""
        long_text = "A" * 5000
        ctx = _build_replied_context(
            replied_text=long_text,
            sender_first_name="bot",
            sender_username=None,
            message_id=1,
        )
        # 컨텍스트에 A가 정확히 2000개 포함되어야 함
        a_count = ctx.count("A")
        assert a_count == 2000

    def test_route_ctx_includes_sender_prefix(self):
        """route_ctx replied_to에 발신자 prefix가 붙어야 함."""
        rt = _build_route_replied_to(
            replied_text="라우터용 텍스트",
            sender_first_name="SomeBot",
            sender_username=None,
        )
        assert rt is not None
        assert rt.startswith("[SomeBot]")
        assert "라우터용 텍스트" in rt

    def test_route_ctx_no_reply_returns_none(self):
        """reply가 없으면 None."""
        rt = _build_route_replied_to(
            replied_text=None,
            sender_first_name="bot",
            sender_username=None,
        )
        assert rt is None

    def test_route_ctx_truncated_at_500(self):
        """route_ctx replied_to는 500자로 잘림."""
        long_text = "B" * 1000
        rt = _build_route_replied_to(
            replied_text=long_text,
            sender_first_name="bot",
            sender_username=None,
        )
        assert rt is not None
        # "[bot] " 이후 본문이 500자
        body = rt[len("[bot] "):]
        assert len(body) == 500
