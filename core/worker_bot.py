"""Worker Bot — workers.yaml 기반 동적 워커."""
from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from core.context_db import ContextDB
from core.message_schema import OrgMessage
from core.telegram_formatting import markdown_to_html

if TYPE_CHECKING:
    from core.group_chat_hub import GroupChatHub, GroupMessage


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
        self._hub: GroupChatHub | None = None  # 그룹채팅 허브 (set_group_hub로 등록)

    def set_group_chat_id(self, chat_id: int) -> None:
        self.group_chat_id = chat_id

    def set_group_hub(self, hub: GroupChatHub, domain_keywords: list[str] | None = None) -> None:
        """GroupChatHub에 이 봇을 참가자로 등록.

        Args:
            hub: 그룹채팅 허브 인스턴스.
            domain_keywords: 이 봇의 전문 영역 키워드 (예: ["코드","버그","API"]).
        """
        from core.group_chat_hub import GroupChatHub as _Hub  # noqa: F401

        self._hub = hub
        hub.register_participant(
            bot_id=self.handle,
            speak_callback=self._group_speak_callback,
            domain_keywords=domain_keywords,
        )
        logger.info(f"[WorkerBot] {self.handle} 그룹 허브 등록 완료")

    async def _group_speak_callback(self, topic: str, context: list[GroupMessage]) -> str | None:
        """GroupChatHub로부터 발언 요청을 받을 때 호출되는 콜백.

        topic: 회의 주제 or 그룹방 메시지.
        context: 최근 대화 이력.
        반환값: 발언 내용 문자열 or None (발언 안 함).
        """
        ctx_text = "\n".join(f"[{m.from_bot}]: {m.text}" for m in context[-6:])
        prompt = (
            f"[그룹 회의/토론]\n"
            f"주제: {topic}\n\n"
            f"최근 대화:\n{ctx_text}\n\n"
            f"당신은 {self.handle} 봇입니다. {self.description}\n"
            f"위 맥락에서 본인의 역할에 맞게 간결하게 발언해주세요. (최대 300자)"
        )
        try:
            result = await self.execute(f"group-{id(topic)}", prompt, None)
            return (result or "").strip()[:300] or None
        except Exception as e:
            logger.error(f"[WorkerBot] {self.handle} 그룹 발언 실패: {e}")
            return None

    async def send_to_group(self, text: str) -> None:
        """그룹방에 직접 메시지 전송."""
        if self.app is None or self.group_chat_id is None:
            logger.warning(f"[WorkerBot] {self.handle} 그룹 미초기화")
            return
        from core.telegram_formatting import markdown_to_html as _mth
        await self.app.bot.send_message(
            chat_id=self.group_chat_id,
            text=_mth(text),
            parse_mode="HTML",
        )

    async def execute(self, task_id: str, content: str, context: dict | None) -> str:
        """engine에 따라 적절한 러너로 태스크 실행."""
        # context가 없으면 context_db에서 프로젝트 컨텍스트 조회
        if context is None:
            try:
                ctx_data = await self.context_db.read_context(task_id)
                if ctx_data:
                    context = {"content": ctx_data.get("content", "")}
            except Exception:
                pass

        prompt = content
        if context:
            prompt = f"[배경 컨텍스트]\n{context.get('content', '')}\n\n[태스크]\n{content}"

        from tools.base_runner import RunnerFactory, RunContext, RunnerError

        if self.engine == "both":
            try:
                return await RunnerFactory.create("claude-code").run(RunContext(prompt=prompt))
            except RunnerError:
                logger.info(f"{self.handle} Claude failed, falling back to codex")
                return await RunnerFactory.create("codex").run(RunContext(prompt=prompt))
        else:
            runner = RunnerFactory.create(self.engine)
            return await runner.run(RunContext(prompt=prompt))

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
            text=markdown_to_html(msg.to_telegram_text()),
            parse_mode="HTML",
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
            text=markdown_to_html(msg.to_telegram_text()),
            parse_mode="HTML",
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
