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
from core.llm_provider import LLMProvider, get_provider

DEFAULT_CONFIDENCE_THRESHOLD = 6

GREETING_PATTERNS = GREETING_KW

# 모듈 수준 캐싱 — 매번 생성 금지
_provider: LLMProvider | None = get_provider()


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

        # LLM provider가 없으면 즉시 keyword fallback
        if _provider is None:
            return self._keyword_score(message, specialties)

        # LLM 엔진으로 자율 판단
        try:
            score = await asyncio.wait_for(
                self._engine_score(message, specialties),
                timeout=15.0,
            )
            logger.debug(f"[confidence] engine score: {score}")
            return score
        except Exception as e:
            logger.warning(f"[confidence] engine 판단 실패, keyword fallback: {e}")
            return self._keyword_score(message, specialties)

    async def _engine_score(self, message: str, specialties: list[str]) -> int:
        """LLMProvider.complete()으로 자율 판단. 초단순 프롬프트."""
        specs = ", ".join(specialties)
        prompt = f"Reply with a single integer 0-10 only. No explanation. How relevant is this message to [{specs}] expert? Message: '{message}'"

        raw = await _provider.complete(prompt, timeout=12.0)  # type: ignore[union-attr]
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
