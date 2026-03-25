"""agent_parser.py — ~/.claude/agents/*.md 파싱 및 부서별 그룹화 모듈.

Phase 1: AgentInfo 데이터 모델
Phase 2: 파서 로직 + 부서별 그룹화 + 활성 여부 판별
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# 에이전트 파일 기본 디렉토리
AGENTS_DIR = Path.home() / ".claude" / "agents"

# 부서 표시명 매핑 (prefix → 한국어 레이블)
DEPARTMENT_LABELS: dict[str, str] = {
    "engineering": "⚙️ 개발",
    "design": "🎨 디자인",
    "marketing": "📣 마케팅",
    "testing": "🔍 테스팅",
    "product": "📦 프로덕트",
    "project-management": "🗂️ 프로젝트관리",
    "support": "🛎️ 지원",
    "strategy": "🧭 전략",
    "sales": "💼 세일즈",
    "paid-media": "💰 유료광고",
    "academic": "🎓 학술",
    "specialized": "🔬 전문",
    "game": "🎮 게임개발",
    "game-development": "🎮 게임개발",
    "unity": "🕹️ Unity",
    "unreal": "🕹️ Unreal",
    "xr": "🥽 XR",
    "roblox": "🟥 Roblox",
    "godot": "🟦 Godot",
    "spatial-computing": "🌐 공간컴퓨팅",
    # agency-agents 추가 부서
    "accounts": "💳 회계",
    "automation": "🤖 자동화",
    "backend": "🖧 백엔드",
    "blender": "🎭 Blender",
    "blockchain": "⛓️ 블록체인",
    "compliance": "📋 컴플라이언스",
    "corporate": "🏢 기업교육",
    "data": "📊 데이터",
    "government": "🏛️ 공공",
    "healthcare": "🏥 헬스케어",
    "identity": "🪪 인증",
    "level": "🎮 레벨디자인",
    "lsp": "🔌 LSP",
    "macos": "🍎 macOS",
    "narrative": "📖 내러티브",
    "nexus": "🌐 넥서스",
    "project": "📋 프로젝트",
    "recruitment": "🤝 채용",
    "report": "📈 리포트",
    "study": "📚 스터디",
    "supply": "📦 공급망",
    "technical": "🔧 기술",
    "terminal": "💻 터미널",
    "visionos": "👓 visionOS",
    "workflow": "🔄 워크플로우",
    "zk": "🔐 ZK증명",
}

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_FIELD_RE = re.compile(r"^(\w+):\s*(.+)$", re.MULTILINE)


# ── 데이터 모델 ─────────────────────────────────────────────────────────────


@dataclass
class AgentInfo:
    """에이전트 한 개의 정규화된 정보."""

    id: str
    """파일명 stem. 예: 'engineering-senior-developer'"""

    name: str
    """프론트매터 name 필드. 없으면 id에서 유추."""

    role: str
    """프론트매터 description 필드 (역할 설명)."""

    department: str
    """부서 키. id의 첫 번째 '-' 이전 부분. 예: 'engineering'"""

    is_active: bool = True
    """파일이 유효하면 True. 런타임 상태는 현재 파일 존재 여부로 판별."""

    emoji: str = ""
    """프론트매터 emoji 필드."""

    color: str = ""
    """프론트매터 color 필드."""

    file_path: Optional[Path] = field(default=None, repr=False)
    """원본 파일 경로 (내부용)."""

    @property
    def department_label(self) -> str:
        """부서 한국어 표시명. 매핑 없으면 원본 키 반환."""
        return DEPARTMENT_LABELS.get(self.department, self.department)

    @property
    def display_name(self) -> str:
        """이모지 + 이름 형식."""
        prefix = f"{self.emoji} " if self.emoji else ""
        return f"{prefix}{self.name}"

    @property
    def short_role(self) -> str:
        """역할 설명 100자 이내 축약."""
        return self.role[:100] + ("…" if len(self.role) > 100 else "")


# ── 프론트매터 파서 ──────────────────────────────────────────────────────────


def _parse_frontmatter(text: str) -> dict[str, str]:
    """YAML 프론트매터를 단순 key-value로 파싱 (PyYAML 의존성 없이)."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    block = m.group(1)
    result: dict[str, str] = {}
    for line in block.splitlines():
        fm = _FIELD_RE.match(line.strip())
        if fm:
            key, val = fm.group(1), fm.group(2).strip()
            # 인라인 문자열 따옴표 제거
            if val.startswith(('"', "'")) and val.endswith(('"', "'")):
                val = val[1:-1]
            result[key] = val
    return result


def _infer_department(stem: str) -> str:
    """파일명 stem에서 부서 키 추출.

    'engineering-senior-developer' → 'engineering'
    'design-ui-designer' → 'design'
    'marketing-seo-specialist' → 'marketing'
    'paid-media-auditor' → 'paid-media'  (두 단어 부서)
    """
    # paid-media, project-management 같은 두 단어 부서 처리
    for key in DEPARTMENT_LABELS:
        if stem.startswith(key + "-") or stem == key:
            return key
    # 일반: 첫 '-' 이전
    return stem.split("-")[0]


