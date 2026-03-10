"""텔레그램 ↔ tmux Claude Code 세션 중계 — 얇은 relay 레이어.

Python봇의 역할: 메시지 수신 → session_manager.send_message() → 응답 전송.
무거운 로직은 tmux 세션 안의 Claude Code가 처리.
"""
from __future__ import annotations

import os

from loguru import logger
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from core.session_manager import SessionManager
from core.memory_manager import MemoryManager

TEAM_ID = "pm"  # aiorg_pm tmux 세션


class TelegramRelay:
    """텔레그램 ↔ tmux Claude Code 세션 중계만 담당."""

    def __init__(
        self,
        token: str,
        allowed_chat_id: int,
        session_manager: SessionManager,
        memory_manager: MemoryManager,
    ) -> None:
        self.token = token
        self.allowed_chat_id = allowed_chat_id
        self.session_manager = session_manager
        self.memory_manager = memory_manager
        self.app: Application | None = None
        self._message_count: int = 0

    # ── 메시지 처리 ────────────────────────────────────────────────────────

    async def on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """메시지 수신 → session_manager.send_message("pm") → 응답 전송."""
        if update.message is None or update.effective_chat is None:
            return

        # 허용된 채팅만 처리
        if update.effective_chat.id != self.allowed_chat_id:
            return

        text = update.message.text or ""
        if not text:
            return

        logger.info(f"텔레그램 수신: {text[:80]}")

        # 세션 보장
        self.session_manager.ensure_session(TEAM_ID)

        # 메모리에 로그 기록
        await self.memory_manager.add_log(f"사용자 메시지: {text[:200]}")

        try:
            response = await self.session_manager.send_message(TEAM_ID, text)
        except Exception as e:
            logger.error(f"세션 메시지 전달 실패: {e}")
            await update.message.reply_text(f"❌ 오류: {e}")
            return

        if response:
            # 4096자 제한 분할
            for chunk in _split_message(response, 4000):
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text("(응답 없음)")

        # 메시지 카운터 + compact 체크
        self._message_count += 1
        compacted = await self.session_manager.maybe_compact(TEAM_ID, self._message_count)
        if compacted:
            self._message_count = 0
            logger.info("compact 실행 → 카운터 리셋")

        # 메모리에 응답 로그
        if response:
            await self.memory_manager.add_log(f"claude 응답: {response[:200]}")

    # ── 명령 처리 ──────────────────────────────────────────────────────────

    async def on_command_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """PM 세션 없으면 생성 + 메모리 주입 후 /start."""
        if update.message is None:
            return

        # 세션 생성 (없으면)
        existed = self.session_manager.session_exists(TEAM_ID)
        self.session_manager.ensure_session(TEAM_ID)

        if not existed:
            # 메모리 컨텍스트 주입
            ctx = self.memory_manager.build_context()
            if ctx:
                self.session_manager.inject_context(TEAM_ID, ctx)
            await update.message.reply_text(
                "🤖 **PM Bot 온라인**\n\n"
                "tmux 세션에서 Claude Code가 실행 중입니다.\n"
                "무엇이든 말씀하세요 — 메시지를 Claude에게 전달합니다.\n\n"
                "/status — 세션 상태 확인",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                "✅ 이미 실행 중인 세션에 연결됩니다.",
            )

    async def on_command_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """세션 상태, 메모리 크기 등 출력."""
        if update.message is None:
            return

        sess_status = self.session_manager.status()
        mem_stats = self.memory_manager.stats()

        text = (
            f"**세션 상태**\n"
            f"  tmux 사용 가능: {sess_status.get('tmux', False)}\n"
            f"  활성 세션: {', '.join(sess_status.get('sessions', [])) or '없음'}\n\n"
            f"**메모리 ({mem_stats['scope']})**\n"
            f"  CORE: {mem_stats['core']}개\n"
            f"  SUMMARY: {mem_stats['summary']}개\n"
            f"  LOG: {mem_stats['log']}개\n\n"
            f"메시지 카운터: {self._message_count}"
        )
        await update.message.reply_text(text, parse_mode="Markdown")

    async def on_command_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """세션 writeback + 리셋."""
        if update.message is None:
            return

        await update.message.reply_text("🔄 세션 writeback 후 리셋 중...")
        try:
            await self.session_manager.writeback_and_reset(TEAM_ID, self.memory_manager)
            self._message_count = 0
            await update.message.reply_text("✅ 새 세션으로 시작합니다.")
        except Exception as e:
            logger.error(f"리셋 실패: {e}")
            await update.message.reply_text(f"❌ 리셋 실패: {e}")

    # ── 앱 빌드 ───────────────────────────────────────────────────────────

    def build(self) -> Application:
        """텔레그램 Application 빌드."""
        self.app = Application.builder().token(self.token).build()

        self.app.add_handler(CommandHandler("start", self.on_command_start))
        self.app.add_handler(CommandHandler("status", self.on_command_status))
        self.app.add_handler(CommandHandler("reset", self.on_command_reset))
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_message)
        )

        return self.app


# ── 유틸 ──────────────────────────────────────────────────────────────────

def _split_message(text: str, max_len: int = 4000) -> list[str]:
    """텔레그램 메시지 길이 제한 분할."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:max_len])
        text = text[max_len:]
    return chunks
