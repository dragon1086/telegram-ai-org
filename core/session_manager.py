"""tmux 세션 매니저 — 팀별 persistent 세션 관리.

세션 이름 규칙: aiorg_{team_id}
예: aiorg_dev, aiorg_marketing
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from loguru import logger

SESSION_PREFIX = "aiorg"
OUTPUT_TIMEOUT = 30  # 응답 대기 최대 초


class SessionManager:
    """tmux 세션 생성/확인/재시작."""

    def session_name(self, team_id: str) -> str:
        return f"{SESSION_PREFIX}_{team_id}"

    # ── tmux 헬퍼 ─────────────────────────────────────────────────────────

    def _run_tmux(self, *args: str) -> str:
        """tmux 명령 실행. stdout 반환. 실패 시 빈 문자열."""
        try:
            result = subprocess.run(
                ["tmux", *args],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return (result.stdout + result.stderr).strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            logger.debug(f"tmux 명령 실패 ({args}): {e}")
            return ""

    def _tmux_available(self) -> bool:
        return bool(self._run_tmux("-V"))

    # ── 세션 관리 ─────────────────────────────────────────────────────────

    def session_exists(self, team_id: str) -> bool:
        """세션이 존재하면 True."""
        name = self.session_name(team_id)
        out = self._run_tmux("has-session", "-t", name)
        return not out  # has-session은 성공 시 출력 없음, 실패 시 에러 출력

    def ensure_session(self, team_id: str) -> str:
        """세션이 없으면 생성. 세션 이름 반환."""
        name = self.session_name(team_id)
        if not self.session_exists(team_id):
            self._run_tmux("new-session", "-d", "-s", name)
            logger.info(f"tmux 세션 생성: {name}")
        else:
            logger.debug(f"tmux 세션 재사용: {name}")
        return name

    def list_sessions(self) -> list[str]:
        """aiorg_ 접두어 세션 목록 반환."""
        out = self._run_tmux("list-sessions", "-F", "#{session_name}")
        if not out:
            return []
        return [s for s in out.splitlines() if s.startswith(SESSION_PREFIX + "_")]

    def kill_session(self, team_id: str) -> None:
        """세션 종료."""
        name = self.session_name(team_id)
        if self.session_exists(team_id):
            self._run_tmux("kill-session", "-t", name)
            logger.info(f"tmux 세션 종료: {name}")

    # ── 명령 전송 ─────────────────────────────────────────────────────────

    async def send_to_session(self, team_id: str, prompt: str) -> str:
        """세션에 프롬프트 전송 (비동기). 출력 캡처는 파일 리디렉션으로."""
        name = self.ensure_session(team_id)
        output_file = Path.home() / ".ai-org" / "sessions" / f"{name}.out"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # 이전 출력 파일 초기화
        output_file.write_text("", encoding="utf-8")

        # 명령을 출력 캡처와 함께 전송
        escaped = prompt.replace("'", "'\\''")
        cmd = f"echo '{escaped}' >> {output_file} && echo '__DONE__' >> {output_file}"
        self._run_tmux("send-keys", "-t", name, cmd, "Enter")

        # __DONE__ 마커 대기
        try:
            return await asyncio.wait_for(
                self._wait_for_output(output_file),
                timeout=OUTPUT_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning(f"세션 응답 타임아웃: {name}")
            return output_file.read_text(encoding="utf-8") if output_file.exists() else ""

    async def _wait_for_output(self, output_file: Path) -> str:
        """출력 파일에 __DONE__ 마커 나타날 때까지 대기."""
        while True:
            await asyncio.sleep(0.5)
            if output_file.exists():
                content = output_file.read_text(encoding="utf-8")
                if "__DONE__" in content:
                    return content.replace("__DONE__", "").strip()

    # ── 컨텍스트 재주입 재시작 ────────────────────────────────────────────

    async def restart_session(self, team_id: str, context: str) -> None:
        """세션 재시작 + 컨텍스트 재주입."""
        self.kill_session(team_id)
        name = self.ensure_session(team_id)

        if context:
            context_file = Path.home() / ".ai-org" / "sessions" / f"{name}_context.md"
            context_file.parent.mkdir(parents=True, exist_ok=True)
            context_file.write_text(context, encoding="utf-8")
            # 세션 시작 시 컨텍스트 파일 경로 환경변수로 설정
            self._run_tmux(
                "send-keys", "-t", name,
                f"export AI_ORG_CONTEXT={context_file}", "Enter",
            )
            logger.info(f"세션 재시작 + 컨텍스트 주입: {name}")

    # ── 상태 요약 ─────────────────────────────────────────────────────────

    def status(self) -> dict:
        """활성 세션 상태 요약."""
        if not self._tmux_available():
            return {"tmux": False, "sessions": []}
        sessions = self.list_sessions()
        return {
            "tmux": True,
            "sessions": sessions,
            "count": len(sessions),
        }
