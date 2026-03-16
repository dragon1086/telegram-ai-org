"""Dynamic team builder — LLM으로 태스크에 맞는 에이전트 팀 구성을 결정한다."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from loguru import logger
import anthropic

from core.agent_catalog import AgentCatalog, AgentPersona
from core.pm_decision import DecisionClientProtocol


class ExecutionMode(str, Enum):
    """팀 실행 모드."""

    structured_team = "structured_team"
    agent_teams = "agent_teams"
    sequential = "sequential"


@dataclass
class TeamConfig:
    """LLM이 결정한 팀 구성 정보."""

    agents: list[AgentPersona]
    execution_mode: ExecutionMode
    engine: str  # "claude-code" | "codex" | "auto"
    team_format: str  # e.g. "2:executor,1:analyst"
    reasoning: str


_TEAM_SYSTEM_PROMPT = """You are a PM (Project Manager) for an AI development team.

Given a task description, decide:
1. Which agent personas to use and how many of each.
2. The execution mode based on task complexity.
3. The execution engine.

Execution mode rules:
- "structured_team": complex dev tasks (implement, build, fix, code, refactor, create feature)
- "agent_teams": parallel research/analysis tasks (research, compare, analyze multiple things)
- "sequential": simple/single tasks (explain, summarize, answer a question)

Engine rules:
- "claude-code": always use for structured_team and agent_teams modes
- "codex": only for simple sequential tasks (quick single-file changes, short answers)
- "auto": when unsure or task complexity is mixed

Available agent names: executor, debugger, architect, analyst, scientist, writer,
document-specialist, code-reviewer, security-reviewer, quality-reviewer,
test-engineer, verifier, qa-tester, planner, explore, designer, build-fixer, critic.

Respond ONLY with valid JSON in this exact format:
{
  "agents": [{"name": "executor", "count": 2}, {"name": "analyst", "count": 1}],
  "execution_mode": "structured_team",
  "engine": "claude-code",
  "reasoning": "brief reason"
}

