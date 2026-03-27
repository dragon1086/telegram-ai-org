"""
Telethon 리스너 유틸리티 — min_id 기반 cross-contamination 방지 헬퍼.

사용법:
    helper = TelethonListenerHelper(client)
    await helper.record_min_id(chat_entity)          # 리스너 시작 전 반드시 호출
    handler = helper.make_handler(chat_entity, collected, stop_flag)
    client.add_event_handler(handler, events.NewMessage(chats=chat_entity))
    ...
    client.remove_event_handler(handler, events.NewMessage(chats=chat_entity))
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class CollectedMessage:
    """Telethon 핸들러가 수집한 봇 메시지 단위."""

    bot: str
    text: str
    ts: float = field(default_factory=time.time)


class TelethonListenerHelper:
    """채팅방별 min_id를 독립 관리하는 Telethon 이벤트 리스너 헬퍼.

    여러 채팅방 또는 여러 시나리오에 걸쳐 메시지 수집을 수행할 때
    이전 메시지가 새 수집 세션에 섞이는 cross-contamination 을 방지한다.

    동작 원리
    ---------
    1. ``record_min_id()`` 로 리스너 활성화 직전의 최신 메시지 ID 를 기록한다.
    2. ``make_handler()`` 가 반환하는 핸들러는 ``event.message.id <= min_id``
       조건에 해당하는 메시지를 무조건 skip 한다.
    3. ``_min_ids`` dict 로 채팅방별 min_id 를 독립 관리하므로,
       동일 클라이언트로 여러 채팅방을 동시에 구독해도 오염이 발생하지 않는다.
    """

    def __init__(self, client: Any) -> None:
        """
        Parameters
        ----------
        client:
            Telethon ``TelegramClient`` 인스턴스.
        """
        self._client = client
        # chat_id(int) → min_id(int) 매핑.  record_min_id() 호출 전에는 0.
        self._min_ids: dict[int, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def record_min_id(self, chat_entity: Any) -> int:
        """리스너 활성화 직전 채팅방의 최신 메시지 ID 를 기록한다.

        반드시 ``client.add_event_handler()`` 호출 *이전* 에 await 해야 한다.
        이미 기록된 채팅방이라도 재호출 시 최신 ID 로 갱신된다.

        Returns
        -------
        int
            기록된 min_id 값 (채팅방이 비어 있으면 0).
        """
        chat_id = _resolve_chat_id(chat_entity)
        latest = await self._client.get_messages(chat_entity, limit=1)
        min_id: int = latest[0].id if latest else 0
        self._min_ids[chat_id] = min_id
        logger.debug("min_id recorded: chat_id=%s, min_id=%s", chat_id, min_id)
        return min_id

    def get_min_id(self, chat_entity: Any) -> int:
        """현재 기록된 min_id 를 반환한다.  기록이 없으면 0."""
        return self._min_ids.get(_resolve_chat_id(chat_entity), 0)

    def make_handler(
        self,
        chat_entity: Any,
        collected: list[CollectedMessage],
        stop_flag: list[bool],
        *,
        on_message: Callable[..., Awaitable[None]] | None = None,
        bot_only: bool = True,
    ) -> Callable[..., Awaitable[None]]:
        """min_id 필터가 내장된 Telethon 이벤트 핸들러를 반환한다.

        Parameters
        ----------
        chat_entity:
            구독 중인 채팅방 entity.  ``record_min_id()`` 에 전달한 것과 동일해야 한다.
        collected:
            수집 결과를 append 할 list.  핸들러가 직접 append 한다.
        stop_flag:
            ``[False]`` 형태의 1-원소 list.  ``True`` 로 바꾸면 핸들러가 즉시 중단된다.
        on_message:
            커스텀 비동기 콜백 ``async (event, collected) -> None``.
            None 이면 기본 동작(봇 메시지만 수집)을 사용한다.
        bot_only:
            True(기본)이면 ``sender.bot == True`` 인 메시지만 수집한다.
            on_message 가 지정된 경우에는 이 플래그를 무시한다.

        Returns
        -------
        Callable
            Telethon ``add_event_handler()`` 에 전달 가능한 async callable.
        """
        chat_id = _resolve_chat_id(chat_entity)
        min_id = self._min_ids.get(chat_id, 0)
        # --- min_id guard: record_min_id() 미호출 시 경고 ---
        if min_id == 0 and chat_id not in self._min_ids:
            logger.warning(
                "[TelethonListenerHelper] make_handler() 가 record_min_id() 없이 호출되었습니다. "
                "cross-contamination 위험: 이전 메시지가 수집될 수 있습니다. "
                "chat_id=%s — 리스너 시작 전 반드시 await helper.record_min_id(chat_entity) 를 호출하세요.",
                chat_id,
            )

        # --- 기본 수집 콜백 (bot_only 모드) ----------------------------------
        async def _default_collect(event: Any, _c: list[CollectedMessage]) -> None:
            sender = await event.get_sender()
            if bot_only and not (sender and getattr(sender, "bot", False)):
                return
            text = getattr(event.message, "text", None) or ""
            if not text:
                return
            _c.append(
                CollectedMessage(
                    bot=getattr(sender, "username", "unknown"),
                    text=text,
                )
            )

        _collect = on_message if on_message is not None else _default_collect

        # --- min_id 필터를 wrapping 한 실제 핸들러 ---------------------------
        async def handler(
            event: Any,
            _c: list[CollectedMessage] = collected,
            _s: list[bool] = stop_flag,
            _mid: int = min_id,
            _cid: int = chat_id,
        ) -> None:
            # 1. 수집 중단 플래그
            if _s[0]:
                return
            # 2. min_id 필터 — 초기화 이전 메시지는 무조건 skip
            if event.message.id <= _mid:
                logger.debug(
                    "min_id filter skip: chat_id=%s, msg_id=%s <= min_id=%s",
                    _cid,
                    event.message.id,
                    _mid,
                )
                return
            # 3. 수집 콜백 호출
            await _collect(event, _c)

        return handler

    def reset(self, chat_entity: Any | None = None) -> None:
        """기록된 min_id 를 초기화한다.

        Parameters
        ----------
        chat_entity:
            None 이면 모든 채팅방 초기화, 지정하면 해당 채팅방만 초기화.
        """
        if chat_entity is None:
            self._min_ids.clear()
        else:
            self._min_ids.pop(_resolve_chat_id(chat_entity), None)


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _resolve_chat_id(chat_entity: Any) -> int:
    """Telethon entity 또는 raw int 에서 chat_id 를 추출한다."""
    if isinstance(chat_entity, int):
        return chat_entity
    # Telethon Entity 객체 (Channel, Chat, User 등)
    raw = getattr(chat_entity, "id", None)
    if raw is not None:
        return int(raw)
    # 문자열 정수
    try:
        return int(str(chat_entity))
    except (ValueError, TypeError) as exc:
        raise TypeError(
            f"chat_entity 에서 chat_id 를 추출할 수 없음: {chat_entity!r}"
        ) from exc
