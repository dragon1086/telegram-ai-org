"""OrgMessage — AI 조직 메시지 스키마."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


MsgType = Literal["assign", "report", "query", "ack", "complete", "broadcast"]


class OrgMessage(BaseModel):
    """AI 조직 내 구조화된 메시지."""

    to: str | list[str]  # "@dev_bot" | ["@dev_bot", "@analyst_bot"] | "ALL"
    from_: str           # "@pm_bot"
    task_id: str         # "T001"
    msg_type: MsgType
    content: str
    context_ref: str | None = None  # context DB 슬롯 ID
    attachments: list[str] = []

    @field_validator("from_", "to")
    @classmethod
    def validate_bot_handle(cls, v: str | list[str]) -> str | list[str]:
        """봇 핸들 형식 검증 (@handle 또는 ALL)."""
        if isinstance(v, list):
            for handle in v:
                cls._check_handle(handle)
            return v
        cls._check_handle(v)
        return v

    @staticmethod
    def _check_handle(handle: str) -> None:
        if handle == "ALL":
            return
        if not re.match(r"^@\w+$", handle):
            raise ValueError(f"유효하지 않은 봇 핸들: {handle!r} (@handle 또는 ALL 형식 필요)")

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        if not re.match(r"^T[-\w]+$", v):
            raise ValueError(f"유효하지 않은 태스크 ID: {v!r} (T001 또는 T-org-001 형식 필요)")
        return v

    def is_addressed_to(self, bot_handle: str) -> bool:
        """이 메시지가 특정 봇에게 전달되는지 확인."""
        if self.to == "ALL":
            return True
        if isinstance(self.to, list):
            return bot_handle in self.to
        return self.to == bot_handle

    def to_telegram_text(self) -> str:
        """Telegram 전송용 텍스트 포맷."""
        to_str = self.to if isinstance(self.to, str) else ", ".join(self.to)
        header = f"[TO: {to_str} | FROM: {self.from_} | TASK: {self.task_id} | TYPE: {self.msg_type}]"
        parts = [header, self.content]
        if self.context_ref:
            parts.append(f"[CTX: {self.context_ref}]")
        if self.attachments:
            parts.append(f"[FILES: {', '.join(self.attachments)}]")
        return "\n".join(parts)

    @classmethod
    def parse_telegram_text(cls, text: str) -> "OrgMessage | None":
        """Telegram 텍스트에서 OrgMessage 파싱."""
        header_match = re.search(
            r"\[TO: (.+?) \| FROM: (.+?) \| TASK: (.+?) \| TYPE: (.+?)\]",
            text,
        )
        if not header_match:
            return None

        to_raw, from_, task_id, msg_type = header_match.groups()
        to: str | list[str] = (
            [t.strip() for t in to_raw.split(",")]
            if "," in to_raw
            else to_raw.strip()
        )

        # 헤더 이후 내용 추출
        content_start = header_match.end()
        content = text[content_start:].strip()

        # CTX, FILES 파싱
        context_ref = None
        ctx_match = re.search(r"\[CTX: (.+?)\]", content)
        if ctx_match:
            context_ref = ctx_match.group(1)
            content = content.replace(ctx_match.group(0), "").strip()

        attachments = []
        files_match = re.search(r"\[FILES: (.+?)\]", content)
        if files_match:
            attachments = [f.strip() for f in files_match.group(1).split(",")]
            content = content.replace(files_match.group(0), "").strip()

        return cls(
            to=to,
            from_=from_,
            task_id=task_id,
            msg_type=msg_type,  # type: ignore[arg-type]
            content=content,
            context_ref=context_ref,
            attachments=attachments,
        )
