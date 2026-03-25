"""메시지 봉투 — 자연어 표시 레이어와 봇 간 메타데이터 레이어를 분리한다.

봇들이 Telegram 채팅에서 사람처럼 자연스럽게 말하면서도
내부 라우팅 정보(task_id, intent 등)를 안전하게 전달할 수 있게 한다.

사용 예:
    env = MessageEnvelope.wrap(
        content="알겠어, 마케팅 분석 시작할게요.",
        sender_bot="dev_bot",
        intent="TASK_ACCEPT",
        task_id="T-001",
    )
    # Telegram에 표시: "알겠어, 마케팅 분석 시작할게요."
    print(env.to_display())

    # 봇 내부 통신용 (전체 메타데이터 포함)
    wire_data = env.to_wire()
    restored = MessageEnvelope.from_wire(wire_data)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MessageEnvelope:
    """봇 메시지 봉투.

    content: Telegram에 표시되는 자연어 텍스트 (사람이 읽는 부분)
    sender_bot: 발신 봇 ID
    intent: 메시지 의도 (TASK_ACCEPT, COLLAB_REQUEST, DIRECT_REPLY 등)
    task_id: 연관 태스크 ID (없으면 None)
    reply_to: Telegram message_id (없으면 None)
    metadata: 추가 메타데이터 dict (라우팅 정보 등)
    """

    content: str
    sender_bot: str
    intent: str
    task_id: str | None = None
    reply_to: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # 생성

    @classmethod
    def wrap(
        cls,
        content: str,
        sender_bot: str,
        intent: str,
        task_id: str | None = None,
        reply_to: int | None = None,
        **kwargs: Any,
    ) -> "MessageEnvelope":
        """자연어 content + 메타데이터로 봉투 생성."""
        return cls(
            content=content,
            sender_bot=sender_bot,
            intent=intent,
            task_id=task_id,
            reply_to=reply_to,
            metadata=kwargs,
        )

    # ------------------------------------------------------------------
    # 표시 / 직렬화

    def to_display(self) -> str:
        """Telegram에 표시할 자연어 텍스트만 반환 (메타데이터 숨김).

        [TYPE:value] 형식의 레거시 메타데이터 태그를 제거한다.
        """
        return re.sub(r"\[[A-Z_]+:[^\]]*\]", "", self.content).strip()

    def to_wire(self) -> dict[str, Any]:
        """봇 내부 통신용 직렬화 — 전체 메타데이터 포함."""
        return {
            "content": self.content,
            "sender_bot": self.sender_bot,
            "intent": self.intent,
            "task_id": self.task_id,
            "reply_to": self.reply_to,
            "metadata": self.metadata,
        }

    @classmethod
    def from_wire(cls, data: dict[str, Any]) -> "MessageEnvelope":
        """to_wire() 결과에서 복원."""
        return cls(
            content=data["content"],
            sender_bot=data["sender_bot"],
            intent=data["intent"],
            task_id=data.get("task_id"),
            reply_to=data.get("reply_to"),
            metadata=data.get("metadata", {}),
        )

    # ------------------------------------------------------------------
    # 레거시 태그 호환

    @staticmethod
    def extract_legacy_tags(raw_text: str) -> dict[str, str]:
        """기존 [TYPE:value] 형식 태그를 파싱한다 (다중 태그 지원).

        예: '[COLLAB_REQUEST:bot_a] [TEAM:dev]' → {'COLLAB_REQUEST': 'bot_a', 'TEAM': 'dev'}
        태그가 없으면 {} 반환 (graceful fallback).
        """
        pattern = r"\[([A-Z_]+):([^\]]*)\]"
        matches = re.findall(pattern, raw_text)
        return {tag_type: value for tag_type, value in matches}


class EnvelopeManager:
    """DB-backed 봉투 저장/조회 (E2 — DB 경유 라우팅)."""

    def __init__(self, db) -> None:
        # db: ContextDB 인스턴스 (duck typing)
        self._db = db

    async def save(self, message_id: int, envelope: MessageEnvelope) -> None:
        """봉투를 DB에 저장."""
        import json

        import aiosqlite
        wire = envelope.to_wire()
        metadata_json = json.dumps(wire.get("metadata", {}), ensure_ascii=False)
        async with aiosqlite.connect(self._db.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO message_envelopes
                   (telegram_message_id, task_id, metadata)
                   VALUES (?, ?, ?)""",
                (message_id, envelope.task_id, metadata_json),
            )
            await db.commit()

    async def load(self, message_id: int) -> "MessageEnvelope | None":
        """DB에서 봉투 조회. 없으면 None."""
        import json

        import aiosqlite
        async with aiosqlite.connect(self._db.db_path) as db:
            async with db.execute(
                "SELECT task_id, metadata FROM message_envelopes WHERE telegram_message_id = ?",
                (message_id,),
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        task_id, metadata_json = row
        metadata = json.loads(metadata_json) if metadata_json else {}
        return MessageEnvelope(
            content="",
            sender_bot="",
            intent="",
            task_id=task_id,
            metadata=metadata,
        )
