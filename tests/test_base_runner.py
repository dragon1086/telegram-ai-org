"""Tests for BaseRunner ABC, RunContext, RunnerError hierarchy, and RunnerFactory."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# RunContext defaults
# ---------------------------------------------------------------------------

def test_run_context_defaults() -> None:
    """RunContext(prompt='test') has correct defaults for all optional fields."""
    from tools.base_runner import RunContext

    ctx = RunContext(prompt="test")

    assert ctx.prompt == "test"
    assert ctx.workdir is None
    assert ctx.system_prompt is None
    assert ctx.progress_callback is None
    assert ctx.session_id is None
    assert ctx.persona is None
    assert ctx.session_store is None
    assert ctx.org_id is None
    assert ctx.global_context is None
    assert ctx.engine_config == {}


def test_run_context_stores_prompt() -> None:
    """RunContext stores the provided prompt value."""
    from tools.base_runner import RunContext

    ctx = RunContext(prompt="hello world")
    assert ctx.prompt == "hello world"


def test_run_context_accepts_engine_config() -> None:
    """RunContext accepts engine_config dict and stores it."""
    from tools.base_runner import RunContext

    config = {"model": "claude-3-5-sonnet", "allowed_tools": ["bash"]}
    ctx = RunContext(prompt="task", engine_config=config)
    assert ctx.engine_config["model"] == "claude-3-5-sonnet"


# ---------------------------------------------------------------------------
# RunnerError hierarchy
# ---------------------------------------------------------------------------

def test_runner_error_is_exception() -> None:
    """RunnerError is a subclass of Exception."""
    from tools.base_runner import RunnerError

    assert issubclass(RunnerError, Exception)


def test_runner_auth_error_is_runner_error() -> None:
    """RunnerAuthError is a subclass of RunnerError."""
    from tools.base_runner import RunnerAuthError, RunnerError

    assert issubclass(RunnerAuthError, RunnerError)


def test_runner_rate_limit_error_is_runner_error() -> None:
    """RunnerRateLimitError is a subclass of RunnerError."""
    from tools.base_runner import RunnerError, RunnerRateLimitError

    assert issubclass(RunnerRateLimitError, RunnerError)


def test_runner_timeout_error_is_runner_error() -> None:
    """RunnerTimeoutError is a subclass of RunnerError."""
    from tools.base_runner import RunnerError, RunnerTimeoutError

    assert issubclass(RunnerTimeoutError, RunnerError)


def test_runner_error_hierarchy_all_subclasses() -> None:
    """RunnerAuthError, RunnerRateLimitError, RunnerTimeoutError are all RunnerError subclasses."""
    from tools.base_runner import (
        RunnerAuthError,
        RunnerError,
        RunnerRateLimitError,
        RunnerTimeoutError,
    )

    for cls in (RunnerAuthError, RunnerRateLimitError, RunnerTimeoutError):
        assert issubclass(cls, RunnerError), f"{cls.__name__} must be a RunnerError subclass"


def test_runner_error_can_be_raised_and_caught() -> None:
    """RunnerError subclasses can be raised and caught as RunnerError."""
    from tools.base_runner import RunnerAuthError, RunnerError

    with pytest.raises(RunnerError):
        raise RunnerAuthError("missing API key")


# ---------------------------------------------------------------------------
# RunnerFactory
# ---------------------------------------------------------------------------

def test_runner_factory_unknown_raises_value_error() -> None:
    """RunnerFactory.create('unknown') raises ValueError."""
    from tools.base_runner import RunnerFactory

    with pytest.raises(ValueError, match="unknown"):
        RunnerFactory.create("unknown")


def test_runner_factory_codex_returns_base_runner_instance() -> None:
    """RunnerFactory.create('codex') returns a BaseRunner instance."""
    from tools.base_runner import BaseRunner, RunnerFactory

    runner = RunnerFactory.create("codex")
    assert isinstance(runner, BaseRunner)


def test_runner_factory_codex_returns_codex_runner() -> None:
    """RunnerFactory.create('codex') returns a CodexRunner."""
    from tools.base_runner import RunnerFactory
    from tools.codex_runner import CodexRunner

    runner = RunnerFactory.create("codex")
    assert isinstance(runner, CodexRunner)


def test_runner_factory_gemini_returns_base_runner_instance() -> None:
    """RunnerFactory.create('gemini') returns a BaseRunner instance."""
    from tools.base_runner import BaseRunner, RunnerFactory

    # Mock google.genai so GeminiRunner can be imported without the SDK installed
    fake_genai = MagicMock()
    with patch.dict("sys.modules", {"google": fake_genai, "google.genai": fake_genai}):
        runner = RunnerFactory.create("gemini")
    assert isinstance(runner, BaseRunner)


def test_runner_factory_gemini_returns_gemini_runner() -> None:
    """RunnerFactory.create('gemini') returns a GeminiRunner."""
    from tools.base_runner import RunnerFactory

    fake_genai = MagicMock()
    with patch.dict("sys.modules", {"google": fake_genai, "google.genai": fake_genai}):
        from tools.gemini_runner import GeminiRunner
        runner = RunnerFactory.create("gemini")
    assert isinstance(runner, GeminiRunner)


def test_runner_factory_claude_returns_base_runner_instance() -> None:
    """RunnerFactory.create('claude-code') returns a BaseRunner instance."""
    from tools.base_runner import BaseRunner, RunnerFactory

    # ClaudeAgentRunner requires claude_agent_sdk; mock it so factory falls
    # back to ClaudeSubprocessRunner (which has no optional deps).
    fake_sdk = MagicMock()
    with patch.dict("sys.modules", {"claude_agent_sdk": fake_sdk}):
        runner = RunnerFactory.create("claude-code")
    assert isinstance(runner, BaseRunner)
