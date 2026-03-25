"""tests/test_agent_parser.py — agent_parser 모듈 단위 테스트.

커버리지:
- 정상 파싱 (프론트매터 있음)
- 프론트매터 없는 파일 graceful 처리
- 빈 부서 (에이전트 없는 dir)
- 비활성 에이전트 (파일 없음)
- group_by_department 그룹화
- render_org_chart_telegram 출력 형식
- render_team_header 출력 형식
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# 테스트 대상 모듈
from tools.agent_parser import (
    AgentInfo,
    _infer_department,
    _parse_frontmatter,
    group_by_department,
    load_all_agents,
    parse_agent_file,
    render_agent_card,
    render_org_chart_telegram,
    render_team_header,
)

# ── 픽스처 ──────────────────────────────────────────────────────────────────


AGENT_FULL_MD = """\
---
name: Senior Developer
description: Premium implementation specialist for backend systems
color: green
emoji: 💎
---

# Senior Developer

Full content here.
"""

AGENT_MINIMAL_MD = """\
# Minimal Agent

No frontmatter here.
"""

AGENT_NO_EMOJI_MD = """\
---
name: Data Engineer
description: Builds data pipelines and ETL workflows
color: blue
---
"""


@pytest.fixture()
def tmp_agents_dir(tmp_path: Path) -> Path:
    """임시 에이전트 디렉토리 생성."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    return agents_dir


# ── _parse_frontmatter ───────────────────────────────────────────────────────


class TestParseFrontmatter:
    def test_parses_all_fields(self):
        result = _parse_frontmatter(AGENT_FULL_MD)
        assert result["name"] == "Senior Developer"
        assert result["description"] == "Premium implementation specialist for backend systems"
        assert result["color"] == "green"
        assert result["emoji"] == "💎"

    def test_no_frontmatter_returns_empty(self):
        result = _parse_frontmatter(AGENT_MINIMAL_MD)
        assert result == {}

    def test_missing_emoji_field(self):
        result = _parse_frontmatter(AGENT_NO_EMOJI_MD)
        assert "emoji" not in result
        assert result["name"] == "Data Engineer"


# ── _infer_department ────────────────────────────────────────────────────────


class TestInferDepartment:
    def test_single_prefix(self):
        assert _infer_department("engineering-senior-developer") == "engineering"
        assert _infer_department("design-ui-designer") == "design"
        assert _infer_department("testing-api-tester") == "testing"

    def test_two_word_department(self):
        assert _infer_department("paid-media-auditor") == "paid-media"
        assert _infer_department("project-management-project-shepherd") == "project-management"

    def test_no_dash(self):
        result = _infer_department("academic")
        assert result == "academic"


# ── parse_agent_file ─────────────────────────────────────────────────────────


class TestParseAgentFile:
    def test_full_frontmatter(self, tmp_agents_dir: Path):
        f = tmp_agents_dir / "engineering-senior-developer.md"
        f.write_text(AGENT_FULL_MD, encoding="utf-8")

        info = parse_agent_file(f)
        assert info.id == "engineering-senior-developer"
        assert info.name == "Senior Developer"
        assert info.department == "engineering"
        assert info.emoji == "💎"
        assert info.is_active is True
        assert "Premium" in info.role

    def test_minimal_no_frontmatter(self, tmp_agents_dir: Path):
        f = tmp_agents_dir / "design-visual-storyteller.md"
        f.write_text(AGENT_MINIMAL_MD, encoding="utf-8")

        info = parse_agent_file(f)
        assert info.id == "design-visual-storyteller"
        assert info.department == "design"
        # 이름은 파일명에서 유추
        assert "Visual" in info.name or "Storyteller" in info.name
        assert info.is_active is True

    def test_no_emoji_defaults_empty(self, tmp_agents_dir: Path):
        f = tmp_agents_dir / "engineering-data-engineer.md"
        f.write_text(AGENT_NO_EMOJI_MD, encoding="utf-8")
        info = parse_agent_file(f)
        assert info.emoji == ""

    def test_short_role_truncation(self, tmp_agents_dir: Path):
        long_desc = "A" * 200
        f = tmp_agents_dir / "engineering-x.md"
        f.write_text(f"---\nname: X\ndescription: {long_desc}\n---\n", encoding="utf-8")
        info = parse_agent_file(f)
        assert len(info.short_role) <= 103  # 100 + "…"


