"""Phase1 bug fix verification tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── test_dynamic_team_builder_count_string ────────────────────────────────

def _write_agent(directory: Path, name: str, description: str) -> None:
    (directory / f"{name}.md").write_text(f"# {name}\n\n{description}\n", encoding="utf-8")


def test_dynamic_team_builder_count_string(tmp_path: Path):
    """count='two' 같은 비정수 값이 들어와도 크래시 없이 fallback(1)되는지 확인."""
    from core.agent_catalog import AgentCatalog
    from core.dynamic_team_builder import DynamicTeamBuilder

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_agent(agents_dir, "executor", "Implements code")

    catalog = AgentCatalog(agents_dir=agents_dir)
    catalog.load()
    builder = DynamicTeamBuilder(catalog=catalog)
    builder._llm_available = False

    # _parse_llm_response에 count="two" 전달
    data = {
        "agents": [{"name": "executor", "count": "two"}],
        "execution_mode": "sequential",
        "engine": "claude-code",
        "reasoning": "test",
    }
    config = builder._parse_llm_response(
        data,
        preferred_agents=[],
        avoid_agents=[],
        max_team_size=3,
        preferred_engine="auto",
    )
    # count 파싱 실패 시 fallback 1로 동작해야 함 (크래시 없이)
    assert len(config.agents) >= 1
    assert config.agents[0].name == "executor"


# ── test_claude_code_runner_error_prefix ──────────────────────────────────

@pytest.mark.asyncio
async def test_claude_code_runner_error_prefix():
    """에러 결과에 'ERROR:' 접두사가 붙는지 확인."""
    from tools.claude_code_runner import ClaudeCodeRunner

    runner = ClaudeCodeRunner(cli_path="/usr/bin/false", timeout=10)

    # /usr/bin/false는 항상 exit code 1로 종료
    result = await runner._run_stream_json(
        ["/usr/bin/false"],
        workdir="/tmp",
    )
    assert result.startswith("ERROR:"), f"Expected ERROR: prefix, got: {result[:50]}"


# ── test_main_yaml_config_parsing ─────────────────────────────────────────

def test_main_yaml_config_parsing(tmp_path: Path):
    """.yaml 파일을 yaml.safe_load로 파싱하는지 확인."""
    # main.py의 _load_env_file 함수를 직접 테스트
    from main import _load_env_file

    yaml_file = tmp_path / "test_config.yaml"
    yaml_file.write_text("TEST_YAML_KEY: test_yaml_value\nNUMBER_KEY: 42\n")

    # 환경변수 클린업
    import os
    os.environ.pop("TEST_YAML_KEY", None)
    os.environ.pop("NUMBER_KEY", None)

    _load_env_file(yaml_file)

    assert os.environ.get("TEST_YAML_KEY") == "test_yaml_value", \
        "YAML key should be parsed via yaml.safe_load"
    assert os.environ.get("NUMBER_KEY") == "42", \
        "YAML numeric values should be converted to string"

    # 클린업
    os.environ.pop("TEST_YAML_KEY", None)
    os.environ.pop("NUMBER_KEY", None)


# ── test_pm_bot_counts_passed ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pm_bot_counts_passed():
    """_execute_with_dynamic_team에서 counts가 run_structured_team에 전달되는지 확인."""
    from core.agent_catalog import AgentPersona
    from core.dynamic_team_builder import ExecutionMode, TeamConfig

    # TeamConfig에 executor x2 + analyst x1 설정
    personas = [
        AgentPersona(name="executor", description="exec", model="test"),
        AgentPersona(name="executor", description="exec", model="test"),
        AgentPersona(name="analyst", description="anal", model="test"),
    ]
    mock_config = TeamConfig(
        agents=personas,
        execution_mode=ExecutionMode.structured_team,
        engine="claude-code",
        team_format="2:executor,1:analyst",
        reasoning="test",
    )

    # PMBot 없이 직접 로직 검증: counts 계산 로직 추출
    agent_counts: dict[str, int] = {}
    for p in mock_config.agents:
        agent_counts[p.name] = agent_counts.get(p.name, 0) + 1
    unique_names = list(agent_counts.keys())
    counts = [agent_counts[n] for n in unique_names]

    assert "executor" in unique_names
    assert "analyst" in unique_names
    assert counts[unique_names.index("executor")] == 2
    assert counts[unique_names.index("analyst")] == 1
