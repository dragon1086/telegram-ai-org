"""ClaudeAgentRunner — BaseRunner + ClaudeSpecificMixin implementation using claude_agent_sdk."""

from __future__ import annotations

import logging
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    CLIConnectionError,
    CLINotFoundError,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    query,
)
from claude_agent_sdk.types import TextBlock

from tools.base_runner import (
    BaseRunner,
    ClaudeSpecificMixin,
    RunContext,
    RunnerError,
)

logger = logging.getLogger(__name__)

_DEFAULT_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]


class ClaudeAgentRunner(BaseRunner, ClaudeSpecificMixin):
    """Runner that uses claude_agent_sdk.query() as the execution backend."""

    def __init__(self, **kwargs: Any) -> None:
        self._kwargs = kwargs
        self._metrics: dict[str, Any] = {}
        self.session_id: str | None = None

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    async def run(self, ctx: RunContext) -> str:
        """Execute prompt via claude_agent_sdk.query() and return result text."""
        allowed_tools: list[str] = ctx.engine_config.get("allowed_tools", _DEFAULT_TOOLS)
        permission_mode: str = ctx.engine_config.get("permission_mode", "bypassPermissions")
        model: str | None = ctx.engine_config.get("model")
        resume: str | None = ctx.engine_config.get("resume") or ctx.session_id

        options = ClaudeAgentOptions(
            cwd=ctx.workdir,
            system_prompt=ctx.system_prompt,
            permission_mode=permission_mode,  # type: ignore[arg-type]
            allowed_tools=allowed_tools,
            model=model,
            resume=resume,
        )

        output: str = ""

        try:
            async for message in query(prompt=ctx.prompt, options=options):
                if isinstance(message, SystemMessage):
                    if message.subtype == "init":
                        self.session_id = message.data.get("session_id") or self.session_id

                elif isinstance(message, AssistantMessage):
                    if ctx.progress_callback is not None:
                        text_parts = [
                            block.text
                            for block in message.content
                            if isinstance(block, TextBlock)
                        ]
                        if text_parts:
                            try:
                                await ctx.progress_callback("".join(text_parts))
                            except Exception:
                                pass

                elif isinstance(message, ResultMessage):
                    if message.result is not None:
                        output = message.result
                    self._metrics = {
                        "duration_ms": message.duration_ms,
                        "duration_api_ms": message.duration_api_ms,
                        "is_error": message.is_error,
                        "num_turns": message.num_turns,
                        "session_id": message.session_id,
                        "stop_reason": message.stop_reason,
                        "total_cost_usd": message.total_cost_usd,
                        "usage": message.usage,
                    }
                    if message.session_id:
                        self.session_id = message.session_id
                    if message.is_error:
                        raise RunnerError(f"claude_agent_sdk returned error: {output}")

        except CLINotFoundError as exc:
            raise RunnerError(f"Claude CLI not found: {exc}") from exc
        except CLIConnectionError as exc:
            raise RunnerError(f"Claude CLI connection failed: {exc}") from exc

        return output

    # ------------------------------------------------------------------
    # BaseRunner overrides
    # ------------------------------------------------------------------

    async def run_single(self, ctx: RunContext) -> str:
        """Execute a single prompt, threading persona/session_store/org_id via engine_config."""
        merged_config = dict(ctx.engine_config)
        if ctx.persona and "persona" not in merged_config:
            merged_config["persona"] = ctx.persona
        if ctx.session_store is not None and "session_store" not in merged_config:
            merged_config["session_store"] = ctx.session_store
        if ctx.org_id and "org_id" not in merged_config:
            merged_config["org_id"] = ctx.org_id

        merged_ctx = RunContext(
            prompt=ctx.prompt,
            workdir=ctx.workdir,
            system_prompt=ctx.system_prompt,
            progress_callback=ctx.progress_callback,
            session_id=ctx.session_id,
            persona=ctx.persona,
            session_store=ctx.session_store,
            org_id=ctx.org_id,
            global_context=ctx.global_context,
            engine_config=merged_config,
        )
        return await self.run(merged_ctx)

    async def run_task(self, ctx: RunContext) -> str:
        """Prepend system_prompt to prompt then delegate to run()."""
        if ctx.system_prompt:
            combined_prompt = f"{ctx.system_prompt}\n\n{ctx.prompt}"
            task_ctx = RunContext(
                prompt=combined_prompt,
                workdir=ctx.workdir,
                system_prompt=None,
                progress_callback=ctx.progress_callback,
                session_id=ctx.session_id,
                persona=ctx.persona,
                session_store=ctx.session_store,
                org_id=ctx.org_id,
                global_context=ctx.global_context,
                engine_config=ctx.engine_config,
            )
            return await self.run(task_ctx)
        return await self.run(ctx)

    # ------------------------------------------------------------------
    # ClaudeSpecificMixin — team modes
    # ------------------------------------------------------------------

    async def run_structured_team(self, *args: Any, **kwargs: Any) -> str:
        """Run structured team execution via run() with team config."""
        task: str = args[0] if args else kwargs.get("task", "")
        agents: list[str] = (args[1] if len(args) > 1 else kwargs.get("agents", []))
        progress_callback = kwargs.get("progress_callback")
        workdir: str | None = kwargs.get("workdir")
        system_prompt: str = kwargs.get("system_prompt", "")
        engine_config = dict(kwargs.get("engine_config") or {})
        engine_config["team_mode"] = "structured"
        engine_config["agents"] = agents

        ctx = RunContext(
            prompt=task,
            workdir=workdir,
            system_prompt=system_prompt or None,
            progress_callback=progress_callback,
            engine_config=engine_config,
        )
        return await self.run(ctx)

    async def run_agent_teams(self, *args: Any, **kwargs: Any) -> str:
        """Run agent teams execution via run() with team config."""
        task: str = args[0] if args else kwargs.get("task", "")
        agent_personas: list[str] = (args[1] if len(args) > 1 else kwargs.get("agent_personas", []))
        progress_callback = kwargs.get("progress_callback")
        workdir: str | None = kwargs.get("workdir")
        system_prompt: str = kwargs.get("system_prompt", "")
        engine_config = dict(kwargs.get("engine_config") or {})
        engine_config["team_mode"] = "agent_teams"
        engine_config["agent_personas"] = agent_personas

        ctx = RunContext(
            prompt=task,
            workdir=workdir,
            system_prompt=system_prompt or None,
            progress_callback=progress_callback,
            engine_config=engine_config,
        )
        return await self.run(ctx)

    async def run_omc_team(self, *args: Any, **kwargs: Any) -> str:
        """Legacy alias — delegates to run_structured_team."""
        return await self.run_structured_team(*args, **kwargs)

    # ------------------------------------------------------------------
    # Metrics / capabilities
    # ------------------------------------------------------------------

    def get_last_metrics(self) -> dict:
        return dict(self._metrics)

    def capabilities(self) -> set[str]:
        return {"streaming", "session_resumption", "team", "tools"}