# ── 핵심 파서 함수 ───────────────────────────────────────────────────────────


def parse_agent_file(path: Path) -> AgentInfo:
    """단일 에이전트 .md 파일을 읽어 AgentInfo 반환.

    프론트매터가 없거나 일부 필드가 빠져 있어도 안전하게 처리한다.
    """
    stem = path.stem
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        fm = _parse_frontmatter(text)
    except OSError:
        fm = {}

    department = _infer_department(stem)
    # name 필드: 프론트매터 → id 기반 유추
    raw_name = fm.get("name", "").strip()
    if not raw_name:
        # 'engineering-senior-developer' → 'Senior Developer'
        parts = stem.split("-")
        raw_name = (
            " ".join(p.capitalize() for p in parts[1:]) if len(parts) > 1 else stem.capitalize()
        )

    role = fm.get("description", "").strip() or fm.get("role", "").strip() or "에이전트"

    return AgentInfo(
        id=stem,
        name=raw_name,
        role=role,
        department=department,
        is_active=True,  # 파일이 존재하면 active
        emoji=fm.get("emoji", "").strip(),
        color=fm.get("color", "").strip(),
        file_path=path,
    )


def load_all_agents(agents_dir: Path = AGENTS_DIR) -> list[AgentInfo]:
    """agents_dir의 모든 .md 파일을 읽어 AgentInfo 리스트로 반환.

    - 하위 디렉토리(design/, engineering/ 등)의 .md도 포함
    - 비-에이전트 문서(README, CONTRIBUTING 등)는 제외
    - is_active=True (파일 존재 = 활성)
    """
    _SKIP_STEMS = {
        "readme", "contributing", "changelog", "license", "quickstart",
        "executive-brief", "agents-orchestrator", "agent-activation-prompts",
        "agentic-identity-trust", "handoff-templates",
        "nexus-strategy", "phase-0-discovery", "phase-1-strategy",
        "phase-2-foundation", "phase-3-build", "phase-4-hardening",
        "phase-5-launch", "phase-6-operate",
    }

    agents: list[AgentInfo] = []
    for path in sorted(agents_dir.rglob("*.md")):
        # 비-에이전트 파일 스킵
        if path.stem.lower() in _SKIP_STEMS:
            continue
        # 비-에이전트 접두어(T-global- 등) 스킵
        if path.stem.startswith("T-") or path.stem.startswith("scenario-"):
            continue
        agents.append(parse_agent_file(path))

    return agents


def group_by_department(agents: list[AgentInfo]) -> dict[str, list[AgentInfo]]:
    """에이전트 리스트를 부서 키 기준으로 그룹화.

    반환: OrderedDict 형태, 알파벳 순 정렬된 부서명.
    """
    groups: dict[str, list[AgentInfo]] = {}
    for agent in agents:
        groups.setdefault(agent.department, []).append(agent)
    # 부서명 알파벳 순 정렬, 알 수 없는 부서는 맨 뒤
    known_order = list(DEPARTMENT_LABELS.keys())
    def _sort_key(dept: str) -> tuple[int, str]:
        try:
            return (known_order.index(dept), dept)
        except ValueError:
            return (len(known_order), dept)

    return dict(sorted(groups.items(), key=lambda kv: _sort_key(kv[0])))


# ── 텔레그램 렌더러 ──────────────────────────────────────────────────────────


def render_org_chart_telegram(
    groups: dict[str, list[AgentInfo]],
    *,
    collapsed: bool = False,
    max_per_dept: int = 6,
    show_role: bool = False,
) -> str:
    """부서별 에이전트 현황을 텔레그램 HTML 형식으로 렌더링.

    Args:
        groups: group_by_department() 반환값
        collapsed: True면 각 부서의 에이전트 수만 표시 (접힘 모드)
        max_per_dept: 부서당 최대 표시 에이전트 수 (성능)
        show_role: True면 에이전트 역할 설명도 표시
    """
    total = sum(len(v) for v in groups.values())
    lines: list[str] = [
        f"🤖 <b>에이전트 조직도</b>  <i>({total}개 · {len(groups)}개 부서)</i>",
        "",
    ]

    for dept, agents in groups.items():
        label = DEPARTMENT_LABELS.get(dept, dept)
        active = sum(1 for a in agents if a.is_active)
        inactive = len(agents) - active

        status_badge = ""
        if inactive > 0:
            status_badge = f" <i>({inactive}개 비활성)</i>"

        lines.append(f"<b>{label}</b> ({len(agents)}){status_badge}")

        if not collapsed:
            for agent in agents[:max_per_dept]:
                badge = "🟢" if agent.is_active else "⚪"
                emoji_prefix = f"{agent.emoji} " if agent.emoji else ""
                role_suffix = f"  <i>{agent.short_role[:60]}</i>" if show_role else ""
                lines.append(f"  {badge} {emoji_prefix}<code>{agent.id}</code>{role_suffix}")
            if len(agents) > max_per_dept:
                lines.append(f"  …외 {len(agents) - max_per_dept}개")
        lines.append("")

    return "\n".join(lines).rstrip()