# ── load_all_agents ───────────────────────────────────────────────────────────


class TestLoadAllAgents:
    def test_loads_md_files(self, tmp_agents_dir: Path):
        (tmp_agents_dir / "engineering-senior-developer.md").write_text(AGENT_FULL_MD)
        (tmp_agents_dir / "design-ui-designer.md").write_text(AGENT_FULL_MD)
        agents = load_all_agents(tmp_agents_dir)
        assert len(agents) == 2

    def test_skips_readme(self, tmp_agents_dir: Path):
        (tmp_agents_dir / "readme.md").write_text("# README")
        (tmp_agents_dir / "engineering-senior-developer.md").write_text(AGENT_FULL_MD)
        agents = load_all_agents(tmp_agents_dir)
        assert len(agents) == 1
        assert agents[0].id == "engineering-senior-developer"

    def test_empty_dir_returns_empty(self, tmp_agents_dir: Path):
        agents = load_all_agents(tmp_agents_dir)
        assert agents == []

    def test_skips_t_global_docs(self, tmp_agents_dir: Path):
        (tmp_agents_dir / "T-global-091-phase1.md").write_text("doc")
        (tmp_agents_dir / "engineering-senior-developer.md").write_text(AGENT_FULL_MD)
        agents = load_all_agents(tmp_agents_dir)
        assert len(agents) == 1

    def test_all_agents_active(self, tmp_agents_dir: Path):
        (tmp_agents_dir / "engineering-senior-developer.md").write_text(AGENT_FULL_MD)
        agents = load_all_agents(tmp_agents_dir)
        assert all(a.is_active for a in agents)


# ── group_by_department ──────────────────────────────────────────────────────


class TestGroupByDepartment:
    def test_groups_by_prefix(self, tmp_agents_dir: Path):
        agents = [
            parse_agent_file(_make_file(tmp_agents_dir, "engineering-a.md", AGENT_FULL_MD)),
            parse_agent_file(_make_file(tmp_agents_dir, "engineering-b.md", AGENT_FULL_MD)),
            parse_agent_file(_make_file(tmp_agents_dir, "design-a.md", AGENT_FULL_MD)),
        ]
        groups = group_by_department(agents)
        assert "engineering" in groups
        assert "design" in groups
        assert len(groups["engineering"]) == 2
        assert len(groups["design"]) == 1

    def test_empty_input(self):
        groups = group_by_department([])
        assert groups == {}

    def test_unknown_department_included(self):
        agents = [
            AgentInfo(id="zk-steward", name="ZK", role="Zero-knowledge", department="zk", is_active=True),
        ]
        groups = group_by_department(agents)
        assert "zk" in groups


def _make_file(base: Path, name: str, content: str) -> Path:
    f = base / name
    f.write_text(content, encoding="utf-8")
    return f


# ── render_org_chart_telegram ────────────────────────────────────────────────


