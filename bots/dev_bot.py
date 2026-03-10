"""Dev Bot — 코딩 전담 봇."""
from __future__ import annotations

from loguru import logger

from core.worker_bot import WorkerBot
from tools.claude_code_runner import ClaudeCodeRunner


class DevBot(WorkerBot):
    """개발/코딩 전담 Worker Bot.

    Claude Code를 실행하여 실제 코딩 작업 수행.
    """

    def __init__(self) -> None:
        super().__init__(handle="@dev_bot", token_env_var="DEV_BOT_TOKEN")
        self.runner = ClaudeCodeRunner()

    async def execute(self, task_id: str, content: str, context: dict | None) -> str:
        """Claude Code로 코딩 태스크 실행."""
        logger.info(f"Dev Bot 실행: {task_id} — {content[:80]}...")

        # 컨텍스트를 프롬프트에 포함
        prompt = content
        if context:
            prompt = f"[배경 컨텍스트]\n{context.get('content', '')}\n\n[태스크]\n{content}"

        result = await self.runner.run(prompt)
        return result


async def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()
    bot = DevBot()
    await bot.run()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
