"""PM Bot — 오케스트레이터."""
from __future__ import annotations

import json
import os

from loguru import logger
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from core.completion import CompletionProtocol
from core.llm_router import LLMRouter
from core.context_db import ContextDB
from core.message_schema import OrgMessage
from core.task_manager import TaskManager, TaskStatus
from core.worker_registry import WorkerRegistry


class PMBot:
    """PM Bot: 유저 요청 → 태스크 분해 → WorkerRegistry에서 적합한 워커 선택 → 할당."""

    def __init__(self) -> None:
        self.token = os.environ["PM_BOT_TOKEN"]
        self.group_chat_id = int(os.environ["TELEGRAM_GROUP_CHAT_ID"])
        self.task_manager = TaskManager()
        self.context_db = ContextDB()
        self.app: Application | None = None
        self.completion: CompletionProtocol | None = None

        # 동적 워커 레지스트리
        self.registry = WorkerRegistry()
        self.workers = self.registry.load()
        self.router = LLMRouter()

    async def _select_workers(self, task_description: str) -> list[str]:
        """LLM으로 태스크 분석 → 최적 워커 자율 선택."""
        available = self.registry.list_workers()
        if not available:
            logger.warning("등록된 워커 없음 — 태스크 할당 불가")
            return []

        try:
            handles = await self.router.route_simple(task_description, available)
            if handles:
                logger.info(f"LLM 워커 선택: {handles}")
                return handles
        except Exception as e:
            logger.warning(f"LLM 라우팅 실패, 키워드 폴백: {e}")

        # 폴백: 키워드 매칭
        task_lower = task_description.lower()
        for worker in available:
            desc_lower = worker["description"].lower()
            keywords = [kw.strip() for kw in desc_lower.replace(",", " ").split() if len(kw) > 2]
            if any(kw in task_lower for kw in keywords):
                return [worker["handle"]]
        return [available[0]["handle"]]

    async def send_org_message(self, msg: OrgMessage) -> None:
        """구조화된 OrgMessage를 그룹에 전송."""
        if self.app is None:
            raise RuntimeError("봇이 초기화되지 않음")
        await self.app.bot.send_message(
            chat_id=self.group_chat_id,
            text=msg.to_telegram_text(),
        )

    async def send_text(self, text: str) -> None:
        """일반 텍스트 메시지 전송."""
        if self.app is None:
            raise RuntimeError("봇이 초기화되지 않음")
        await self.app.bot.send_message(chat_id=self.group_chat_id, text=text)

    async def handle_user_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """유저 메시지 처리 → 태스크 생성 → 적합한 워커 봇 할당."""
        if update.message is None or update.effective_user is None:
            return

        user_text = update.message.text or ""
        user_name = update.effective_user.username or "unknown"

        # 봇 메시지 무시
        if "[TO:" in user_text and "[FROM:" in user_text:
            return

        logger.info(f"유저 메시지 수신: @{user_name}: {user_text[:100]}")

        # 적합한 워커 선택
        worker_handles = await self._select_workers(user_text)
        if not worker_handles:
            await self.send_text("❌ 현재 사용 가능한 워커 봇이 없습니다. `workers.yaml`을 확인하세요.")
            return

        # 태스크 생성
        task = await self.task_manager.create_task(
            description=user_text,
            assigned_to=worker_handles,
        )

        # Context DB에 저장
        await self.context_db.create_project(task.id, f"Task {task.id}")
        await self.context_db.write_context(
            slot_id=f"{task.id}_request",
            project_id=task.id,
            slot_type="user_request",
            content=user_text,
        )

        # Worker 봇에 할당
        assign_msg = OrgMessage(
            to=worker_handles,
            from_="@pm_bot",
            task_id=task.id,
            msg_type="assign",
            content=user_text,
            context_ref=f"{task.id}_request",
        )
        await self.send_org_message(assign_msg)
        await self.task_manager.update_status(task.id, TaskStatus.RUNNING)
        logger.info(f"태스크 {task.id} 할당 완료 → {worker_handles}")

    async def handle_bot_report(self, org_msg: OrgMessage) -> None:
        """Worker 봇의 보고 처리."""
        task = self.task_manager.get_task(org_msg.task_id)
        if task is None:
            logger.warning(f"알 수 없는 태스크 ID: {org_msg.task_id}")
            return

        if org_msg.msg_type == "report":
            await self.task_manager.update_status(org_msg.task_id, TaskStatus.DONE, result=org_msg.content)
            if self.completion:
                await self.completion.initiate_completion(task)

        elif org_msg.msg_type == "ack":
            if self.completion:
                await self.completion.receive_ack(org_msg.task_id, org_msg.from_)

    async def handle_group_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """그룹 내 모든 메시지 감청."""
        if update.message is None:
            return
        text = update.message.text or ""

        org_msg = OrgMessage.parse_telegram_text(text)
        if org_msg and org_msg.from_ != "@pm_bot":
            await self.handle_bot_report(org_msg)
            return

        await self.handle_user_message(update, context)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            workers = self.registry.list_workers()
            worker_lines = "\n".join(
                f"  • {w['handle']} ({w['engine']}) — {w['description']}"
                for w in workers
            ) or "  (워커 없음 — workers.yaml 확인)"
            await update.message.reply_text(
                f"🤖 PM Bot 온라인. AI 조직 준비 완료.\n\n"
                f"현재 워커 팀:\n{worker_lines}\n\n"
                f"요청사항을 입력하면 적합한 팀원에게 태스크를 할당합니다."
            )

    def build(self) -> Application:
        """애플리케이션 빌드."""
        self.app = Application.builder().token(self.token).build()
        self.completion = CompletionProtocol(self.task_manager, self.send_text)

        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_group_message))

        return self.app

    async def run(self) -> None:
        """봇 실행."""
        await self.context_db.initialize()
        app = self.build()
        logger.info(f"PM Bot 시작... (워커 {len(self.workers)}개)")
        await app.run_polling()
