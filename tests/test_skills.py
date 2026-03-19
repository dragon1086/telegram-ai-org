"""스킬 구조 및 품질 검증 테스트.

Anthropic 스킬 가이드 준수 여부를 자동 검증한다:
- 모든 스킬에 SKILL.md 존재
- frontmatter name/description 필드 존재
- description이 트리거 조건 중심으로 작성됨
- quality-gate 스킬에 실행 스크립트 존재
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).parent.parent / "skills"
CLAUDE_SKILLS_DIR = Path(__file__).parent.parent / ".claude" / "skills"


def get_all_skill_dirs() -> list[Path]:
    """skills/ 아래 모든 스킬 디렉토리 반환."""
    if not SKILLS_DIR.exists():
        return []
    return [d for d in SKILLS_DIR.iterdir() if d.is_dir()]


def parse_frontmatter(skill_md: Path) -> dict:
    """SKILL.md의 YAML frontmatter 파싱."""
    content = skill_md.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    fm_text = content[3:end].strip()
    result = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip().strip('"')
    return result


class TestSkillStructure:
    """모든 스킬의 기본 구조 검증."""

    def test_skills_directory_exists(self):
        """skills/ 디렉토리가 존재해야 한다."""
        assert SKILLS_DIR.exists(), f"skills/ 디렉토리 없음: {SKILLS_DIR}"

    def test_minimum_skill_count(self):
        """최소 10개 이상의 스킬이 있어야 한다."""
        skill_dirs = get_all_skill_dirs()
        assert len(skill_dirs) >= 10, f"스킬 수 부족: {len(skill_dirs)}개"

    def test_all_skills_have_skill_md(self):
        """모든 스킬 디렉토리에 SKILL.md가 있어야 한다."""
        skill_dirs = get_all_skill_dirs()
        missing = [d.name for d in skill_dirs if not (d / "SKILL.md").exists()]
        assert not missing, f"SKILL.md 없는 스킬: {missing}"

    def test_all_skills_have_name_field(self):
        """모든 SKILL.md에 frontmatter name 필드가 있어야 한다."""
        skill_dirs = get_all_skill_dirs()
        missing = []
        for d in skill_dirs:
            skill_md = d / "SKILL.md"
            if skill_md.exists():
                fm = parse_frontmatter(skill_md)
                if not fm.get("name"):
                    missing.append(d.name)
        assert not missing, f"name 필드 없는 스킬: {missing}"

    def test_all_skills_have_description_field(self):
        """모든 SKILL.md에 frontmatter description 필드가 있어야 한다."""
        skill_dirs = get_all_skill_dirs()
        missing = []
        for d in skill_dirs:
            skill_md = d / "SKILL.md"
            if skill_md.exists():
                fm = parse_frontmatter(skill_md)
                if not fm.get("description"):
                    missing.append(d.name)
        assert not missing, f"description 필드 없는 스킬: {missing}"

    def test_skill_descriptions_contain_triggers(self):
        """description에 트리거 키워드(Triggers: 또는 Use when)가 포함되어야 한다."""
        skill_dirs = get_all_skill_dirs()
        non_trigger = []
        for d in skill_dirs:
            skill_md = d / "SKILL.md"
            if skill_md.exists():
                fm = parse_frontmatter(skill_md)
                desc = fm.get("description", "")
                has_trigger = (
                    "Triggers:" in desc
                    or "Use when" in desc
                    or "triggers" in desc.lower()
                    or "when" in desc.lower()
                )
                if not has_trigger:
                    non_trigger.append(d.name)
        assert not non_trigger, f"트리거 조건 없는 description 스킬: {non_trigger}"

    def test_skill_descriptions_not_too_short(self):
        """description이 최소 50자 이상이어야 한다."""
        skill_dirs = get_all_skill_dirs()
        too_short = []
        for d in skill_dirs:
            skill_md = d / "SKILL.md"
            if skill_md.exists():
                fm = parse_frontmatter(skill_md)
                desc = fm.get("description", "")
                if len(desc) < 50:
                    too_short.append(f"{d.name} ({len(desc)}자)")
        assert not too_short, f"description 너무 짧은 스킬: {too_short}"


class TestQualityGateSkill:
    """quality-gate 스킬 상세 검증."""

    def test_quality_gate_exists(self):
        skill_dir = SKILLS_DIR / "quality-gate"
        assert skill_dir.exists()

    def test_quality_gate_has_script(self):
        """quality-gate 스킬에 실행 스크립트가 있어야 한다."""
        script = SKILLS_DIR / "quality-gate" / "scripts" / "run.sh"
        assert script.exists(), f"quality-gate 스크립트 없음: {script}"

    def test_quality_gate_script_is_executable_bash(self):
        """run.sh가 bash 스크립트여야 한다."""
        script = SKILLS_DIR / "quality-gate" / "scripts" / "run.sh"
        if script.exists():
            content = script.read_text()
            assert "#!/" in content, "shebang 없음"
            assert "pytest" in content or "ruff" in content, "린트/테스트 명령 없음"

    def test_quality_gate_has_gotchas(self):
        """quality-gate에 gotchas.md가 있어야 한다."""
        gotchas = SKILLS_DIR / "quality-gate" / "gotchas.md"
        assert gotchas.exists(), "gotchas.md 없음"


class TestPMTaskDispatchSkill:
    """pm-task-dispatch 스킬 상세 검증."""

    def test_pm_task_dispatch_has_config(self):
        """pm-task-dispatch에 config.json이 있어야 한다."""
        config = SKILLS_DIR / "pm-task-dispatch" / "config.json"
        assert config.exists(), "config.json 없음"

    def test_pm_task_dispatch_config_valid_json(self):
        """config.json이 유효한 JSON이어야 한다."""
        config = SKILLS_DIR / "pm-task-dispatch" / "config.json"
        if config.exists():
            data = json.loads(config.read_text())
            assert "routing_matrix" in data, "routing_matrix 필드 없음"

    def test_pm_task_dispatch_has_references(self):
        """pm-task-dispatch에 references/ 디렉토리가 있어야 한다."""
        refs = SKILLS_DIR / "pm-task-dispatch" / "references"
        assert refs.exists() and refs.is_dir(), "references/ 없음"

    def test_pm_task_dispatch_has_gotchas(self):
        gotchas = SKILLS_DIR / "pm-task-dispatch" / "gotchas.md"
        assert gotchas.exists(), "gotchas.md 없음"


class TestAutonomousSkillProxy:
    """autonomous-skill-proxy 스킬 상세 검증."""

    def test_has_config(self):
        config = SKILLS_DIR / "autonomous-skill-proxy" / "config.json"
        assert config.exists(), "config.json 없음"

    def test_has_gotchas(self):
        gotchas = SKILLS_DIR / "autonomous-skill-proxy" / "gotchas.md"
        assert gotchas.exists(), "gotchas.md 없음"

    def test_config_has_autonomous_mode(self):
        config = SKILLS_DIR / "autonomous-skill-proxy" / "config.json"
        if config.exists():
            data = json.loads(config.read_text())
            assert "autonomous_mode" in data, "autonomous_mode 필드 없음"


class TestWeeklyReviewSkill:
    """weekly-review 스킬 상세 검증."""

    def test_has_data_dir(self):
        data_dir = SKILLS_DIR / "weekly-review" / "data"
        assert data_dir.exists(), "data/ 디렉토리 없음"

    def test_has_template(self):
        template = SKILLS_DIR / "weekly-review" / "templates" / "report-template.md"
        assert template.exists(), "report-template.md 없음"

    def test_has_gotchas(self):
        gotchas = SKILLS_DIR / "weekly-review" / "gotchas.md"
        assert gotchas.exists(), "gotchas.md 없음"


class TestEnvExample:
    """.env.example 검증."""

    def test_env_example_exists(self):
        env_example = Path(__file__).parent.parent / ".env.example"
        assert env_example.exists(), ".env.example 없음"

    def test_env_example_has_autonomous_mode(self):
        env_example = Path(__file__).parent.parent / ".env.example"
        if env_example.exists():
            content = env_example.read_text()
            assert "AUTONOMOUS_MODE" in content, "AUTONOMOUS_MODE 항목 없음"
