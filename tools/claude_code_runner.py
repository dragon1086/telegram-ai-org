"""Claude Code 실행 래퍼."""
from __future__ import annotations

import asyncio
import os
import shlex
from pathlib import Path

from loguru import logger


CLAUDE_CLI = os.environ.get("CLAUDE_CLI_PATH", "claude")
DEFAULT_TIMEOUT = 300  # 5분


class ClaudeCodeRunner:
    """Claude Code CLI를 subprocess로 실행하는 래퍼."""

    def __init__(
        self,
        cli_path: str = CLAUDE_CLI,
        timeout: int = DEFAULT_TIMEOUT,
        workdir: str | None = None,
    ) -> None:
        self.cli_path = cli_path
        self.timeout = timeout
        self.workdir = workdir or str(Path.home() / ".ai-org" / "workspace")
        Path(self.workdir).mkdir(parents=True, exist_ok=True)

    async def run(self, prompt: str, flags: list[str] | None = None) -> str:
        """Claude Code 실행 후 결과 반환."""
        cmd = [self.cli_path, "--print", prompt]
        if flags:
            cmd.extend(flags)

        logger.debug(f"Claude Code 실행: {cmd[:3]}...")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workdir,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout,
            )

            if proc.returncode != 0:
                error = stderr.decode(errors="replace")
                logger.error(f"Claude Code 오류 (exit {proc.returncode}): {error[:500]}")
                return f"❌ 실행 오류 (exit {proc.returncode}):\n{error[:500]}"

            result = stdout.decode(errors="replace").strip()
            logger.info(f"Claude Code 완료: {len(result)}자 출력")
            return result or "(결과 없음)"

        except asyncio.TimeoutError:
            logger.error(f"Claude Code 타임아웃 ({self.timeout}초)")
            return f"❌ 타임아웃 ({self.timeout}초 초과)"
        except FileNotFoundError:
            logger.error(f"Claude CLI를 찾을 수 없음: {self.cli_path}")
            return f"❌ Claude CLI 없음: {self.cli_path}\n`CLAUDE_CLI_PATH` 환경변수를 설정하세요."
        except Exception as e:
            logger.error(f"Claude Code 예외: {e}")
            return f"❌ 예외 발생: {e}"
