"""텔레그램 ↔ tmux Claude Code 세션 중계 — 얇은 relay 레이어.

Python봇의 역할: 메시지 수신 → session_manager.send_message() → 응답 전송.
무거운 로직은 tmux 세션 안의 Claude Code가 처리.
자율 라우팅: confidence scoring + 파일 기반 claim으로 가장 적합한 PM이 담당.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import time
from pathlib import Path

from loguru import logger
from telegram import Update
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from core.message_bus import MessageBus, Event, EventType
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
from core.display_limiter import DisplayLimiter, MessagePriority
from core.nl_classifier import NLClassifier, Intent

TEAM_ID = "pm"  # aiorg_pm tmux 세션
DEFAULT_CONFIDENCE_THRESHOLD = 5  # 이 점수 미만이면 다른 PM에게 양보
USE_NL_CLASSIFIER = True  # 2-tier NLClassifier 활성화 플래그 (False 시 기존 키워드 로직 사용)

# /setup 마법사 ConversationHandler 상태
SETUP_MENU, SETUP_AWAIT_TOKEN, SETUP_AWAIT_ENGINE = range(3)


class TelegramRelay:
    """텔레그램 ↔ tmux Claude Code 세션 중계만 담당."""

    def __init__(
        self,
        token: str,
        allowed_chat_id: int,
        session_manager: SessionManager,
        memory_manager: MemoryManager,
        org_id: str = "global",
        engine: str = "claude-code",
        bus: MessageBus | None = None,
    ) -> None:
        self.token = token
        self.allowed_chat_id = allowed_chat_id
        self.session_manager = session_manager
        self.memory_manager = memory_manager
        self.org_id = org_id
        self.engine = engine
        self.bus = bus
        self.app: Application | None = None
        self._message_count: int = 0

        # 자율 라우팅 컴포넌트
        self.identity = PMIdentity(org_id)
        self.identity.load()
        self.claim_manager = ClaimManager()
        self.confidence_scorer = ConfidenceScorer()
        self._start_time = time.time()  # 봇 시작 시각 — 이전 메시지 무시용

        # Claude Code 세션 영속화 (--resume으로 대화 맥락 유지)
        self.session_store = SessionStore(org_id)

        # PM 집단 기억 — PM 간 맥락 공유
        self.global_context = GlobalContext()
        self._anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")

        self.display = DisplayLimiter(
            debounce_sec=5.0,
            enabled=os.getenv("USE_DISPLAY_LIMITER", "true").lower() == "true",
        )
        self._nl_classifier = NLClassifier()

    def _make_runner(self):
        """engine 설정에 따라 적합한 runner를 반환한다."""
        if self.engine == "codex":
            from tools.codex_runner import CodexRunner
            return _CodexRunnerAdapter(CodexRunner())
        # claude-code (기본) 또는 auto
        from tools.claude_code_runner import ClaudeCodeRunner
        return ClaudeCodeRunner()

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
        # 봇 시작 이전 메시지 무시 (pending updates 방지)
        if update.message.date and update.message.date.timestamp() < self._start_time - 5:
            logger.debug(f"[{self.org_id}] 오래된 메시지 무시 (message_id={message_id})")
            return
        logger.info(f"텔레그램 수신 [{self.org_id}]: {text[:80]}")

        # 명령어 처리 (/ 로 시작)
        if text.startswith("/"):
            await self._handle_command(text, update, context)
            return

        # 1. 대화형 vs 작업 분류
        if USE_NL_CLASSIFIER:
            _result = self._nl_classifier.classify(text)
            _intent = _result.intent
            is_greeting = _intent == Intent.GREETING
            # APPROVE/REJECT/CANCEL/STATUS 는 짧은 명령이므로 task로 라우팅
            # CHAT 은 greeting과 동일하게 default PM만 처리
            is_greeting = is_greeting or _intent == Intent.CHAT
            is_task = _intent in (Intent.TASK, Intent.APPROVE, Intent.REJECT, Intent.CANCEL, Intent.STATUS)
        else:
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
            await self.display.send_reply(update.message, reply[:300])
            return

        # 3. 작업 요청 → confidence 계산
        score = await self.confidence_scorer.score(text, self.identity)
        is_default = self.identity._data.get("default_handler", False)
        if score < DEFAULT_CONFIDENCE_THRESHOLD and not is_default:
            return

        # 1단계: 입찰 제출 (default_handler threshold 미달 시 score=0으로 최후 보루)
        text_hash = hashlib.md5(text.encode()).hexdigest()
        bid_score = score if score >= DEFAULT_CONFIDENCE_THRESHOLD else 0
        self.claim_manager.submit_bid(text_hash, self.org_id, bid_score)

        # 2단계: BID_WAIT_SEC 대기 (다른 봇들도 입찰 제출하도록)
        BID_WAIT_SEC = 2.5
        await asyncio.sleep(BID_WAIT_SEC)

        # 3단계: 내가 winner인지 확인
        winner = self.claim_manager.get_winner(text_hash)
        if winner != self.org_id:
            logger.debug(f"[bid] {self.org_id} 패배 — winner: {winner}")
            return

        # 4단계: hash lock + message_id claim (race condition 최종 방지)
        if not self.claim_manager.try_claim(message_id, self.org_id, text_hash):
            return

        asyncio.get_event_loop().run_in_executor(None, self.claim_manager.cleanup_old_claims)

        # 4. 담당 선언 + 실행 (Claude Code가 팀 구성 자율 결정)
        await self.display.send_reply(update.message, f"✋ {self.org_id} 담당 — 팀 구성 중...")
        await self.memory_manager.add_log(f"사용자 메시지: {text[:200]}")

        runner = self._make_runner()
        system_prompt = self.identity.build_system_prompt()

        progress_msg = await self.display.send_reply(update.message, "⚙️ 처리 중...")
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
                    await self.display.edit_progress(progress_msg, f"⚙️ 작업 중...\n\n{display}", agent_id=self.org_id)
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

        # [TEAM:에이전트1,에이전트2,...] 태그 감지 → 팀 구성 공지
        if response:
            import re as _re
            team_match = _re.search(r'\[TEAM:([^\]]+)\]', response)
            if team_match:
                members = [m.strip() for m in team_match.group(1).split(',')]
                if members == ['solo']:
                    team_notice = f"👤 {self.org_id} 단독 처리"
                else:
                    member_lines = "\n".join(f"• {m}" for m in members)
                    team_notice = f"👥 팀 구성 완료\n{member_lines}"
                response = _re.sub(r'\[TEAM:[^\]]+\]', '', response).strip()
            else:
                # 태그 없으면 solo로 자동 처리
                team_notice = f"👤 {self.org_id} 단독 처리"
            try:
                await self.display.send_to_chat(context.bot, update.effective_chat.id, team_notice)
            except Exception as _e:
                logger.warning(f"팀 구성 공지 실패: {_e}")

        # [COLLAB:task|맥락:ctx] 태그 감지 → 협업 요청 채팅방 발송
        if response:
            import re as _re
            for match in _re.findall(r'\[COLLAB:([^\]]+)\]', response):
                parts = match.split("|맥락:", 1)
                collab_task = parts[0].strip()
                collab_ctx = parts[1].strip() if len(parts) > 1 else ""
                collab_msg = make_collab_request(collab_task, self.org_id, context=collab_ctx)
                try:
                    await self.display.send_to_chat(context.bot, update.effective_chat.id, collab_msg)
                except Exception as _e:
                    logger.warning(f"협업 요청 발송 실패: {_e}")
            response = _re.sub(r'\[COLLAB:[^\]]+\]', '', response).strip()

        if response:
            for chunk in _split_message(response, 4000):
                await self.display.send_reply(update.message, chunk)
            await self.memory_manager.add_log(f"claude 응답: {response[:200]}")
            await runner._auto_upload(response, self.token, self.allowed_chat_id)
            if self.bus:
                await self.bus.publish(Event(
                    type=EventType.TASK_RESULT,
                    source=self.org_id,
                    data={"response": response[:500], "message_id": message_id},
                ))

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
        runner = self._make_runner()
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

    async def on_command_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """설정 마법사 진입 — 메뉴 표시."""
        if update.message is None:
            return ConversationHandler.END
        keyboard = [
            [InlineKeyboardButton("📋 현재 봇 설정 보기", callback_data="setup_view")],
            [InlineKeyboardButton("🤖 새 조직 봇 추가 (토큰 입력)", callback_data="setup_add")],
            [InlineKeyboardButton("❌ 취소", callback_data="setup_cancel")],
        ]
        await update.message.reply_text(
            "🔧 *봇 설정 마법사*\n\n원하는 작업을 선택하세요:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return SETUP_MENU

    async def _setup_callback_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """메뉴 버튼 선택 처리."""
        query = update.callback_query
        await query.answer()

        if query.data == "setup_view":
            me = await query.bot.get_me()
            bot_name = me.username or "봇이름"
            d = self.identity._data
            msg = (
                f"🔧 *{self.org_id} 봇 현재 설정*\n\n"
                f"역할: {d.get('role', '미설정')}\n"
                f"전문분야: {', '.join(d.get('specialties', [])) or '미설정'}\n"
                f"방향성: {d.get('direction', '미설정')}\n\n"
                f"*설정 변경 명령어*\n"
                f"`/pm set@{bot_name} 역할|전문분야1,분야2|방향성`\n"
                f"`/org add@{bot_name} <이름> [engine]`\n\n"
                f"💡 그룹방에서는 `/명령어@{bot_name}` 형식으로 사용하세요."
            )
            await query.edit_message_text(msg, parse_mode="Markdown")
            return ConversationHandler.END

        elif query.data == "setup_add":
            await query.edit_message_text(
                "🤖 *새 조직 봇 추가*\n\n"
                "BotFather에서 발급받은 토큰을 입력하세요:\n\n"
                "⚠️ 보안: 토큰 메시지는 즉시 삭제됩니다.\n"
                "취소하려면 /cancel 을 입력하세요.",
                parse_mode="Markdown",
            )
            return SETUP_AWAIT_TOKEN

        else:  # setup_cancel
            await query.edit_message_text("❌ 설정 취소됨.")
            return ConversationHandler.END

    async def _setup_receive_token(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """토큰 수신 → 검증 → 등록 → 봇 실행."""
        if update.message is None:
            return SETUP_AWAIT_TOKEN

        token = (update.message.text or "").strip()

        # 보안: 토큰 메시지 즉시 삭제
        try:
            await update.message.delete()
        except Exception:
            pass

        processing_msg = await update.effective_chat.send_message("🔍 토큰 검증 중...")

        bot_info = await _validate_bot_token(token)
        if not bot_info:
            await processing_msg.edit_text(
                "❌ 유효하지 않은 토큰입니다.\n\n"
                "토큰을 다시 입력하거나 /cancel 로 취소하세요."
            )
            return SETUP_AWAIT_TOKEN

        username = bot_info["username"]
        bot_display = bot_info["first_name"]
        chat_id = update.effective_chat.id

        # 토큰 임시 저장 후 엔진 선택 단계로 진행
        context.user_data["setup_token"] = token
        context.user_data["setup_username"] = username
        context.user_data["setup_bot_display"] = bot_display
        context.user_data["setup_chat_id"] = chat_id

        keyboard = [
            [InlineKeyboardButton("1️⃣ Claude Code (기본, 권장)", callback_data="engine_claude-code")],
            [InlineKeyboardButton("2️⃣ Codex", callback_data="engine_codex")],
            [InlineKeyboardButton("3️⃣ Auto (자동 결정)", callback_data="engine_auto")],
        ]
        await processing_msg.edit_text(
            f"✅ 봇 확인: *@{username}*\n\n"
            f"⚙️ *실행 엔진을 선택하세요:*\n\n"
            f"1️⃣ `claude-code` — 복잡한 작업, 고품질 *(기본)*\n"
            f"2️⃣ `codex` — 단순한 작업, 저렴\n"
            f"3️⃣ `auto` — LLM이 자동 결정",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return SETUP_AWAIT_ENGINE

    async def _setup_receive_engine(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """엔진 선택 콜백 → 등록 완료."""
        query = update.callback_query
        await query.answer()

        engine = (query.data or "").replace("engine_", "") or "claude-code"
        token = context.user_data.get("setup_token", "")
        username = context.user_data.get("setup_username", "")
        bot_display = context.user_data.get("setup_bot_display", "")
        chat_id = context.user_data.get("setup_chat_id", 0)

        _engine_labels = {
            "claude-code": "Claude Code (omc /team)",
            "codex": "Codex",
            "auto": "자동 결정",
        }
        await query.edit_message_text(
            f"✅ 엔진 선택: `{engine}` — {_engine_labels.get(engine, engine)}\n\n⚙️ 등록 중...",
            parse_mode="Markdown",
        )

        try:
            env_key = f"BOT_TOKEN_{username.upper().replace('-', '_')}"
            _append_env_var(env_key, token)
            _create_bot_config(username, env_key, org_id=username, chat_id=chat_id, engine=engine)
            pid = _launch_bot_subprocess(token, username, chat_id)
            await _set_org_bot_commands(token)

            await query.edit_message_text(
                f"✅ *@{username} 등록 완료!*\n\n"
                f"봇 이름: {bot_display}\n"
                f"엔진: `{engine}` ({_engine_labels.get(engine, engine)})\n"
                f"PID: {pid}\n\n"
                f"봇이 시작되었습니다. 그룹방에 초대 후\n"
                f"`/start@{username}` 으로 초기화하세요.",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"봇 등록 실패: {e}")
            await query.edit_message_text(f"❌ 등록 실패: {e}")

        return ConversationHandler.END

    async def _setup_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """설정 마법사 취소."""
        if update.message:
            await update.message.reply_text("❌ 설정 취소됨.")
        return ConversationHandler.END

    # ── 앱 빌드 ───────────────────────────────────────────────────────────

    def build(self) -> Application:
        """텔레그램 Application 빌드."""
        from telegram.request import HTTPXRequest
        req = HTTPXRequest(connection_pool_size=1)
        self.app = Application.builder().token(self.token).request(req).build()

        # /setup 마법사 — ConversationHandler로 다단계 대화 처리
        setup_conv = ConversationHandler(
            entry_points=[CommandHandler("setup", self.on_command_setup)],
            states={
                SETUP_MENU: [
                    CallbackQueryHandler(self._setup_callback_menu, pattern="^setup_"),
                ],
                SETUP_AWAIT_TOKEN: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._setup_receive_token),
                    CommandHandler("cancel", self._setup_cancel),
                ],
                SETUP_AWAIT_ENGINE: [
                    CallbackQueryHandler(self._setup_receive_engine, pattern="^engine_"),
                    CommandHandler("cancel", self._setup_cancel),
                ],
            },
            fallbacks=[CommandHandler("cancel", self._setup_cancel)],
            per_chat=True,
            per_user=True,
            allow_reentry=True,
        )
        self.app.add_handler(setup_conv)

        self.app.add_handler(CommandHandler("start", self.on_command_start))
        self.app.add_handler(CommandHandler("status", self.on_command_status))
        self.app.add_handler(CommandHandler("reset", self.on_command_reset))
        self.app.add_handler(
            MessageHandler(filters.TEXT, self.on_message)  # 명령어 포함
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

        runner = self._make_runner()
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

    async def _handle_command(
        self, text: str, update, context
    ) -> None:
        """/ 명령어 처리 — 특정 봇 태그(/org@aiorg_pm_bot)도 지원."""
        import re as _re
        import os as _os
        cmd_full = text.strip().split()[0].lower()
        cmd = _re.sub(r'@\S+', '', cmd_full)  # /org@bot → /org
        arg = text[len(text.split()[0]):].strip()

        # 이 PM 대상이 아닌 태그된 명령어면 응답
        bot_tag = _re.search(r'@(\S+)', text.split()[0])
        if bot_tag:
            my_username = (await context.bot.get_me()).username or ""
            if bot_tag.group(1).lower() != my_username.lower():
                return  # 다른 봇 대상 명령어는 조용히 무시

        # /org — 조직 정체성 조회/설정
        if cmd == "/org":
            # @태그 없을 때 다중 PM 보호: default_handler만 처리
            pm_count = int(_os.environ.get("PM_COUNT", "1"))
            if not bot_tag and pm_count > 1:
                is_default = self.identity._data.get("default_handler", False)
                if not is_default:
                    return  # 다른 PM은 조용히 무시
                # default_handler가 경고 메시지 (설정 변경 없이)
                if arg and arg.lower() != "status":
                    await update.message.reply_text(
                        f"⚠️ PM이 {pm_count}개 있습니다. 특정 PM을 지정해주세요:\n"
                        f"`/org@봇이름 역할|전문분야|방향성`",
                        parse_mode="Markdown"
                    )
                    return

            if not arg or arg.lower() == "status":
                d = self.identity._data
                me = await context.bot.get_me()
                bot_name = me.username or "봇이름"
                msg = (
                    f"🏢 **{self.org_id} 조직 정체성**\n\n"
                    f"현재 설정:\n"
                    f"• 역할: {d.get('role','미설정')}\n"
                    f"• 전문분야: {', '.join(d.get('specialties', [])) or '미설정'}\n"
                    f"• 방향성: {d.get('direction','미설정')}\n\n"
                    f"⚙️ 설정 방법:\n"
                    f"`/org@{bot_name} 프로덕트PM|기획,UX|사용자중심`\n\n"
                    f"형식: `역할|전문분야1,분야2|방향성`\n"
                    f"예시:\n"
                    f"  • 개발PM|백엔드,API|빠른출시\n"
                    f"  • 디자인PM|UI,UX|사용자경험\n"
                    f"  • 마케팅PM|콘텐츠,SNS|성장"
                )
                await update.message.reply_text(msg, parse_mode="Markdown")
            else:
                # 자유 텍스트 → 정체성 업데이트 (빈 필드 skip)
                parts = [p.strip() for p in arg.split("|")]
                new_data: dict = {}
                if len(parts) >= 1 and parts[0]:
                    new_data["role"] = parts[0]
                if len(parts) >= 2 and parts[1]:
                    new_data["specialties"] = [s.strip() for s in parts[1].split(",") if s.strip()]
                if len(parts) >= 3 and parts[2]:
                    new_data["direction"] = parts[2]
                elif not new_data:
                    new_data["direction"] = arg  # 파이프 없으면 전체를 direction으로
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

        # /org add <이름> [engine] — 새 조직 등록
        if arg.lower().startswith("add ") or arg.lower() == "add":
            add_parts = arg.split(None, 2)  # ["add", <name>, <engine?>]
            if len(add_parts) < 2:
                await update.message.reply_text(
                    "사용법: `/org add <이름> [engine]`\n"
                    "engine: `claude-code` (기본) | `codex` | `auto`",
                    parse_mode="Markdown"
                )
                return
            new_org_id = add_parts[1].strip()
            raw_engine = add_parts[2].strip() if len(add_parts) >= 3 else "claude-code"
            _valid_engines = {"claude-code", "codex", "auto"}
            if raw_engine not in _valid_engines:
                await update.message.reply_text(
                    f"⚠️ 알 수 없는 engine: `{raw_engine}`\n"
                    f"사용 가능: `claude-code` | `codex` | `auto`",
                    parse_mode="Markdown"
                )
                return
            try:
                from core.org_registry import OrgRegistry
                registry = OrgRegistry()
                registry.load()
                registry.register_org(
                    org_id=new_org_id,
                    bot_token=self.token,
                    chat_id=self.allowed_chat_id,
                    specialties=["일반"],
                    engine=raw_engine,
                )
                _engine_labels = {"claude-code": "Claude Code (omc /team)", "codex": "Codex", "auto": "자동 결정"}
                await update.message.reply_text(
                    f"✅ **{new_org_id}** 조직 등록 완료!\n"
                    f"engine: `{raw_engine}` ({_engine_labels.get(raw_engine, raw_engine)})",
                    parse_mode="Markdown"
                )
            except Exception as _e:
                logger.error(f"조직 등록 실패: {_e}")
                await update.message.reply_text(f"❌ 조직 등록 실패: {_e}")
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

        # /pm — 다중 PM 관리
        if cmd == "/pm":
            parts = arg.split(None, 1)
            sub = parts[0].lower() if parts else "list"
            sub_arg = parts[1] if len(parts) > 1 else ""

            if not arg or sub == "list":
                me = await context.bot.get_me()
                bot_name = me.username or "봇이름"
                d = self.identity._data
                msg = (
                    f"🤖 **PM 정체성**\n\n"
                    f"현재 설정:\n"
                    f"• 역할: {d.get('role','미설정')}\n"
                    f"• 전문분야: {', '.join(d.get('specialties', [])) or '미설정'}\n"
                    f"• 방향성: {d.get('direction','미설정')}\n\n"
                    f"⚙️ 설정 방법:\n"
                    f"`/pm set@{bot_name} 역할|전문분야|방향성`\n\n"
                    f"예시:\n"
                    f"  • `/pm set@{bot_name} 시니어PM|모바일,앱|린스타트업`\n"
                    f"  • `/pm set@{bot_name} 주니어PM|기획,분석|데이터드리븐`\n\n"
                    f"_여러 PM이 있으면 각 봇마다 이 명령어가 표시됩니다_"
                )
                await update.message.reply_text(msg, parse_mode="Markdown")

            elif sub == "set":
                # /pm set 역할|전문분야|방향성
                fields = [f.strip() for f in sub_arg.split("|")]
                new_data: dict = {}
                if len(fields) >= 1 and fields[0]: new_data["role"] = fields[0]
                if len(fields) >= 2 and fields[1]: new_data["specialties"] = [s.strip() for s in fields[1].split(",")]
                if len(fields) >= 3 and fields[2]: new_data["direction"] = fields[2]
                if new_data:
                    self.identity.update(new_data)
                    d = self.identity._data
                    await update.message.reply_text(
                        f"✅ **{self.org_id} 업데이트!**\n"
                        f"역할: {d.get('role','')}\n"
                        f"전문분야: {', '.join(d.get('specialties',[]))}\n"
                        f"방향성: {d.get('direction','')}",
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text("사용법: `/pm set 역할|전문분야1,분야2|방향성`", parse_mode="Markdown")

            elif sub == "delete":
                await update.message.reply_text(
                    f"⚠️ PM 삭제는 봇을 그룹에서 내보내고\n"
                    f"`~/.ai-org/memory/pm_{self.org_id}.md` 삭제 후\n"
                    f"봇을 재시작하면 됩니다."
                )
            return

        # /prompt — 시스템 프롬프트 조회/수정
        if cmd == "/prompt":
            parts = arg.split(None, 1)
            sub = parts[0].lower() if parts else "show"
            sub_arg = parts[1] if len(parts) > 1 else ""

            if sub == "show" or not arg:
                prompt_text = self.identity.build_system_prompt()
                await update.message.reply_text(
                    f"📋 **현재 시스템 프롬프트 ({self.org_id})**\n\n{prompt_text[:3000]}",
                    parse_mode="Markdown",
                )
            elif sub == "add" and sub_arg:
                current = self.identity._data.get("direction", "") or ""
                new_direction = (current + "\n" + sub_arg).strip() if current else sub_arg
                self.identity.update({"direction": new_direction})
                await update.message.reply_text(
                    f"✅ direction에 추가됨:\n`{sub_arg}`\n\n현재 방향성:\n{new_direction}",
                    parse_mode="Markdown",
                )
            elif sub == "set" and sub_arg:
                self.identity.update({"direction": sub_arg})
                await update.message.reply_text(
                    f"✅ direction 교체됨:\n`{sub_arg}`",
                    parse_mode="Markdown",
                )
            elif sub == "reset":
                self.identity.update({"direction": ""})
                await update.message.reply_text("✅ direction 초기화됨.")
            else:
                await update.message.reply_text(
                    "사용법:\n"
                    "`/prompt show` — 현재 시스템 프롬프트 표시\n"
                    "`/prompt add <텍스트>` — direction에 추가\n"
                    "`/prompt set <텍스트>` — direction 전체 교체\n"
                    "`/prompt reset` — direction 초기화",
                    parse_mode="Markdown",
                )
            return

        # /help
        if cmd == "/help":
            import os as _os
            me = await context.bot.get_me()
            bot_name = me.username or "봇이름"
            pm_count = int(_os.environ.get("PM_COUNT", "1"))
            multibot_hint = (
                f"\n🤖 **그룹방 멀티봇 사용법**\n"
                f"`/명령어@{bot_name}` — 이 봇에게만 명령\n"
                f"`@{bot_name} 메시지` — 이 봇에게 메시지\n"
                f"봇 목록: PM_COUNT={pm_count}개 활성 중"
            ) if pm_count > 1 else (
                f"\n💡 그룹방에선 `/명령어@{bot_name}` 형식 사용 권장"
            )
            msg = (
                f"📋 **명령어 안내**\n\n"
                f"🔧 **설정**\n"
                f"`/org` — 조직 정체성 조회·설정\n"
                f"  예) `/org@{bot_name} 프로덕트PM|기획,UX|사용자중심`\n"
                f"`/pm` — PM 정체성 조회·설정\n"
                f"  예) `/pm set@{bot_name} 시니어PM|모바일|린스타트업`\n\n"
                f"📊 **조회**\n"
                f"`/status` — 봇 상태 확인\n"
                f"`/team` — 전체 팀 현황\n"
                f"`/agents` — 에이전트 목록\n\n"
                f"⚙️ **관리 (총괄PM만)**\n"
                f"`/setup` — 새 조직 봇 등록 마법사\n"
                f"`/reset` — 세션 초기화\n"
                + multibot_hint
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
            return



def _split_message(text: str, max_len: int) -> list[str]:
    """긴 메시지를 max_len 단위로 분할한다."""
    return [text[i : i + max_len] for i in range(0, len(text), max_len)]


# ── /setup 마법사 헬퍼 함수 ────────────────────────────────────────────────

async def _set_org_bot_commands(token: str) -> None:
    """새로 등록된 조직봇에 전용 명령어 세트를 자동으로 등록한다."""
    from telegram import Bot as _TGBot, BotCommand as _BotCommand
    org_commands = [
        _BotCommand("status", "봇 상태 확인"),
        _BotCommand("org", "조직 정체성 설정"),
        _BotCommand("pm", "PM 정체성 설정"),
        _BotCommand("prompt", "시스템 프롬프트 조회/수정"),
        _BotCommand("team", "현재 팀 전략 확인"),
        _BotCommand("help", "명령어 안내"),
        _BotCommand("reset", "세션 초기화"),
    ]
    try:
        bot = _TGBot(token=token)
        await bot.set_my_commands(org_commands)
        logger.info(f"조직봇 명령어 자동 등록 완료: {[c.command for c in org_commands]}")
    except Exception as e:
        logger.warning(f"조직봇 명령어 등록 실패 (무시): {e}")


async def _validate_bot_token(token: str) -> dict | None:
    """토큰으로 봇 정보를 조회한다. 유효하지 않으면 None 반환."""
    from telegram import Bot as _TGBot
    try:
        bot = _TGBot(token=token)
        me = await bot.get_me()
        return {"username": me.username, "first_name": me.first_name, "id": me.id}
    except Exception:
        return None


def _append_env_var(key: str, value: str) -> None:
    """.env 파일에 환경변수를 추가한다. 이미 존재하면 덮어쓴다."""
    env_path = Path(__file__).parent.parent / ".env"
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    new_lines = [line for line in lines if not line.startswith(f"{key}=")]
    new_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(new_lines) + "\n")


def _create_bot_config(username: str, token_env: str, org_id: str, chat_id: int, engine: str = "claude-code") -> None:
    """bots/ 디렉토리에 봇 설정 YAML 파일을 생성한다."""
    import datetime
    bots_dir = Path(__file__).parent.parent / "bots"
    bots_dir.mkdir(exist_ok=True)
    config_path = bots_dir / f"{username}.yaml"
    config_path.write_text(
        f"# 자동 생성 봇 설정 — {datetime.datetime.now().isoformat()}\n"
        f"username: \"{username}\"\n"
        f"org_id: \"{org_id}\"\n"
        f"token_env: \"{token_env}\"\n"
        f"chat_id: {chat_id}\n"
        f"engine: \"{engine}\"\n"
    )


def _launch_bot_subprocess(token: str, org_id: str, chat_id: int) -> int:
    """새 봇 프로세스를 시작하고 PID를 반환한다."""
    import subprocess as _subprocess
    import sys as _sys
    project_dir = Path(__file__).parent.parent
    env = {
        **os.environ,
        "PM_BOT_TOKEN": token,
        "TELEGRAM_GROUP_CHAT_ID": str(chat_id),
        "PM_ORG_NAME": org_id,
    }
    proc = _subprocess.Popen(
        [_sys.executable, str(project_dir / "main.py")],
        env=env,
        stdout=_subprocess.DEVNULL,
        stderr=_subprocess.DEVNULL,
        cwd=str(project_dir),
    )
    pid_dir = Path.home() / ".ai-org" / "bots"
    pid_dir.mkdir(parents=True, exist_ok=True)
    (pid_dir / f"{org_id}.pid").write_text(str(proc.pid))
    return proc.pid


class _CodexRunnerAdapter:
    """CodexRunner를 ClaudeCodeRunner와 동일한 run_task 인터페이스로 감싸는 어댑터."""

    def __init__(self, codex_runner) -> None:
        self._runner = codex_runner

    async def run_task(
        self,
        task: str,
        system_prompt: str = "",
        progress_callback=None,
        session_store=None,
        global_context=None,
        org_id: str = "global",
    ) -> str:
        full_prompt = f"{system_prompt}\n\n{task}".strip() if system_prompt else task
        result = await self._runner.run(full_prompt)
        if progress_callback:
            await progress_callback(result[:200])
        return result

    async def _auto_upload(self, response: str, token: str, chat_id: int) -> None:
        """Codex runner는 자동 업로드 미지원 — no-op."""
