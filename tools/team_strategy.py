"""TeamStrategy — omc/native/solo 자동 감지 및 실행."""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path

CLAUDE_CLI = os.environ.get("CLAUDE_CLI_PATH", "/Users/rocky/.local/bin/claude")
AGENTS_DIR = Path.home() / ".claude" / "agents"


def detect_strategy() -> str:
    """사용 가능한 팀 전략 자동 감지."""
    # omc MCP 서버 활성화 여부
    settings = Path.home() / ".claude" / "settings.json"
    if settings.exists():
        try:
            s = json.loads(settings.read_text())
            mcps = s.get("mcpServers", {})
            if any("omc" in k or "oh-my-claude" in k for k in mcps):
                return "omc"
        except Exception:
            pass

    # EXPERIMENTAL_AGENT_TEAMS 활성화 여부
    if os.environ.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS") == "1":
        return "native"

    return "solo"


class TeamStrategy(ABC):
    @abstractmethod
    def build_cmd(self, task: str, agents: list[str], base_cmd: list[str]) -> list[str]:
        """실행 커맨드 반환."""


class OmcTeamStrategy(TeamStrategy):
    """omc /team 명령어 사용."""

    def build_cmd(self, task: str, agents: list[str], base_cmd: list[str]) -> list[str]:
        if not agents:
            return base_cmd + [task]
        agent_spec = ",".join(agents[:5])
        return base_cmd + [f"/team {len(agents)}:{agent_spec}\n\n{task}"]


class NativeAgentStrategy(TeamStrategy):
    """CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS + --agents 파라미터."""

    def build_cmd(self, task: str, agents: list[str], base_cmd: list[str]) -> list[str]:
        cmd = list(base_cmd)
        if agents:
            agents_def: dict[str, dict] = {}
            for name in agents[:5]:
                agent_file = AGENTS_DIR / f"{name}.md"
                if not agent_file.exists():
                    matches = list(AGENTS_DIR.glob(f"*{name}*.md"))
                    agent_file = matches[0] if matches else None  # type: ignore[assignment]

                if agent_file and agent_file.exists():
                    desc_lines = [
                        line for line in agent_file.read_text().splitlines()[:5]
                        if line.strip()
                    ]
                    desc = desc_lines[0][:100] if desc_lines else name
                    agents_def[name] = {
                        "description": desc,
                        "prompt": f"Act as {name} specialist.",
                    }
                else:
                    agents_def[name] = {
                        "description": f"{name} specialist",
                        "prompt": f"Act as {name}.",
                    }

            cmd.extend(["--agents", json.dumps(agents_def)])
        cmd.append(task)
        return cmd


class SoloStrategy(TeamStrategy):
    """단일 에이전트 (팀 없음)."""

    def build_cmd(self, task: str, agents: list[str], base_cmd: list[str]) -> list[str]:
        return base_cmd + [task]


def get_strategy(override: str | None = None) -> TeamStrategy:
    """전략 인스턴스 반환."""
    name = override or detect_strategy()
    if name == "omc":
        return OmcTeamStrategy()
    if name == "native":
        return NativeAgentStrategy()
    return SoloStrategy()
