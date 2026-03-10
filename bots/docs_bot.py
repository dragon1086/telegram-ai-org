"""Docs Bot — 문서화 전담 봇."""
from __future__ import annotations

from loguru import logger

from core.worker_bot import WorkerBot


class DocsBot(WorkerBot):
    """문서화/README 전담 Worker Bot."""

    def __init__(self) -> None:
        super().__init__(handle="@docs_bot", token_env_var="DOCS_BOT_TOKEN")

    async def execute(self, task_id: str, content: str, context: dict | None) -> str:
        """문서 생성 태스크 실행."""
        logger.info(f"Docs Bot 실행: {task_id}")

        # TODO: Claude API로 문서 생성
        # 현재는 기본 마크다운 템플릿 반환
        doc = f"""# 작업 결과 문서 ({task_id})

## 개요
{content}

## 구현 내용
(dev_bot 결과를 기반으로 자동 생성 예정)

## 사용 방법
TBD

---
*telegram-ai-org docs_bot 자동 생성*
"""
        return f"문서 초안 생성 완료:\n{doc[:500]}..."


async def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()
    bot = DocsBot()
    await bot.run()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
