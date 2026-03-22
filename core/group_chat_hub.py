"""GroupChatHub — 멀티봇 그룹채팅 자율 참가 허브.

설계 원칙:
- 각 봇이 공통 그룹방 메시지를 구독하고 자체 판단으로 응답 여부를 결정
- PM 봇이 TurnManager를 통해 발언 순서를 조율 (턴-테이킹)
- GroupChatContext로 그룹방 대화 이력을 봇들이 공유

사용 예:
    hub = GroupChatHub(send_to_group=my_send_func)
    hub.register_participant("engineering", engineering_speak_callback, domain_keywords=["코드","버그"])
    hub.register_participant("product", product_speak_callback, domain_keywords=["기획","PRD"])

    # 그룹 메시지 수신 시
    await hub.on_group_message("@engineering 이번 주 작업 보고해줘", from_user="user")

    # 주간 회의 시작
    await hub.start_meeting("주간 스탠드업", participants=["engineering","product","growth"])
"""
from __future__ import annotations

import asyncio
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from loguru import logger


# ── 상수 ─────────────────────────────────────────────────────────────────────

TURN_TIMEOUT_SEC = 45       # 봇 응답 대기 최대 시간
MEETING_TURN_GAP_SEC = 2    # 발언 간 간격 (연속 발언 방지)
MAX_CONTEXT_MESSAGES = 50   # 그룹 컨텍스트 최대 보존 메시지 수


# ── 데이터 클래스 ──────────────────────────────────────────────────────────────

@dataclass
class GroupMessage:
    """그룹방 메시지 레코드."""
    from_bot: str           # 발신 봇 ID (사람 발언은 "user")
    text: str
    ts: float = field(default_factory=time.time)


@dataclass
class ParticipantInfo:
    """그룹방 참가 봇 정보."""
    bot_id: str
    speak_callback: Callable[[str, list[GroupMessage]], Awaitable[str | None]]
    """speak_callback(message, context) → 응답 문자열 or None(발언 안 함)"""
    domain_keywords: list[str] = field(default_factory=list)
    """이 키워드가 메시지에 포함될 때 응답 우선 고려."""


# ── 그룹 컨텍스트 ──────────────────────────────────────────────────────────────

class GroupChatContext:
    """그룹방 대화 이력 공유 저장소.

    인메모리 큐(deque) 기반. 봇들이 동일 GroupChatHub 인스턴스를 공유하면
    모든 봇이 같은 컨텍스트를 볼 수 있다.
    """

    def __init__(self, max_messages: int = MAX_CONTEXT_MESSAGES) -> None:
        self._messages: deque[GroupMessage] = deque(maxlen=max_messages)
        self._lock = asyncio.Lock()

    async def add(self, msg: GroupMessage) -> None:
        async with self._lock:
            self._messages.append(msg)

    async def recent(self, n: int = 10) -> list[GroupMessage]:
        async with self._lock:
            return list(self._messages)[-n:]

    async def snapshot(self) -> list[GroupMessage]:
        async with self._lock:
            return list(self._messages)

    def __len__(self) -> int:
        return len(self._messages)


# ── TurnManager ────────────────────────────────────────────────────────────────

