"""Worker Bot — workers.yaml 기반 동적 워커."""
from __future__ import annotations

from loguru import logger
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from core.context_db import ContextDB
from core.message_schema import OrgMessage


class WorkerBot:
    """동적 워커 봇.

    workers.yaml에서 name/token/engine/description을 읽어 WorkerRegistry가 생성.
    engine에 따라 ClaudeCodeRunner 또는 CodexRunner로 태스크 실행.
    """

    def __init__(self, handle: str, token: str, engine: str = "claude-code", description: str = "") -> None:
        self.handle = handle          # "@cokac_bot"
        self.token = token
        self.engine = engine          # "claude-code" | "codex" | "both"
        self.description = description
        self.group_chat_id: int | None = None
        self.context_db = ContextDB()
        self.app: Application | None = None

    def set_group_chat_id(self, chat_id: int) -> None:
        self.group_chat_id = chat_id

    async def execute(self, task_id: str, content: str, context: dict | None) -> str:
        """engine에 따라 적절한 러너로 태스크 실행."""
        prompt = content
        if context:
            prompt = f"[배경 컨텍스트]\n{context.get('content', '')}\n\n[태스크]\n{content}"

        if self.engine == "codex":
            return await self._run_codex(prompt)
        elif self.engine == "both":
            # PM이 "both"로 지정 시 claude-code 우선 (fallback: codex)
            result = await self._run_claude(prompt)
            if result.startswith("❌"):
                logger.info(f"{self.handle} Claude 실패, Codex로 폴백")
                result = await self._run_codex(prompt)
            return result
        else:  # "claude-code" (기본값)
            return await self._run_claude(prompt)

    async def _run_claude(self, prompt: str) -> str:
        from tools.claude_code_runner import ClaudeCodeRunner
        runner = ClaudeCodeRunner()
        return await runner.run(prompt)

    async def _run_codex(self, prompt: str) -> str:
        from tools.codex_runner import CodexRunner
        runner = CodexRunner()
        return await runner.run(prompt)

    async def send_report(self, task_id: str, result: str) -> None:
        """PM Bot에게 결과 보고."""
        if self.app is None or self.group_chat_id is None:
            raise RuntimeError("봇이 초기화되지 않음")
        msg = OrgMessage(
            to="@pm_bot",
            from_=self.handle,
            task_id=task_id,
            msg_type="report",
            content=result,
        )
        await self.app.bot.send_message(
            chat_id=self.group_chat_id,
            text=msg.to_telegram_text(),
        )
        logger.info(f"{self.handle} 보고 전송: {task_id}")

    async def send_ack(self, task_id: str) -> None:
        """완료 확인 ACK 전송."""
        if self.app is None or self.group_chat_id is None:
            raise RuntimeError("봇이 초기화되지 않음")
        msg = OrgMessage(
            to="@pm_bot",
            from_=self.handle,
            task_id=task_id,
            msg_type="ack",
            content=f"✅ {self.handle} 담당 파트 완료 확인",
        )
        await self.app.bot.send_message(
            chat_id=self.group_chat_id,
            text=msg.to_telegram_text(),
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """메시지 수신 처리."""
        if update.message is None:
            return
        text = update.message.text or ""

        org_msg = OrgMessage.parse_telegram_text(text)
        if org_msg is None:
            return

        if not org_msg.is_addressed_to(self.handle):
            return

        if org_msg.msg_type == "assign":
            await self._handle_assign(org_msg)
        elif org_msg.msg_type == "query":
            await self.send_ack(org_msg.task_id)

    async def _handle_assign(self, org_msg: OrgMessage) -> None:
        """태스크 할당 처리."""
        logger.info(f"{self.handle} 태스크 수신: {org_msg.task_id}")

        ctx = None
        if org_msg.context_ref:
            ctx = await self.context_db.read_context(org_msg.context_ref)

        try:
            result = await self.execute(org_msg.task_id, org_msg.content, ctx)
            await self.send_report(org_msg.task_id, result)
        except Exception as e:
            logger.error(f"{self.handle} 실행 오류: {e}")
            await self.send_report(org_msg.task_id, f"❌ 실행 실패: {e}")

    def build(self, group_chat_id: int) -> Application:
        """애플리케이션 빌드."""
        self.group_chat_id = group_chat_id
        self.app = Application.builder().token(self.token).build()
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        return self.app

    async def run(self, group_chat_id: int) -> None:
        """봇 실행."""
        await self.context_db.initialize()
        app = self.build(group_chat_id)
        logger.info(f"{self.handle} 시작... (engine={self.engine})")
        await app.run_polling()