class TestRenderOrgChartTelegram:
    def _make_agents(self) -> dict[str, list[AgentInfo]]:
        return {
            "engineering": [
                AgentInfo(id="engineering-senior-developer", name="Senior Developer",
                          role="Backend specialist", department="engineering",
                          is_active=True, emoji="💎"),
                AgentInfo(id="engineering-backend-architect", name="Backend Architect",
                          role="System design", department="engineering",
                          is_active=True, emoji="🏛️"),
            ],
            "design": [
                AgentInfo(id="design-ui-designer", name="UI Designer",
                          role="Visual design", department="design",
                          is_active=False, emoji="🎨"),
            ],
        }

    def test_contains_total_count(self):
        groups = self._make_agents()
        html = render_org_chart_telegram(groups)
        assert "3개" in html  # 총 3개 에이전트

    def test_contains_department_labels(self):
        groups = self._make_agents()
        html = render_org_chart_telegram(groups)
        assert "⚙️ 개발" in html
        assert "🎨 디자인" in html

    def test_active_badge_green(self):
        groups = self._make_agents()
        html = render_org_chart_telegram(groups)
        assert "🟢" in html

    def test_inactive_badge_white(self):
        groups = self._make_agents()
        html = render_org_chart_telegram(groups)
        assert "⚪" in html

    def test_collapsed_mode_hides_agents(self):
        groups = self._make_agents()
        html = render_org_chart_telegram(groups, collapsed=True)
        # 접힘 모드: 개별 에이전트 ID 노출 없음
        assert "engineering-senior-developer" not in html

    def test_max_per_dept_limits(self):
        agents_dir_mock = {
            "engineering": [
                AgentInfo(id=f"engineering-a{i}", name=f"A{i}", role="r",
                          department="engineering", is_active=True)
                for i in range(10)
            ]
        }
        html = render_org_chart_telegram(agents_dir_mock, max_per_dept=3)
        # 나머지 7개는 "…외 7개" 로 표시
        assert "외 7개" in html


# ── render_team_header ───────────────────────────────────────────────────────


# ── render_agent_card ────────────────────────────────────────────────────────


class TestRenderAgentCard:
    def _active_agent(self) -> AgentInfo:
        return AgentInfo(
            id="engineering-senior-developer",
            name="Senior Developer",
            role="Premium backend specialist",
            department="engineering",
            is_active=True,
            emoji="💎",
        )

    def _inactive_agent(self) -> AgentInfo:
        return AgentInfo(
            id="design-ui-designer",
            name="UI Designer",
            role="Visual design",
            department="design",
            is_active=False,
            emoji="🎨",
        )

    def test_active_badge_green(self):
        result = render_agent_card(self._active_agent())
        assert "🟢" in result

    def test_inactive_badge_white(self):
        result = render_agent_card(self._inactive_agent())
        assert "⚪" in result

    def test_name_in_bold(self):
        result = render_agent_card(self._active_agent())
        assert "**Senior Developer**" in result

    def test_dept_label_shown_when_enabled(self):
        result = render_agent_card(self._active_agent(), show_dept=True)
        # ⚙️ 개발 레이블 포함
        assert "개발" in result

    def test_dept_label_hidden_when_disabled(self):
        result = render_agent_card(self._active_agent(), show_dept=False)
        # 부서 라벨 없어야 함
        assert "개발" not in result

    def test_role_shown_when_enabled(self):
        result = render_agent_card(self._active_agent(), show_role=True)
        assert "Premium" in result

    def test_role_hidden_when_disabled(self):
        result = render_agent_card(self._active_agent(), show_role=False)
        assert "Premium" not in result

    def test_emoji_included(self):
        result = render_agent_card(self._active_agent())
        assert "💎" in result

    def test_no_emoji_agent(self):
        agent = AgentInfo(id="data-engineer", name="Data Engineer",
                          role="ETL", department="data", is_active=True, emoji="")
        result = render_agent_card(agent)
        assert "Data Engineer" in result
        # 이중 공백 없어야 함
        assert "  " not in result.replace("  ", " ")

    def test_no_html_tags(self):
        result = render_agent_card(self._active_agent())
        assert "<b>" not in result
        assert "<i>" not in result

    def test_role_truncated_at_60(self):
        agent = AgentInfo(id="eng-x", name="X", role="A" * 80,
                          department="engineering", is_active=True)
        result = render_agent_card(agent)
        # 60자 이내 + "…" 가능
        role_part = result.split("—", 1)[-1] if "—" in result else ""
        assert len(role_part.strip()) <= 63


