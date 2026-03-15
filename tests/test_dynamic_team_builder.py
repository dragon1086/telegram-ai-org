from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agent_catalog import AgentCatalog
from core.dynamic_team_builder import DynamicTeamBuilder


def _write_agent(directory: Path, name: str, description: str) -> None:
    (directory / f"{name}.md").write_text(f"# {name}\n\n{description}\n", encoding="utf-8")


class _FakeDecisionClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    async def complete(self, prompt: str, *, system_prompt: str = "", workdir: str | None = None) -> str:
        self.calls += 1
        return self.response


@pytest.mark.asyncio
async def test_build_team_respects_preferred_and_avoid_agents(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_agent(agents_dir, "executor", "Implements code changes")
    _write_agent(agents_dir, "architect", "Designs architecture and interfaces")
    _write_agent(agents_dir, "debugger", "Finds root causes")
    _write_agent(agents_dir, "analyst", "Analyzes requirements")

    catalog = AgentCatalog(agents_dir=agents_dir)
    catalog.load()
    builder = DynamicTeamBuilder(catalog=catalog)
    builder._llm_available = False
    builder._client = None

    config = await builder.build_team(
        "로그인 API 구현과 구조 정리를 해줘",
        preferred_agents=["architect", "executor"],
        avoid_agents=["debugger"],
        max_team_size=2,
        preferred_engine="claude-code",
    )

    names = [persona.name for persona in config.agents]
    assert "debugger" not in names
    assert names[:2] == ["architect", "executor"]
    assert len(set(names)) <= 2


@pytest.mark.asyncio
async def test_build_team_prefers_decision_client(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_agent(agents_dir, "executor", "Implements code changes")
    _write_agent(agents_dir, "analyst", "Analyzes requirements")

    catalog = AgentCatalog(agents_dir=agents_dir)
    catalog.load()
    client = _FakeDecisionClient(
        '{"agents":[{"name":"analyst","count":1}],"execution_mode":"sequential","engine":"codex","reasoning":"simple"}'
    )
    builder = DynamicTeamBuilder(catalog=catalog, decision_client=client)

    config = await builder.build_team("간단한 분석", preferred_engine="codex")

    assert [persona.name for persona in config.agents] == ["analyst"]
    assert config.engine == "codex"
    assert client.calls == 1
