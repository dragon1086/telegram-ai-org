"""amp MCP 연동 — 분석/리서치 도구."""
from __future__ import annotations

import asyncio
from loguru import logger


class AmpCaller:
    """amp MCP 서버 연동.

    amp는 Claude의 공식 research/analysis 도구.
    현재는 플레이스홀더이며, amp MCP 설정 후 활성화.
    """

    def __init__(self) -> None:
        self.available = self._check_amp_available()

    def _check_amp_available(self) -> bool:
        """amp가 사용 가능한지 확인."""
        try:
            import subprocess
            result = subprocess.run(["which", "amp"], capture_output=True)
            return result.returncode == 0
        except Exception:
            return False

    async def query(self, question: str) -> str:
        """amp로 질문/분석 실행."""
        if not self.available:
            logger.warning("amp를 찾을 수 없음. 플레이스홀더 응답 반환.")
            return (
                f"📊 분석 요청: {question[:100]}...\n\n"
                "⚠️ amp MCP가 설치되지 않았습니다. "
                "amp를 설치하거나 ANALYST_MODE=claude로 설정하세요."
            )

        cmd = ["amp", "query", question]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode == 0:
                return stdout.decode(errors="replace").strip()
            return f"❌ amp 오류: {stderr.decode(errors='replace')[:300]}"
        except asyncio.TimeoutError:
            return "❌ amp 타임아웃"
        except Exception as e:
            return f"❌ amp 예외: {e}"
