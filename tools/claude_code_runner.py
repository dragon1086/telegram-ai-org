"""Claude Code 실행 래퍼 — omc_team / agent_teams / single 3가지 모드 지원."""
from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Awaitable, Callable
from pathlib import Path

from loguru import logger

FILE_PATTERN = re.compile(r"(?:저장[됨했]|생성[됨했]|작성[됨했]):?\s*([~/\w\-\.]+\.\w+)")

TOOL_EMOJI = {
    "Bash": "🔧",
    "Read": "📖",
    "Edit": "✏️",
    "Write": "📝",
    "MultiEdit": "✏️",
    "WebSearch": "🔍",
    "WebFetch": "🌐",
    "Task": "🤖",
    "TodoWrite": "📋",
    "Glob": "📂",
    "Grep": "🔎",
    "LS": "📂",
}


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
        return await self._run_stream_json(cmd, progress_callback=progress_callback)

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
        return await self._run_stream_json(cmd, progress_callback=progress_callback)

    # ------------------------------------------------------------------
    # Mode 4: codex_mode
    # ------------------------------------------------------------------
    async def run_codex(
        self,
        task: str,
        agents: list[str] | None = None,
        progress_callback=None,
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
        return await self._run_subprocess(cmd, workdir=codex_workdir, progress_callback=progress_callback)

    # ------------------------------------------------------------------
    # Backward compat
    # ------------------------------------------------------------------
    async def run(self, prompt: str, flags: list[str] | None = None) -> str:
        """Backward compat — single mode."""
        return await self.run_single(prompt)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    async def _run_stream_json(
        self,
        cmd: list[str],
        extra_env: dict[str, str] | None = None,
        progress_callback: Callable[[str], Awaitable[None]] | None = None,
        workdir: str | None = None,
    ) -> str:
        """--output-format stream-json으로 실행 → tool_use 이벤트 파싱 후 결과 반환.

        stream-json 실패 시 _run_subprocess로 fallback.
        """
        # --print 뒤에 --verbose --output-format stream-json 삽입
        stream_cmd: list[str] = []
        for i, arg in enumerate(cmd):
            stream_cmd.append(arg)
            if arg in ("--print", "-p"):
                stream_cmd.extend(["--verbose", "--output-format", "stream-json"])

        env = os.environ.copy()
        oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        if oauth_token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token
        if extra_env:
            env.update(extra_env)
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_SESSION_ID", None)

        logger.debug(f"[stream_json] cmd: {' '.join(stream_cmd[:4])}...")

        try:
            proc = await asyncio.create_subprocess_exec(
                *stream_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=workdir or self.workdir,
                env=env,
            )
        except FileNotFoundError:
            msg = f"❌ Claude CLI를 찾을 수 없습니다: {stream_cmd[0]}"
            logger.error(msg)
            return msg

        final_result = ""
        tool_counts: dict[str, int] = {}
        raw_lines: list[str] = []

        async def _read_stream() -> None:
            nonlocal final_result
            assert proc.stdout is not None
            async for raw_line in proc.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                raw_lines.append(line)
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type", "")

                if etype == "assistant":
                    msg_obj = event.get("message", {})
                    for block in msg_obj.get("content", []):
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") != "tool_use":
                            continue
                        tool_name = block.get("name", "")
                        tool_input = block.get("input", {})
                        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

                        emoji = TOOL_EMOJI.get(tool_name, "⚙️")
                        if tool_name == "Bash":
                            snippet = str(tool_input.get("command", ""))[:60]
                            msg_text = f"{emoji} `{snippet}`"
                        elif tool_name in ("Read", "Edit", "Write", "MultiEdit"):
                            fpath = str(tool_input.get("file_path", tool_input.get("path", "")))
                            fpath = fpath.replace("/Users/rocky/", "~/")
                            msg_text = f"{emoji} {tool_name}: `{fpath}`"
                        elif tool_name == "Task":
                            desc = str(tool_input.get("description", ""))[:50]
                            msg_text = f"🤖 서브에이전트: {desc}"
                        elif tool_name == "WebSearch":
                            q = str(tool_input.get("query", ""))[:50]
                            msg_text = f"🔍 검색: {q}"
                        else:
                            msg_text = f"{emoji} {tool_name}"

                        if progress_callback:
                            try:
                                await progress_callback(msg_text)
                            except Exception as cb_err:
                                logger.warning(f"progress_callback 오류: {cb_err}")

                elif etype == "result":
                    if event.get("subtype") == "success":
                        final_result = event.get("result", "")
                        duration = event.get("duration_ms", 0) / 1000
                        if progress_callback:
                            tools_summary = (
                                " · ".join(f"{v}×{k}" for k, v in tool_counts.items())
                                if tool_counts else "없음"
                            )
                            try:
                                await progress_callback(
                                    f"✅ 완료 ({duration:.1f}초) | 도구: {tools_summary}"
                                )
                            except Exception:
                                pass
                    elif event.get("subtype") == "error":
                        final_result = event.get("result", "")

        try:
            await asyncio.wait_for(_read_stream(), timeout=self.timeout)
            await proc.wait()
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            msg = f"❌ 타임아웃 ({self.timeout}s) 초과"
            logger.error(msg)
            return msg
        except Exception as exc:
            proc.kill()
            await proc.wait()
            msg = f"❌ 실행 중 오류: {exc}"
            logger.exception(msg)
            return msg

        # stream-json이 아무 JSON도 못 파싱했으면 raw 텍스트 반환
        if not final_result and raw_lines:
            logger.warning("[stream_json] result 이벤트 없음 — raw 텍스트 반환")
            return "\n".join(raw_lines)

        return final_result or "(결과 없음)"

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
