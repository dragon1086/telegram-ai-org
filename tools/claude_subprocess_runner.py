"""ClaudeSubprocessRunner — adapter wrapping ClaudeCodeRunner behind BaseRunner interface."""

from __future__ import annotations

from typing import Any

from tools.base_runner import BaseRunner, ClaudeSpecificMixin, RunContext, RunnerError


class ClaudeSubprocessRunner(BaseRunner, ClaudeSpecificMixin):
    """Wrapper/adapter that delegates to an internal ClaudeCodeRunner instance."""

    def __init__(self, **kwargs: Any) -> None:
        from tools.claude_code_runner import ClaudeCodeRunner

        self._runner = ClaudeCodeRunner(**kwargs)

    # ------------------------------------------------------------------
    # BaseRunner abstract
    # ------------------------------------------------------------------

    async def run(self, ctx: RunContext) -> str:
        """Execute a prompt via ClaudeCodeRunner.run()."""
        flags = ctx.engine_config.get("flags")
        try:
            if flags:
                result = await self._runner.run(ctx.prompt, flags=flags)
            else:
                result = await self._runner.run(ctx.prompt)
        except Exception as exc:
            raise RunnerError(str(exc)) from exc

        if isinstance(result, str) and result.startswith("❌"):
            raise RunnerError(result)
        return result

    async def run_single(self, ctx: RunContext) -> str:
        """Execute a single prompt via ClaudeCodeRunner.run_single()."""
        extra = {
            k: v
            for k, v in ctx.engine_config.items()
            if k in ("shell_session_manager", "shell_team_id")
        }
        return await self._runner.run_single(
            ctx.prompt,
            workdir=ctx.workdir,
            system_prompt=ctx.system_prompt or "",
            progress_callback=ctx.progress_callback,
            persona=ctx.persona,
            session_store=ctx.session_store,
            org_id=ctx.org_id or "global",
            global_context=ctx.global_context,
            **extra,
        )

    async def run_task(self, ctx: RunContext) -> str:
        """Execute a task via ClaudeCodeRunner.run_task()."""
        return await self._runner.run_task(
            ctx.prompt,
            system_prompt=ctx.system_prompt or "",
            progress_callback=ctx.progress_callback,
            session_store=ctx.session_store,
            global_context=ctx.global_context,
            org_id=ctx.org_id or "global",
            workdir=ctx.workdir,
        )

    # ------------------------------------------------------------------
    # ClaudeSpecificMixin abstract — direct delegation
    # ------------------------------------------------------------------

    async def run_structured_team(self, *args: Any, **kwargs: Any) -> str:
        return await self._runner.run_structured_team(*args, **kwargs)

    async def run_agent_teams(self, *args: Any, **kwargs: Any) -> str:
        return await self._runner.run_agent_teams(*args, **kwargs)

    async def run_omc_team(self, *args: Any, **kwargs: Any) -> str:
        return await self._runner.run_omc_team(*args, **kwargs)

    # ------------------------------------------------------------------
    # Metrics & capabilities
    # ------------------------------------------------------------------

    def get_last_metrics(self) -> dict:
        if hasattr(self._runner, "get_last_metrics"):
            return self._runner.get_last_metrics()
        return {}

    def capabilities(self) -> set[str]:
        return {"streaming", "session_resumption", "team", "tools"}
