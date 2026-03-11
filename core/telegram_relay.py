"""텔레그램 ↔ tmux Claude Code 세션 중계 — 얇은 relay 레이어.

Python봇의 역할: 메시지 수신 → session_manager.send_message() → 응답 전송.
무거운 로직은 tmux 세션 안의 Claude Code가 처리.
자율 라우팅: confidence scoring + 파일 기반 claim으로 가장 적합한 PM이 담당.
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

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
from core.pm_identity import PMIdentity
from core.claim_manager import ClaimManager
from core.confidence_scorer import ConfidenceScorer
from core.session_store import SessionStore

TEAM_ID = "pm"  # aiorg_pm tmux 세션
DEFAULT_CONFIDENCE_THRESHOLD = 5  # 이 점수 미만이면 다른 PM에게 양보


class TelegramRelay:
    """텔레그램 ↔ tmux Claude Code 세션 중계만 담당."""

    def __init__(
        self,
        token: str,
        allowed_chat_id: int,
        session_manager: SessionManager,
        memory_manager: MemoryManager,
        org_id: str = "global",
    ) -> None:
        self.token = token
        self.allowed_chat_id = allowed_chat_id
        self.session_manager = session_manager
        self.memory_manager = memory_manager
        self.org_id = org_id
        self.app: Application | None = None
        self._message_count: int = 0

        # 자율 라우팅 컴포넌트
        self.identity = PMIdentity(org_id)
        self.identity.load()
        self.claim_manager = ClaimManager()
        self.confidence_scorer = ConfidenceScorer()

        # Claude Code 세션 영속화 (--resume으로 대화 맥락 유지)
        self.session_store = SessionStore(org_id)

    # ── 메시지 처리 ────────────────────────────────────────────────────────

    async def on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """메시지 수신 → confidence scoring → claim → 응답."""
        if update.message is None or update.effective_chat is None:
            return

        # 허용된 채팅만 처리
        if update.effective_chat.id != self.allowed_chat_id:
            return

        text = update.message.text or ""
        if not text:
            return

        message_id = str(update.message.message_id)
        logger.info(f"텔레그램 수신 [{self.org_id}]: {text[:80]}")

        # 1. 대화형 vs 작업 분류
        greeting_kw = ["안녕", "hi", "hello", "ㅎㅇ", "잘 지내", "뭐해", "있어?", "왔어", "반가"]
        action_kw = ["작성해","만들어","분석해","구현해","개발해","조사해","생성해","수정해",
                     "고쳐","빌드","보고서","리포트","기획","설계","평가","검토","요약","정리",
                     "비교","추천","제안","계획","전략","조회","확인해","알려줘","해줘"]
        is_greeting = any(kw in text for kw in greeting_kw) and len(text) < 15
        is_task = not is_greeting and (any(kw in text for kw in action_kw) or len(text) > 20)

        # 2. 인사 → default PM만 claim 후 응답
        if is_greeting:
            is_default = self.identity._data.get("default_handler", False)
            if not is_default:
                return
            if not self.claim_manager.try_claim(message_id, self.org_id):
                return
            import anthropic as _anth
            client = _anth.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
            resp = client.messages.create(
                model="claude-haiku-4-5", max_tokens=80,
                system="친근하게 아주 짧게 한국어로 대화. 이모지 1개.",
                messages=[{"role": "user", "content": text}],
            )
            await update.message.reply_text(resp.content[0].text if resp.content else "안녕하세요! 😊")
            return

        # 3. 작업 요청 → confidence 계산
        score = await self.confidence_scorer.score(text, self.identity)
        is_default = self.identity._data.get("default_handler", False)
        if score < DEFAULT_CONFIDENCE_THRESHOLD and not is_default:
            return

        wait_time = max(0.0, (10 - score) * 0.3) if (not is_default or score >= DEFAULT_CONFIDENCE_THRESHOLD) else ClaimManager.CLAIM_TIMEOUT - 0.1
        await asyncio.sleep(wait_time)

        if not self.claim_manager.try_claim(message_id, self.org_id):
            return

        asyncio.get_event_loop().run_in_executor(None, self.claim_manager.cleanup_old_claims)

        # 4. 담당 선언 + 팀 구성
        await update.message.reply_text(f"✋ {self.org_id} PM 담당! 팀 구성 중...")
        await self.memory_manager.add_log(f"사용자 메시지: {text[:200]}")

        from core.dynamic_team_builder import DynamicTeamBuilder
        from core.agent_catalog import AgentCatalog
        from tools.claude_code_runner import ClaudeCodeRunner

        catalog = AgentCatalog(); catalog.load()
        builder = DynamicTeamBuilder(catalog)
        runner = ClaudeCodeRunner()

        team_config = await builder.build_team(text)
        from core.dynamic_team_builder import ExecutionMode
        agent_names = [p.name for p in team_config.agents]

        await update.message.reply_text(f"🤖 팀: {', '.join(agent_names[:3])}")

        # 진행상황 실시간 edit
        progress_msg = await update.message.reply_text("⚙️ 작업 시작...")
        history: list[str] = []
        last_edit = time.time()

        async def on_progress(line: str) -> None:
            nonlocal last_edit
            stripped = line.strip()
            if not stripped:
                return
            history.append(stripped)
            if time.time() - last_edit > 1.5:
                display = "\n".join(history[-5:])
                try:
                    await progress_msg.edit_text(f"⚙️ 작업 중...\n\n{display}")
                    last_edit = time.time()
                except Exception:
                    pass

        if team_config.execution_mode == ExecutionMode.omc_team:
            response = await runner.run_omc_team(text, agent_names, progress_callback=on_progress, session_store=self.session_store)
        elif team_config.execution_mode == ExecutionMode.agent_teams:
            response = await runner.run_agent_teams(text, agent_names, progress_callback=on_progress)
        else:
            response = await runner.run_single(text, progress_callback=on_progress, session_store=self.session_store)

        try:
            await progress_msg.edit_text("✅ 완료!")
        except Exception:
            pass

        if response:
            for chunk in _split_message(response, 4000):
                await update.message.reply_text(chunk)
            await self.memory_manager.add_log(f"claude 응답: {response[:200]}")
            # 생성 파일 자동 업로드
            await runner._auto_upload(response, self.token, self.allowed_chat_id)

    # ── 첨부파일 처리 ──────────────────────────────────────────────────────

    async def on_attachment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """문서/이미지 수신 → 로컬 저장 → claude에 전달."""
        msg = update.message
        if msg is None:
            return
        if update.effective_chat is None or update.effective_chat.id != self.allowed_chat_id:
            return

        save_dir = Path.home() / ".ai-org" / "uploads"
        save_dir.mkdir(parents=True, exist_ok=True)

        if msg.document:
            tg_file = await context.bot.get_file(msg.document.file_id)
            filename = msg.document.file_name or f"doc_{msg.message_id}"
            save_path = save_dir / filename
            await tg_file.download_to_drive(save_path)
            caption = msg.caption or f"{filename} 파일을 분석해줘"
        elif msg.photo:
            photo = msg.photo[-1]
            tg_file = await context.bot.get_file(photo.file_id)
            save_path = save_dir / f"photo_{msg.message_id}.jpg"
            await tg_file.download_to_drive(save_path)
            caption = msg.caption or "이 이미지를 분석해줘"
        else:
            return

        await msg.reply_text(f"📎 파일 수신: {save_path.name}\n처리 중...")
        logger.info(f"[on_attachment] 저장: {save_path}")

        task = f"{caption}\n\n첨부파일 경로: {save_path}"
        score = await self.confidence_scorer.score(task, self.identity)
        is_default = self.identity._data.get("default_handler", False)
        if score < DEFAULT_CONFIDENCE_THRESHOLD and not is_default:
            return

        message_id = str(msg.message_id) + "_att"
        if not self.claim_manager.try_claim(message_id, self.org_id):
            return

        await self._execute_task(task, msg)

    async def _execute_task(self, task: str, msg: object) -> None:
        """태스크 실행 공통 로직 (progress 스트리밍 + 결과 전송)."""
        from core.dynamic_team_builder import DynamicTeamBuilder, ExecutionMode
        from core.agent_catalog import AgentCatalog
        from tools.claude_code_runner import ClaudeCodeRunner

        catalog = AgentCatalog(); catalog.load()
        builder = DynamicTeamBuilder(catalog)
        runner = ClaudeCodeRunner()

        team_config = await builder.build_team(task)
        agent_names = [p.name for p in team_config.agents]

        progress_msg = await msg.reply_text("⚙️ 작업 시작...")
        history: list[str] = []
        last_edit = time.time()

        async def on_progress(line: str) -> None:
            nonlocal last_edit
            stripped = line.strip()
            if not stripped:
                return
            history.append(stripped)
            if time.time() - last_edit > 1.5:
                display = "\n".join(history[-5:])
                try:
                    await progress_msg.edit_text(f"⚙️ 작업 중...\n\n{display}")
                    last_edit = time.time()
                except Exception:
                    pass

        if team_config.execution_mode == ExecutionMode.omc_team:
            response = await runner.run_omc_team(task, agent_names, progress_callback=on_progress, session_store=self.session_store)
        elif team_config.execution_mode == ExecutionMode.agent_teams:
            response = await runner.run_agent_teams(task, agent_names, progress_callback=on_progress)
        else:
            response = await runner.run_single(task, progress_callback=on_progress, session_store=self.session_store)

        try:
            await progress_msg.edit_text("✅ 완료!")
        except Exception:
            pass

        if response:
            for chunk in _split_message(response, 4000):
                await msg.reply_text(chunk)
            await self.memory_manager.add_log(f"claude 응답: {response[:200]}")
            await runner._auto_upload(response, self.token, self.allowed_chat_id)

    # ── 명령 처리 ──────────────────────────────────────────────────────────

    async def on_command_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """PM 세션 없으면 생성 + 메모리 주입 후 /start."""
        if update.message is None:
            return

        existed = self.session_manager.session_exists(TEAM_ID)
        self.session_manager.ensure_session(TEAM_ID)

        if not existed:
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
            await update.message.reply_text("✅ 이미 실행 중인 세션에 연결됩니다.")

    async def on_command_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """세션 상태, 메모리 크기, PM 정체성 출력."""
        if update.message is None:
            return

        sess_status = self.session_manager.status()
        mem_stats = self.memory_manager.stats()
        specialties = self.identity.get_specialty_text() or "없음"

        text = (
            f"**세션 상태**\n"
            f"  tmux 사용 가능: {sess_status.get('tmux', False)}\n"
            f"  활성 세션: {', '.join(sess_status.get('sessions', [])) or '없음'}\n\n"
            f"**PM 정체성 [{self.org_id}]**\n"
            f"  전문분야: {specialties}\n\n"
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
            self.session_store.reset()
            await update.message.reply_text("✅ 새 세션으로 시작합니다. 대화 기록도 초기화했습니다.")
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
        self.app.add_handler(MessageHandler(filters.Document.ALL, self.on_attachment))
        self.app.add_handler(MessageHandler(filters.PHOTO, self.on_attachment))

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
