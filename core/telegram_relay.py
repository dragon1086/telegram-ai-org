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
from core.global_context import GlobalContext
from core.collab_request import (
    is_collab_request, make_collab_request, make_collab_claim,
    make_collab_done, parse_collab_request,
)
from core.keywords import GREETING_KW, ACTION_KW

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

        # PM 집단 기억 — PM 간 맥락 공유
        self.global_context = GlobalContext()
        self._anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")

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

        # 봇 메시지 처리 — 협업 요청만 수락
        sender = update.message.from_user
        if sender and sender.is_bot:
            if is_collab_request(text):
                await self._handle_collab_request(text, update, context)
            return

        message_id = str(update.message.message_id)
        logger.info(f"텔레그램 수신 [{self.org_id}]: {text[:80]}")

        # 명령어 처리 (/ 로 시작)
        if text.startswith("/"):
            await self._handle_command(text, update, context)
            return

        # 1. 대화형 vs 작업 분류
        is_greeting = any(kw in text for kw in GREETING_KW) and len(text) < 15
        is_task = not is_greeting and (any(kw in text for kw in ACTION_KW) or len(text) > 20)

        # 2. 인사 → default PM만 claim 후 응답
        if is_greeting:
            is_default = self.identity._data.get("default_handler", False)
            if not is_default:
                return
            if not self.claim_manager.try_claim(message_id, self.org_id):
                return
            # claude --print로 인사 응답 (Anthropic API 키 불필요)
            import asyncio as _aio, subprocess as _sp
            _env = {**os.environ, "CLAUDECODE": "", "ANTHROPIC_API_KEY": ""}
            _proc = await _aio.create_subprocess_exec(
                "/Users/rocky/.local/bin/claude",
                "--permission-mode", "bypassPermissions", "-p",
                "--system-prompt", "친근하게 아주 짧게 한국어로 대화. 이모지 1개. 두 문장 이내.",
                text,
                stdout=_aio.subprocess.PIPE, stderr=_aio.subprocess.DEVNULL,
                env=_env, cwd="/Users/rocky/telegram-ai-org",
            )
            _out, _ = await _aio.wait_for(_proc.communicate(), timeout=15)
            reply = (_out.decode().strip() if _out else "") or "안녕하세요! 😊"
            await update.message.reply_text(reply[:300])
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

        # 4. 담당 선언 + 실행 (Claude Code가 팀 구성 자율 결정)
        await update.message.reply_text(f"✋ {self.org_id} PM 담당!")
        await self.memory_manager.add_log(f"사용자 메시지: {text[:200]}")

        from tools.claude_code_runner import ClaudeCodeRunner

        runner = ClaudeCodeRunner()
        system_prompt = self.identity.build_system_prompt()

        progress_msg = await update.message.reply_text("⚙️ 처리 중...")
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

        response = await runner.run_task(
            task=text,
            system_prompt=system_prompt,
            progress_callback=on_progress,
            session_store=self.session_store,
            global_context=self.global_context,
            org_id=self.org_id,
        )

        try:
            await progress_msg.edit_text("✅ 완료!")
        except Exception:
            pass

        # [COLLAB:task|맥락:ctx] 태그 감지 → 협업 요청 채팅방 발송
        if response:
            import re as _re
            for match in _re.findall(r'\[COLLAB:([^\]]+)\]', response):
                parts = match.split("|맥락:", 1)
                collab_task = parts[0].strip()
                collab_ctx = parts[1].strip() if len(parts) > 1 else ""
                collab_msg = make_collab_request(collab_task, self.org_id, context=collab_ctx)
                try:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=collab_msg)
                except Exception as _e:
                    logger.warning(f"협업 요청 발송 실패: {_e}")
            response = _re.sub(r'\[COLLAB:[^\]]+\]', '', response).strip()

        if response:
            for chunk in _split_message(response, 4000):
                await update.message.reply_text(chunk)
            await self.memory_manager.add_log(f"claude 응답: {response[:200]}")
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
        from tools.claude_code_runner import ClaudeCodeRunner

        runner = ClaudeCodeRunner()
        system_prompt = self.identity.build_system_prompt()

        progress_msg = await msg.reply_text("⚙️ 처리 중...")
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

        response = await runner.run_task(
            task=task,
            system_prompt=system_prompt,
            progress_callback=on_progress,
            session_store=self.session_store,
            global_context=self.global_context,
            org_id=self.org_id,
        )

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

    async def _handle_collab_request(
        self, text: str, update, context
    ) -> None:
        """다른 PM의 협업 요청 — confidence → claim → 실행 → 결과 채팅방 발송."""
        parsed = parse_collab_request(text)
        task = parsed["task"]
        ctx = parsed["context"]
        from_org = parsed["from_org"]

        if from_org == self.org_id or not task:
            return

        # confidence 계산
        score = await self.confidence_scorer.score(task, self.identity)
        if score < 6:
            return

        import asyncio as _asyncio
        await _asyncio.sleep(max(0.0, (10 - score) * 0.3))

        message_id = f"collab_{update.message.message_id}"
        if not self.claim_manager.try_claim(message_id, self.org_id):
            return

        await update.message.reply_text(make_collab_claim(self.org_id))

        # 요청 조직의 맥락 + 글로벌 맥락 모두 주입
        system_prompt = self.identity.build_system_prompt()
        if ctx:
            system_prompt += f"\n\n## 협업 요청 조직({from_org})의 작업 맥락\n{ctx}"

        runner = ClaudeCodeRunner()
        progress_msg = await update.message.reply_text("⚙️ 협업 작업 중...")
        history: list[str] = []
        last_edit = 0.0

        async def on_progress(line: str) -> None:
            nonlocal last_edit
            import time
            history.append(line)
            if time.time() - last_edit > 1.5:
                try:
                    await progress_msg.edit_text(
                        "⚙️ 협업 작업 중...\n\n" + "\n".join(history[-5:])
                    )
                    last_edit = time.time()
                except Exception:
                    pass

        response = await runner.run_task(
            task=task,
            system_prompt=system_prompt,
            progress_callback=on_progress,
            session_store=self.session_store,
            global_context=self.global_context,
            org_id=self.org_id,
        )

        try:
            await progress_msg.edit_text("✅ 협업 완료!")
        except Exception:
            pass

        summary = (response or "(결과 없음)")[:300]
        await update.message.reply_text(make_collab_done(self.org_id, summary))
        if response and len(response) > 300:
            for chunk in _split_message(response[300:], 4000):
                await update.message.reply_text(chunk)


