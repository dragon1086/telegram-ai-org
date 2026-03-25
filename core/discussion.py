"""DiscussionManager — ContextDB 기반 부서 간 토론 관리."""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from loguru import logger

from core.context_db import ContextDB
from core.message_bus import Event, EventType, MessageBus

ENABLE_DISCUSSION_PROTOCOL = os.environ.get("ENABLE_DISCUSSION_PROTOCOL", "0") == "1"

VALID_MSG_TYPES = {"PROPOSE", "COUNTER", "OPINION", "REVISE", "DECISION"}


class DiscussionManager:
    """부서 간 토론을 관리하는 매니저. 모든 상태는 ContextDB에 저장."""

    def __init__(
        self,
        context_db: ContextDB,
        telegram_send_func: Callable[[int, str], Awaitable[None]],
        bus: MessageBus | None = None,
        org_id: str = "pm",
    ):
        self._db = context_db
        self._send = telegram_send_func
        self._bus = bus
        self._org_id = org_id
        self._disc_counter = 0

    def _next_discussion_id(self) -> str:
        self._disc_counter += 1
        return f"D-{self._org_id}-{self._disc_counter:03d}"

    async def start_discussion(
        self,
        topic: str,
        initial_proposal: str,
        from_dept: str,
        participants: list[str],
        parent_task_id: str | None = None,
        chat_id: int | None = None,
    ) -> dict:
        """새 토론 시작. ContextDB에 생성 + 첫 PROPOSE 메시지 추가."""
        disc_id = self._next_discussion_id()
        disc = await self._db.create_discussion(
            discussion_id=disc_id,
            topic=topic,
            participants=participants,
            parent_task_id=parent_task_id,
        )

        # 첫 번째 PROPOSE 메시지 등록
        await self._db.add_discussion_message(
            discussion_id=disc_id,
            msg_type="PROPOSE",
            topic=topic,
            content=initial_proposal,
            from_dept=from_dept,
            round_num=1,
        )

        # 텔레그램 알림
        if chat_id is not None:
            parts_str = ", ".join(participants)
            msg = (
                f"💬 토론 시작: {topic}\n"
                f"ID: {disc_id}\n"
                f"참여: {parts_str}\n\n"
                f"[PROPOSE:{topic}|{initial_proposal[:300]}]"
            )
            await self._send(chat_id, msg)

        # 프로세스 내 이벤트
        if self._bus:
            await self._bus.publish(Event(
                type=EventType.DISCUSSION_STARTED,
                source=self._org_id,
                data={"discussion_id": disc_id, "topic": topic, "participants": participants},
            ))

        logger.info(f"[Discussion] 토론 시작: {disc_id} — {topic}")
        return disc

    async def add_message(
        self,
        discussion_id: str,
        msg_type: str,
        content: str,
        from_dept: str,
        chat_id: int | None = None,
    ) -> dict | None:
        """토론에 메시지 추가. 수렴 감지 + 라운드 제한 체크."""
        if msg_type not in VALID_MSG_TYPES:
            logger.warning(f"[Discussion] 잘못된 메시지 유형: {msg_type}")
            return None

        disc = await self._db.get_discussion(discussion_id)
        if not disc:
            logger.warning(f"[Discussion] 토론 없음: {discussion_id}")
            return None

        if disc["status"] != "open":
            logger.warning(f"[Discussion] 토론 종료됨: {discussion_id} ({disc['status']})")
            return None

        # DECISION은 PM만 가능
        if msg_type == "DECISION":
            return await self.force_decision(discussion_id, content, chat_id)

        current_round = disc["current_round"]
        topic = disc["topic"]

        msg = await self._db.add_discussion_message(
            discussion_id=discussion_id,
            msg_type=msg_type,
            topic=topic,
            content=content,
            from_dept=from_dept,
            round_num=current_round,
        )

        # 프로세스 내 이벤트
        if self._bus:
            await self._bus.publish(Event(
                type=EventType.DISCUSSION_MESSAGE,
                source=from_dept,
                data={"discussion_id": discussion_id, "msg_type": msg_type,
                       "content": content[:200], "round": current_round},
            ))

        # 수렴 체크
        converged = await self._db.check_convergence(discussion_id)
        if converged:
            await self._db.update_discussion_status(discussion_id, "converging")
            if self._bus:
                await self._bus.publish(Event(
                    type=EventType.DISCUSSION_CONVERGED,
                    source=self._org_id,
                    data={"discussion_id": discussion_id, "round": current_round},
                ))
            if chat_id is not None:
                await self._send(chat_id, f"✅ 토론 {discussion_id} 수렴 — PM 결정 대기 중")
            logger.info(f"[Discussion] 수렴 감지: {discussion_id} round={current_round}")

        return msg

    async def advance_round(self, discussion_id: str, chat_id: int | None = None) -> int:
        """라운드 진행. max_rounds 초과 시 타임아웃."""
        disc = await self._db.get_discussion(discussion_id)
        if not disc or disc["status"] != "open":
            return -1

        if disc["current_round"] >= disc["max_rounds"]:
            await self._db.update_discussion_status(discussion_id, "timed_out")
            if self._bus:
                await self._bus.publish(Event(
                    type=EventType.DISCUSSION_TIMED_OUT,
                    source=self._org_id,
                    data={"discussion_id": discussion_id, "rounds": disc["max_rounds"]},
                ))
            if chat_id is not None:
                await self._send(chat_id,
                    f"⏰ 토론 {discussion_id} 시간 초과 ({disc['max_rounds']}라운드) — PM 강제 결정 필요")
            logger.info(f"[Discussion] 타임아웃: {discussion_id}")
            return -1

        new_round = await self._db.advance_discussion_round(discussion_id)
        if chat_id is not None:
            await self._send(chat_id, f"🔄 토론 {discussion_id} 라운드 {new_round} 시작")
        return new_round

    async def force_decision(
        self, discussion_id: str, decision: str, chat_id: int | None = None
    ) -> dict | None:
        """PM이 토론을 강제 종료하고 결정."""
        disc = await self._db.get_discussion(discussion_id)
        if not disc:
            return None

        topic = disc["topic"]
        current_round = disc["current_round"]

        # DECISION 메시지 기록
        await self._db.add_discussion_message(
            discussion_id=discussion_id,
            msg_type="DECISION",
            topic=topic,
            content=decision,
            from_dept=self._org_id,
            round_num=current_round,
        )

        updated = await self._db.update_discussion_status(
            discussion_id, "decided", decision=decision
        )

        if self._bus:
            await self._bus.publish(Event(
                type=EventType.DISCUSSION_DECIDED,
                source=self._org_id,
                data={"discussion_id": discussion_id, "decision": decision[:200]},
            ))

        if chat_id is not None:
            await self._send(chat_id,
                f"🔨 토론 {discussion_id} 결정\n\n[DECISION:{topic}|{decision[:300]}]")

        logger.info(f"[Discussion] 결정: {discussion_id} — {decision[:80]}")
        return updated

    async def get_active_discussions(self) -> list[dict]:
        """진행 중인 토론 목록."""
        return await self._db.get_active_discussions()