Rules:
- Use at most 3 distinct agent types.
- Each count must be 1, 2, or 3.
- agent names must be from the available list above.
"""


def _build_team_format(agents_spec: list[dict]) -> str:
    """[{"name": "executor", "count": 2}, ...] → "2:executor,1:analyst"."""
    parts = [f"{spec.get('count', 1)}:{spec['name']}" for spec in agents_spec]
    return ",".join(parts)


def _normalize_execution_mode(mode: str) -> str:
    aliases = {
        "omc_team": ExecutionMode.structured_team.value,
    }
    return aliases.get(mode, mode)


class DynamicTeamBuilder:
    """LLM을 사용해 태스크에 적합한 에이전트 팀 구성을 동적으로 결정한다."""

    def __init__(
        self,
        catalog: AgentCatalog | None = None,
        decision_client: DecisionClientProtocol | None = None,
    ) -> None:
        """
        Args:
            catalog: 에이전트 페르소나 카탈로그. None이면 기본 경로에서 로드.
        """
        self._catalog = catalog or AgentCatalog()
        if not self._catalog.list_agents():
            self._catalog.load()
        self._decision_client = decision_client

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            # Claude Code OAuth 토큰으로 fallback
            api_key = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
            if not api_key:
                try:
                    from pathlib import Path as _Path
                    api_key = (_Path.home() / ".claude" / "oauth-token").read_text().strip()
                except Exception:
                    pass
        self._model = os.environ.get("PM_MODEL", "claude-haiku-4-5")
        self._llm_available = bool(api_key)
        if self._llm_available:
            if api_key.startswith("sk-ant-oat"):
                self._client = anthropic.AsyncAnthropic(
                    auth_token=api_key,
                    base_url="https://api.anthropic.com",
                )
            else:
                self._client = anthropic.AsyncAnthropic(api_key=api_key)
        else:
            self._client = None

        if not self._llm_available:
            logger.warning("ANTHROPIC_API_KEY not set — DynamicTeamBuilder will use fallback mode")
        self._hints: dict = {}  # lazy-loaded from agent_hints.yaml

    def set_decision_client(self, decision_client: DecisionClientProtocol | None) -> None:
        self._decision_client = decision_client

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

    async def build_team(
        self,
        task: str,
        *,
        role: str = "",
        specialties: list[str] | None = None,
        direction: str = "",
        preferred_agents: list[str] | None = None,
        avoid_agents: list[str] | None = None,
        max_team_size: int = 3,
        preferred_engine: str = "auto",
        guidance: str = "",
    ) -> TeamConfig:
        """LLM으로 태스크를 분석하고 팀 구성을 결정한다.

        LLM을 사용할 수 없으면 _fallback_team()을 사용한다.

        Args:
            task: 유저 태스크 설명 문자열.

        Returns:
            TeamConfig 인스턴스.
        """
        specialties = specialties or []
        preferred_agents = preferred_agents or []
        avoid_agents = avoid_agents or []
        max_team_size = max(1, max_team_size)

        if self._decision_client is None and (not self._llm_available or self._client is None):
            logger.info("LLM unavailable, using fallback team for task: {}", task[:60])
            return self._fallback_team(
                task,
                role=role,
                specialties=specialties,
                direction=direction,
                preferred_agents=preferred_agents,
                avoid_agents=avoid_agents,
                max_team_size=max_team_size,
                preferred_engine=preferred_engine,
                guidance=guidance,
            )

        try:
            task_context = (
                f"Task: {task}\n"
                f"Role: {role or 'generalist PM'}\n"
                f"Specialties: {', '.join(specialties) or 'none'}\n"
                f"Direction: {direction or 'none'}\n"
                f"Preferred agents: {', '.join(preferred_agents) or 'none'}\n"
                f"Avoid agents: {', '.join(avoid_agents) or 'none'}\n"
                f"Max distinct agent types: {max_team_size}\n"
                f"Preferred engine: {preferred_engine}\n"
                f"Guidance: {guidance or 'none'}"
            )
            if self._decision_client is not None:
                content = await self._decision_client.complete(
                    task_context,
                    system_prompt=_TEAM_SYSTEM_PROMPT,
                )
            else:
                import asyncio as _asyncio
                resp = await _asyncio.wait_for(
                    self._client.messages.create(
                        model=self._model,
                        max_tokens=512,
                        system=_TEAM_SYSTEM_PROMPT,
                        messages=[
                            {"role": "user", "content": task_context},
                        ],
                    ),
                    timeout=30.0,
                )
                content = resp.content[0].text if resp.content else "{}"
            data = json.loads(content)
            return self._parse_llm_response(
                data,
                preferred_agents=preferred_agents,
                avoid_agents=avoid_agents,
                max_team_size=max_team_size,
                preferred_engine=preferred_engine,
            )

        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM team build failed ({}), using fallback", exc)
            return self._fallback_team(
                task,
                role=role,
                specialties=specialties,
                direction=direction,
                preferred_agents=preferred_agents,
                avoid_agents=avoid_agents,
                max_team_size=max_team_size,
                preferred_engine=preferred_engine,
                guidance=guidance,
            )

    def _parse_llm_response(
        self,
        data: dict,
        *,
        preferred_agents: list[str],
        avoid_agents: list[str],
        max_team_size: int,
        preferred_engine: str,
    ) -> TeamConfig:
        """LLM JSON 응답을 TeamConfig로 변환한다."""
        agents_spec: list[dict] = data.get("agents", [])
        mode_str = _normalize_execution_mode(data.get("execution_mode", "sequential"))
        reasoning = data.get("reasoning", "")

        try:
            execution_mode = ExecutionMode(mode_str)
        except ValueError:
            logger.warning("Unknown execution_mode '{}', defaulting to sequential", mode_str)
            execution_mode = ExecutionMode.sequential

        personas: list[AgentPersona] = []
        for spec in agents_spec:
            try:
                name = spec.get("name", "")
                raw_count = spec.get("count", 1)
                try:
                    count = max(1, min(3, int(raw_count)))
                except (ValueError, TypeError):
                    logger.warning("Invalid agent count '{}', defaulting to 1", raw_count)
                    count = 1
                persona = self._catalog.get_persona(name)
                if persona is None:
                    from core.agent_catalog import AgentPersona, DEFAULT_MODEL
                    persona = AgentPersona(name=name, description=f"{name} agent", model=DEFAULT_MODEL)
                for _ in range(count):
                    personas.append(persona)
            except Exception as spec_err:
                logger.warning("Failed to parse agent spec {}: {}", spec, spec_err)

        # Engine: from LLM response, validated
        engine_raw = data.get("engine", "")
        if engine_raw in ("claude-code", "codex", "auto"):
            engine = engine_raw
        elif execution_mode == ExecutionMode.structured_team:
            engine = "claude-code"
        elif execution_mode == ExecutionMode.agent_teams:
            engine = "claude-code"
        else:
            engine = "auto"
        if preferred_engine in ("claude-code", "codex"):
            engine = preferred_engine

        personas = self._apply_preferences(
            personas,
            preferred_agents=preferred_agents,
            avoid_agents=avoid_agents,
            max_team_size=max_team_size,
        )
        if not personas:
            fallback = self._fallback_team(
                "",
                preferred_agents=preferred_agents,
                avoid_agents=avoid_agents,
                max_team_size=max_team_size,
                preferred_engine=preferred_engine,
            )
            return fallback

        team_format = self._build_team_format_from_personas(personas)

        logger.info(
            "Team built via LLM: {} agents, mode={}, engine={}, format={}",
            len(personas),
            execution_mode.value,
            engine,
            team_format,
        )
        return TeamConfig(
            agents=personas,
            execution_mode=execution_mode,
            engine=engine,
            team_format=team_format,
            reasoning=reasoning,
        )

    def _build_team_format_from_personas(self, personas: list[AgentPersona]) -> str:
        counts: dict[str, int] = {}
        for persona in personas:
            counts[persona.name] = counts.get(persona.name, 0) + 1
        return ",".join(f"{count}:{name}" for name, count in counts.items())

    def _apply_preferences(
        self,
        personas: list[AgentPersona],
        *,
        preferred_agents: list[str],
        avoid_agents: list[str],
        max_team_size: int,
    ) -> list[AgentPersona]:
        avoid = set(avoid_agents)
        preferred_order = {name: idx for idx, name in enumerate(preferred_agents)}

        filtered = [persona for persona in personas if persona.name not in avoid]
        filtered.sort(
            key=lambda persona: (
                0 if persona.name in preferred_order else 1,
                preferred_order.get(persona.name, 999),
                persona.name,
            )
        )

        results: list[AgentPersona] = []
        distinct: set[str] = set()
        for persona in filtered:
            if persona.name in distinct or len(distinct) < max_team_size:
                results.append(persona)
                distinct.add(persona.name)
        return results

    def _fallback_team(
        self,
        task: str,
        *,
        role: str = "",
        specialties: list[str] | None = None,
        direction: str = "",
        preferred_agents: list[str] | None = None,
        avoid_agents: list[str] | None = None,
        max_team_size: int = 3,
        preferred_engine: str = "auto",
        guidance: str = "",
    ) -> TeamConfig:
        """LLM 없이 AgentCatalog.recommend()로 팀을 구성한다.

        Args:
            task: 유저 태스크 설명 문자열.

        Returns:
            TeamConfig 인스턴스.
        """
        specialties = specialties or []
        preferred_agents = preferred_agents or []
        avoid_agents = avoid_agents or []

        profile_text = " ".join(
            part for part in [task, role, " ".join(specialties), direction, guidance] if part
        ).strip()
        recommended = self._catalog.recommend(profile_text or task)

        combined: list[AgentPersona] = []
        for name in preferred_agents:
            persona = self._catalog.get_persona(name)
            if persona is not None:
                combined.append(persona)
        combined.extend(recommended)
        recommended = self._apply_preferences(
            combined,
            preferred_agents=preferred_agents,
            avoid_agents=avoid_agents,
            max_team_size=max_team_size,
        )
        unique_recommended: list[AgentPersona] = []
        seen_names: set[str] = set()
        for persona in recommended:
            if persona.name in seen_names:
                continue
            seen_names.add(persona.name)
            unique_recommended.append(persona)
        recommended = unique_recommended
        if not recommended:
            first = next(iter(self._catalog.list_agents()), None)
            if first is not None:
                recommended = [first]

        lower = profile_text.lower()
        dev_keywords = {
            "implement", "build", "fix", "code", "refactor", "create", "develop",
            "구현", "개발", "코드", "버그", "수정", "빌드",
        }
        research_keywords = {
            "research", "compare", "analyze", "analyse", "investigate",
            "리서치", "비교", "분석", "조사",
        }
        question_keywords = {"?", "설명", "요약", "질문", "알려줘", "왜", "어떻게"}
        multimodal_keywords = {
            "[첨부 입력]", "[첨부 묶음]", "image/jpeg", "video/mp4", "audio/", "photo", "voice",
            "이미지", "사진", "첨부", "문서", "pdf", "비디오", "오디오", "음성",
        }

        if any(kw in lower for kw in multimodal_keywords):
            execution_mode = ExecutionMode.agent_teams
        elif any(kw in lower for kw in dev_keywords):
            execution_mode = ExecutionMode.structured_team
        elif any(kw in lower for kw in research_keywords):
            execution_mode = ExecutionMode.agent_teams
        elif any(kw in lower for kw in question_keywords):
            execution_mode = ExecutionMode.sequential
        else:
            execution_mode = ExecutionMode.sequential

        team_format = self._build_team_format_from_personas(recommended)

        if any(kw in lower for kw in multimodal_keywords):
            preferred_names = ["designer", "analyst", "document-specialist"]
            multimodal_personas: list[AgentPersona] = []
            for name in preferred_names:
                persona = self._catalog.get_persona(name)
                if persona is not None:
                    multimodal_personas.append(persona)
            if multimodal_personas:
                recommended = self._apply_preferences(
                    multimodal_personas + recommended,
                    preferred_agents=preferred_agents or preferred_names,
                    avoid_agents=avoid_agents,
                    max_team_size=max_team_size,
                )
                team_format = self._build_team_format_from_personas(recommended)

        # Determine engine from hints or mode defaults
        if preferred_engine in ("claude-code", "codex"):
            engine = preferred_engine
        elif execution_mode == ExecutionMode.structured_team:
            engine = self._engine_for_category("coding", default="claude-code")
        elif execution_mode == ExecutionMode.agent_teams:
            engine = self._engine_for_category("analysis", default="claude-code")
        else:
            engine = self._engine_for_category("writing", default="claude-code")
        # structured_team always needs Claude Code unless org explicitly fixed to codex
        if execution_mode == ExecutionMode.structured_team and preferred_engine != "codex":
            engine = "claude-code"

        if execution_mode != ExecutionMode.sequential and engine == "codex":
            reasoning = (
                "org preferred codex; 복잡 작업이지만 다중 페르소나를 Codex 프롬프트 컨텍스트로 압축 실행"
            )
        else:
            reasoning = "keyword/profile-based fallback (LLM unavailable)"

        logger.info(
            "Fallback team: {} agents, mode={}, engine={}, format={}",
            len(recommended),
            execution_mode.value,
            engine,
            team_format,
        )
        return TeamConfig(
            agents=recommended,
            execution_mode=execution_mode,
            engine=engine,
            team_format=team_format,
            reasoning=reasoning,
        )

    def format_team_announcement(self, config: TeamConfig) -> str:
        """Telegram 친화적인 팀 구성 안내 문자열을 반환한다.

        Example output:
            🤖 팀 구성: executor×2 + analyst×1 (structured_team 모드)

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
            "claude-code": "Claude Code",
            "codex": "Codex CLI",
            "auto": "자동 선택",
        }.get(config.engine, config.engine)

        announcement = (
            f"🤖 팀 구성 완료\n"
            f"  엔진: {engine_label}\n"
            f"  팀: {parts}\n"
            f"  전략 모드: {mode_label}"
        )
        if config.reasoning:
            announcement += f"\n💡 이유: {config.reasoning}"
        return announcement
