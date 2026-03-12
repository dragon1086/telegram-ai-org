"""메시지에 대한 PM 담당 confidence 계산 (0-10).

각 봇이 자신의 Claude Code 엔진으로 자율 판단.
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
from pathlib import Path

from loguru import logger

from core.pm_identity import PMIdentity
from core.keywords import GREETING_KW

DEFAULT_CONFIDENCE_THRESHOLD = 6

GREETING_PATTERNS = GREETING_KW

# Claude CLI 경로
CLAUDE_CLI = "/Users/rocky/.local/bin/claude"


def _get_oauth_token() -> str:
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    if token:
        return token
    try:
        zrc = Path(os.path.expanduser("~/.zshrc")).read_text()
        m = re.search(r"CLAUDE_CODE_OAUTH_TOKEN='([^']+)'", zrc)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


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

        # Claude Code 엔진으로 자율 판단
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
        """Claude Code (--print) 로 자율 판단. 초단순 프롬프트."""
        specs = ", ".join(specialties)
        prompt = f"숫자만 0~10: '{message}'가 [{specs}] 전문가가 담당해야 하나?"

        token = _get_oauth_token()
        env = {**os.environ, "CLAUDECODE": ""}
        if token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = token

        loop = asyncio.get_event_loop()

        def _run():
            result = subprocess.run(
                [CLAUDE_CLI, "--print", "-p", prompt],
                capture_output=True, text=True, timeout=5, env=env,
            )
            return result.stdout.strip()

        raw = await loop.run_in_executor(None, _run)
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
