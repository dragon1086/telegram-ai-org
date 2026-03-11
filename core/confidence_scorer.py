"""메시지에 대한 PM 담당 confidence 계산 (0-10)."""
from __future__ import annotations

import os
import re

from loguru import logger

from core.pm_identity import PMIdentity

DEFAULT_CONFIDENCE_THRESHOLD = 6  # 이 점수 이상이어야 claim

# 짧은 인사말 패턴 — 담당 없음 (0점)
GREETING_PATTERNS = ["안녕", "hi", "hello", "잘 지내", "뭐해", "왔어", "있어?", "ㅎㅇ", "반가"]


class ConfidenceScorer:
    """메시지에 대한 이 PM의 담당 confidence 계산 (0-10)."""

    SCORING_PROMPT = """\
당신은 {org_id} PM입니다.
전문분야: {specialties}

다음 메시지가 당신이 담당해야 할 내용인지 0-10점으로 평가하세요.
기준:
- 전문분야와 직접 관련: 8-10
- 간접 관련: 4-7
- 관련 없음: 0-3
숫자 하나만 응답.

메시지: {message}
"""

    async def score(self, message: str, identity: PMIdentity) -> int:
        """confidence 점수 계산. Anthropic API 없으면 keyword fallback."""
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        specialties = identity.get_specialty_text()

        if api_key:
            try:
                return await self._llm_score(message, identity.org_id, specialties, api_key)
            except Exception as e:
                logger.warning(f"[confidence] LLM 점수 실패, keyword fallback: {e}")

        return self._keyword_score(message, identity._data.get("specialties", []))

    async def _llm_score(self, message: str, org_id: str, specialties: str, api_key: str) -> int:
        """Anthropic API로 confidence 점수 계산."""
        import anthropic  # lazy import

        prompt = self.SCORING_PROMPT.format(
            org_id=org_id,
            specialties=specialties,
            message=message,
        )

        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        match = re.search(r"\d+", raw)
        score = int(match.group()) if match else 5
        return max(0, min(10, score))

    def _keyword_score(self, message: str, specialties: list[str]) -> int:
        """키워드 매칭 기반 fallback scoring."""
        # 짧은 인사말은 담당 없음 (0점)
        if len(message) < 20 and any(p in message.lower() for p in GREETING_PATTERNS):
            return 0

        if not specialties:
            return 3  # 전문분야 없으면 낮은 점수

        message_lower = message.lower()
        matched = sum(
            1 for s in specialties
            if s.lower() in message_lower
        )

        if matched == 0:
            return 2
        elif matched == 1:
            return 6
        elif matched == 2:
            return 8
        else:
            return 10