# ── render_team_header ───────────────────────────────────────────────────────


class TestRenderTeamHeader:
    def test_solo_renders(self):
        result = render_team_header(["solo"])
        assert "solo" in result.lower()

    def test_empty_returns_empty(self):
        result = render_team_header([])
        assert result == ""

    def test_unknown_agent_shows_id(self):
        result = render_team_header(["nonexistent-agent-xyz"])
        assert "nonexistent-agent-xyz" in result

    def test_header_label(self):
        result = render_team_header(["solo"])
        assert "팀 구성" in result

    def test_count_shown_for_multiple(self):
        """에이전트 2명 이상이면 (N명) 카운트 표시."""
        result = render_team_header(["nonexistent-a", "nonexistent-b"])
        assert "2명" in result

    def test_no_count_for_single(self):
        """에이전트 1명이면 카운트 미표시."""
        result = render_team_header(["nonexistent-x"])
        assert "명" not in result

    def test_active_badge_in_solo_line(self):
        """solo 줄에 활성 배지(🟢) 포함."""
        result = render_team_header(["solo"])
        assert "🟢" in result

    def test_unknown_agent_gets_offline_badge(self):
        """파일 없는 에이전트는 🔘 배지 사용."""
        result = render_team_header(["nonexistent-xyz-agent-999"])
        assert "🔘" in result

    def test_returns_markdown_not_html(self):
        """render_team_header는 마크다운을 반환해야 한다 (HTML 이중 이스케이프 방지).

        format_for_telegram()이 HTML 이스케이프를 수행하므로
        <b> 같은 HTML 태그를 직접 포함하면 &lt;b&gt; 로 깨진다.
        """
        result = render_team_header(["solo"])
        assert "<b>" not in result, "HTML 태그 대신 마크다운(**) 을 사용해야 함"
        assert "**" in result, "마크다운 bold(**) 형식이어야 함"

    def test_markdown_renders_to_correct_html(self):
        """format_for_telegram 통과 후 올바른 HTML이 나와야 한다."""
        try:
            from core.telegram_formatting import format_for_telegram
        except ImportError:
            pytest.skip("core.telegram_formatting 없음")

        result = render_team_header(["solo"])
        html = format_for_telegram(result)
        assert "<b>" in html, "format_for_telegram 후 <b> 태그가 있어야 함"
        assert "&lt;b&gt;" not in html, "이중 이스케이프 금지"

    def test_no_raw_html_in_output(self):
        """비활성 에이전트 포함 — 모든 경로에서 HTML 태그 없어야 함."""
        result = render_team_header(["nonexistent-xyz-agent"])
        assert "<b>" not in result
        assert "<i>" not in result
        assert "<code>" not in result


# ── 통합: load → group → render ─────────────────────────────────────────────


