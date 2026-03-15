from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import codex_runner
from tools.codex_runner import CodexRunner
import pytest


def test_prefers_explicit_path_as_workdir(tmp_path: Path) -> None:
    repo_dir = tmp_path / "openclaw"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    nested_dir = repo_dir / "src"
    nested_dir.mkdir()

    runner = CodexRunner(workdir=str(tmp_path / "fallback"))

    resolved = runner._resolve_workdir(
        f"{nested_dir} 디렉토리에서 openclaw 에러를 재현하고 고쳐줘",
    )

    assert resolved == str(repo_dir)


def test_falls_back_to_named_repo_search(tmp_path: Path, monkeypatch) -> None:
    repo_dir = tmp_path / "Downloads" / "openclaw"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()
    monkeypatch.setenv("CODEX_REPO_SEARCH_ROOTS", str(tmp_path / "Downloads"))

    runner = CodexRunner(workdir=str(tmp_path / "fallback"))

    resolved = runner._resolve_workdir(
        "로컬에 있는 openclaw 리파지토리에서 원인 분석해줘",
    )

    assert resolved == str(repo_dir)


def test_uses_default_workdir_when_no_repo_match(tmp_path: Path) -> None:
    fallback = tmp_path / "fallback"
    fallback.mkdir()
    runner = CodexRunner(workdir=str(fallback))

    resolved = runner._resolve_workdir("권한 이슈를 정리해줘")

    assert resolved == str(fallback)


def test_named_repo_search_requires_explicit_repo_cues(tmp_path: Path, monkeypatch) -> None:
    repo_dir = tmp_path / "Downloads" / "opencode"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()
    fallback = tmp_path / "fallback"
    fallback.mkdir()
    monkeypatch.setenv("CODEX_REPO_SEARCH_ROOTS", str(tmp_path / "Downloads"))

    runner = CodexRunner(workdir=str(fallback))

    resolved = runner._resolve_workdir(
        "코딩 에이전트 시장 동향 및 레퍼런스 심층 분석을 다시 수행해줘",
    )

    assert resolved == str(fallback)


def test_select_agent_prompts_prefers_explicit_agents(tmp_path: Path, monkeypatch) -> None:
    claude_agents = tmp_path / ".claude" / "agents"
    claude_agents.mkdir(parents=True)
    (claude_agents / "architect.md").write_text(
        "# architect\n\nArchitecture agent",
        encoding="utf-8",
    )
    (claude_agents / "executor.md").write_text(
        "# executor\n\nExecutor agent",
        encoding="utf-8",
    )
    monkeypatch.setattr(codex_runner, "AGENT_DIRS", [claude_agents])

    prompts = codex_runner._select_agent_prompts(
        "아무 작업",
        agent_names=["architect", "executor"],
    )

    assert "[Agent: architect]" in prompts
    assert "[Agent: executor]" in prompts


def test_effective_timeout_increases_for_multi_agent_tasks(tmp_path: Path) -> None:
    runner = CodexRunner(workdir=str(tmp_path / "fallback"))

    assert runner._effective_timeout(["analyst", "writer"]) == codex_runner.COMPLEX_TASK_TIMEOUT
    assert runner._effective_timeout(["analyst"]) == codex_runner.DEFAULT_TIMEOUT


@pytest.mark.asyncio
async def test_agent_prompt_paths_do_not_override_workdir(tmp_path: Path, monkeypatch) -> None:
    fallback = tmp_path / "fallback"
    fallback.mkdir()
    runner = CodexRunner(workdir=str(fallback))

    monkeypatch.setattr(
        codex_runner,
        "_select_agent_prompts",
        lambda *args, **kwargs: "[Agent: scientist]\nPath: ~/.claude/agents",
    )

    captured: dict[str, str] = {}

    class _FakeProc:
        returncode = 0

        async def communicate(self):
            return b"ok", b""

    async def fake_exec(*cmd, **kwargs):
        captured["cwd"] = kwargs.get("cwd")
        return _FakeProc()

    monkeypatch.setattr(codex_runner.asyncio, "create_subprocess_exec", fake_exec)

    result = await runner.run("시장조사 정리해줘", agents=["analyst", "writer"])

    assert result == "ok"
    assert captured["cwd"] == str(fallback)


@pytest.mark.asyncio
async def test_workdir_hint_is_used_instead_of_prompt_metadata_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fallback = tmp_path / "fallback"
    fallback.mkdir()
    runner = CodexRunner(workdir=str(fallback))

    captured: dict[str, str] = {}

    class _FakeProc:
        returncode = 0

        async def communicate(self):
            return b"ok", b""

    async def fake_exec(*cmd, **kwargs):
        captured["cwd"] = kwargs.get("cwd")
        return _FakeProc()

    monkeypatch.setattr(codex_runner.asyncio, "create_subprocess_exec", fake_exec)

    result = await runner.run(
        "전체 목록: ~/.claude/agents/\n\n시장조사 정리해줘",
        workdir_hint="시장조사 정리해줘",
        agents=["analyst", "writer"],
    )

    assert result == "ok"
    assert captured["cwd"] == str(fallback)


def test_sanitize_codex_output_keeps_final_team_response() -> None:
    raw = """
OpenAI Codex v0.114.0 (research preview)
workdir: /Users/rocky/Downloads/openclaw
thinking
I should inspect the repo first.
codex
중간 정리입니다.
tokens used
12,345
[TEAM:solo]
🏗️ 팀 구성
• solo: 시장 조사
이유: 최신 공식 문서 확인

## 협업 요청
작업 중 다른 조직의 도움이 필요할 때:
→ 응답에 [COLLAB:구체적 작업 설명|맥락: 현재 작업 요약] 태그를 포함하세요
"""

    cleaned = codex_runner._sanitize_codex_output(raw)

    assert cleaned.startswith("[TEAM:solo]")
    assert "OpenAI Codex v0.114.0" not in cleaned
    assert "thinking" not in cleaned
    assert "현재 작업 요약" not in cleaned


@pytest.mark.asyncio
async def test_streaming_progress_emits_meaningful_lines(tmp_path: Path) -> None:
    runner = CodexRunner(workdir=str(tmp_path))
    seen: list[str] = []

    class _Stream:
        def __init__(self, lines: list[bytes]) -> None:
            self._lines = list(lines)

        async def readline(self) -> bytes:
            if not self._lines:
                return b""
            return self._lines.pop(0)

    class _Proc:
        def __init__(self) -> None:
            self.stdout = _Stream([b"thinking\n", "핵심 진행 업데이트\n".encode("utf-8")])
            self.stderr = _Stream([])

        async def wait(self) -> None:
            return None

    async def _progress(line: str) -> None:
        seen.append(line)

    stdout, stderr = await runner._communicate_with_progress(_Proc(), _progress)

    assert "핵심 진행 업데이트".encode("utf-8") in stdout
    assert stderr == b""
    assert seen == ["핵심 진행 업데이트"]
