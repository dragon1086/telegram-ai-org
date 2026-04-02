"""Base runner abstraction for engine execution.

Provides BaseRunner ABC, RunContext dataclass, RunnerError hierarchy,
ClaudeSpecificMixin, and RunnerFactory for unified engine execution.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------

class RunnerError(Exception):
    """Base exception for runner errors."""


class RunnerAuthError(RunnerError):
    """API key missing or invalid."""


class RunnerRateLimitError(RunnerError):
    """Rate limit hit."""


class RunnerTimeoutError(RunnerError):
    """Execution timed out."""


# ---------------------------------------------------------------------------
# RunContext
# ---------------------------------------------------------------------------

@dataclass
class RunContext:
    """Unified execution context for all runners."""

    prompt: str
    workdir: str | None = None
    system_prompt: str | None = None
    progress_callback: Callable[..., Any] | None = None
    session_id: str | None = None
    persona: str | None = None
    session_store: dict | None = None
    org_id: str | None = None
    global_context: str | None = None
    engine_config: dict = field(default_factory=dict)
    # engine_config examples:
    # Claude: {"allowed_tools": [...], "permission_mode": "bypassPermissions",
    #          "model": "...", "flags": ["--verbose"]}
    # Codex:  {"model": "...", "agents": [...]}
    # Gemini: {"model": "gemini-2.5-flash", "temperature": 0.7}
    # Note: ClaudeCodeRunner.run(prompt, flags=) flags absorbed into engine_config["flags"]


# ---------------------------------------------------------------------------
# BaseRunner ABC
# ---------------------------------------------------------------------------

class BaseRunner(ABC):
    """Abstract base class for all engine runners."""

    @abstractmethod
    async def run(self, ctx: RunContext) -> str:
        """Execute a prompt and return the result."""
        ...

    async def run_single(self, ctx: RunContext) -> str:
        """Execute a single prompt (default: delegates to run)."""
        return await self.run(ctx)

    async def run_task(self, ctx: RunContext) -> str:
        """Execute with system_prompt prepended (default: prepend + run)."""
        if ctx.system_prompt:
            combined = RunContext(
                prompt=f"{ctx.system_prompt}\n\n{ctx.prompt}",
                workdir=ctx.workdir,
                progress_callback=ctx.progress_callback,
                session_id=ctx.session_id,
                persona=ctx.persona,
                session_store=ctx.session_store,
                org_id=ctx.org_id,
                global_context=ctx.global_context,
                engine_config=ctx.engine_config,
            )
            return await self.run(combined)
        return await self.run(ctx)

    def get_last_metrics(self) -> dict:
        """Return metrics from the last execution."""
        return {}

    def capabilities(self) -> set[str]:
        """Return set of supported capabilities.

        Known capabilities: 'streaming', 'session_resumption', 'team', 'tools'
        """
        return set()


# ---------------------------------------------------------------------------
# ClaudeSpecificMixin — team methods only Claude runners implement
# ---------------------------------------------------------------------------

class ClaudeSpecificMixin(ABC):
    """Mixin for Claude-specific team execution methods."""

    @abstractmethod
    async def run_structured_team(self, *args: Any, **kwargs: Any) -> str:
        """Run structured team execution (Claude only)."""
        ...

    @abstractmethod
    async def run_agent_teams(self, *args: Any, **kwargs: Any) -> str:
        """Run agent teams execution (Claude only)."""
        ...

    @abstractmethod
    async def run_omc_team(self, *args: Any, **kwargs: Any) -> str:
        """Run OMC team execution (Claude only)."""
        ...


# ---------------------------------------------------------------------------
# RunnerFactory
# ---------------------------------------------------------------------------

class RunnerFactory:
    """Factory for creating engine-specific runners."""

    _registry: dict[str, type[BaseRunner]] = {}

    @classmethod
    def register(cls, engine: str, runner_class: type[BaseRunner]) -> None:
        """Register a runner class for an engine name."""
        cls._registry[engine] = runner_class

    @classmethod
    def create(cls, engine: str, **kwargs: Any) -> BaseRunner:
        """Create a runner for the given engine.

        Args:
            engine: Engine name ('claude-code', 'codex', 'gemini', 'gemini-cli')
            **kwargs: Passed to runner constructor

        Returns:
            BaseRunner instance

        Raises:
            ValueError: Unknown engine name
        """
        # Lazy imports to avoid circular deps and allow optional installs
        if engine == "claude-code":
            return cls._create_claude_runner(**kwargs)
        elif engine == "codex":
            from tools.codex_runner import CodexRunner
            return CodexRunner(**kwargs)
        elif engine in ("gemini", "gemini-2.5-flash"):
            from tools.gemini_runner import GeminiRunner
            runner = GeminiRunner(**kwargs)
            # gemini-2.5-flash 명시 시 RunContext의 engine_config에 model 주입
            if engine == "gemini-2.5-flash":
                runner._default_model = "gemini-2.5-flash"
            return runner
        elif engine == "gemini-cli":
            from tools.gemini_cli_runner import GeminiCLIRunner
            return GeminiCLIRunner(**kwargs)
        elif engine in cls._registry:
            return cls._registry[engine](**kwargs)
        else:
            raise ValueError(
                f"Unknown engine: {engine!r}. "
                f"Valid engines: 'claude-code', 'codex', 'gemini', 'gemini-2.5-flash', 'gemini-cli'"
            )

    @classmethod
    def _create_claude_runner(cls, **kwargs: Any) -> BaseRunner:
        """Create Claude runner based on CLAUDE_RUNNER_MODE env var.

        Modes:
          - "cli" (default): Use Claude Code CLI subprocess — supports all auth
            methods (OAuth token, API key, z.ai proxy). Recommended for most setups.
          - "sdk": Use claude_agent_sdk Python package — requires ANTHROPIC_API_KEY.
            Faster for short prompts but limited auth options.
          - "auto": Prefer CLI when any auth token is detected, fall back to SDK.

        The CLI subprocess inherits env vars (ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL,
        ANTHROPIC_API_KEY, CLAUDE_CODE_OAUTH_TOKEN) and handles routing automatically.
        """
        import os

        mode = os.environ.get("CLAUDE_RUNNER_MODE", "cli").lower()

        # Determine if we should prefer CLI
        prefer_cli = (
            mode == "cli"
            or (mode == "auto" and (
                os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
                or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or not os.environ.get("ANTHROPIC_API_KEY")
            ))
        )

        if prefer_cli:
            try:
                from tools.claude_subprocess_runner import ClaudeSubprocessRunner
                _auth = "AUTH_TOKEN" if os.environ.get("ANTHROPIC_AUTH_TOKEN") else (
                    "OAUTH" if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") else "API_KEY"
                )
                logger.info(f"Claude runner: CLI subprocess (auth={_auth}, mode={mode})")
                return ClaudeSubprocessRunner(**kwargs)
            except (ImportError, Exception) as e:
                logger.warning("CLI runner unavailable (%s), trying SDK", e)

        # SDK fallback
        try:
            from tools.claude_agent_runner import ClaudeAgentRunner
            logger.info("Claude runner: SDK (mode=%s)", mode)
            return ClaudeAgentRunner(**kwargs)
        except (ImportError, Exception) as e:
            logger.warning(
                "SDK runner unavailable (%s), falling back to CLI subprocess", e,
            )
            from tools.claude_subprocess_runner import ClaudeSubprocessRunner
            return ClaudeSubprocessRunner(**kwargs)
