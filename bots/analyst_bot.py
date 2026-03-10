"""Analyst Bot — 분석/리서치 전담 봇."""
from __future__ import annotations

from loguru import logger

from core.worker_bot import WorkerBot
from tools.amp_caller import AmpCaller


class AnalystBot(WorkerBot):
    """분석/리서치 전담 Worker Bot."""

    def __init__(self) -> None:
        super().__init__(handle="@analyst_bot", token_env_var="ANALYST_BOT_TOKEN")
        self.amp = AmpCaller()

    async def execute(self, task_id: str, content: str, context: dict | None) -> str:
        """amp MCP로 분석 태스크 실행."""
        logger.info(f"Analyst Bot 실행: {task_id}")
        result = await self.amp.query(content)
        return result


async def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()
    bot = AnalystBot()
    await bot.run()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
