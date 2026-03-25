"""Tests for asyncio.LimitOverrunError handling in ClaudeCodeRunner._read_stream()."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeStreamReader:
    """asyncio.StreamReader를 흉내내는 가짜 스트림. 미리 정해진 줄 목록을 반환한다."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)
        self._index = 0

    async def readline(self) -> bytes:
        if self._index >= len(self._lines):
            return b""
        val = self._lines[self._index]
        self._index += 1
        if isinstance(val, asyncio.LimitOverrunError):
            raise val
        return val

    async def read(self, n: int) -> bytes:
        # drain용 — 소비할 내용이 있다면 그냥 빈 바이트 반환
        return b""

    def __aiter__(self):
        return self

    async def __anext__(self):
        line = await self.readline()
        if not line:
            raise StopAsyncIteration
        return line


def _make_runner():
    """실제 CLI 없이 ClaudeCodeRunner 인스턴스 생성."""
    with patch("pathlib.Path.mkdir"):
        from tools.claude_code_runner import ClaudeCodeRunner
        return ClaudeCodeRunner(cli_path="/fake/claude", timeout=10, workdir="/tmp")


# ---------------------------------------------------------------------------
# Test: 정상 JSON 스트림 (regression 확인)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_stream_normal_json_lines() -> None:
    """정상 JSON 라인들이 올바르게 파싱되어 final_result가 채워지는지 확인."""
    result_event = json.dumps({
        "type": "result",
        "subtype": "success",
        "result": "작업 완료",
        "duration_ms": 1000,
    }).encode() + b"\n"

    lines: list[bytes] = [result_event, b""]

    runner = _make_runner()

    proc = MagicMock()
    proc.stdout = _FakeStreamReader(lines)
    proc.stderr = None
    proc.returncode = 0

    async def fake_wait():
        pass
    proc.wait = fake_wait

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        result = await runner._run_stream_json(
            ["/fake/claude", "--print", "test"],
        )

    assert "작업 완료" in result, f"Expected '작업 완료' in result, got: {result!r}"


# ---------------------------------------------------------------------------
# Test: LimitOverrunError — 하나의 초과 라인 후 정상 라인 처리
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_stream_limit_overrun_then_normal() -> None:
    """LimitOverrunError 발생 후 스트림이 중단되지 않고 이후 정상 라인을 처리하는지 확인."""

    # 10MB 초과 라인 시뮬레이션: LimitOverrunError → drain read → normal readline → EOF
    oversized_error = asyncio.LimitOverrunError("Separator is not found, and chunk exceed the limit", 1024 * 1024 * 10)

    normal_result_line = json.dumps({
        "type": "result",
        "subtype": "success",
        "result": "초과 후 성공",
        "duration_ms": 500,
    }).encode() + b"\n"

    class _OverrunThenNormal:
        """첫 readline()에서 LimitOverrunError, 그 후 drain read, 마지막 에서 정상 줄 반환."""
        def __init__(self):
            self._calls = 0

        async def readline(self) -> bytes:
            self._calls += 1
            if self._calls == 1:
                raise asyncio.LimitOverrunError(
                    "Separator is not found, and chunk exceed the limit",
                    1024 * 1024 * 10,
                )
            if self._calls == 2:
                # inner drain loop readline → 줄 끝 찾았다고 간주 (정상 반환)
                return b"\n"
            if self._calls == 3:
                return normal_result_line
            return b""  # EOF

        async def read(self, n: int) -> bytes:
            return b"x" * min(n, 100)  # 드레인 성공 시뮬레이션

    runner = _make_runner()

    proc = MagicMock()
    proc.stdout = _OverrunThenNormal()
    proc.stderr = None
    proc.returncode = 0

    async def fake_wait():
        pass
    proc.wait = fake_wait

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        result = await runner._run_stream_json(
            ["/fake/claude", "--print", "test"],
        )

    assert "초과 후 성공" in result, f"LimitOverrunError 후 스트림 복구 실패: {result!r}"


# ---------------------------------------------------------------------------
# Test: LimitOverrunError — 스트림 전체가 초과 라인만인 경우 (graceful degradation)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_stream_only_oversized_lines() -> None:
    """모든 라인이 LimitOverrunError인 경우 예외 없이 빈 결과를 반환하는지 확인."""

    class _AlwaysOverrun:
        def __init__(self):
            self._calls = 0

        async def readline(self) -> bytes:
            self._calls += 1
            if self._calls <= 4:
                raise asyncio.LimitOverrunError("chunk exceed limit", 1024 * 1024 * 10)
            return b""  # EOF

        async def read(self, n: int) -> bytes:
            return b"x" * min(n, 100)

    runner = _make_runner()

    proc = MagicMock()
    proc.stdout = _AlwaysOverrun()
    proc.stderr = None
    proc.returncode = 0

    async def fake_wait():
        pass
    proc.wait = fake_wait

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        result = await runner._run_stream_json(
            ["/fake/claude", "--print", "test"],
        )

    # 예외 없이 종료되어야 하고, result는 빈 결과 또는 "(결과 없음)"
    assert isinstance(result, str), "결과가 문자열이어야 함"
    # ❌ 패턴이 아닌 한 정상 종료
    assert not result.startswith("❌ 실행 중 오류"), f"예외가 상위로 전파됨: {result!r}"


# ---------------------------------------------------------------------------
# Test: _read_stdout (run_subprocess) — LimitOverrunError 처리
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_stdout_limit_overrun() -> None:
    """_run_subprocess의 _read_stdout도 LimitOverrunError를 안전하게 처리하는지 확인."""

    class _SubprocessOverrunStream:
        def __init__(self):
            self._calls = 0

        async def readline(self) -> bytes:
            self._calls += 1
            if self._calls == 1:
                raise asyncio.LimitOverrunError("chunk exceed limit", 10 * 1024 * 1024)
            if self._calls == 2:
                return b"\n"  # drain inner readline 완료
            if self._calls == 3:
                return b"normal output line\n"
            return b""

        async def read(self, n: int) -> bytes:
            return b"x" * min(n, 100)

    runner = _make_runner()

    proc = MagicMock()
    proc.stdout = _SubprocessOverrunStream()
    proc.stderr = AsyncMock()
    proc.stderr.read = AsyncMock(return_value=b"")
    proc.returncode = 0

    async def fake_wait():
        pass
    proc.wait = fake_wait

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        result = await runner._run_subprocess(
            ["/fake/claude", "--print", "test"],
        )

    assert "normal output line" in result, f"초과 라인 이후 정상 출력이 누락됨: {result!r}"
