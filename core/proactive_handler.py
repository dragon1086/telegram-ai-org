"""프로액티브 봇 행동 핸들러 — INACTIVITY_DETECTED/DAILY_INSIGHT 이벤트 구독."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.message_bus import MessageBus

from core.message_bus import Event, EventType

logger = logging.getLogger(__name__)


class ProactiveHandler:
    """MessageBus 이벤트를 구독해 프로액티브 메시지를 전송한다."""

    def __init__(self, bus: "MessageBus", bots: dict) -> None:
        self._bus = bus
        self._bots = bots  # {bot_id: bot_config_dict}

    def register(self) -> None:
        self._bus.subscribe(EventType.INACTIVITY_DETECTED, self._on_inactivity)
        self._bus.subscribe(EventType.DAILY_INSIGHT, self._on_daily_insight)

    def _is_within_active_hours(self, bot_id: str) -> bool:
        bot_cfg = self._bots.get(bot_id, {})
        active_hours = bot_cfg.get("active_hours")
        if not active_hours:
            return True  # 미설정 = 항상 활성
        now_hour = datetime.now().hour
        return active_hours.get("start", 0) <= now_hour < active_hours.get("end", 24)

    async def _on_inactivity(self, event: Event) -> None:
        chat_id = event.data.get("chat_id", "")
        bot_id = event.data.get("bot_id", "")
        if bot_id and not self._is_within_active_hours(bot_id):
            logger.debug(f"[Proactive] active_hours 범위 밖, 이벤트 억제: {bot_id}")
            return
        await self._send_proactive_message(
            chat_id, "💭 잠시 조용하네요. 현재 진행 중인 작업이 있으신가요?"
        )

    async def _on_daily_insight(self, event: Event) -> None:
        chat_id = event.data.get("chat_id", "")
        bot_id = event.data.get("bot_id", "")
        if bot_id and not self._is_within_active_hours(bot_id):
            return
        await self._send_proactive_message(chat_id, "📊 오늘의 팀 인사이트를 준비했어요!")

    async def _send_proactive_message(self, chat_id: str, text: str) -> None:
        """실제 Telegram 전송 — 봇 인스턴스 주입 시 오버라이드."""
        logger.info(f"[Proactive] 메시지 전송 → chat={chat_id}: {text}")
