"""GeminiCLIRunner 단위 테스트 — subprocess mock 기반."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.base_runner import RunContext, RunnerError, RunnerFactory, RunnerTimeoutError
from tools.gemini_cli_runner import GeminiCLIRunner, _sanitize_output, _extract_json_block


# ---------------------------------------------------------------------------
# _sanitize_output
# ---------------------------------------------------------------------------

def test_sanitize_removes_noise_lines() -> None:
    raw = "Loaded cached credentials.\nHello world"
    assert _sanitize_output(raw) == "Hello world"


def test_sanitize_preserves_normal_lines() -> None:
    raw = "This is a normal response."
    assert _sanitize_output(raw) == raw


def test_sanitize_case_insensitive() -> None:
    raw = "LOADED CACHED CREDENTIALS.\nActual response"
    assert _sanitize_output(raw) == "Actual response"


# ---------------------------------------------------------------------------
# _extract_json_block
# ---------------------------------------------------------------------------

def test_extract_json_block_with_prefix() -> None:
    text = "noise\n{\"key\": \"val\"}"
    result = _extract_json_block(text)
    assert result.startswith("{")


def test_extract_json_block_no_json() -> None:
    text = "plain text only"
    assert _extract_json_block(text) == text


# ---------------------------------------------------------------------------
# GeminiCLIRunner.run — 정상 케이스
# ---------------------------------------------------------------------------

@pytest.fixture()
def runner() -> GeminiCLIRunner:
    return GeminiCLIRunner()


def _make_proc(stdout: bytes, stderr: bytes = b"", returncode: int = 0) -> MagicMock:
    """asyncio.create_subprocess_exec mock 반환."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    return proc


@pytest.mark.asyncio
async def test_run_success_json(runner: GeminiCLIRunner) -> None:
    payload = {"response": "pong", "session_id": "abc", "stats": {"models": {}}}
    stdout = (f"Loaded cached credentials.\n{json.dumps(payload)}").encode()

    proc = _make_proc(stdout)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        ctx = RunContext(prompt="ping")
        result = await runner.run(ctx)

    assert result == "pong"
    assert runner.get_last_metrics()["usage_source"] == "gemini_cli_json"


@pytest.mark.asyncio
async def test_run_success_with_token_metrics(runner: GeminiCLIRunner) -> None:
    payload = {
        "response": "hello",
        "stats": {
            "models": {
                "gemini-2.5-flash": {
                    "tokens": {"total": 500}
                }
            }
        },
    }
    stdout = json.dumps(payload).encode()
    proc = _make_proc(stdout)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        result = await runner.run(RunContext(prompt="hi"))

    assert result == "hello"
    assert runner.get_last_metrics()["total_tokens"] == 500


@pytest.mark.asyncio
async def test_run_plain_text_fallback(runner: GeminiCLIRunner) -> None:
    """JSON 파싱 실패 시 plain text 폴백."""
    stdout = b"Loaded cached credentials.\nThis is plain text."
    proc = _make_proc(stdout)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        result = await runner.run(RunContext(prompt="hi"))

    assert result == "This is plain text."
    assert runner.get_last_metrics()["usage_source"] == "gemini_cli_plain"


@pytest.mark.asyncio
async def test_run_empty_response_returns_placeholder(runner: GeminiCLIRunner) -> None:
    payload = {"response": "", "stats": {}}
    stdout = json.dumps(payload).encode()
    proc = _make_proc(stdout)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        result = await runner.run(RunContext(prompt=""))

    assert result == "(결과 없음)"


# ---------------------------------------------------------------------------
# GeminiCLIRunner.run — 오류 케이스
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_nonzero_returncode_raises(runner: GeminiCLIRunner) -> None:
    proc = _make_proc(b"", stderr=b"auth error", returncode=1)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        with pytest.raises(RunnerError, match="Gemini CLI 오류"):
            await runner.run(RunContext(prompt="hi"))


@pytest.mark.asyncio
async def test_run_timeout_raises(runner: GeminiCLIRunner) -> None:
    proc = MagicMock()
    proc.returncode = None
    proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
    proc.kill = MagicMock()

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        with pytest.raises(RunnerTimeoutError):
            await runner.run(RunContext(prompt="hi"))


@pytest.mark.asyncio
async def test_run_file_not_found_raises(runner: GeminiCLIRunner) -> None:
    with patch("asyncio.create_subprocess_exec", AsyncMock(side_effect=FileNotFoundError())):
        with pytest.raises(RunnerError, match="Gemini CLI 없음"):
            await runner.run(RunContext(prompt="hi"))


# ---------------------------------------------------------------------------
# API 키 환경 격리 확인
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_keys_removed_from_env(runner: GeminiCLIRunner) -> None:
    """GEMINI_API_KEY / GOOGLE_API_KEY 가 subprocess 환경에서 제거되는지 확인."""
    captured_env: dict = {}

    async def fake_exec(*args, **kwargs):  # type: ignore[override]
        captured_env.update(kwargs.get("env", {}))
        return _make_proc(b'{"response": "ok", "stats": {}}')

    import os
    with patch.dict(os.environ, {"GEMINI_API_KEY": "secret1", "GOOGLE_API_KEY": "secret2"}):
        with patch("asyncio.create_subprocess_exec", fake_exec):
            await runner.run(RunContext(prompt="test"))

    assert "GEMINI_API_KEY" not in captured_env
    assert "GOOGLE_API_KEY" not in captured_env


# ---------------------------------------------------------------------------
# RunnerFactory 등록 확인
# ---------------------------------------------------------------------------

def test_runner_factory_creates_gemini_cli() -> None:
    runner = RunnerFactory.create("gemini-cli")
    assert isinstance(runner, GeminiCLIRunner)


def test_runner_factory_unknown_engine_error() -> None:
    with pytest.raises(ValueError, match="Unknown engine"):
        RunnerFactory.create("unknown-engine-xyz")
