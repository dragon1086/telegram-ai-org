"""P2P 봇 간 직접 메시지 교환 — PM 경유 없는 협업 채널.

봇들이 PM을 거치지 않고 서로 직접 통신할 수 있게 해주는 허브.
완료 알림, 결과 공유, 협업 요청, 브로드캐스트에 활용.

사용 예:
    messenger = P2PMessenger(bus=bus)
    messenger.register("dev_bot", my_handler)
    await messenger.send("analyst_bot", "dev_bot", {"type": "result", "data": "..."})
    await messenger.notify_task_done("dev_bot", "T-001", "파일 3개 생성 완료")
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Any

from loguru import logger

from core.message_bus import MessageBus, Event, EventType


@dataclass
class P2PMessage:
    """P2P 직접 메시지."""

    from_bot: str
    to_bot: str  # "*" = 브로드캐스트
    payload: dict
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


BotHandler = Callable[[P2PMessage], Awaitable[None]]


class P2PMessenger:
    """봇 간 직접 메시지 교환 허브.

    - PM 경유 없이 봇끼리 직접 통신
    - 완료 알림, 결과 공유, 협업 요청에 활용
    - MessageBus P2P_MESSAGE 이벤트와 통합
    - 메시지 로그 보관 (최근 200개)
    """

    _LOG_LIMIT = 200

    def __init__(self, bus: MessageBus | None = None) -> None:
        self._bus = bus
        self._handlers: dict[str, list[BotHandler]] = {}
        self._message_log: list[P2PMessage] = []
        if bus:
            bus.subscribe(EventType.P2P_MESSAGE, self._on_bus_event)

    # ------------------------------------------------------------------
    # 등록

    def register(self, bot_name: str, handler: BotHandler) -> None:
        """봇 핸들러 등록. 같은 봇에 여러 핸들러 허용."""
        self._handlers.setdefault(bot_name, []).append(handler)
        logger.info(f"P2P 등록: {bot_name}")

    def unregister(self, bot_name: str) -> None:
        """봇 등록 해제."""
        self._handlers.pop(bot_name, None)
        logger.info(f"P2P 해제: {bot_name}")

    # ------------------------------------------------------------------
    # 송신

    async def send(self, from_bot: str, to_bot: str, payload: dict) -> P2PMessage:
        """특정 봇에게 직접 메시지 전송."""
        msg = P2PMessage(from_bot=from_bot, to_bot=to_bot, payload=payload)
        self._log(msg)
        await self._deliver(msg)
        await self._publish_bus_event(msg)
        logger.debug(f"P2P 전송: {from_bot} → {to_bot} [{msg.msg_id}] type={payload.get('type','?')}")
        return msg

    async def broadcast(self, from_bot: str, payload: dict) -> list[P2PMessage]:
        """등록된 모든 봇(발신자 제외)에게 브로드캐스트."""
        msgs: list[P2PMessage] = []
        for bot_name in list(self._handlers.keys()):
            if bot_name == from_bot:
                continue
            msg = await self.send(from_bot, bot_name, payload)
            msgs.append(msg)
        logger.info(f"P2P 브로드캐스트: {from_bot} → {len(msgs)}개 봇")
        return msgs

    async def notify_task_done(
        self,
        from_bot: str,
        task_id: str,
        result_summary: str,
        notify_bots: list[str] | None = None,
    ) -> list[P2PMessage]:
        """태스크 완료 후 관련 봇에게 자동 알림.

        notify_bots가 None이면 등록된 모든 봇에게 브로드캐스트.
        """
        payload = {
            "type": "task_done",
            "task_id": task_id,
            "summary": result_summary[:500],
            "from": from_bot,
        }
        if notify_bots:
            msgs = []
            for bot in notify_bots:
                msgs.append(await self.send(from_bot, bot, payload))
            return msgs
        return await self.broadcast(from_bot, payload)

    async def request_collab(
        self,
        from_bot: str,
        to_bot: str,
        task: str,
        context: str = "",
    ) -> P2PMessage:
        """다른 봇에게 협업 요청 전송."""
        return await self.send(
            from_bot,
            to_bot,
            {
                "type": "collab_request",
                "task": task,
                "context": context[:400],
                "from": from_bot,
            },
        )

    # ------------------------------------------------------------------
    # 내부

    async def _deliver(self, msg: P2PMessage) -> None:
        """메시지를 핸들러에 전달. 에러는 격리."""
        if msg.to_bot == "*":
            targets: list[BotHandler] = [
                h for bot, handlers in self._handlers.items()
                if bot != msg.from_bot
                for h in handlers
            ]
        else:
            targets = self._handlers.get(msg.to_bot, [])

        if not targets:
            logger.debug(f"P2P: 핸들러 없음 — {msg.to_bot} (등록된 봇: {list(self._handlers.keys())})")
            return

        for handler in targets:
            try:
                await handler(msg)
            except Exception:
                logger.exception(f"P2P 핸들러 에러: {msg.to_bot}/{handler.__name__}")

    async def _publish_bus_event(self, msg: P2PMessage) -> None:
        if not self._bus:
            return
        await self._bus.publish(Event(
            type=EventType.P2P_MESSAGE,
            source=msg.from_bot,
            target=msg.to_bot,
            data={
                "msg_id": msg.msg_id,
                "to": msg.to_bot,
                "payload": msg.payload,
            },
        ))

    async def _on_bus_event(self, event: Event) -> None:
        """버스 이벤트 → P2P 메시지 변환 (외부 발행 지원)."""
        data = event.data
        to_bot = data.get("to") or event.target
        if not to_bot:
            return
        # 이미 send()를 통해 처리된 메시지는 msg_id로 중복 방지
        msg_id = data.get("msg_id", "")
        if any(m.msg_id == msg_id for m in self._message_log[-20:]):
            return
        msg = P2PMessage(
            from_bot=event.source,
            to_bot=to_bot,
            payload=data.get("payload", {}),
            msg_id=msg_id or str(uuid.uuid4())[:8],
        )
        self._log(msg)
        await self._deliver(msg)

    def _log(self, msg: P2PMessage) -> None:
        self._message_log.append(msg)
        if len(self._message_log) > self._LOG_LIMIT:
            self._message_log = self._message_log[-self._LOG_LIMIT:]

    # ------------------------------------------------------------------
    # 조회

    def list_bots(self) -> list[str]:
        """등록된 봇 목록."""
        return list(self._handlers.keys())

    def message_log(self, limit: int = 50) -> list[dict]:
        """최근 메시지 로그 (요약)."""
        return [
            {
                "msg_id": m.msg_id,
                "from": m.from_bot,
                "to": m.to_bot,
                "type": m.payload.get("type", "?"),
            }
            for m in self._message_log[-limit:]
        ]
