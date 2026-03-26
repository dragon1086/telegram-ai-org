"""Dynamic team builder — LLM으로 태스크에 맞는 에이전트 팀 구성을 결정한다."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from loguru import logger

from core.agent_catalog import AgentCatalog, AgentPersona
from core.pm_decision import DecisionClientProtocol


def load_personas(agents_dir: Path | None = None) -> list[str]:
    """~/.claude/agents 디렉토리의 .md 파일명(확장자 제외) 목록을 반환한다.

    Args:
        agents_dir: 페르소나 .md 파일이 있는 디렉토리. None이면 ~/.claude/agents 사용.

    Returns:
        파일명(stem) 목록. 디렉토리가 없거나 읽기 실패 시 빈 리스트.
    """
    target = agents_dir or (Path.home() / ".claude" / "agents")
    if not target.exists():
        logger.debug("load_personas: agents_dir not found: {}", target)
        return []
    try:
        return sorted(p.stem for p in target.rglob("*.md"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("load_personas: 디렉토리 읽기 실패 ({}): {}", target, exc)
        return []


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


_TEAM_SYSTEM_PROMPT_FALLBACK_AGENTS = (
    "engineering-senior-developer, engineering-rapid-prototyper, engineering-backend-architect, "
    "engineering-software-architect, engineering-code-reviewer, engineering-security-engineer, "
    "engineering-incident-response-commander, engineering-technical-writer, "
    "data-analytics-reporter, product-trend-researcher, product-behavioral-nudge-engine, "
    "engineering-technical-writer, specialized-document-generator, "
    "testing-api-tester, testing-evidence-collector, testing-reality-checker, testing-workflow-optimizer, "
    "project-management-project-shepherd, product-manager, "
    "design-ux-architect, design-ui-designer, specialized-model-qa"
)


def _build_team_system_prompt(agent_names: list[str]) -> str:
    """사용 가능한 에이전트 이름을 동적으로 주입해 팀 구성 LLM 프롬프트를 생성한다.

    Args:
        agent_names: AgentCatalog에서 로드된 실제 에이전트 이름 목록.
                     비어 있으면 하드코딩된 폴백 목록을 사용한다.

    Returns:
        LLM에 전달할 시스템 프롬프트 문자열.
    """
    names_str = ", ".join(agent_names) if agent_names else _TEAM_SYSTEM_PROMPT_FALLBACK_AGENTS
    return f"""You are a PM (Project Manager) for an AI development team.

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

Available agent names: {names_str}

CRITICAL: You MUST respond with ONLY a single JSON object. No markdown, no explanation, no prose.
Do NOT execute or answer the task — only decide the team composition.

Output format (nothing else):
{{"agents": [{{"name": "engineering-senior-developer", "count": 2}}, {{"name": "data-analytics-reporter", "count": 1}}], "execution_mode": "structured_team", "engine": "claude-code", "reasoning": "brief reason"}}

