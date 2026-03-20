"""LLM-based PM message router — replaces ALL keyword matching in telegram_relay.py.

Instead of brittle keyword arrays, a single LLM call decides:
- What the user intends (new task, confirm pending, retry task, status, chat)
- What parameters to extract (task_id, etc.)

Returns structured PMRoute dataclass consumed by telegram_relay.py.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Any

from loguru import logger

from core.pm_decision import DecisionClientProtocol

ROUTE_ACTIONS = Literal["new_task", "retry_task", "confirm_pending", "status_query", "chat"]

_PROMPT_TEMPLATE = """\
You are a routing AI for a PM bot. Given a user message and context, return JSON only.

Actions:
- "new_task": user wants something new done
- "retry_task": user wants to retry a specific failed task (extract task_id from context if available)
- "confirm_pending": user is confirming/approving a pending proposal (yes/ok/do it)
- "status_query": user asks about current state/progress
- "chat": casual conversation, not a task

Context:
{context_json}

User message: {text}

Rules:
- Short affirmatives (응/ㅇㅇ/네/해줘/ok/yes/그래/좋아) when pending_confirmation exists in context → confirm_pending
- Messages mentioning retry/다시해줘/고쳐/재시도 + task reference → retry_task
- Questions about progress/status → status_query
- Everything else with substantive content → new_task
- Very short casual messages with no task intent → chat

Return ONLY valid JSON in this exact format (no explanation):
{{"action": "<action>", "task_id": null, "confidence": 0.9}}

If action is retry_task and you can identify a task_id from context, include it as a string.
"""


@dataclass
class PMRoute:
    action: ROUTE_ACTIONS
    task_id: str | None = None
    confidence: float = 1.0
    raw: str = ""


class PMRouter:
    """LLM-based message router. Falls back to 'new_task' if LLM is unavailable or fails."""

    def __init__(self, decision_client: DecisionClientProtocol | None = None) -> None:
        self._decision_client = decision_client

    async def route(self, text: str, context: dict[str, Any] | None = None) -> PMRoute:
        """메시지를 라우팅. LLM 실패 시 new_task로 폴백."""
        ctx = context or {}
        if self._decision_client is None:
            return self._fallback(text, ctx)

        prompt = _PROMPT_TEMPLATE.format(
            context_json=json.dumps(ctx, ensure_ascii=False, default=str),
            text=text,
        )

        try:
            raw = await self._decision_client.complete(prompt)
            return self._parse(raw)
        except Exception as e:
            logger.warning(f"[pm_router] LLM 라우팅 실패 ({e}), fallback 사용")
            return self._fallback(text, ctx)

    def _parse(self, raw: str) -> PMRoute:
        """LLM JSON 응답 파싱."""
        try:
            # JSON 블록 추출 (마크다운 코드블록 대응)
            text = raw.strip()
            if "```" in text:
                import re
                m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
                if m:
                    text = m.group(1).strip()
            # 첫 번째 { ... } 블록만 추출
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                text = text[start:end]
            data = json.loads(text)
            action = data.get("action", "new_task")
            valid_actions = {"new_task", "retry_task", "confirm_pending", "status_query", "chat"}
            if action not in valid_actions:
                action = "new_task"
            return PMRoute(
                action=action,
                task_id=data.get("task_id") or None,
                confidence=float(data.get("confidence", 0.8)),
                raw=raw,
            )
        except Exception as e:
            logger.warning(f"[pm_router] 파싱 실패 ({e}): {raw[:100]}")
            return PMRoute(action="new_task", confidence=0.5, raw=raw)

    def _fallback(self, text: str, ctx: dict) -> PMRoute:
        """LLM 없을 때 간단한 휴리스틱 폴백."""
        t = text.strip().lower()
        # pending이 있을 때 단순 긍정어 → confirm
        if ctx.get("pending_confirmation"):
            affirm = ["응", "ㅇㅇ", "네", "예", "그래", "해줘", "맞아", "좋아", "ok", "yes", "응 해줘", "그렇게 해", "해"]
            if len(t) <= 15 and any(kw in t for kw in affirm):
                return PMRoute(action="confirm_pending", confidence=0.9)
        # 재시도 키워드
        retry_kw = ["다시해줘", "재시도", "retry", "다시 해줘", "다시해", "fix this"]
        if any(kw in t for kw in retry_kw):
            return PMRoute(action="retry_task", confidence=0.8)
        # 상태 조회
        status_kw = ["상태", "진행", "status", "어떻게 되고 있", "현황"]
        if any(kw in t for kw in status_kw):
            return PMRoute(action="status_query", confidence=0.7)
        return PMRoute(action="new_task", confidence=0.6)