def _split_message(text: str, max_len: int = 4000) -> list[str]:
    """텔레그램 메시지 길이 제한 분할."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:max_len])
        text = text[max_len:]
    return chunks


    async def _handle_command(
        self, text: str, update, context
    ) -> None:
        """/ 명령어 처리 — 특정 봇 태그(/org@aiorg_pm_bot)도 지원."""
        # @봇이름 제거
        import re as _re
        cmd_full = text.strip().split()[0].lower()
        cmd = _re.sub(r'@\S+', '', cmd_full)  # /org@bot → /org
        arg = text[len(text.split()[0]):].strip()

        # 이 PM 대상이 아닌 태그된 명령어면 무시
        bot_tag = _re.search(r'@(\S+)', text.split()[0])
        if bot_tag:
            my_username = (await context.bot.get_me()).username or ""
            if bot_tag.group(1).lower() != my_username.lower():
                return

        # /org — 조직 정체성 조회/설정
        if cmd == "/org":
            if not arg or arg.lower() == "status":
                d = self.identity._data
                msg = (
                    f"🏢 **{self.org_id} 조직 정체성**\n\n"
                    f"역할: {d.get('role','미설정')}\n"
                    f"전문분야: {', '.join(d.get('specialties', []))}\n"
                    f"방향성: {d.get('direction','미설정')}"
                )
                await update.message.reply_text(msg, parse_mode="Markdown")
            else:
                # 자유 텍스트 → 정체성 업데이트
                parts = [p.strip() for p in arg.split("|")]
                new_data: dict = {"direction": arg}
                # 파이프 구분 파싱: 역할|전문분야|방향성
                if len(parts) >= 1:
                    new_data["role"] = parts[0]
                if len(parts) >= 2:
                    new_data["specialties"] = [s.strip() for s in parts[1].split(",")]
                if len(parts) >= 3:
                    new_data["direction"] = parts[2]
                self.identity.update(new_data)
                d = self.identity._data
                msg = (
                    f"✅ **{self.org_id} 정체성 업데이트!**\n\n"
                    f"역할: {d.get('role','')}\n"
                    f"전문분야: {', '.join(d.get('specialties', []))}\n"
                    f"방향성: {d.get('direction','')}\n\n"
                    f"이제 이 방향성으로 팀을 구성할게요 🤖"
                )
                await update.message.reply_text(msg, parse_mode="Markdown")
            return

        # /agents — 에이전트 목록
        if cmd == "/agents":
            from pathlib import Path as _Path
            agents_dir = _Path.home() / ".claude" / "agents"
            agents = sorted(agents_dir.glob("*.md"))
            by_cat: dict = {}
            for a in agents:
                cat = a.stem.split("-")[0]
                by_cat.setdefault(cat, []).append(a.stem.split("-", 1)[-1])
            msg = f"🤖 **에이전트 {len(agents)}개**\n\n"
            for cat, names in sorted(by_cat.items()):
                preview = ", ".join(names[:4])
                suffix = f" +{len(names)-4}" if len(names) > 4 else ""
                msg += f"**{cat}** ({len(names)}): {preview}{suffix}\n"
            await update.message.reply_text(msg[:4000], parse_mode="Markdown")
            return

        # /team — 현재 전략
        if cmd == "/team":
            from tools.team_strategy import detect_strategy
            s = detect_strategy()
            desc = {
                "omc": "omc /team (plan→exec→verify)",
                "native": "native --agents",
                "solo": "단독 실행",
            }
            await update.message.reply_text(
                f"⚙️ 현재 팀 전략: **{desc.get(s, s)}**",
                parse_mode="Markdown",
            )
            return

        # /reset — 세션 초기화
        if cmd == "/reset":
            self.session_store.reset(self.org_id)
            await update.message.reply_text("🔄 PM 세션 초기화됨")
            return

        # /pm — 이 방의 PM 목록 (여러 PM 있을 때 관리)
        if cmd == "/pm":
            sub = arg.lower()
            if not sub or sub == "list":
                msg = (
                    f"🤖 **현재 활성 PM**\n\n"
                    f"• @{(await context.bot.get_me()).username} — {self.org_id}\n"
                    f"  역할: {self.identity._data.get('role','')}\n"
                    f"  전문분야: {', '.join(self.identity._data.get('specialties', []))}\n"
                )
                await update.message.reply_text(msg, parse_mode="Markdown")
            return