class TurnManager:
    """봇 발언 순서(턴) 조율.

    - start_meeting(): 회의 시작, 순서대로 각 봇에게 발언 요청
    - request_turn(): 봇이 자율적으로 발언 의사 표시 (큐에 추가)
    - PM이 큐를 처리하여 Telegram 그룹방에 전달
    """

    def __init__(
        self,
        send_to_group: Callable[[str], Awaitable[None]],
        context: GroupChatContext,
    ) -> None:
        self._send = send_to_group
        self._context = context
        self._queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self._active_meeting: bool = False
        self._lock = asyncio.Lock()
        self._processor_task: asyncio.Task | None = None

    def start_processor(self) -> None:
        """백그라운드 큐 프로세서 시작."""
        if self._processor_task is None or self._processor_task.done():
            self._processor_task = asyncio.create_task(self._process_queue())

    async def request_turn(self, bot_id: str, content: str) -> None:
        """봇이 발언 큐에 등록. 큐는 순서대로 처리된다."""
        await self._queue.put((bot_id, content))
        logger.debug(f"[TurnManager] {bot_id} 발언 큐 등록 (qsize={self._queue.qsize()})")

    async def start_meeting(
        self,
        topic: str,
        participants: list[str],
        speak_callbacks: dict[str, Callable[[str, list[GroupMessage]], Awaitable[str | None]]],
    ) -> None:
        """주간회의/회고 등 구조화된 모임 실행.

        각 참가 봇에게 순서대로 발언을 요청하고, 응답을 그룹방에 전송한다.
        """
        async with self._lock:
            if self._active_meeting:
                logger.warning("[TurnManager] 이미 진행 중인 회의가 있음 — 스킵")
                return
            self._active_meeting = True

        try:
            await self._send(f"📋 **{topic}** 시작합니다. 참여: {', '.join(participants)}")

            for bot_id in participants:
                callback = speak_callbacks.get(bot_id)
                if callback is None:
                    logger.warning(f"[TurnManager] {bot_id} 콜백 없음 — 스킵")
                    continue

                # 각 봇 호출 직전 최신 컨텍스트를 갱신 → 이전 봇 발언이 포함됨
                ctx = await self._context.recent(15)
                await self._send(f"🎙️ *{bot_id}* 발언 요청 중...")
                try:
                    response = await asyncio.wait_for(
                        callback(topic, ctx),
                        timeout=TURN_TIMEOUT_SEC,
                    )
                    if response and response.strip():
                        msg_text = f"**[{bot_id}]** {response.strip()}"
                        await self._send(msg_text)
                        await self._context.add(GroupMessage(from_bot=bot_id, text=response.strip()))
                    else:
                        await self._send(f"_[{bot_id}] 발언 없음 (패스)_")
                except asyncio.TimeoutError:
                    logger.warning(f"[TurnManager] {bot_id} 응답 타임아웃 ({TURN_TIMEOUT_SEC}s)")
                    await self._send(f"⏱️ *{bot_id}* 타임아웃 — 다음으로 넘어갑니다")
                except Exception as e:
                    logger.error(f"[TurnManager] {bot_id} 발언 오류: {e}")
                    await self._send(f"❌ *{bot_id}* 발언 중 오류 발생")

                await asyncio.sleep(MEETING_TURN_GAP_SEC)

            await self._send(f"✅ **{topic}** 완료.")
        finally:
            async with self._lock:
                self._active_meeting = False

    async def _process_queue(self) -> None:
        """큐에서 발언을 꺼내 그룹에 전송 (자율 발언 처리)."""
        while True:
            try:
                bot_id, content = await asyncio.wait_for(self._queue.get(), timeout=5.0)
                msg_text = f"**[{bot_id}]** {content}"
                await self._send(msg_text)
                await self._context.add(GroupMessage(from_bot=bot_id, text=content))
                self._queue.task_done()
                await asyncio.sleep(MEETING_TURN_GAP_SEC)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[TurnManager] 큐 처리 오류: {e}")


# ── GroupChatHub (메인) ────────────────────────────────────────────────────────