def render_agent_card(info: AgentInfo, *, show_dept: bool = True, show_role: bool = True) -> str:
    """단일 AgentInfo를 텔레그램 마크다운 카드 한 줄로 렌더링.

    형식: 🟢 [emoji] **Name** *(dept_label)* — role snippet
    - show_dept: True면 부서 라벨 포함
    - show_role: True면 역할 설명 포함 (최대 60자)

    NOTE: 반환값은 마크다운. format_for_telegram() 통과 후 HTML로 변환됨.
    """
    badge = "🟢" if info.is_active else "⚪"
    emoji_prefix = f"{info.emoji} " if info.emoji else ""
    dept_str = f" *({info.department_label})*" if show_dept else ""
    role_str = ""
    if show_role and info.role and info.role != "에이전트":
        role_str = f" — {info.short_role[:60]}"
    return f"{badge} {emoji_prefix}**{info.name}**{dept_str}{role_str}"


def _lookup_agent(aid: str) -> Optional[AgentInfo]:
    """에이전트 ID로 AgentInfo 조회. 정확 일치 → glob 부분 일치 순서."""
    exact = AGENTS_DIR / f"{aid}.md"
    if exact.exists():
        return parse_agent_file(exact)
    matches = list(AGENTS_DIR.glob(f"*{aid}*.md"))
    if matches:
        return parse_agent_file(matches[0])
    # 하위 디렉토리 검색 (design/, engineering/ 등)
    for sub in AGENTS_DIR.iterdir():
        if sub.is_dir():
            sub_exact = sub / f"{aid}.md"
            if sub_exact.exists():
                return parse_agent_file(sub_exact)
    return None


def render_team_header(agent_ids: list[str]) -> str:
    """[TEAM:a,b,c] 태그에서 추출된 에이전트 ID로 팀 구성 헤더 렌더링.

    agents_dir에서 해당 에이전트 파일을 읽어 이름·역할·활성배지·부서라벨을 표시.
    파일이 없으면 ID만 표시 (graceful degradation).

    NOTE: 반환값은 마크다운 형식. format_for_telegram()을 통해 HTML로 변환됨.
          (HTML로 반환하면 format_for_telegram → escape_html 에서 이중 이스케이프 발생)
    """
    if not agent_ids:
        return ""

    real_agents = [aid.strip() for aid in agent_ids if aid.strip() and aid.strip().lower() != "solo"]
    has_solo = any(aid.strip().lower() in ("solo", "") for aid in agent_ids)
    count = len(real_agents) + (1 if has_solo else 0)
    count_str = f" ({count}명)" if count > 1 else ""

    lines = [f"🏗️ **팀 구성**{count_str}"]

    if has_solo:
        lines.append("- 🟢 **solo** *(PM 직접 처리)*")

    for aid in real_agents:
        info = _lookup_agent(aid)
        if info is not None:
            lines.append(f"- {render_agent_card(info, show_dept=True, show_role=True)}")
        else:
            lines.append(f"- 🔘 `{aid}`")

    return "\n".join(lines)


# ── CLI 진입점 ───────────────────────────────────────────────────────────────


def _cli_main() -> None:
    """python -m tools.agent_parser 로 실행 시 조직도 출력."""
    import argparse

    parser = argparse.ArgumentParser(description="에이전트 조직도 파서")
    parser.add_argument("--collapsed", action="store_true", help="접힘 모드 (부서별 수만 표시)")
    parser.add_argument("--show-role", action="store_true", help="역할 설명 포함")
    parser.add_argument("--dept", default="", help="특정 부서만 필터 (예: engineering)")
    parser.add_argument("--json", action="store_true", dest="as_json", help="JSON 출력")
    args = parser.parse_args()

    agents = load_all_agents()
    groups = group_by_department(agents)

    if args.dept:
        groups = {k: v for k, v in groups.items() if k == args.dept}

    if args.as_json:
        import json
        data = {
            dept: [
                {"id": a.id, "name": a.name, "role": a.role, "is_active": a.is_active}
                for a in agent_list
            ]
            for dept, agent_list in groups.items()
        }
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        # HTML 태그 제거하여 터미널 출력
        raw = render_org_chart_telegram(
            groups, collapsed=args.collapsed, show_role=args.show_role
        )
        import re
        clean = re.sub(r"<[^>]+>", "", raw)
        print(clean)


if __name__ == "__main__":
    _cli_main()
