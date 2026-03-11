"""Claude Code 실행 래퍼 — omc_team / agent_teams / single 3가지 모드 지원."""
from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Awaitable, Callable
from pathlib import Path

from loguru import logger

FILE_PATTERN = re.compile(r"(?:저장[됨했]|생성[됨했]|작성[됨했]):?\s*([~/\w\-\.]+\.\w+)")


CLAUDE_CLI = os.environ.get("CLAUDE_CLI_PATH", "/Users/rocky/.local/bin/claude")
CODEX_CLI = os.environ.get("CODEX_CLI_PATH", "/opt/homebrew/bin/codex")
DEFAULT_TIMEOUT = 300  # 5분


class ClaudeCodeRunner:
    """Claude Code CLI를 subprocess로 실행하는 래퍼. 3가지 실행 모드 지원."""

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

    # ------------------------------------------------------------------
    # Mode 1: omc_team_mode
    # ------------------------------------------------------------------
    async def run_omc_team(
        self,
        task: str,
        agents: list[str],
        counts: list[int] | None = None,
        progress_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """omc /team 형식으로 다중 에이전트 실행.

        Args:
            task: 실행할 태스크 문자열.
            agents: 에이전트 이름 목록 (e.g. ["executor", "analyst"]).
            counts: 각 에이전트 수 (e.g. [2, 1] → "2:executor,1:analyst").
                    None이면 각 1명씩.
        """
        if counts is None:
            counts = [1] * len(agents)

        if len(counts) != len(agents):
            return "❌ agents와 counts의 길이가 일치하지 않습니다."

        team_spec = ",".join(
            f"{count}:{agent}" for count, agent in zip(counts, agents)
        )
        prompt = f"/team {team_spec} {task}"
        cmd = [
            self.cli_path,
            "--permission-mode", "bypassPermissions",
            "--print",
            prompt,
        ]
        logger.info(f"[omc_team] team_spec={team_spec}")
        return await self._run_subprocess(cmd, progress_callback=progress_callback)

    # ------------------------------------------------------------------
    # Mode 2: agent_teams_mode
    # ------------------------------------------------------------------
    async def run_agent_teams(
        self,
        task: str,
        agent_personas: list[str],
        progress_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 환경변수로 에이전트 팀 실행.

        Args:
            task: 실행할 태스크 문자열.
            agent_personas: 페르소나 이름 목록. 태스크 설명에 포함됨.
        """
        persona_context = ", ".join(agent_personas) if agent_personas else "general"
        full_task = f"[Personas: {persona_context}] {task}"
        cmd = [
            self.cli_path,
            "--permission-mode", "bypassPermissions",
            "--print",
            full_task,
        ]
        extra_env = {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}
        logger.info(f"[agent_teams] personas={agent_personas}")
        return await self._run_subprocess(cmd, extra_env=extra_env, progress_callback=progress_callback)

    # ------------------------------------------------------------------
    # Mode 3: single_agent_mode
    # ------------------------------------------------------------------
    async def run_single(
        self,
        task: str,
        persona: str | None = None,
        progress_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """단일 에이전트 실행.

        Args:
            task: 실행할 태스크 문자열.
            persona: 페르소나 이름 (있으면 프롬프트 앞에 컨텍스트 추가).
        """
        if persona:
            full_task = f"[Persona: {persona}] {task}"
        else:
            full_task = task

        cmd = [
            self.cli_path,
            "--permission-mode", "bypassPermissions",
            "--print",
            full_task,
        ]
        logger.info(f"[single] persona={persona}")
        return await self._run_subprocess(cmd, progress_callback=progress_callback)

    # ------------------------------------------------------------------
    # Mode 4: codex_mode
    # ------------------------------------------------------------------
    async def run_codex(
        self,
        task: str,
        agents: list[str] | None = None,
    ) -> str:
        """Codex CLI로 태스크 실행.

        Args:
            task: 실행할 태스크 문자열.
            agents: 힌트용 에이전트 이름 목록 (태스크 컨텍스트에 포함).
        """
        codex_cli = CODEX_CLI
        if not os.path.exists(codex_cli):
            # fallback: PATH에서 찾기
            import shutil
            found = shutil.which("codex")
            if found:
                codex_cli = found
            else:
                msg = f"❌ Codex CLI를 찾을 수 없습니다: {codex_cli}"
                logger.error(msg)
                return msg

        full_task = task
        if agents:
            full_task = f"[Agents: {', '.join(agents)}] {task}"

        # Codex는 git repo 안에서만 실행 가능 → 프로젝트 루트 사용
        codex_workdir = str(Path(__file__).parent.parent)  # ~/telegram-ai-org
        cmd = [codex_cli, "exec", "--full-auto", "--skip-git-repo-check", full_task]
        logger.info(f"[codex] task={task[:60]}, workdir={codex_workdir}")
        return await self._run_subprocess(cmd, workdir=codex_workdir)

    # ------------------------------------------------------------------
    # Backward compat
    # ------------------------------------------------------------------
    async def run(self, prompt: str, flags: list[str] | None = None) -> str:
        """Backward compat — single mode."""
        return await self.run_single(prompt)

    # ------------------------------------------------------------------
    # Private helper
    # ------------------------------------------------------------------
    async def _run_subprocess(
        self,
        cmd: list[str],
        extra_env: dict[str, str] | None = None,
        progress_callback: Callable[[str], Awaitable[None]] | None = None,
        workdir: str | None = None,
    ) -> str:
        """subprocess 실행 후 stdout 스트림 → 결과 반환.

        Args:
            cmd: 실행할 명령어 리스트.
            extra_env: 추가 환경 변수 (기존 env에 병합).
            progress_callback: stdout 라인마다 호출되는 비동기 콜백.

        Returns:
            전체 stdout 문자열. 오류 시 ❌ 접두사 문자열.
        """
        env = os.environ.copy()

        # CLAUDE_CODE_OAUTH_TOKEN 자동 주입
        oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        if oauth_token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token

        if extra_env:
            env.update(extra_env)

        # 중첩 Claude Code 세션 방지 — CLAUDECODE 반드시 unset
        env.pop("CLAUDECODE", None)

        logger.debug(f"Running cmd: {' '.join(cmd[:3])}...")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir or self.workdir,
                env=env,
            )
        except FileNotFoundError:
            msg = f"❌ Claude CLI를 찾을 수 없습니다: {cmd[0]}"
            logger.error(msg)
            return msg

        output_lines: list[str] = []

        async def _read_stdout() -> None:
            assert proc.stdout is not None
            async for raw_line in proc.stdout:
                line = raw_line.decode("utf-8", errors="replace").rstrip()
                output_lines.append(line)
                if progress_callback is not None:
                    try:
                        await progress_callback(line)
                    except Exception as cb_err:
                        logger.warning(f"progress_callback 오류: {cb_err}")

        try:
            await asyncio.wait_for(_read_stdout(), timeout=self.timeout)
            await proc.wait()
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            msg = f"❌ 타임아웃 ({self.timeout}s) 초과: {' '.join(cmd[:3])}"
            logger.error(msg)
            return msg
        except Exception as exc:
            proc.kill()
            await proc.wait()
            msg = f"❌ 실행 중 오류 발생: {exc}"
            logger.exception(msg)
            return msg

        full_output = "\n".join(output_lines)

        if proc.returncode != 0:
            assert proc.stderr is not None
            stderr_raw = await proc.stderr.read()
            stderr = stderr_raw.decode("utf-8", errors="replace").strip()
            logger.warning(
                f"프로세스 종료 코드 {proc.returncode}. stderr: {stderr[:200]}"
            )
            if not full_output:
                return f"❌ 프로세스 오류 (code={proc.returncode}): {stderr}"

        return full_output or "(결과 없음)"

    async def _auto_upload(self, response: str, bot_token: str, chat_id: int) -> None:
        """응답에서 생성된 파일 경로 감지 → 자동 텔레그램 업로드."""
        from tools.telegram_uploader import upload_file

        matches = FILE_PATTERN.findall(response)
        for fpath in matches:
            fpath = os.path.expanduser(fpath.strip())
            if os.path.exists(fpath):
                logger.info(f"[auto_upload] {fpath}")
                await upload_file(bot_token, chat_id, fpath, f"📄 생성된 파일: {Path(fpath).name}")
