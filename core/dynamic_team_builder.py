"""Dynamic team builder — LLM으로 태스크에 맞는 에이전트 팀 구성을 결정한다."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from loguru import logger
from openai import AsyncOpenAI

from core.agent_catalog import AgentCatalog, AgentPersona


class ExecutionMode(str, Enum):
    """팀 실행 모드."""

    omc_team = "omc_team"
    agent_teams = "agent_teams"
    sequential = "sequential"


@dataclass
class TeamConfig:
    """LLM이 결정한 팀 구성 정보."""

    agents: list[AgentPersona]
    execution_mode: ExecutionMode
    engine: str  # "claude-code" | "codex" | "auto"
    omc_team_format: str  # e.g. "2:executor,1:analyst"
    reasoning: str


_TEAM_SYSTEM_PROMPT = """You are a PM (Project Manager) for an AI development team.

Given a task description, decide:
1. Which agent personas to use and how many of each.
2. The execution mode based on task complexity.
3. The execution engine.

Execution mode rules:
- "omc_team": complex dev tasks (implement, build, fix, code, refactor, create feature)
- "agent_teams": parallel research/analysis tasks (research, compare, analyze multiple things)
- "sequential": simple/single tasks (explain, summarize, answer a question)

Engine rules:
- "claude-code": always use for omc_team and agent_teams modes
- "codex": only for simple sequential tasks (quick single-file changes, short answers)
- "auto": when unsure or task complexity is mixed

Available agent names: executor, debugger, architect, analyst, scientist, writer,
document-specialist, code-reviewer, security-reviewer, quality-reviewer,
test-engineer, verifier, qa-tester, planner, explore, designer, build-fixer, critic.

Respond ONLY with valid JSON in this exact format:
{
  "agents": [{"name": "executor", "count": 2}, {"name": "analyst", "count": 1}],
  "execution_mode": "omc_team",
  "engine": "claude-code",
  "reasoning": "brief reason"
}

