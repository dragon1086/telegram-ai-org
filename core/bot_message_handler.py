"""봇 메시지 수신·파싱 모듈.

Phase 1b 리팩토링 — telegram_relay.py에서 메시지 수신·분류·첨부파일 처리 책임 분리.

의존성 방향 (단방향, 순환 참조 없음):
    bot_message_handler → core.attachment_manager
    telegram_relay      → bot_message_handler  (import 추가)
    telegram_relay      → (기존 내부 로직 유지, ENABLE_REFACTORED_HANDLER=False 시 동작)
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from core.attachment_manager import AttachmentContext

# ─── Feature Flag ───────────────────────────────────────────────────────────
# True 시 telegram_relay.py가 이 모듈에 메시지 처리를 위임.
# 기본값 False — 기존 코드 그대로 동작.
ENABLE_REFACTORED_HANDLER: bool = False

# ─── 상수 ────────────────────────────────────────────────────────────────────
ATTACHMENT_GROUP_DEBOUNCE_SEC: float = 1.2
"""미디어 그룹 디바운스 대기 시간(초)."""

# ─── 순환참조 방지 상수 (RETRO-17 설계값) ────────────────────────────────────
MAX_ORCHESTRATION_DEPTH: int = 10
"""오케스트레이션 최대 깊이 제한 (CIRC-004)."""

MAX_ROUTING_HOPS: int = 3
"""라우팅 최대 홉 수 제한 (CIRC-002)."""


def check_circular_ref(
    sender_id: object = None,
    target_bot_id: object = None,
    routing_hops: int | None = None,
    orchestration_depth: int | None = None,
    reply_sender_id: object = None,
    current_bot_id: object = None,
) -> None:
    """순환참조 방지 4규칙 검증 (RETRO-17 CIRC-001 ~ CIRC-004).

    Args:
        sender_id: 메시지 발신자 ID
        target_bot_id: 라우팅 대상 봇 ID
        routing_hops: 현재까지 라우팅 홉 수
        orchestration_depth: 현재 오케스트레이션 깊이
        reply_sender_id: reply_to_message 의 발신자 ID
        current_bot_id: 현재 처리 중인 봇 ID

    Raises:
        ValueError: 순환참조 규칙 위반 시 [CIRC-00N] 마커 포함 메시지
    """
    # CIRC-001: sender_id == target_bot_id 금지
    if sender_id is not None and target_bot_id is not None and sender_id == target_bot_id:
        raise ValueError(
            f"[CIRC-001] sender_id({sender_id!r}) == target_bot_id({target_bot_id!r}): "
            "자기 자신에게 메시지를 보낼 수 없습니다."
        )

    # CIRC-002: 라우팅 홉 초과 금지
    if routing_hops is not None and routing_hops > MAX_ROUTING_HOPS:
        raise ValueError(
            f"[CIRC-002] routing_hops({routing_hops}) > MAX_ROUTING_HOPS({MAX_ROUTING_HOPS}): "
            "라우팅 홉 한도를 초과했습니다."
        )

    # CIRC-003: reply 발신자 == 현재 봇 금지
    if reply_sender_id is not None and current_bot_id is not None and reply_sender_id == current_bot_id:
        raise ValueError(
            f"[CIRC-003] reply_sender_id({reply_sender_id!r}) == current_bot_id({current_bot_id!r}): "
            "reply_to_message 순환 참조가 감지되었습니다."
        )

    # CIRC-004: 오케스트레이션 깊이 초과 금지
    if orchestration_depth is not None and orchestration_depth > MAX_ORCHESTRATION_DEPTH:
        raise ValueError(
            f"[CIRC-004] orchestration_depth({orchestration_depth}) > MAX_ORCHESTRATION_DEPTH({MAX_ORCHESTRATION_DEPTH}): "
            "오케스트레이션 깊이 한도를 초과했습니다."
        )


PM_DONE_PATTERN: re.Pattern = re.compile(
    r"태스크\s+T-[A-Za-z0-9_]+-\d+\s+(완료|실패)"
)
"""PM 태스크 완료/실패 이벤트 감지 정규식."""


# ─── 데이터 클래스 ────────────────────────────────────────────────────────────
@dataclass
class AttachmentGroupState:
    """미디어 그룹 디바운스 상태.

    telegram_relay.py 의 ``_AttachmentGroupState`` 에서 추출.
    공개 이름으로 변경 (언더스코어 제거).
    """

    items: list[AttachmentContext] = field(default_factory=list)
    caption: str = ""
    message: object | None = None
    task: asyncio.Task | None = None


# ─── 메시지 분류기 (순수 정적 메서드, 완전 테스트 가능) ───────────────────────
class MessageClassifier:
    """메시지 타입 분류 — TelegramRelay 의존성 없이 순수 정적 메서드로 구성.

    모든 메서드는 ``self`` 없이 호출 가능. 단위 테스트가 용이하다.
    """

    @staticmethod
    def is_bot_sender(sender: object | None) -> bool:
        """발신자가 봇인지 확인."""
        return bool(sender and getattr(sender, "is_bot", False))

    @staticmethod
    def is_command(text: str) -> bool:
        """명령어 메시지인지 확인 (슬래시로 시작)."""
        return text.startswith("/")

    @staticmethod
    def is_pm_done_event(text: str) -> bool:
        """PM 태스크 완료/실패 이벤트 메시지인지 확인."""
        return bool(PM_DONE_PATTERN.search(text))

    @staticmethod
    def is_old_message(
        msg_ts: float,
        start_time: float,
        grace_sec: float = 120.0,
    ) -> bool:
        """봇 시작 이전(grace_sec 이상 과거) 메시지인지 확인.

        pending updates 방지용. grace_sec 기본값 120s — 재시작에 30s+ 소요.
        """
        return bool(msg_ts and msg_ts < start_time - grace_sec)

    @staticmethod
    def is_startup_recovery_message(msg_ts: float, start_time: float) -> bool:
        """재시작 중 수신된 복구 처리 대상 메시지인지 확인."""
        return bool(msg_ts and msg_ts < start_time)

    @staticmethod
    def extract_text(message: object) -> str:
        """메시지에서 텍스트를 안전하게 추출."""
        return getattr(message, "text", None) or ""


# ─── 첨부파일 다운로더 (순수 I/O, TelegramRelay 상태 불필요) ────────────────────
async def download_attachment(
    msg: object,
    context: object,
    save_dir: Path,
) -> AttachmentContext | None:
    """첨부파일 다운로드 — 문서/이미지/영상/오디오/음성 지원.

    ``telegram_relay.TelegramRelay._download_attachment_context`` 에서 추출.
    순수 입출력 함수 — TelegramRelay 상태 불필요. 단위 테스트 가능.

    Args:
        msg: telegram.Message 객체 (duck-typed).
        context: telegram.ext.ContextTypes.DEFAULT_TYPE (bot 접근용).
        save_dir: 파일 저장 디렉터리.

    Returns:
        AttachmentContext 또는 None (지원하지 않는 타입).
    """
    bot = context.bot  # type: ignore[union-attr]

    if getattr(msg, "document", None):
        tg_file = await bot.get_file(msg.document.file_id)  # type: ignore[union-attr]
        filename = msg.document.file_name or f"doc_{msg.message_id}"  # type: ignore[union-attr]
        save_path = save_dir / filename
        await tg_file.download_to_drive(save_path)
        caption = getattr(msg, "caption", None) or f"{filename} 파일을 분석해줘"
        return AttachmentContext.from_local_file(
            kind="document",
            local_path=save_path,
            caption=caption,
            original_filename=filename,
            mime_type=getattr(msg.document, "mime_type", None) or "",  # type: ignore[union-attr]
        )

    if getattr(msg, "photo", None):
        photo = msg.photo[-1]  # type: ignore[index]
        tg_file = await bot.get_file(photo.file_id)
        save_path = save_dir / f"photo_{msg.message_id}.jpg"  # type: ignore[union-attr]
        await tg_file.download_to_drive(save_path)
        caption = getattr(msg, "caption", None) or "이 이미지를 분석해줘"
        return AttachmentContext.from_local_file(
            kind="photo",
            local_path=save_path,
            caption=caption,
            original_filename=save_path.name,
            mime_type="image/jpeg",
        )

    if getattr(msg, "video", None):
        tg_file = await bot.get_file(msg.video.file_id)  # type: ignore[union-attr]
        filename = getattr(msg.video, "file_name", None) or f"video_{msg.message_id}.mp4"  # type: ignore[union-attr]
        save_path = save_dir / filename
        await tg_file.download_to_drive(save_path)
        caption = getattr(msg, "caption", None) or f"{filename} 비디오를 분석해줘"
        return AttachmentContext.from_local_file(
            kind="video",
            local_path=save_path,
            caption=caption,
            original_filename=filename,
            mime_type=getattr(msg.video, "mime_type", None) or "video/mp4",  # type: ignore[union-attr]
        )

    if getattr(msg, "audio", None):
        tg_file = await bot.get_file(msg.audio.file_id)  # type: ignore[union-attr]
        filename = getattr(msg.audio, "file_name", None) or f"audio_{msg.message_id}.mp3"  # type: ignore[union-attr]
        save_path = save_dir / filename
        await tg_file.download_to_drive(save_path)
        caption = getattr(msg, "caption", None) or f"{filename} 오디오를 분석해줘"
        return AttachmentContext.from_local_file(
            kind="audio",
            local_path=save_path,
            caption=caption,
            original_filename=filename,
            mime_type=getattr(msg.audio, "mime_type", None) or "audio/mpeg",  # type: ignore[union-attr]
        )

    if getattr(msg, "voice", None):
        tg_file = await bot.get_file(msg.voice.file_id)  # type: ignore[union-attr]
        save_path = save_dir / f"voice_{msg.message_id}.ogg"  # type: ignore[union-attr]
        await tg_file.download_to_drive(save_path)
        caption = getattr(msg, "caption", None) or "이 음성 메시지를 분석해줘"
        return AttachmentContext.from_local_file(
            kind="voice",
            local_path=save_path,
            caption=caption,
            original_filename=save_path.name,
            mime_type="audio/ogg",
        )

    logger.debug("download_attachment: 지원하지 않는 첨부파일 타입 — None 반환")
    return None


# ─── 공개 API ─────────────────────────────────────────────────────────────────
__all__ = [
    "ENABLE_REFACTORED_HANDLER",
    "ATTACHMENT_GROUP_DEBOUNCE_SEC",
    "PM_DONE_PATTERN",
    "AttachmentGroupState",
    "MessageClassifier",
    "download_attachment",
]
