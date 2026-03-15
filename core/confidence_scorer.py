"""메시지에 대한 PM 담당 confidence 계산 (0-10).

각 봇이 자율 판단. LLMProvider 추상화 레이어로 Gemini/OpenAI/Anthropic/DeepSeek/Ollama 자동 선택.
LLMProvider 없으면 keyword fallback 유지.
"""
from __future__ import annotations

import asyncio
import re

from loguru import logger

from core.pm_identity import PMIdentity
from core.keywords import GREETING_KW
from core.pm_decision import PMDecisionClient

DEFAULT_CONFIDENCE_THRESHOLD = 6

GREETING_PATTERNS = GREETING_KW
_decision_clients: dict[str, PMDecisionClient] = {}


class ConfidenceScorer:
    """각 봇이 자기 AI 엔진으로 자율적으로 담당 여부 판단."""

    async def score(self, message: str, identity: PMIdentity) -> int:
        specialties = identity._data.get("specialties", [])

        # 짧은 인사말 → 0점 (greeting handler가 처리)
        msg = message.lower()
        if len(message) < 20 and any(p in msg for p in GREETING_PATTERNS):
            return 0

        # specialties 없으면 keyword fallback
        if not specialties:
            return 3

        org_id = identity._data.get("org_id") or "global"
        decision_client = _decision_clients.get(org_id)
        if decision_client is None:
            try:
                decision_client = PMDecisionClient(org_id=org_id, engine="auto", session_store=None)
                _decision_clients[org_id] = decision_client
            except Exception as e:
                logger.warning(f"[confidence] decision client 초기화 실패, keyword fallback: {e}")
                return self._keyword_score(message, specialties)

        try:
            score = await asyncio.wait_for(
                self._engine_score(message, specialties, decision_client),
                timeout=15.0,
            )
            logger.debug(f"[confidence] engine score: {score}")
            return score
        except Exception as e:
            logger.warning(f"[confidence] org engine 판단 실패, keyword fallback: {e}")
            return self._keyword_score(message, specialties)

    async def _engine_score(
        self,
        message: str,
        specialties: list[str],
        decision_client: PMDecisionClient,
    ) -> int:
        """조직 엔진으로 relevance score를 판단한다."""
        specs = ", ".join(specialties)
        prompt = f"Reply with a single integer 0-10 only. No explanation. How relevant is this message to [{specs}] expert? Message: '{message}'"

        raw = await decision_client.complete(prompt)
        m = re.search(r"\d+", raw)
        score = int(m.group()) if m else 0
        return max(0, min(10, score))

    def _keyword_score(self, message: str, specialties: list[str]) -> int:
        """keyword 양방향 매칭 fallback."""
        msg = message.lower()
        msg_words = [w for w in re.split(r"\s+", msg) if len(w) >= 2]
        matched = sum(
            1 for sp in specialties
            if sp.lower() in msg
            or any(w in sp.lower() for w in msg_words)
        )
        if matched == 0:
            return 2
        elif matched == 1:
            return 6
        elif matched == 2:
            return 8
        else:
            return 10
