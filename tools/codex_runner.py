"""Codex CLI 실행 래퍼."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from loguru import logger


CODEX_CLI = os.environ.get("CODEX_CLI_PATH", "codex")
DEFAULT_TIMEOUT = 300


class CodexRunner:
    """OpenAI Codex CLI를 subprocess로 실행하는 래퍼."""

    def __init__(
        self,
        cli_path: str = CODEX_CLI,
        timeout: int = DEFAULT_TIMEOUT,
        workdir: str | None = None,
    ) -> None:
        self.cli_path = cli_path
        self.timeout = timeout
        self.workdir = workdir or str(Path.home() / ".ai-org" / "workspace")
        Path(self.workdir).mkdir(parents=True, exist_ok=True)

    async def run(self, prompt: str, model: str | None = None) -> str:
        """Codex 실행 후 결과 반환."""
        # codex exec <PROMPT> — 비인터랙티브 모드, --prompt 플래그 없음
        cmd = [self.cli_path, "exec", "--skip-git-repo-check", prompt]
        if model:
            cmd += ["-c", f"model={model}"]

        logger.debug(f"Codex 실행: 프롬프트 {len(prompt)}자")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workdir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)

            if proc.returncode != 0:
                error = stderr.decode(errors="replace")
                return f"❌ Codex 오류: {error[:500]}"

            return stdout.decode(errors="replace").strip() or "(결과 없음)"

        except asyncio.TimeoutError:
            return f"❌ Codex 타임아웃 ({self.timeout}초)"
        except FileNotFoundError:
            return f"❌ Codex CLI 없음: {self.cli_path}"
        except Exception as e:
            return f"❌ 예외: {e}"
