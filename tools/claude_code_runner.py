"""Claude Code 실행 래퍼 — structured_team / agent_teams / single 3가지 모드 지원."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
from collections.abc import Awaitable, Callable
from pathlib import Path

from loguru import logger

from core.global_context import GlobalContext
from core.session_store import SessionStore

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
DEFAULT_TIMEOUT = int(os.environ.get("CLAUDE_DEFAULT_TIMEOUT_SEC", "14400"))  # 4시간


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
        _project_root = Path(__file__).resolve().parent.parent  # telegram-ai-org
        self.workdir = workdir or str(_project_root)
        Path(self.workdir).mkdir(parents=True, exist_ok=True)
        self._last_run_metrics: dict[str, int | float | str] = {}
        self._last_partial_output: str = ""  # 외부 취소 시 부분 결과 보존

    def get_last_run_metrics(self) -> dict[str, int | float | str]:
        return dict(self._last_run_metrics)

    def get_last_partial_output(self) -> str:
        """외부 CancelledError 취소 시 보존된 부분 결과 반환."""
        return self._last_partial_output

    def _reset_last_run_metrics(self) -> None:
        self._last_run_metrics = {}
        self._last_partial_output = ""

    @staticmethod
    def _extract_usage_metrics(event: dict) -> dict[str, int | float | str]:
        metrics: dict[str, int | float | str] = {}
        candidates = []
        usage = event.get("usage")
        if isinstance(usage, dict):
            candidates.append(usage)
        candidates.append(event)

        for source in candidates:
            for key in (
                "input_tokens",
                "output_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
                "context_percent",
                "context_usage_percent",
            ):
                value = source.get(key)
                if isinstance(value, (int, float)):
                    metrics[key] = int(value) if isinstance(value, int) or float(value).is_integer() else float(value)

        if "total_tokens" in event and isinstance(event["total_tokens"], (int, float)):
            metrics["total_tokens"] = int(event["total_tokens"])
        elif "input_tokens" in metrics or "output_tokens" in metrics:
            metrics["total_tokens"] = int(metrics.get("input_tokens", 0)) + int(metrics.get("output_tokens", 0))

        if metrics:
            metrics["usage_source"] = "runner_event"
        return metrics

    # ------------------------------------------------------------------
    # Mode 1: structured_team_mode
    # ------------------------------------------------------------------
    async def run_structured_team(
        self,
        task: str,
        agents: list[str],
        counts: list[int] | None = None,
        progress_callback: Callable[[str], Awaitable[None]] | None = None,
        session_store: SessionStore | None = None,
        org_id: str = "global",
        global_context: GlobalContext | None = None,
        system_prompt: str = "",
        workdir: str | None = None,
        shell_session_manager=None,
        shell_team_id: str | None = None,
    ) -> str:
        """구조화된 팀 형식으로 다중 에이전트 실행.

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
            *self._get_dir_flags(org_id),
            "--print",
            prompt,
        ]

        # system_prompt + 글로벌 맥락 주입
        prompt_parts: list[str] = []
        if system_prompt:
            prompt_parts.append(system_prompt)
        if global_context:
            ctx_prompt = await global_context.build_system_prompt(org_id, task)
            if ctx_prompt:
                prompt_parts.append(ctx_prompt)
        if prompt_parts:
            cmd.extend(["--append-system-prompt", "\n\n".join(prompt_parts)])

        logger.info(f"[structured_team] team_spec={team_spec}")
        if shell_session_manager and shell_team_id:
            result = await self._run_subprocess(
                cmd,
                progress_callback=progress_callback,
                workdir=workdir,
                shell_session_manager=shell_session_manager,
                shell_team_id=shell_team_id,
                shell_purpose="claude-team",
            )
        else:
            result = await self._run_stream_json(
                cmd,
                progress_callback=progress_callback,
                session_store=session_store,
                workdir=workdir,
            )

        # 작업 완료 후 핵심 내용 추출 → global_context 저장
        if global_context and result:
            await global_context.extract_and_save(org_id, task, result)

        return result

    async def run_omc_team(self, *args, **kwargs) -> str:
        """Legacy alias for structured team execution."""
        return await self.run_structured_team(*args, **kwargs)

    # ------------------------------------------------------------------
    # Mode 2: agent_teams_mode
    # ------------------------------------------------------------------
    async def run_agent_teams(
        self,
        task: str,
        agent_personas: list[str],
        progress_callback: Callable[[str], Awaitable[None]] | None = None,
        system_prompt: str = "",
        workdir: str | None = None,
        shell_session_manager=None,
        shell_team_id: str | None = None,
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
        if system_prompt:
            cmd.extend(["--append-system-prompt", system_prompt])
        extra_env = {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}
        logger.info(f"[agent_teams] personas={agent_personas}")
        return await self._run_subprocess(
            cmd,
            extra_env=extra_env,
            progress_callback=progress_callback,
            workdir=workdir,
            shell_session_manager=shell_session_manager,
            shell_team_id=shell_team_id,
            shell_purpose="claude-agent-team",
        )

    # ------------------------------------------------------------------
    # Mode 3: single_agent_mode
    # ------------------------------------------------------------------
    async def run_single(
        self,
        task: str,
        persona: str | None = None,
        progress_callback: Callable[[str], Awaitable[None]] | None = None,
        session_store: SessionStore | None = None,
        org_id: str = "global",
        global_context: GlobalContext | None = None,
        system_prompt: str = "",
        workdir: str | None = None,
        shell_session_manager=None,
        shell_team_id: str | None = None,
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
            *self._get_dir_flags(org_id),
            "--print",
            full_task,
        ]

        # system_prompt + 글로벌 맥락 주입
        prompt_parts: list[str] = []
        if system_prompt:
            prompt_parts.append(system_prompt)
        if global_context:
            ctx_prompt = await global_context.build_system_prompt(org_id, task)
            if ctx_prompt:
                prompt_parts.append(ctx_prompt)
        if prompt_parts:
            cmd.extend(["--append-system-prompt", "\n\n".join(prompt_parts)])

        logger.info(f"[single] persona={persona}")
        if shell_session_manager and shell_team_id:
            result = await self._run_subprocess(
                cmd,
                progress_callback=progress_callback,
                workdir=workdir,
                shell_session_manager=shell_session_manager,
                shell_team_id=shell_team_id,
                shell_purpose="claude-single",
            )
        else:
            result = await self._run_stream_json(
                cmd,
                progress_callback=progress_callback,
                session_store=session_store,
                workdir=workdir,
            )

        # 작업 완료 후 핵심 내용 추출 → global_context 저장
        if global_context and result:
            await global_context.extract_and_save(org_id, task, result)

        return result

    # ------------------------------------------------------------------
    # Mode 4: codex_mode
    # ------------------------------------------------------------------
    async def run_codex(
        self,
        task: str,
        org_id: str = "global",
        agents: list[str] | None = None,
        progress_callback=None,
    ) -> str:
        """Codex CLI로 태스크 실행.

        Args:
            task: 실행할 태스크 문자열.
            org_id: 조직 ID (방법론 주입에 사용).
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

        # 조직별 방법론 prepend (AGENTS.md 내용을 task 앞에 주입)
        org_dir = Path.home() / ".ai-org" / "orgs" / org_id
        agents_file = org_dir / "AGENTS.md"
        if not agents_file.exists():
            agents_file = Path.home() / ".ai-org" / "workspace" / "AGENTS.md"
        if agents_file.exists():
            methodology = agents_file.read_text().strip()
            full_task = f"{methodology}\n\n---\n\n{full_task}"

        # Codex는 git repo 안에서만 실행 가능 → 프로젝트 루트 사용
        codex_workdir = str(Path(__file__).parent.parent)  # ~/telegram-ai-org
        cmd = [
            codex_cli,
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            full_task,
        ]
        logger.info(f"[codex] task={task[:60]}, workdir={codex_workdir}")
        return await self._run_subprocess(cmd, workdir=codex_workdir, progress_callback=progress_callback)

    # ------------------------------------------------------------------
    # Mode 5: run_task (PM 자율 판단 — DynamicTeamBuilder 대체)
    # ------------------------------------------------------------------
    async def run_task(
        self,
        task: str,
        system_prompt: str = "",
        progress_callback: Callable[[str], Awaitable[None]] | None = None,
        session_store: "SessionStore | None" = None,
        global_context: "GlobalContext | None" = None,
        org_id: str = "global",
        workdir: str | None = None,
    ) -> str:
        """PM 자율 판단으로 태스크 실행. 팀 구성 여부는 Claude Code가 결정.

        조직 정체성 + 팀 구성 지침이 담긴 system_prompt를 주입하면
        Claude Code가 스스로 팀 구성 여부와 에이전트 선택을 결정한다.
        """
        cmd = [
            self.cli_path,
            "--permission-mode", "bypassPermissions",
            *self._get_dir_flags(org_id),
            "--print",
        ]

        # system_prompt + global_context → 단일 --append-system-prompt
        parts: list[str] = []
        if system_prompt:
            parts.append(system_prompt)
        parts.append("팀 구성 여부는 태스크 복잡도에 따라 당신이 판단하세요.")
        if global_context:
            ctx = await global_context.build_system_prompt(org_id, task)
            if ctx:
                parts.append(ctx)
        combined = "\n\n".join(parts)
        cmd.extend(["--append-system-prompt", combined])

        cmd.append(task)

        logger.info(f"[run_task] org_id={org_id}, task={task[:60]}")
        result = await self._run_stream_json(
            cmd,
            progress_callback=progress_callback,
            workdir=workdir,
            session_store=session_store,
        )

        if global_context and result:
            await global_context.extract_and_save(org_id, task, result)

        return result

    # ------------------------------------------------------------------
    # Backward compat
    # ------------------------------------------------------------------
    async def run(self, prompt: str, flags: list[str] | None = None) -> str:
        """Backward compat — single mode."""
        return await self.run_single(prompt)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _get_dir_flags(self, org_id: str = "global") -> list[str]:
        """조직별 --add-dir 플래그 반환 (전역 workspace + 조직별 디렉토리)."""
        flags = ["--add-dir", str(Path.home() / ".ai-org" / "workspace")]
        org_dir = Path.home() / ".ai-org" / "orgs" / org_id
        if org_dir.exists():
            flags.extend(["--add-dir", str(org_dir)])
        return flags

    async def _run_stream_json(
        self,
        cmd: list[str],
        extra_env: dict[str, str] | None = None,
        progress_callback: Callable[[str], Awaitable[None]] | None = None,
        workdir: str | None = None,
        session_store: SessionStore | None = None,
    ) -> str:
        """--output-format stream-json으로 실행 → tool_use 이벤트 파싱 후 결과 반환.

        stream-json 실패 시 _run_subprocess로 fallback.
        """
        self._reset_last_run_metrics()
        # --resume 삽입 (기존 session_id 있으면 이전 대화 이어받기)
        if session_store:
            # 자동 로테이션: 세션 나이/컨텍스트/메시지 수 초과 시 새 세션으로 시작
            rotate, reason = session_store.should_rotate()
            if rotate:
                logger.warning(
                    f"[stream_json] 세션 자동 로테이션 — {reason}. 새 세션으로 시작합니다."
                )
                session_store.clear_session_id()
            existing_id = session_store.get_session_id()
            if existing_id:
                new_cmd: list[str] = []
                for arg in cmd:
                    new_cmd.append(arg)
                    if arg in ("--print", "-p"):
                        new_cmd.extend(["--resume", existing_id])
                cmd = new_cmd
                logger.info(f"[stream_json] --resume {existing_id[:8]}...")

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
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir or self.workdir,
                env=env,
                limit=1024 * 1024 * 10,  # 10MB — 기본 64KB 한도 초과 방지
            )
        except FileNotFoundError:
            msg = f"❌ Claude CLI를 찾을 수 없습니다: {stream_cmd[0]}"
            logger.error(msg)
            return msg

        final_result = ""
        tool_counts: dict[str, int] = {}
        raw_lines: list[str] = []
        current_session_id: str | None = None

        async def _read_stream() -> None:
            nonlocal final_result, current_session_id
            assert proc.stdout is not None
            while True:
                try:
                    raw_line = await proc.stdout.readline()
                except asyncio.LimitOverrunError as exc:
                    logger.warning(
                        f"[stream_json] LimitOverrunError: 단일 라인이 10MB 버퍼 초과 "
                        f"({exc.consumed:,} bytes). 초과 라인 스킵 후 스트림 계속."
                    )
                    try:
                        # consumed 만큼 버퍼에서 제거 후 줄 끝(\n)까지 나머지 소비
                        await proc.stdout.read(exc.consumed)
                        while True:
                            try:
                                await proc.stdout.readline()
                                break  # 줄 끝 도달
                            except asyncio.LimitOverrunError as inner_exc:
                                await proc.stdout.read(inner_exc.consumed)
                    except Exception as drain_err:
                        logger.error(f"[stream_json] 초과 라인 drain 실패, 스트림 중단: {drain_err}")
                        break
                    continue
                if not raw_line:
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                raw_lines.append(line)
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type", "")

                # session_id 추출 (system init 이벤트)
                if etype == "system" and event.get("subtype") == "init":
                    current_session_id = event.get("session_id")

                if etype == "assistant":
                    msg_obj = event.get("message", {})
                    for block in msg_obj.get("content", []):
                        if not isinstance(block, dict):
                            continue
                        # 팀 구성 공지 텍스트 감지
                        if block.get("type") == "text":
                            text_chunk = block.get("text", "")
                            if "🤖 팀 구성:" in text_chunk and progress_callback:
                                try:
                                    await progress_callback(text_chunk.strip())
                                except Exception:
                                    pass
                            continue
                        if block.get("type") != "tool_use":
                            continue
                        tool_name = block.get("name", "")
                        tool_input = block.get("input", {})
                        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

                        if tool_name == "Bash":
                            snippet = str(tool_input.get("command", ""))[:60]
                            msg_text = f"🔧 Bash: `{snippet}`"
                        elif tool_name in ("Read", "Edit", "Write", "MultiEdit"):
                            fpath = str(tool_input.get("file_path", tool_input.get("path", "")))
                            fpath = fpath.replace("/Users/rocky/", "~/")
                            EDIT_EMOJI = {"Read": "📖", "Edit": "✏️", "Write": "📝", "MultiEdit": "✏️"}
                            msg_text = f"{EDIT_EMOJI.get(tool_name, '📄')} {tool_name}: `{fpath}`"
                        elif tool_name == "Task":
                            desc = str(tool_input.get("description", tool_input.get("prompt", "")))[:60]
                            msg_text = f"🤖 Task: {desc}"
                        elif tool_name == "WebSearch":
                            q = str(tool_input.get("query", ""))[:50]
                            msg_text = f"🔍 WebSearch: {q}"
                        elif tool_name == "Glob":
                            pat = str(tool_input.get("pattern", ""))[:50]
                            msg_text = f"📂 Glob: `{pat}`"
                        elif tool_name == "Grep":
                            pat = str(tool_input.get("pattern", ""))[:40]
                            msg_text = f"🔎 Grep: `{pat}`"
                        # omc 전용 툴
                        elif tool_name in ("mcp__omc__Skill", "Skill"):
                            skill = (tool_input.get("skill_name") or
                                     tool_input.get("name") or
                                     list(tool_input.values())[0] if tool_input else "")
                            desc = str(skill)[:50]
                            msg_text = f"🛠️ Skill: {desc}"
                        elif tool_name in ("mcp__omc__Agent", "Agent"):
                            agent = (tool_input.get("agent_name") or
                                     tool_input.get("name") or
                                     tool_input.get("role") or
                                     list(tool_input.values())[0] if tool_input else "")
                            desc = str(agent)[:50]
                            msg_text = f"🤝 Agent: {desc}"
                        elif tool_name.startswith("mcp__omc__"):
                            short = tool_name.replace("mcp__omc__", "")
                            msg_text = f"⚡ omc/{short}"
                        else:
                            # 알 수 없는 tool: input 첫 값 힌트로 보여주기
                            hint = ""
                            if tool_input:
                                first_val = str(list(tool_input.values())[0])[:40]
                                hint = f": {first_val}"
                            msg_text = f"⚙️ {tool_name}{hint}"

                        if progress_callback:
                            try:
                                await progress_callback(msg_text)
                            except Exception as cb_err:
                                logger.warning(f"progress_callback 오류: {cb_err}")

                elif etype == "result":
                    subtype = event.get("subtype", "")
                    if subtype == "error":
                        err_msg = event.get("error", event.get("result", "unknown error"))
                        logger.error(f"[stream_json] result error: {str(err_msg)[:300]}")
                        final_result = f"ERROR: {err_msg}"
                    if subtype == "success":
                        final_result = event.get("result", "")
                        self._last_run_metrics = self._extract_usage_metrics(event)
                        # session_id 저장 (다음 실행 시 --resume으로 재사용)
                        if session_store and current_session_id:
                            session_store.save_session_id(current_session_id)
                            logger.info(f"[stream_json] session_id 저장: {current_session_id[:8]}...")
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
                        usage_metrics = self._extract_usage_metrics(event)
                        if usage_metrics:
                            self._last_run_metrics = usage_metrics

        try:
            await asyncio.wait_for(_read_stream(), timeout=self.timeout)
            await proc.wait()
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            msg = f"❌ 타임아웃 ({self.timeout}s) 초과"
            logger.error(msg)
            return msg
        except asyncio.CancelledError:
            # 외부 watchdog(hang/total_timeout)에 의한 취소 — subprocess 정리 + 부분 결과 보존
            try:
                proc.kill()
                await proc.wait()
            except Exception as _kill_err:
                logger.warning(f"[stream_json] CancelledError 시 proc.kill 실패: {_kill_err}")
            # 지금까지 수집된 부분 결과 보존 (호출자가 get_last_partial_output()으로 조회 가능)
            if final_result:
                self._last_partial_output = final_result
            elif raw_lines:
                self._last_partial_output = "\n".join(raw_lines[-30:])
            logger.warning(
                f"[stream_json] 외부 취소로 subprocess 종료. "
                f"부분 결과 {len(raw_lines)}줄 보존 ({len(self._last_partial_output)}자)."
            )
            raise  # CancelledError 재전파 (watchdog 루프로 전달)
        except Exception as exc:
            proc.kill()
            await proc.wait()
            msg = f"❌ 실행 중 오류: {exc}"
            logger.exception(msg)
            return msg

        # stderr 읽기
        stderr_text = ""
        if proc.stderr is not None:
            try:
                stderr_raw = await proc.stderr.read()
                stderr_text = stderr_raw.decode("utf-8", errors="replace").strip()
                if stderr_text:
                    logger.error(f"[stream_json] stderr (rc={proc.returncode}): {stderr_text[:500]}")
            except Exception:
                pass

        # 에러 반환코드 시 ERROR: 접두사 추가
        if proc.returncode and proc.returncode != 0:
            # 만료된 세션으로 --resume 실패한 경우 세션 ID 초기화 (다음 호출은 새 세션으로)
            if session_store and session_store.get_session_id():
                logger.warning(
                    f"[stream_json] code={proc.returncode} — 세션 초기화 (만료된 --resume 가능성)"
                )
                session_store.reset(preserve_metrics=True)
            stderr_hint = f"\nstderr: {stderr_text[:300]}" if stderr_text else ""
            if final_result:
                return f"ERROR: {final_result}{stderr_hint}"
            if stderr_text:
                return f"ERROR: 프로세스 오류 (code={proc.returncode})\n{stderr_text[:1000]}"
            if raw_lines:
                raw_hint = "\n".join(raw_lines[-5:])[:500]
                return f"ERROR: 프로세스 오류 (code={proc.returncode})\n{raw_hint}"
            return f"ERROR: 프로세스 오류 (code={proc.returncode})"

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
        shell_session_manager=None,
        shell_team_id: str | None = None,
        shell_purpose: str = "claude-batch",
    ) -> str:
        """subprocess 실행 후 stdout 스트림 → 결과 반환.

        Args:
            cmd: 실행할 명령어 리스트.
            extra_env: 추가 환경 변수 (기존 env에 병합).
            progress_callback: stdout 라인마다 호출되는 비동기 콜백.

        Returns:
            전체 stdout 문자열. 오류 시 ❌ 접두사 문자열.
        """
        self._reset_last_run_metrics()
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

        if shell_session_manager and shell_team_id:
            shell_cmd = self._build_shell_command(cmd, env, workdir or self.workdir)
            try:
                output, exit_code = await shell_session_manager.run_shell_command(
                    shell_team_id,
                    shell_cmd,
                    purpose=shell_purpose,
                    timeout=self.timeout,
                )
                if progress_callback is not None and output:
                    for line in output.splitlines()[-10:]:
                        try:
                            await progress_callback(line)
                        except Exception as cb_err:
                            logger.warning(f"progress_callback 오류: {cb_err}")
                self._last_run_metrics = {
                    "output_chars": len(output or ""),
                    "usage_source": "subprocess_no_usage",
                }
                if exit_code != 0 and not output:
                    return f"❌ 프로세스 오류 (code={exit_code})"
                return output or "(결과 없음)"
            except asyncio.TimeoutError:
                msg = f"❌ 타임아웃 ({self.timeout}s) 초과: {' '.join(cmd[:3])}"
                logger.error(msg)
                return msg

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=1024 * 1024 * 10,  # 10MB — 기본 64KB 한도 초과 방지
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
            while True:
                try:
                    raw_line = await proc.stdout.readline()
                except asyncio.LimitOverrunError as exc:
                    logger.warning(
                        f"[subprocess] LimitOverrunError: 단일 라인이 10MB 버퍼 초과 "
                        f"({exc.consumed:,} bytes). 초과 라인 스킵."
                    )
                    try:
                        await proc.stdout.read(exc.consumed)
                        while True:
                            try:
                                await proc.stdout.readline()
                                break
                            except asyncio.LimitOverrunError as inner_exc:
                                await proc.stdout.read(inner_exc.consumed)
                    except Exception as drain_err:
                        logger.error(f"[subprocess] 초과 라인 drain 실패, 스트림 중단: {drain_err}")
                        break
                    continue
                if not raw_line:
                    break
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
        except asyncio.CancelledError:
            # 외부 watchdog에 의한 취소 — subprocess 정리 + 부분 결과 보존
            try:
                proc.kill()
                await proc.wait()
            except Exception as _kill_err:
                logger.warning(f"[subprocess] CancelledError 시 proc.kill 실패: {_kill_err}")
            if output_lines:
                self._last_partial_output = "\n".join(output_lines[-30:])
            logger.warning(
                f"[subprocess] 외부 취소로 subprocess 종료. "
                f"부분 결과 {len(output_lines)}줄 보존 ({len(self._last_partial_output)}자)."
            )
            raise  # CancelledError 재전파
        except Exception as exc:
            proc.kill()
            await proc.wait()
            msg = f"❌ 실행 중 오류 발생: {exc}"
            logger.exception(msg)
            return msg

        full_output = "\n".join(output_lines)
        self._last_run_metrics = {
            "output_chars": len(full_output or ""),
            "usage_source": "subprocess_no_usage",
        }

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

    def _build_shell_command(self, cmd: list[str], env: dict[str, str], workdir: str) -> str:
        env_parts: list[str] = []
        for key in ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"):
            if key in env:
                env_parts.append(f"{key}={shlex.quote(env[key])}")
        env_prefix = f"env {' '.join(env_parts)} " if env_parts else "env "
        return f"cd {shlex.quote(workdir)} && {env_prefix}{shlex.join(cmd)}"

    async def _auto_upload(self, response: str, bot_token: str, chat_id: int) -> None:
        """응답에서 생성된 파일 경로 감지 → 자동 텔레그램 업로드."""
        from tools.telegram_uploader import upload_file

        matches = FILE_PATTERN.findall(response)
        for fpath in matches:
            fpath = os.path.expanduser(fpath.strip())
            if os.path.exists(fpath):
                logger.info(f"[auto_upload] {fpath}")
                await upload_file(bot_token, chat_id, fpath, f"📄 생성된 파일: {Path(fpath).name}")
