"""Rate-limited Telegram 메시지 전송 레이어.

에이전트별 디바운스로 STATUS_UPDATE 메시지 빈도를 제어하고,
RESULT/TASK_ASSIGN 같은 중요 메시지는 즉시 전송.

feature flag: USE_DISPLAY_LIMITER 환경변수 (기본: true)
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from enum import Enum

from loguru import logger

_METADATA_TAG_RE = re.compile(r'\[[A-Z_]+:[^\]]*\]')


class MessagePriority(Enum):
    IMMEDIATE = "immediate"
    NORMAL = "normal"


@dataclass
class PendingEdit:
    progress_msg: object
    text: str
    timestamp: float


class DisplayLimiter:
    """Telegram 메시지 전송 래퍼 — 디바운스 + 우선순위."""

    def __init__(self, debounce_sec: float = 5.0, enabled: bool = True) -> None:
        self._debounce_sec = debounce_sec
        self._enabled = enabled
        self._pending: dict[str, PendingEdit] = {}
        self._flush_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        for key, pending in list(self._pending.items()):
            try:
                await pending.progress_msg.edit_text(pending.text)
            except Exception as e:
                logger.warning(f"stop flush 실패 [{key}]: {e}")
        self._pending.clear()

    async def send_reply(
        self,
        message: object,
        text: str,
        priority: MessagePriority = MessagePriority.IMMEDIATE,
        reply_to_message_id: int | None = None,
    ) -> object:
        text = _METADATA_TAG_RE.sub('', text).strip()
        kwargs = {}
        if reply_to_message_id is not None:
            kwargs["reply_to_message_id"] = reply_to_message_id
        try:
            return await message.reply_text(text, **kwargs)
        except Exception as e:
            if reply_to_message_id is not None and self._should_retry_without_reply(e):
                logger.warning(f"reply 대상 메시지를 찾지 못해 일반 응답으로 재시도: {e}")
                return await message.reply_text(text)
            raise

    async def edit_progress(self, progress_msg: object, text: str,
                            agent_id: str | None = None) -> None:
        if not self._enabled or agent_id is None:
            await progress_msg.edit_text(text)
            return
        self._pending[agent_id] = PendingEdit(progress_msg, text, time.time())

    async def send_to_chat(
        self,
        bot: object,
        chat_id: int,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> object:
        text = _METADATA_TAG_RE.sub('', text).strip()
        kwargs = {"chat_id": chat_id, "text": text}
        if reply_to_message_id is not None:
            kwargs["reply_to_message_id"] = reply_to_message_id
        try:
            return await bot.send_message(**kwargs)
        except Exception as e:
            if reply_to_message_id is not None and self._should_retry_without_reply(e):
                logger.warning(f"reply 대상 메시지를 찾지 못해 일반 전송으로 재시도: {e}")
                return await bot.send_message(chat_id=chat_id, text=text)
            raise

    @staticmethod
    def _should_retry_without_reply(error: Exception) -> bool:
        return "Message to be replied not found" in str(error)

    async def _flush_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self._debounce_sec)
            except asyncio.CancelledError:
                return
            now = time.time()
            to_flush = [
                (key, pending) for key, pending in self._pending.items()
                if now - pending.timestamp >= self._debounce_sec
            ]
            for key, pending in to_flush:
                try:
                    await pending.progress_msg.edit_text(pending.text)
                except Exception as e:
                    logger.warning(f"flush 실패 [{key}]: {e}")
                del self._pending[key]
