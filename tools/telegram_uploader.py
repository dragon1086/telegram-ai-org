"""텔레그램 파일 업로드 유틸리티."""
from __future__ import annotations

from pathlib import Path

from loguru import logger
from telegram import Bot

from core.telegram_formatting import escape_html


async def upload_file(bot_token: str, chat_id: int, file_path: str, caption: str = "") -> bool:
    """파일을 텔레그램으로 전송.

    Args:
        bot_token: 텔레그램 봇 토큰.
        chat_id: 대상 채팅 ID.
        file_path: 업로드할 파일 경로.
        caption: 파일 설명 (선택).

    Returns:
        성공 여부.
    """
    p = Path(file_path)
    if not p.exists():
        logger.warning(f"[upload_file] 파일 없음: {file_path}")
        return False

    bot = Bot(token=bot_token)
    suffix = p.suffix.lower()

    safe_caption = escape_html(caption) if caption else ""
    try:
        async with bot:
            with open(p, "rb") as fh:
                if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
                    await bot.send_photo(chat_id=chat_id, photo=fh, caption=safe_caption, parse_mode="HTML")
                elif suffix in {".mp4", ".mov", ".avi"}:
                    await bot.send_video(chat_id=chat_id, video=fh, caption=safe_caption, parse_mode="HTML")
                elif suffix in {".mp3", ".ogg", ".wav", ".m4a"}:
                    await bot.send_audio(chat_id=chat_id, audio=fh, caption=safe_caption, parse_mode="HTML")
                else:
                    await bot.send_document(chat_id=chat_id, document=fh, caption=safe_caption, parse_mode="HTML")
        logger.info(f"[upload_file] 업로드 완료: {p.name}")
        return True
    except Exception as exc:
        logger.error(f"[upload_file] 업로드 실패 {p.name}: {exc}")
        return False
