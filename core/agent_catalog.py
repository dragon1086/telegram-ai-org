"""Agent catalog — ~/.claude/agents/ 디렉토리에서 에이전트 페르소나를 동적으로 로드."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from loguru import logger

DEFAULT_MODEL = "claude-sonnet-4-6"

# keyword → agent name mapping for recommend()
_KEYWORD_MAP: list[tuple[list[str], list[str]]] = [
    (
        ["coding", "implement", "debug", "fix", "code", "build", "refactor",
         "구현", "코딩", "개발", "수정", "버그", "빌드", "리팩토링"],
        ["executor", "debugger", "architect"],
    ),
    (
        ["analysis", "research", "data", "market", "analyze", "analyse",
         "분석", "리서치", "데이터", "시장", "조사", "리포트"],
        ["analyst", "scientist"],
    ),
    (
        ["write", "document", "report", "readme", "docs", "documentation",
         "작성", "문서", "보고서", "글쓰기", "마케팅"],
        ["writer", "document-specialist"],
    ),
    (
        ["review", "audit", "security", "quality", "vulnerability",
         "리뷰", "검토", "감사", "보안", "품질"],
        ["code-reviewer", "security-reviewer", "quality-reviewer"],
    ),
    (
        ["test", "qa", "verify", "testing", "coverage", "spec",
         "테스트", "검증", "qa", "커버리지"],
        ["test-engineer", "verifier", "qa-tester"],
    ),
    (
        ["plan", "design", "architect", "architecture", "strategy",
         "계획", "설계", "전략", "아키텍처"],
        ["planner", "architect"],
    ),
]


@dataclass
class AgentPersona:
    """에이전트 페르소나 정보."""

    name: str
    description: str
    model: str = DEFAULT_MODEL
    skills: list[str] = field(default_factory=list)
    personality: str = ""
    tone: str = ""
    catchphrase: str = ""
    strengths: list[str] = field(default_factory=list)


def _extract_skills(description: str) -> list[str]:
    """description에서 capability 키워드를 추출한다."""
    stopwords = {
        "a", "an", "the", "and", "or", "for", "in", "of", "to", "is", "are",
        "that", "this", "with", "from", "by", "on", "as", "at", "be", "it",
        "its", "you", "your", "can", "will", "do", "does", "not", "but", "if",
    }
    words = re.findall(r"[a-zA-Z][\w\-]*", description.lower())
    seen: set[str] = set()
    skills: list[str] = []
    for w in words:
        if w not in stopwords and len(w) > 3 and w not in seen:
            seen.add(w)
            skills.append(w)
        if len(skills) >= 10:
            break
    return skills


def _parse_md(path: Path) -> AgentPersona:
    """단일 .md 파일을 파싱해 AgentPersona를 반환한다."""
    name = path.stem
    text = path.read_text(encoding="utf-8")

    # strip YAML frontmatter
    body = text
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            body = text[end + 3:].lstrip()

    # find first non-empty, non-heading paragraph
    description = ""
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        description = stripped
        break

    if not description:
        description = f"{name} agent"

    # cap length
    if len(description) > 200:
        description = description[:197] + "..."

    skills = _extract_skills(description)
    return AgentPersona(name=name, description=description, model=DEFAULT_MODEL, skills=skills)


class AgentCatalog:
    """~/.claude/agents/ 디렉토리에서 에이전트 페르소나를 동적으로 로드하는 카탈로그."""

    def __init__(self, agents_dir: Path | None = None) -> None:
        """
        Args:
            agents_dir: .md 파일들이 있는 디렉토리. None이면 ~/.claude/agents/ 사용.
        """
        self._agents_dir: Path = agents_dir or (Path.home() / ".claude" / "agents")
        self._personas: dict[str, AgentPersona] = {}

    def load(self) -> None:
        """agents_dir의 모든 .md 파일을 읽어 페르소나를 파싱한다."""
        self._personas.clear()
        if not self._agents_dir.exists():
            logger.warning("agents_dir not found: {}", self._agents_dir)
            return

        for md_path in sorted(self._agents_dir.glob("*.md")):
            try:
                persona = _parse_md(md_path)
                self._personas[persona.name] = persona
                logger.debug("Loaded agent persona: {}", persona.name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to parse {}: {}", md_path.name, exc)

        logger.info("AgentCatalog loaded {} personas from {}", len(self._personas), self._agents_dir)

    def load_bot_yamls(self, bots_dir: Path | None = None) -> None:
        """bots/ 디렉토리의 YAML 파일에서 봇 페르소나를 로드한다."""
        if bots_dir is None:
            bots_dir = Path(__file__).parent.parent / "bots"

        if not bots_dir.exists():
            logger.warning("bots_dir not found: {}", bots_dir)
            return

        loaded = 0
        for yaml_path in sorted(bots_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue

                key = data.get("username") or data.get("org_id") or yaml_path.stem
                name = data.get("dept_name") or data.get("role") or key
                description = data.get("role") or data.get("instruction") or f"{name} bot"
                if len(description) > 200:
                    description = description[:197] + "..."

                persona = AgentPersona(
                    name=key,
                    description=description,
                    model=DEFAULT_MODEL,
                    skills=_extract_skills(description),
                    personality=data.get("personality", ""),
                    tone=data.get("tone", ""),
                    catchphrase=data.get("catchphrase", ""),
                    strengths=data.get("strengths") or [],
                )
                self._personas[key] = persona
                loaded += 1
                logger.debug("Loaded bot persona: {}", key)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to parse {}: {}", yaml_path.name, exc)

        logger.info("load_bot_yamls loaded {} personas from {}", loaded, bots_dir)

    def list_agents(self) -> list[AgentPersona]:
        """로드된 모든 에이전트 페르소나 목록을 반환한다."""
        return list(self._personas.values())

    def get_persona(self, name: str) -> AgentPersona | None:
        """이름으로 에이전트 페르소나를 반환한다. 없으면 None."""
        return self._personas.get(name)

    def recommend(self, task_description: str) -> list[AgentPersona]:
        """태스크 설명을 기반으로 최대 3개의 에이전트를 추천한다.

        키워드 매칭 방식으로 LLM 호출 없이 동작한다.

        Args:
            task_description: 유저 태스크 설명 문자열.

        Returns:
            최대 3개의 추천 AgentPersona 리스트.
        """
        lower = task_description.lower()
        scores: dict[str, int] = {}

        for keywords, agent_names in _KEYWORD_MAP:
            matched = sum(1 for kw in keywords if kw in lower)
            if matched:
                for agent_name in agent_names:
                    scores[agent_name] = scores.get(agent_name, 0) + matched

        ranked = sorted(scores.keys(), key=lambda n: scores[n], reverse=True)

        results: list[AgentPersona] = []
        for name in ranked:
            persona = self._personas.get(name)
            if persona is None:
                # build a minimal persona if not loaded from disk
                persona = AgentPersona(name=name, description=f"{name} agent", model=DEFAULT_MODEL)
            results.append(persona)
            if len(results) >= 3:
                break

        if not results:
            # fallback: return first available persona
            first = next(iter(self._personas.values()), None)
            if first:
                results.append(first)

        logger.debug("recommend('{}') -> {}", task_description[:60], [p.name for p in results])
        return results
