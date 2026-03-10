"""LLM-based task router — PM이 유저 요청을 분석해 워커에게 지시 분배."""
from __future__ import annotations

import json
import os

from openai import AsyncOpenAI


SYSTEM_PROMPT = """You are a PM (Project Manager) for an AI team operating over Telegram.

Your job: analyze the user's request and decide which workers should handle it,
and what specific instructions each worker should receive.

Respond ONLY with valid JSON in this exact format:
{
  "analysis": "brief analysis of the request",
  "assignments": [
    {
      "worker_name": "worker name from the list",
      "instruction": "specific, actionable instruction for this worker",
      "priority": "high|medium|low"
    }
  ],
  "completion_criteria": "how to know when the overall task is done"
}
"""


class LLMRouter:
    """GPT/Claude로 태스크를 분석하고 워커에게 분배하는 라우터."""

    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        self.model = os.environ.get("PM_MODEL", "gpt-4o")

    async def route(self, user_request: str, workers: list[dict]) -> dict:
        """유저 요청 → 워커별 지시 분배.

        Returns:
            {
                "analysis": str,
                "assignments": [{"worker_name", "instruction", "priority"}],
                "completion_criteria": str
            }
        """
        if not workers:
            return {
                "analysis": "No workers available",
                "assignments": [],
                "completion_criteria": "N/A",
            }

        worker_list = "\n".join(
            f"- {w['name']} (engine: {w['engine']}): {w['description']}"
            for w in workers
        )

        user_content = f"""Available workers:
{worker_list}

User request:
{user_request}

Analyze and assign tasks to the appropriate workers."""

        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        content = resp.choices[0].message.content or "{}"
        return json.loads(content)

    async def route_simple(self, user_request: str, workers: list[dict]) -> list[str]:
        """단순화된 버전 — 워커 이름 목록만 반환."""
        result = await self.route(user_request, workers)
        return [a["worker_name"] for a in result.get("assignments", [])]
