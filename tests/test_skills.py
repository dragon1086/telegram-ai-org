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


class TestUS201GotchasFiles:
    """US-201: 9개 스킬에 gotchas.md가 추가되었는지 확인"""

    ALL_SKILLS = [
        "brainstorming-auto", "design-critique", "engineering-review",
        "growth-analysis", "harness-audit", "loop-checkpoint",
        "performance-eval", "pm-discussion", "retro",
        # 기존 gotchas.md 보유 스킬
        "quality-gate", "pm-task-dispatch", "autonomous-skill-proxy", "weekly-review"
    ]

    @pytest.fixture
    def skills_dir(self):
        return Path(__file__).parent.parent / "skills"

    def test_all_skills_have_gotchas(self, skills_dir):
        """13개 스킬 모두 gotchas.md 존재 확인"""
        missing = []
        for skill_name in self.ALL_SKILLS:
            gotchas_file = skills_dir / skill_name / "gotchas.md"
            if not gotchas_file.exists():
                missing.append(skill_name)
        assert not missing, f"gotchas.md 없는 스킬: {missing}"

    def test_gotchas_have_minimum_content(self, skills_dir):
        """각 gotchas.md에 최소 3개 gotcha 포함 확인 (## 헤딩 기준)"""
        for skill_name in self.ALL_SKILLS:
            gotchas_file = skills_dir / skill_name / "gotchas.md"
            if gotchas_file.exists():
                content = gotchas_file.read_text()
                # "## Gotcha" 형식 또는 "## 1." 같은 번호 헤딩 모두 허용
                gotcha_count = content.count("## Gotcha")
                if gotcha_count == 0:
                    # 번호 기반 헤딩 ("## 1.", "## 2." 등) 카운트
                    import re
                    gotcha_count = len(re.findall(r"^## \d+[\.:]", content, re.MULTILINE))
                assert gotcha_count >= 3, \
                    f"{skill_name}/gotchas.md에 Gotcha가 {gotcha_count}개뿐 (최소 3개 필요)"


class TestUS204SaveLogScript:
    """US-204: weekly-review save-log.py 존재 및 기능 확인"""

    @pytest.fixture
    def skills_dir(self):
        return Path(__file__).parent.parent / "skills"

    def test_save_log_script_exists(self, skills_dir):
        """save-log.py 파일 존재 확인"""
        script = skills_dir / "weekly-review" / "scripts" / "save-log.py"
        assert script.exists(), "skills/weekly-review/scripts/save-log.py 없음"

    def test_save_log_is_executable(self, skills_dir):
        """save-log.py 실행 권한 확인"""
        import os
        script = skills_dir / "weekly-review" / "scripts" / "save-log.py"
        if script.exists():
            assert os.access(script, os.X_OK), "save-log.py가 실행 가능하지 않음"

    def test_save_log_uses_flock(self, skills_dir):
        """save-log.py에 fcntl.flock 사용 확인"""
        script = skills_dir / "weekly-review" / "scripts" / "save-log.py"
        if script.exists():
            content = script.read_text()
            assert "flock" in content, "save-log.py에 flock 사용 없음 (race condition 위험)"

    def test_save_log_creates_jsonl(self, skills_dir, tmp_path):
        """save-log.py 실행 시 JSONL 파일 생성 확인"""
        import subprocess, json
        script = skills_dir / "weekly-review" / "scripts" / "save-log.py"
        if not script.exists():
            return

        test_data = json.dumps({"week": "2026-W99", "test": True})
        result = subprocess.run(
            [".venv/bin/python", str(script), test_data],
            cwd=skills_dir.parent,  # 프로젝트 루트
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"save-log.py 실행 실패: {result.stderr}"
        assert "OK" in result.stdout or "appended" in result.stdout.lower(), \
            f"예상 출력 없음: {result.stdout}"


class TestUS202QualityGateIntegration:
    """US-202: quality-gate 지침 강화 확인"""

    @pytest.fixture
    def skills_dir(self):
        return Path(__file__).parent.parent / "skills"

    def test_quality_gate_skill_has_when_to_run_first(self, skills_dir):
        """quality-gate/SKILL.md에 'When to Run First' 섹션 존재"""
        skill_md = skills_dir / "quality-gate" / "SKILL.md"
        content = skill_md.read_text()
        assert "When to Run First" in content or "Prerequisites" in content, \
            "quality-gate/SKILL.md에 실행 시점 가이드 없음"

    def test_pm_task_dispatch_references_quality_gate(self, skills_dir):
        """pm-task-dispatch/SKILL.md에 quality-gate 선행 실행 언급"""
        skill_md = skills_dir / "pm-task-dispatch" / "SKILL.md"
        content = skill_md.read_text()
        assert "quality-gate" in content.lower(), \
            "pm-task-dispatch/SKILL.md에 quality-gate 언급 없음"


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