class GroupChatHub:
    """멀티봇 그룹채팅 허브.

    - 각 봇(org)이 register_participant()로 등록
    - on_group_message()로 그룹 메시지를 수신하면:
        1. 컨텍스트에 저장
        2. 명시적으로 언급된 봇이 있으면 그 봇만 응답
        3. 없으면 도메인 키워드 매칭 봇에게 응답 기회 부여
        4. PM 중재 시 turn_manager.request_turn() 활용
    - start_meeting()으로 주간회의/회고 구동
    """

    def __init__(
        self,
        send_to_group: Callable[[str], Awaitable[None]],
        max_context: int = MAX_CONTEXT_MESSAGES,
    ) -> None:
        self._send = send_to_group
        self.context = GroupChatContext(max_messages=max_context)
        self.turn_manager = TurnManager(send_to_group=send_to_group, context=self.context)
        self._participants: dict[str, ParticipantInfo] = {}

    def register_participant(
        self,
        bot_id: str,
        speak_callback: Callable[[str, list[GroupMessage]], Awaitable[str | None]],
        domain_keywords: list[str] | None = None,
    ) -> None:
        """봇을 그룹 참가자로 등록."""
        self._participants[bot_id] = ParticipantInfo(
            bot_id=bot_id,
            speak_callback=speak_callback,
            domain_keywords=domain_keywords or [],
        )
        logger.info(f"[GroupChatHub] 참가자 등록: {bot_id} (키워드={domain_keywords})")

    def unregister_participant(self, bot_id: str) -> None:
        self._participants.pop(bot_id, None)

    async def on_group_message(
        self,
        text: str,
        from_user: str = "user",
        *,
        auto_respond: bool = True,
    ) -> None:
        """그룹방 메시지 수신 → 컨텍스트 저장 + 봇 응답 결정.

        Args:
            text: 메시지 내용.
            from_user: 발신자 식별자 (사람: "user", 봇: bot_id).
            auto_respond: True이면 적합한 봇들에게 자동으로 응답 기회를 줌.
        """
        msg = GroupMessage(from_bot=from_user, text=text)
        await self.context.add(msg)
        logger.debug(f"[GroupChatHub] 메시지 수신 from={from_user}: {text[:60]}")

        if not auto_respond:
            return

        ctx = await self.context.recent(10)

        # 1. 명시적으로 언급된 봇 탐지: @bot_id 또는 [봇이름]
        mentioned = self._find_mentioned(text)
        if mentioned:
            for bot_id in mentioned:
                info = self._participants.get(bot_id)
                if info:
                    await self._invoke_speaker(info, text, ctx)
            return

        # 2. 도메인 키워드 매칭
        matched = self._find_domain_match(text)
        for bot_id in matched:
            info = self._participants[bot_id]
            await self._invoke_speaker(info, text, ctx)

    async def start_meeting(self, topic: str, participants: list[str] | None = None) -> None:
        """주간회의/회고 등 구조화된 회의 시작.

        Args:
            topic: 회의 주제 (예: "주간 스탠드업", "월간 회고").
            participants: 참여할 봇 ID 목록. None이면 등록된 전체 봇.
        """
        parts = participants or list(self._participants.keys())
        callbacks = {bid: info.speak_callback for bid, info in self._participants.items()}
        await self.turn_manager.start_meeting(topic, parts, callbacks)

    def start_background_processor(self) -> None:
        """자율 발언 큐 처리 태스크 시작."""
        self.turn_manager.start_processor()

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _find_mentioned(self, text: str) -> list[str]:
        """메시지에서 명시적으로 언급된 봇 ID 추출."""
        found: list[str] = []
        lower = text.lower()
        for bot_id in self._participants:
            # @bot_id 또는 bot_id 가 텍스트에 포함되면 언급으로 간주
            pattern = rf"(?:@|^|\s){re.escape(bot_id.lower())}(?:\s|$|[,:])"
            if re.search(pattern, lower):
                found.append(bot_id)
        return found

    def _find_domain_match(self, text: str) -> list[str]:
        """도메인 키워드 기반 응답 봇 목록 반환."""
        lower = text.lower()
        matched: list[str] = []
        for bot_id, info in self._participants.items():
            if any(kw.lower() in lower for kw in info.domain_keywords):
                matched.append(bot_id)
        return matched

    async def _invoke_speaker(
        self,
        info: ParticipantInfo,
        text: str,
        ctx: list[GroupMessage],
    ) -> None:
        """봇 speak_callback 호출 → 응답 있으면 그룹에 전송."""
        try:
            response = await asyncio.wait_for(
                info.speak_callback(text, ctx),
                timeout=TURN_TIMEOUT_SEC,
            )
            if response and response.strip():
                await self._send(f"**[{info.bot_id}]** {response.strip()}")
                await self.context.add(GroupMessage(from_bot=info.bot_id, text=response.strip()))
        except asyncio.TimeoutError:
            logger.warning(f"[GroupChatHub] {info.bot_id} 응답 타임아웃")
        except Exception as e:
            logger.error(f"[GroupChatHub] {info.bot_id} 응답 오류: {e}")

    @property
    def participant_ids(self) -> list[str]:
        return list(self._participants.keys())
