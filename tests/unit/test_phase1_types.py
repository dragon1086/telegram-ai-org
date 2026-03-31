"""Phase 1 단위 테스트 — core.types 모듈.

테스트 대상: core/types.py (TypeAlias, TypedDict, Literal 정의)
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 타입 별칭 존재 확인
# ---------------------------------------------------------------------------

class TestTypeAliases:
    def test_task_id_is_str_alias(self):
        from core.types import TaskID
        assert TaskID is str

    def test_org_id_is_str_alias(self):
        from core.types import OrgID
        assert OrgID is str

    def test_bot_handle_is_str_alias(self):
        from core.types import BotHandle
        assert BotHandle is str

    def test_engine_type_literal_exists(self):
        """EngineType Literal 타입이 정의되어 있어야 한다."""
        import typing

        from core.types import EngineType
        args = typing.get_args(EngineType)
        assert "claude-code" in args
        assert "codex" in args
        assert "gemini-cli" in args

    def test_task_status_literal_exists(self):
        import typing

        from core.types import TaskStatusLiteral
        args = typing.get_args(TaskStatusLiteral)
        expected = {"pending", "in_progress", "done", "failed", "cancelled"}
        assert expected == set(args)


# ---------------------------------------------------------------------------
# MessageEnvelope TypedDict
# ---------------------------------------------------------------------------

class TestMessageEnvelope:
    def test_create_message_envelope_happy_path(self):
        from core.types import MessageEnvelope
        msg: MessageEnvelope = {
            "to": "dev",
            "from_": "pm",
            "task_id": "T-001",
            "content": "안녕하세요",
            "msg_type": "task",
            "timestamp": "2026-03-29T00:00:00Z",
        }
        assert msg["to"] == "dev"
        assert msg["from_"] == "pm"
        assert msg["task_id"] == "T-001"

    def test_message_envelope_has_required_keys(self):
        from core.types import MessageEnvelope
        required = {"to", "from_", "task_id", "content", "msg_type", "timestamp"}
        annotations = MessageEnvelope.__annotations__
        assert required.issubset(set(annotations.keys()))

    def test_message_envelope_content_can_be_empty_string(self):
        """content 빈 문자열도 허용돼야 한다 (엣지 케이스)."""
        from core.types import MessageEnvelope
        msg: MessageEnvelope = {
            "to": "dev",
            "from_": "pm",
            "task_id": "",
            "content": "",
            "msg_type": "ping",
            "timestamp": "2026-03-29T00:00:00Z",
        }
        assert msg["content"] == ""

    def test_message_envelope_task_id_is_str(self):
        import typing

        from core.types import MessageEnvelope
        hints = typing.get_type_hints(MessageEnvelope)
        assert hints["task_id"] is str


# ---------------------------------------------------------------------------
# BotState TypedDict
# ---------------------------------------------------------------------------

class TestBotState:
    def test_create_bot_state_happy_path(self):
        from core.types import BotState
        state: BotState = {
            "bot_id": "dev_bot",
            "org_id": "dev",
            "is_alive": True,
            "last_seen": "2026-03-29T00:00:00Z",
            "engine": "claude-code",
        }
        assert state["is_alive"] is True
        assert state["engine"] == "claude-code"

    def test_bot_state_has_required_keys(self):
        from core.types import BotState
        required = {"bot_id", "org_id", "is_alive", "last_seen", "engine"}
        annotations = BotState.__annotations__
        assert required.issubset(set(annotations.keys()))

    def test_bot_state_is_alive_false(self):
        """is_alive = False 도 유효한 상태."""
        from core.types import BotState
        state: BotState = {
            "bot_id": "dead_bot",
            "org_id": "ops",
            "is_alive": False,
            "last_seen": "2026-03-29T00:00:00Z",
            "engine": "gemini-cli",
        }
        assert state["is_alive"] is False

    def test_bot_state_engine_values(self):
        """BotState.engine 필드 타입이 EngineType Literal임을 확인."""
        import typing

        from core.types import BotState, EngineType
        hints = typing.get_type_hints(BotState)
        # EngineType 이 engine 필드 어노테이션 타입과 같아야 한다
        assert hints["engine"] == EngineType
