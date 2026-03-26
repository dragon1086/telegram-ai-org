from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agent_catalog import AgentCatalog
from core.dynamic_team_builder import DynamicTeamBuilder, _build_team_system_prompt


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


@pytest.mark.asyncio
async def test_fallback_team_uses_multimodal_lane(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_agent(agents_dir, "designer", "Understands visuals")
    _write_agent(agents_dir, "analyst", "Analyzes requirements")
    _write_agent(agents_dir, "document-specialist", "Reads documents well")

    catalog = AgentCatalog(agents_dir=agents_dir)
    catalog.load()
    builder = DynamicTeamBuilder(catalog=catalog)
    builder._llm_available = False
    builder._client = None

    config = await builder.build_team("[첨부 입력]\n- 종류: photo\n- MIME: image/jpeg", preferred_engine="claude-code")

    assert config.execution_mode.value == "agent_teams"
    assert {persona.name for persona in config.agents} & {"designer", "analyst", "document-specialist"}


# ── Change 1: _build_team_system_prompt 동적 주입 ───────────────────────────

def test_build_team_system_prompt_injects_real_names() -> None:
    """_build_team_system_prompt에 실제 에이전트 이름이 포함돼야 한다."""
    names = ["engineering-senior-developer", "testing-api-tester", "engineering-rapid-prototyper"]
    prompt = _build_team_system_prompt(names)
    assert "engineering-senior-developer" in prompt
    assert "testing-api-tester" in prompt
    assert "engineering-rapid-prototyper" in prompt
    # 하드코딩된 추상 이름이 Available agent names 줄에 남아있지 않아야 한다
    available_line = next(
        line for line in prompt.splitlines() if line.startswith("Available agent names:")
    )
    assert "executor" not in available_line  # 폴백 상수가 아닌 주입된 이름만


def test_build_team_system_prompt_uses_fallback_when_empty() -> None:
    """에이전트 이름 목록이 비어 있으면 폴백 상수를 사용해야 한다."""
    prompt = _build_team_system_prompt([])
    assert "executor" in prompt  # 폴백 상수에 포함된 이름


@pytest.mark.asyncio
async def test_build_team_injects_catalog_names_into_system_prompt(tmp_path: Path) -> None:
    """build_team() 호출 시 catalog 에이전트 이름이 LLM 프롬프트에 동적으로 주입돼야 한다."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_agent(agents_dir, "engineering-senior-developer", "Senior dev who codes")
    _write_agent(agents_dir, "testing-api-tester", "Tests API endpoints")

    catalog = AgentCatalog(agents_dir=agents_dir)
    catalog.load()

    received_prompts: list[str] = []

    class _CapturingClient:
        async def complete(self, prompt: str, *, system_prompt: str = "", workdir: str | None = None) -> str:
            received_prompts.append(system_prompt)
            return '{"agents":[{"name":"engineering-senior-developer","count":1}],"execution_mode":"sequential","engine":"claude-code","reasoning":"test"}'

    builder = DynamicTeamBuilder(catalog=catalog, decision_client=_CapturingClient())
    await builder.build_team("API 구현해줘")

    assert len(received_prompts) == 1
    assert "engineering-senior-developer" in received_prompts[0]
    assert "testing-api-tester" in received_prompts[0]


# ── Change 2: AgentCatalog rglob 서브디렉토리 로드 ──────────────────────────

def test_agent_catalog_rglob_loads_subdirectory_personas(tmp_path: Path) -> None:
    """rglob 변경 후 design/, engineering/ 하위 디렉토리 페르소나도 로드돼야 한다."""
    agents_dir = tmp_path / "agents"
    eng_dir = agents_dir / "engineering"
    design_dir = agents_dir / "design"
    eng_dir.mkdir(parents=True)
    design_dir.mkdir(parents=True)

    _write_agent(agents_dir, "top-level-agent", "Root level agent")
    _write_agent(eng_dir, "engineering-senior-developer", "Senior developer")
    _write_agent(design_dir, "design-ui-designer", "UI designer")

    catalog = AgentCatalog(agents_dir=agents_dir)
    catalog.load()

    names = {p.name for p in catalog.list_agents()}
    assert "top-level-agent" in names
    assert "engineering-senior-developer" in names
    assert "design-ui-designer" in names