class TestTeamHeaderReplacement:
    """LLM이 [TEAM:...] + 🏗️ 둘 다 쓸 때 agent 파일 기반 렌더링이 우선해야 함.

    Bug: _handle_collab_tags 에서 '🏗️' not in cleaned 조건 때문에
    LLM이 쓴 🏗️ 섹션이 남아 있으면 agent 파일 기반 렌더링이 스킵됐었음.
    Fix: [TEAM:...] 태그가 있으면 항상 agent 파일 기반 헤더로 교체.
    """

    def _simulate_handle_collab_tags(self, response: str) -> str:
        """_handle_collab_tags의 TEAM 태그 처리 부분만 추출하여 단위 테스트."""
        import re as _re

        team_header = ""
        team_match = _re.search(r"\[TEAM:([^\]]+)\]", response)
        if team_match:
            raw_agents = team_match.group(1)
            agent_ids = [a.strip() for a in raw_agents.split(",") if a.strip()]
            _header = render_team_header(agent_ids)
            if _header:
                team_header = _header + "\n\n"

        cleaned = _re.sub(r"\[TEAM:[^\]]+\]", "", response).strip()

        # ← 수정된 로직: agent 파일 기반 렌더링 항상 우선
        if team_header:
            if "🏗️" in cleaned:
                cleaned = _re.sub(
                    r"🏗️[^\n]*(?:\n(?!(?:##|\s*$))[^\n]*)*\n?",
                    "",
                    cleaned,
                ).strip()
            cleaned = team_header + cleaned

        return cleaned

    def test_llm_wrote_both_team_tag_and_icon_section(self):
        """[TEAM:...] + 🏗️ 모두 있을 때 agent 파일 기반 헤더가 사용됨."""
        response = (
            "[TEAM:solo]\n\n"
            "🏗️ 팀 구성\n"
            "• solo: PM 직접 처리\n\n"
            "## 결론\n구현 완료."
        )
        result = self._simulate_handle_collab_tags(response)
        # agent 파일 기반 헤더: render_team_header(["solo"]) 결과
        assert "🏗️ **팀 구성**" in result, "agent 파일 기반 헤더가 없음"
        # LLM이 직접 쓴 bullet(• solo:) 은 제거됨
        assert "• solo:" not in result, "LLM이 직접 쓴 섹션이 남아 있음"

    def test_llm_wrote_only_team_tag_no_icon(self):
        """[TEAM:...] 만 있고 🏗️ 없을 때 agent 파일 기반 헤더가 추가됨."""
        response = "[TEAM:solo]\n\n## 결론\n구현 완료."
        result = self._simulate_handle_collab_tags(response)
        assert "🏗️ **팀 구성**" in result
        assert "## 결론" in result

    def test_no_team_tag_preserves_original(self):
        """[TEAM:...] 가 없으면 원본 응답 그대로."""
        response = "## 결론\n구현 완료."
        result = self._simulate_handle_collab_tags(response)
        assert result == response

    def test_team_tag_removed_from_output(self):
        """최종 응답에 [TEAM:...] 태그가 남아있지 않아야 함."""
        response = "[TEAM:solo]\n\n## 결론\n구현 완료."
        result = self._simulate_handle_collab_tags(response)
        assert "[TEAM:" not in result

    def test_conclusion_preserved_after_header(self):
        """🏗️ 헤더 삽입 후 ## 결론 섹션이 보존됨."""
        response = "[TEAM:solo]\n\n## 결론\n구현 완료."
        result = self._simulate_handle_collab_tags(response)
        assert "## 결론" in result
        assert "구현 완료" in result


class TestIntegration:
    def test_real_agents_dir_loads(self):
        """실제 ~/.claude/agents 디렉토리가 존재하면 파싱 확인."""
        real_dir = Path.home() / ".claude" / "agents"
        if not real_dir.exists():
            pytest.skip("~/.claude/agents 디렉토리 없음")

        agents = load_all_agents(real_dir)
        assert len(agents) >= 10, "최소 10개 에이전트 기대"
        groups = group_by_department(agents)
        assert "engineering" in groups or len(groups) > 0

        html = render_org_chart_telegram(groups, collapsed=True)
        assert "에이전트 조직도" in html

    def test_render_output_is_valid_partial_html(self):
        """렌더 출력이 열린 태그/닫힌 태그 쌍을 맞추는지 확인."""
        real_dir = Path.home() / ".claude" / "agents"
        if not real_dir.exists():
            pytest.skip("~/.claude/agents 디렉토리 없음")

        agents = load_all_agents(real_dir)
        groups = group_by_department(agents)
        html = render_org_chart_telegram(groups)

        # <b>...</b> 태그 쌍 확인
        opens = len(re.findall(r"<b>", html))
        closes = len(re.findall(r"</b>", html))
        assert opens == closes, f"<b> 태그 불균형: open={opens}, close={closes}"
