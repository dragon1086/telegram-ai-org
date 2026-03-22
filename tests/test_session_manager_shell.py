from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.session_manager import SessionManager


def test_ensure_shell_session_reset_recreates_tmux_session(monkeypatch) -> None:
    manager = SessionManager()
    calls: list[tuple[str, ...]] = []
    exists = {"value": True}

    monkeypatch.setattr(manager, "_tmux_available", lambda: True)

    def fake_run_tmux(*args: str) -> str:
        calls.append(args)
        if args[:2] == ("has-session", "-t"):
            return "" if exists["value"] else "missing"
        if args[:2] == ("kill-session", "-t"):
            exists["value"] = False
            return ""
        if args[:2] == ("new-session", "-d"):
            exists["value"] = True
            return ""
        return ""

    monkeypatch.setattr(manager, "_run_tmux", fake_run_tmux)

    name = manager._ensure_shell_session_name("aiorg_demo_codex-batch", reset=True)

    assert name == "aiorg_demo_codex-batch"
    assert ("kill-session", "-t", "aiorg_demo_codex-batch") in calls
    assert ("new-session", "-d", "-s", "aiorg_demo_codex-batch", "-x", "220", "-y", "50") in calls


@pytest.mark.asyncio
async def test_run_shell_command_kills_session_on_timeout(monkeypatch, tmp_path: Path) -> None:
    manager = SessionManager()
    calls: list[tuple[str, ...]] = []

    monkeypatch.setattr(manager, "_tmux_available", lambda: True)
    monkeypatch.setattr(manager, "shell_session_name", lambda team_id, purpose="exec": "aiorg_demo_codex-batch")
    monkeypatch.setattr(manager, "_ensure_shell_session_name", lambda name, reset=False: name)
    monkeypatch.setattr("core.session_manager.Path.home", lambda: tmp_path)

    def fake_run_tmux(*args: str) -> str:
        calls.append(args)
        return ""

    monkeypatch.setattr(manager, "_run_tmux", fake_run_tmux)
    monkeypatch.setattr(
        manager,
        "_wait_for_output",
        lambda output_file, progress_callback=None, **kwargs: asyncio.sleep(3600),
    )

    with pytest.raises(asyncio.TimeoutError):
        await manager.run_shell_command("demo", "echo hi", purpose="codex-batch", timeout=0.01)

    assert ("kill-session", "-t", "aiorg_demo_codex-batch") in calls


@pytest.mark.asyncio
async def test_wait_for_output_streams_progress(tmp_path: Path) -> None:
    manager = SessionManager()
    output_file = tmp_path / "demo.out"
    seen: list[str] = []

    async def _writer() -> None:
        await asyncio.sleep(0.1)
        output_file.write_text("line one\n", encoding="utf-8")
        await asyncio.sleep(0.6)
        output_file.write_text("line one\nline two\n__DONE__\n", encoding="utf-8")

    async def _progress(line: str) -> None:
        seen.append(line)

    writer = asyncio.create_task(_writer())
    content = await manager._wait_for_output(output_file, progress_callback=_progress)
    await writer

    assert "line one" in content
    assert "line two" in content
    assert seen[:2] == ["line one", "line two"]
