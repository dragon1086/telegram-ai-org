"""Worker Bot 베이스 클래스."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod

from loguru import logger
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from core.context_db import ContextDB
from core.message_schema import OrgMessage


class WorkerBot(ABC):
    """Worker 봇 베이스 클래스.

    상속하여 execute() 메서드를 구현하면 새 봇 추가 가능.
    """

    def __init__(self, handle: str, token_env_var: str) -> None:
        self.handle = handle  # "@dev_bot"
        self.token = os.environ[token_env_var]
        self.group_chat_id = int(os.environ["TELEGRAM_GROUP_CHAT_ID"])
        self.context_db = ContextDB()
        self.app: Application | None = None

    @abstractmethod
    async def execute(self, task_id: str, content: str, context: dict | None) -> str:
        """태스크 실행. 결과 문자열 반환."""
        ...

    async def send_report(self, task_id: str, result: str) -> None:
        """PM Bot에게 결과 보고."""
        if self.app is None:
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
        if self.app is None:
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

        # 나에게 온 메시지인지 확인
        if not org_msg.is_addressed_to(self.handle):
            return

        if org_msg.msg_type == "assign":
            await self._handle_assign(org_msg)
        elif org_msg.msg_type == "query":
            # 완료 확인 요청 → ACK 전송
            await self.send_ack(org_msg.task_id)

    async def _handle_assign(self, org_msg: OrgMessage) -> None:
        """태스크 할당 처리."""
        logger.info(f"{self.handle} 태스크 수신: {org_msg.task_id}")

        # 컨텍스트 로드
        ctx = None
        if org_msg.context_ref:
            ctx = await self.context_db.read_context(org_msg.context_ref)

        try:
            result = await self.execute(org_msg.task_id, org_msg.content, ctx)
            await self.send_report(org_msg.task_id, result)
        except Exception as e:
            logger.error(f"{self.handle} 실행 오류: {e}")
            await self.send_report(org_msg.task_id, f"❌ 실행 실패: {e}")

    def build(self) -> Application:
        """애플리케이션 빌드."""
        self.app = Application.builder().token(self.token).build()
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        return self.app

    async def run(self) -> None:
        """봇 실행."""
        await self.context_db.initialize()
        app = self.build()
        logger.info(f"{self.handle} 시작...")
        await app.run_polling()
