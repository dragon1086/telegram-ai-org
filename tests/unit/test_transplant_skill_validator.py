"""Unit tests for core/skill_validator.py (P0-2: Structured Skill Validation).

Tests cover:
  - validate_skill_file with valid, missing, and malformed files.
  - Edge cases: empty body, no frontmatter, missing required keys.
  - audit_report formatting.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from core.skill_validator import (
    audit_report,
    validate_all_skills,
    validate_skill,
    validate_skill_file,
)

# ---------------------------------------------------------------------------
# Fixtures — write temp skill files
# ---------------------------------------------------------------------------


@pytest.fixture
def skills_root(tmp_path: Path) -> Path:
    return tmp_path / "skills"


def _make_skill(skills_root: Path, name: str, content: str) -> Path:
    skill_dir = skills_root / name
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(content, encoding="utf-8")
    return skill_file


VALID_SKILL_CONTENT = textwrap.dedent("""\
    ---
    name: my-skill
    description: "Does something useful for testing"
    allowed-tools: Bash, Read
    ---

    # My Skill

    ## Triggers
    - keyword: "test", "my-skill"

    ## Steps
    1. Do step one
    2. Do step two

    ## Output Format
    Returns a summary string.
""")


# ---------------------------------------------------------------------------
# validate_skill_file tests
# ---------------------------------------------------------------------------


class TestValidateSkillFile:
    def test_valid_skill_passes(self, skills_root):
        path = _make_skill(skills_root, "good-skill", VALID_SKILL_CONTENT)
        result = validate_skill_file(path)
        assert result.is_valid, result.errors

    def test_missing_file_fails(self, tmp_path):
        path = tmp_path / "nonexistent" / "SKILL.md"
        result = validate_skill_file(path)
        assert not result.is_valid
        assert any("not found" in i.message.lower() for i in result.errors)

    def test_empty_file_fails(self, skills_root):
        path = _make_skill(skills_root, "empty", "")
        result = validate_skill_file(path)
        assert not result.is_valid

    def test_no_frontmatter_fails(self, skills_root):
        content = "# Just a markdown header\n\nSome body text.\n"
        path = _make_skill(skills_root, "no-fm", content)
        result = validate_skill_file(path)
        assert not result.is_valid
        assert any("frontmatter" in i.message.lower() for i in result.errors)

    def test_missing_required_frontmatter_key(self, skills_root):
        content = textwrap.dedent("""\
            ---
            name: partial
            description: "ok"
            ---

            ## Steps
            - step 1
        """)
        path = _make_skill(skills_root, "partial-fm", content)
        result = validate_skill_file(path)
        assert not result.is_valid
        assert any("allowed-tools" in i.message for i in result.errors)

    def test_missing_name_in_frontmatter(self, skills_root):
        content = textwrap.dedent("""\
            ---
            description: "has desc"
            allowed-tools: Bash
            ---

            ## Steps
            Do something.
        """)
        path = _make_skill(skills_root, "no-name", content)
        result = validate_skill_file(path)
        assert not result.is_valid
        assert any("name" in i.message for i in result.errors)

    def test_short_description_is_warning(self, skills_root):
        content = textwrap.dedent("""\
            ---
            name: short-desc
            description: "ok"
            allowed-tools: Bash
            ---

            ## Steps
            Do something.

            ## Output
            Result.
        """)
        path = _make_skill(skills_root, "short-desc", content)
        result = validate_skill_file(path)
        assert any(i.level == "warning" and "short" in i.message.lower() for i in result.warnings)

    def test_no_procedure_section_is_warning(self, skills_root):
        content = textwrap.dedent("""\
            ---
            name: no-steps
            description: "No steps section here at all"
            allowed-tools: Bash
            ---

            Some random text without any procedure.

            ## Output
            Result.
        """)
        path = _make_skill(skills_root, "no-steps", content)
        result = validate_skill_file(path)
        assert any(i.level == "warning" and "trigger" in i.message.lower() for i in result.warnings)

    def test_no_output_section_is_warning(self, skills_root):
        content = textwrap.dedent("""\
            ---
            name: no-output
            description: "Has steps but no output section"
            allowed-tools: Bash
            ---

            ## Triggers
            - test

            ## Steps
            - do something
        """)
        path = _make_skill(skills_root, "no-output", content)
        result = validate_skill_file(path)
        assert any(i.level == "warning" and "output" in i.message.lower() for i in result.warnings)


# ---------------------------------------------------------------------------
# validate_skill tests
# ---------------------------------------------------------------------------


class TestValidateSkill:
    def test_named_skill(self, skills_root):
        _make_skill(skills_root, "named", VALID_SKILL_CONTENT)
        result = validate_skill("named", skills_root=skills_root)
        assert result.is_valid

    def test_missing_skill_returns_error(self, skills_root):
        result = validate_skill("ghost", skills_root=skills_root)
        assert not result.is_valid


# ---------------------------------------------------------------------------
# validate_all_skills tests
# ---------------------------------------------------------------------------


class TestValidateAllSkills:
    def test_empty_root(self, tmp_path):
        results = validate_all_skills(skills_root=tmp_path)
        assert results == []

    def test_mixed_skills(self, skills_root):
        _make_skill(skills_root, "good", VALID_SKILL_CONTENT)
        bad_dir = skills_root / "bad"
        bad_dir.mkdir()
        (bad_dir / "SKILL.md").write_text("---\nname: x\n---\nbody", encoding="utf-8")
        # dir without SKILL.md
        (skills_root / "naked-dir").mkdir()

        results = validate_all_skills(skills_root=skills_root)
        names = {r.skill_name for r in results}
        assert "good" in names
        assert "bad" in names
        assert "naked-dir" in names

    def test_nonexistent_root(self, tmp_path):
        results = validate_all_skills(skills_root=tmp_path / "does_not_exist")
        assert results == []


# ---------------------------------------------------------------------------
# audit_report tests
# ---------------------------------------------------------------------------


class TestAuditReport:
    def test_empty_results(self):
        report = audit_report([])
        assert "No skills" in report

    def test_report_with_pass_and_fail(self, skills_root):
        _make_skill(skills_root, "good", VALID_SKILL_CONTENT)
        _make_skill(skills_root, "empty-skill", "")
        results = validate_all_skills(skills_root=skills_root)
        report = audit_report(results)
        assert "PASS" in report
        assert "FAIL" in report
