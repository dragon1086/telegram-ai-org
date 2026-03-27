"""GeminiCLIRunner Preview 모델 폴백 단위 테스트.

Preview 모델 호출 실패 시 GEMINI_FALLBACK_MODEL(기본값: gemini-2.5-flash GA)로
자동 재시도하는 로직을 검증한다.
"""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from tools.base_runner import RunContext, RunnerError
from tools.gemini_cli_runner import GeminiCLIRunner


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _make_proc(stdout: bytes, stderr: bytes = b"", returncode: int = 0) -> MagicMock:
    """asyncio.create_subprocess_exec mock 반환."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    return proc


def _ok_proc(text: str = "fallback response") -> MagicMock:
    payload = {"response": text, "stats": {"models": {}}}
    return _make_proc(json.dumps(payload).encode())


def _fail_proc() -> MagicMock:
    return _make_proc(b"", stderr=b"model not available", returncode=1)


# ---------------------------------------------------------------------------
# 폴백 발동 조건
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_triggered_on_preview_model_failure() -> None:
    """Preview 모델 실패 시 GEMINI_FALLBACK_MODEL(gemini-2.5-flash)로 재시도한다."""
    runner = GeminiCLIRunner()
    ctx = RunContext(
        prompt="test",
        engine_config={"model": "gemini-2.5-flash-preview-image-generation"},
    )

    # 1차 호출(Preview): 실패 / 2차 호출(GA): 성공
    call_count = 0

    async def fake_exec(*args, **kwargs):  # type: ignore[override]
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _fail_proc()
        return _ok_proc("fallback ok")

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        result = await runner.run(ctx)

    assert result == "fallback ok"
    assert call_count == 2


@pytest.mark.asyncio
async def test_fallback_uses_correct_model_arg() -> None:
    """폴백 시 subprocess에 --model gemini-2.5-flash 인자가 전달된다."""
    runner = GeminiCLIRunner()
    ctx = RunContext(
        prompt="hi",
        engine_config={"model": "gemini-3-flash-preview"},
    )

    captured_cmds: list[tuple] = []
    call_count = 0

    async def fake_exec(*args, **kwargs):  # type: ignore[override]
        nonlocal call_count
        call_count += 1
        captured_cmds.append(args)
        if call_count == 1:
            return _fail_proc()
        return _ok_proc()

    with patch.dict(os.environ, {"GEMINI_FALLBACK_MODEL": "gemini-2.5-flash"}):
        with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            await runner.run(ctx)

    # 2차 호출 커맨드에 --model gemini-2.5-flash 가 포함되어야 한다
    assert call_count == 2
    second_cmd = list(captured_cmds[1])
    model_idx = second_cmd.index("--model")
    assert second_cmd[model_idx + 1] == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_fallback_not_triggered_when_model_already_ga() -> None:
    """이미 GA 모델(gemini-2.5-flash)이면 폴백 없이 에러를 그대로 전파한다."""
    runner = GeminiCLIRunner()
    ctx = RunContext(
        prompt="hi",
        engine_config={"model": "gemini-2.5-flash"},
    )

    call_count = 0

    async def fake_exec(*args, **kwargs):  # type: ignore[override]
        nonlocal call_count
        call_count += 1
        return _fail_proc()

    with patch.dict(os.environ, {"GEMINI_FALLBACK_MODEL": "gemini-2.5-flash"}):
        with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            with pytest.raises(RunnerError):
                await runner.run(ctx)

    # 폴백 없이 1회만 호출
    assert call_count == 1


@pytest.mark.asyncio
async def test_fallback_not_triggered_when_no_model_specified() -> None:
    """모델이 지정되지 않은 경우(기본 모델) 폴백 없이 에러를 전파한다."""
    runner = GeminiCLIRunner()
    ctx = RunContext(prompt="hi")

    call_count = 0

    async def fake_exec(*args, **kwargs):  # type: ignore[override]
        nonlocal call_count
        call_count += 1
        return _fail_proc()

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        with pytest.raises(RunnerError):
            await runner.run(ctx)

    assert call_count == 1


@pytest.mark.asyncio
async def test_fallback_model_env_override() -> None:
    """GEMINI_FALLBACK_MODEL 환경변수로 폴백 모델을 커스터마이즈할 수 있다."""
    runner = GeminiCLIRunner()
    ctx = RunContext(
        prompt="test",
        engine_config={"model": "gemini-2.5-flash-preview-image-generation"},
    )

    captured_cmds: list[tuple] = []
    call_count = 0
    custom_fallback = "gemini-2.5-flash-8b"

    async def fake_exec(*args, **kwargs):  # type: ignore[override]
        nonlocal call_count
        call_count += 1
        captured_cmds.append(args)
        if call_count == 1:
            return _fail_proc()
        return _ok_proc("custom fallback ok")

    # 모듈 레벨 상수 재정의 (환경변수는 모듈 임포트 시 읽히므로 패치로 우회)
    with patch("tools.gemini_cli_runner.GEMINI_FALLBACK_MODEL", custom_fallback):
        with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            result = await runner.run(ctx)

    assert result == "custom fallback ok"
    second_cmd = list(captured_cmds[1])
    model_idx = second_cmd.index("--model")
    assert second_cmd[model_idx + 1] == custom_fallback


@pytest.mark.asyncio
async def test_fallback_logs_warning() -> None:
    """폴백 발동 시 [FALLBACK] 경고 로그가 출력된다 (loguru 캡처)."""
    from loguru import logger as loguru_logger

    runner = GeminiCLIRunner()
    ctx = RunContext(
        prompt="hi",
        engine_config={"model": "gemini-2.5-flash-preview-image-generation"},
    )

    call_count = 0
    captured_messages: list[str] = []

    def sink(message) -> None:  # type: ignore[override]
        captured_messages.append(message)

    handler_id = loguru_logger.add(sink, level="WARNING")

    async def fake_exec(*args, **kwargs):  # type: ignore[override]
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _fail_proc()
        return _ok_proc()

    try:
        with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            await runner.run(ctx)
    finally:
        loguru_logger.remove(handler_id)

    assert any("[FALLBACK]" in msg for msg in captured_messages)


@pytest.mark.asyncio
async def test_fallback_second_attempt_also_fails_raises() -> None:
    """폴백 모델도 실패하면 RunnerError를 전파한다."""
    runner = GeminiCLIRunner()
    ctx = RunContext(
        prompt="hi",
        engine_config={"model": "gemini-2.5-flash-preview-image-generation"},
    )

    async def fake_exec(*args, **kwargs):  # type: ignore[override]
        return _fail_proc()

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        with pytest.raises(RunnerError):
            await runner.run(ctx)