Rules:
- Use at most 3 distinct agent types.
- Each count must be 1, 2, or 3.
- agent names must be from the available list above.
- NEVER answer or summarize the task. ONLY output JSON.
"""


def _extract_json_from_response(text: str) -> dict:
    """LLM 응답에서 JSON 객체를 추출한다.

    순수 JSON, ```json 코드블록, 텍스트 속 {...} 모두 처리.
    """
    text = text.strip()
    # 1) 순수 JSON
    if text.startswith("{"):
        return json.loads(text)
    # 2) ```json ... ``` 코드블록
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # 3) 텍스트 안에 섞인 JSON 객체
    m = re.search(r"\{[^{}]*\"agents\"[^{}]*\[.*?\].*?\}", text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"No JSON found in LLM response: {text[:200]}")


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

        # LLM은 _decision_client (PMDecisionClient → Claude Code)로만 처리
        # AsyncAnthropic 직접 호출 제거 — OAuth 토큰이 REST API를 지원하지 않음
        self._llm_available = decision_client is not None
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

        if self._decision_client is None:
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
                agent_names = [p.name for p in self._catalog.list_agents()]
                system_prompt = _build_team_system_prompt(agent_names)
                content = await self._decision_client.complete(
                    task_context,
                    system_prompt=system_prompt,
                )
            logger.debug("LLM team build raw response (first 500 chars): {}", content[:500])
            data = _extract_json_from_response(content)
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
                # 추상 역할명(analyst, executor 등) → 실제 페르소나명 즉시 해소
                # 카탈로그에 직접 없는 경우에만 _ABSTRACT_TO_PERSONA 매핑 적용
                resolved_name = name
                persona = self._catalog.get_persona(name)
                if persona is None and name in self._ABSTRACT_TO_PERSONA:
                    available_now = set(load_personas())
                    for candidate in self._ABSTRACT_TO_PERSONA[name]:
                        if candidate in available_now:
                            resolved_name = candidate
                            break
                    else:
                        # 후보가 없으면 첫 번째 후보를 폴백으로 사용
                        resolved_name = self._ABSTRACT_TO_PERSONA[name][0] if self._ABSTRACT_TO_PERSONA[name] else name
                    if resolved_name != name:
                        logger.debug("Abstract role '{}' resolved to '{}'", name, resolved_name)
                    persona = self._catalog.get_persona(resolved_name)
                if persona is None:
                    from core.agent_catalog import DEFAULT_MODEL, AgentPersona
                    persona = AgentPersona(name=resolved_name, description=f"{resolved_name} agent", model=DEFAULT_MODEL)
                for _ in range(count):
                    personas.append(persona)
            except Exception as spec_err:
                logger.warning("Failed to parse agent spec {}: {}", spec, spec_err)

        # Engine: from LLM response, validated
        engine_raw = data.get("engine", "")
        if engine_raw in ("claude-code", "codex", "gemini-cli", "auto"):
            engine = engine_raw
        elif execution_mode == ExecutionMode.structured_team:
            engine = "claude-code"
        elif execution_mode == ExecutionMode.agent_teams:
            engine = "claude-code"
        else:
            engine = "auto"
        if preferred_engine in ("claude-code", "codex", "gemini-cli"):
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
            preferred_names = ["design-ui-designer", "data-analytics-reporter", "specialized-document-generator"]
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
        if preferred_engine in ("claude-code", "codex", "gemini-cli"):
            engine = preferred_engine
        elif execution_mode == ExecutionMode.structured_team:
            engine = self._engine_for_category("coding", default="claude-code")
        elif execution_mode == ExecutionMode.agent_teams:
            engine = self._engine_for_category("analysis", default="claude-code")
        else:
            engine = self._engine_for_category("writing", default="claude-code")
        # structured_team always needs Claude Code unless org explicitly fixed to codex/gemini-cli
        if execution_mode == ExecutionMode.structured_team and preferred_engine not in ("codex", "gemini-cli"):
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

    # 추상 역할명 → 실제 페르소나명 후보 매핑 (우선순위 순)
    # 새 항목 추가 시: ~/.claude/agents/ 파일명 기준으로 작성
    _ABSTRACT_TO_PERSONA: dict[str, list[str]] = {
        "executor": ["engineering-senior-developer", "engineering-rapid-prototyper", "engineering-backend-architect"],
        "debugger": ["engineering-incident-response-commander", "engineering-code-reviewer"],
        "architect": ["engineering-software-architect", "engineering-backend-architect"],
        "analyst": ["data-analytics-reporter", "product-trend-researcher"],
        "scientist": ["data-analytics-reporter", "product-behavioral-nudge-engine"],
        "writer": ["engineering-technical-writer", "marketing-content-creator"],
        "document-specialist": ["specialized-document-generator", "engineering-technical-writer"],
        "code-reviewer": ["engineering-code-reviewer"],
        "security-reviewer": ["engineering-security-engineer", "blockchain-security-auditor"],
        "quality-reviewer": ["testing-reality-checker", "testing-tool-evaluator"],
        "test-engineer": ["testing-api-tester", "testing-performance-benchmarker"],
        "verifier": ["testing-evidence-collector", "testing-reality-checker"],
        "qa-tester": ["testing-api-tester", "testing-workflow-optimizer"],
        "planner": ["project-management-project-shepherd", "product-manager"],
        "explore": ["product-trend-researcher", "academic-psychologist"],
        "designer": ["design-ux-architect", "design-ui-designer"],
        "build-fixer": ["engineering-rapid-prototyper", "engineering-git-workflow-master"],
        "critic": ["testing-reality-checker", "specialized-model-qa"],
        # 시스템 프롬프트 예시에서 자주 등장하는 비정규 약어 → 구체 페르소나 폴백
        "backend-engineer": ["engineering-backend-architect", "engineering-senior-developer"],
        "frontend-engineer": ["engineering-frontend-developer", "engineering-senior-developer"],
        "ux-designer": ["design-ux-architect", "design-ui-designer"],
        "ui-designer": ["design-ui-designer", "design-ux-architect"],
        "data-analyst": ["data-analytics-reporter", "product-trend-researcher"],
        "researcher": ["product-trend-researcher", "data-analytics-reporter"],
        "devops": ["engineering-devops-automator", "engineering-sre"],
        "security": ["engineering-security-engineer", "blockchain-security-auditor"],
        "pm": ["product-manager", "project-management-project-shepherd"],
        "tester": ["testing-api-tester", "testing-reality-checker"],
        "developer": ["engineering-senior-developer", "engineering-rapid-prototyper"],
        "engineer": ["engineering-senior-developer", "engineering-backend-architect"],
    }

    def _resolve_persona_display_name(self, abstract_name: str, available_personas: set[str]) -> str:
        """추상 역할명을 실제 페르소나명으로 변환한다.

        available_personas에 후보가 없어도 _ABSTRACT_TO_PERSONA의 첫 번째 후보를 반환(폴백).
        load_personas()가 빈 집합을 반환하는 경우에도 추상명이 노출되지 않도록 한다.

        Args:
            abstract_name: 추상 역할명 (예: "executor").
            available_personas: ~/.claude/agents에서 로드한 실제 페르소나 파일명 집합.

        Returns:
            실제 페르소나명. 매핑이 없으면 추상명 그대로.
        """
        candidates = self._ABSTRACT_TO_PERSONA.get(abstract_name, [])
        # 1순위: available_personas에 실제 존재하는 후보
        for candidate in candidates:
            if candidate in available_personas:
                return candidate
        # 2순위: 추상명이 이미 실제 페르소나명인 경우
        if abstract_name in available_personas:
            return abstract_name
        # 3순위: available_personas가 비어 있어도 매핑된 첫 번째 후보 사용
        # (load_personas() 실패 시에도 analyst→data-analytics-reporter 등이 표시되도록)
        if candidates:
            return candidates[0]
        # 폴백: 매핑 자체가 없으면 추상명 그대로
        return abstract_name

    def format_persona_footer(self, config: TeamConfig, *, agents_dir: Path | None = None) -> str:
        """완료보고 결론 하단에 추가할 사용 에이전트/페르소나 목록 문자열을 반환한다.

        각 조직(dept) 봇 자체 보고에만 포함 — PM 봇은 호출하지 않는다.

        Args:
            config: build_team()이 반환한 TeamConfig.
            agents_dir: 페르소나 디렉토리. None이면 ~/.claude/agents 사용.

        Returns:
            사용 에이전트/페르소나 목록 문자열. 에이전트 없으면 빈 문자열.
        """
        available = set(load_personas(agents_dir))
        resolved = []
        seen: set[str] = set()
        for persona in config.agents:
            display = self._resolve_persona_display_name(persona.name, available)
            if display not in seen:
                seen.add(display)
                resolved.append(display)
        if not resolved:
            return ""
        names_str = ", ".join(resolved)
        return f"\n\n**사용 에이전트/페르소나**: [{names_str}]"

    def format_team_announcement(self, config: TeamConfig, *, agents_dir: Path | None = None) -> str:
        """Telegram 친화적인 팀 구성 안내 문자열을 반환한다.

        추상 역할명(executor, analyst 등) 대신 ~/.claude/agents의 실제 페르소나명을 표시한다.
        매핑 실패 시 추상명을 그대로 사용(폴백).

        Args:
            config: build_team()이 반환한 TeamConfig.
            agents_dir: 페르소나 디렉토리. None이면 ~/.claude/agents 사용.

        Returns:
            포맷된 문자열.
        """
        available = set(load_personas(agents_dir))

        # count occurrences of each agent name, resolving to real persona names
        counts: dict[str, int] = {}
        for persona in config.agents:
            display = self._resolve_persona_display_name(persona.name, available)
            counts[display] = counts.get(display, 0) + 1

        parts = " + ".join(
            f"{name}×{cnt}" if cnt > 1 else name
            for name, cnt in counts.items()
        )
        mode_label = config.execution_mode.value
        engine_label = {
            "claude-code": "Claude Code",
            "codex": "Codex CLI",
            "gemini-cli": "Gemini CLI",
            "auto": "자동 선택",
        }.get(config.engine, config.engine)

        announcement = (
            f"🤖 팀 구성 완료\n"
            f"  엔진: {engine_label}\n"
            f"  팀: {parts}\n"
            f"  전략 모드: {mode_label}"
        )
        if config.reasoning and "fallback" not in config.reasoning.lower():
            announcement += f"\n💡 이유: {config.reasoning}"
        return announcement