Rules:
- Use at most 3 distinct agent types.
- Each count must be 1, 2, or 3.
- agent names must be from the available list above.
"""


def _build_omc_format(agents_spec: list[dict]) -> str:
    """[{"name": "executor", "count": 2}, ...] → "2:executor,1:analyst"."""
    parts = [f"{spec.get('count', 1)}:{spec['name']}" for spec in agents_spec]
    return ",".join(parts)


class DynamicTeamBuilder:
    """LLM을 사용해 태스크에 적합한 에이전트 팀 구성을 동적으로 결정한다."""

    def __init__(self, catalog: AgentCatalog | None = None) -> None:
        """
        Args:
            catalog: 에이전트 페르소나 카탈로그. None이면 기본 경로에서 로드.
        """
        self._catalog = catalog or AgentCatalog()
        if not self._catalog.list_agents():
            self._catalog.load()

        api_key = os.environ.get("OPENAI_API_KEY", "")
        self._model = os.environ.get("PM_MODEL", "gpt-4o")
        self._llm_available = bool(api_key)
        self._client: AsyncOpenAI | None = AsyncOpenAI(api_key=api_key) if self._llm_available else None

        if not self._llm_available:
            logger.warning("OPENAI_API_KEY not set — DynamicTeamBuilder will use fallback mode")
        self._hints: dict = {}  # lazy-loaded from agent_hints.yaml

    def _load_hints(self) -> dict:
        """agent_hints.yaml에서 카테고리 힌트 로드 (캐시)."""
        if self._hints:
            return self._hints
        hints_path = Path(__file__).parent.parent / "agent_hints.yaml"
        if hints_path.exists():
            try:
                import yaml  # type: ignore[import]
                with hints_path.open(encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                self._hints = data.get("agent_hints", {}) if data else {}
            except Exception as exc:
                logger.warning("agent_hints.yaml 로드 실패: {}", exc)
        return self._hints

    def _engine_for_category(self, category: str, default: str = "claude-code") -> str:
        """카테고리별 preferred_engine 반환."""
        hints = self._load_hints()
        return hints.get(category, {}).get("preferred_engine", default)

    async def build_team(self, task: str) -> TeamConfig:
        """LLM으로 태스크를 분석하고 팀 구성을 결정한다.

        LLM을 사용할 수 없으면 _fallback_team()을 사용한다.

        Args:
            task: 유저 태스크 설명 문자열.

        Returns:
            TeamConfig 인스턴스.
        """
        if not self._llm_available or self._client is None:
            logger.info("LLM unavailable, using fallback team for task: {}", task[:60])
            return self._fallback_team(task)

        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _TEAM_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Task: {task}"},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or "{}"
            data = json.loads(content)
            return self._parse_llm_response(data)

        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM team build failed ({}), using fallback", exc)
            return self._fallback_team(task)

    def _parse_llm_response(self, data: dict) -> TeamConfig:
        """LLM JSON 응답을 TeamConfig로 변환한다."""
        agents_spec: list[dict] = data.get("agents", [])
        mode_str = data.get("execution_mode", "sequential")
        reasoning = data.get("reasoning", "")

        try:
            execution_mode = ExecutionMode(mode_str)
        except ValueError:
            logger.warning("Unknown execution_mode '{}', defaulting to sequential", mode_str)
            execution_mode = ExecutionMode.sequential

        personas: list[AgentPersona] = []
        for spec in agents_spec:
            name = spec.get("name", "")
            count = max(1, min(3, int(spec.get("count", 1))))
            persona = self._catalog.get_persona(name)
            if persona is None:
                from core.agent_catalog import AgentPersona, DEFAULT_MODEL
                persona = AgentPersona(name=name, description=f"{name} agent", model=DEFAULT_MODEL)
            for _ in range(count):
                personas.append(persona)

        omc_format = _build_omc_format(agents_spec)

        # Engine: from LLM response, validated
        engine_raw = data.get("engine", "")
        if engine_raw in ("claude-code", "codex", "auto"):
            engine = engine_raw
        elif execution_mode == ExecutionMode.omc_team:
            engine = "claude-code"
        elif execution_mode == ExecutionMode.agent_teams:
            engine = "claude-code"
        else:
            engine = "auto"

        logger.info(
            "Team built via LLM: {} agents, mode={}, engine={}, format={}",
            len(personas),
            execution_mode.value,
            engine,
            omc_format,
        )
        return TeamConfig(
            agents=personas,
            execution_mode=execution_mode,
            engine=engine,
            omc_team_format=omc_format,
            reasoning=reasoning,
        )

    def _fallback_team(self, task: str) -> TeamConfig:
        """LLM 없이 AgentCatalog.recommend()로 팀을 구성한다.

        Args:
            task: 유저 태스크 설명 문자열.

        Returns:
            TeamConfig 인스턴스.
        """
        recommended = self._catalog.recommend(task)

        lower = task.lower()
        dev_keywords = {"implement", "build", "fix", "code", "refactor", "create", "develop"}
        research_keywords = {"research", "compare", "analyze", "analyse", "investigate"}

        if any(kw in lower for kw in dev_keywords):
            execution_mode = ExecutionMode.omc_team
        elif any(kw in lower for kw in research_keywords):
            execution_mode = ExecutionMode.agent_teams
        else:
            execution_mode = ExecutionMode.sequential

        # build omc_team_format: each recommended agent × 1
        seen: list[str] = []
        for p in recommended:
            if p.name not in seen:
                seen.append(p.name)
        omc_format = ",".join(f"1:{name}" for name in seen)

        # Determine engine from hints or mode defaults
        if execution_mode == ExecutionMode.omc_team:
            engine = self._engine_for_category("coding", default="claude-code")
        elif execution_mode == ExecutionMode.agent_teams:
            engine = self._engine_for_category("analysis", default="claude-code")
        else:
            engine = self._engine_for_category("simple", default="codex")
        # omc_team always needs claude-code regardless of hints
        if execution_mode == ExecutionMode.omc_team:
            engine = "claude-code"

        logger.info(
            "Fallback team: {} agents, mode={}, engine={}, format={}",
            len(recommended),
            execution_mode.value,
            engine,
            omc_format,
        )
        return TeamConfig(
            agents=recommended,
            execution_mode=execution_mode,
            engine=engine,
            omc_team_format=omc_format,
            reasoning="keyword-based fallback (LLM unavailable)",
        )

    def format_team_announcement(self, config: TeamConfig) -> str:
        """Telegram 친화적인 팀 구성 안내 문자열을 반환한다.

        Example output:
            🤖 팀 구성: executor×2 + analyst×1 (omc_team 모드)

        Args:
            config: build_team()이 반환한 TeamConfig.

        Returns:
            포맷된 문자열.
        """
        # count occurrences of each agent name
        counts: dict[str, int] = {}
        for persona in config.agents:
            counts[persona.name] = counts.get(persona.name, 0) + 1

        parts = " + ".join(f"{name}×{cnt}" for name, cnt in counts.items())
        mode_label = config.execution_mode.value
        engine_label = {
            "claude-code": "Claude Code (omc /team)",
            "codex": "Codex CLI",
            "auto": "자동 선택",
        }.get(config.engine, config.engine)

        announcement = (
            f"🤖 팀 구성 완료\n"
            f"  엔진: {engine_label}\n"
            f"  팀: {parts}\n"
            f"  모드: {mode_label}"
        )
        if config.reasoning:
            announcement += f"\n💡 이유: {config.reasoning}"
        return announcement
