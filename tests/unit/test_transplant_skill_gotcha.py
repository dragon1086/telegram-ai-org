"""Unit tests for core/skill_gotcha_manager.py (P1-2: Skill Gotcha Auto-Learning).

Tests cover:
  - append_gotcha: creates new file, appends entries, skips duplicates.
  - list_gotchas: reads existing entries.
  - Edge cases: invalid skill_name, empty title, missing skill dir.
"""
from __future__ import annotations

from core.skill_gotcha_manager import (
    GotchaEntry,
    append_gotcha,
    get_gotchas_text,
    list_gotchas,
    list_skills_with_gotchas,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(title: str = "Test error", index: int = 0) -> GotchaEntry:
    return GotchaEntry(
        title=title,
        situation=f"When doing task {index}",
        symptom="Crashes with RuntimeError",
        solution="Check the import order",
        added_at="2026-03-29",
    )


# ---------------------------------------------------------------------------
# append_gotcha tests
# ---------------------------------------------------------------------------


class TestAppendGotcha:
    def test_creates_gotchas_file(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        entry = _make_entry("First error")
        result = append_gotcha("my-skill", entry, skills_root=tmp_path)
        assert result is True
        assert (skill_dir / "gotchas.md").exists()

    def test_creates_skill_dir_if_missing(self, tmp_path):
        # skill dir does not exist — should still work
        entry = _make_entry("No dir error")
        result = append_gotcha("nonexistent-skill", entry, skills_root=tmp_path)
        assert result is True
        assert (tmp_path / "nonexistent-skill" / "gotchas.md").exists()

    def test_appended_content_contains_title(self, tmp_path):
        skill_dir = tmp_path / "s"
        skill_dir.mkdir()
        entry = _make_entry("My unique error title")
        append_gotcha("s", entry, skills_root=tmp_path)
        text = (skill_dir / "gotchas.md").read_text()
        assert "My unique error title" in text

    def test_duplicate_title_skipped(self, tmp_path):
        skill_dir = tmp_path / "dup-skill"
        skill_dir.mkdir()
        entry = _make_entry("Duplicate error")
        append_gotcha("dup-skill", entry, skills_root=tmp_path)
        result = append_gotcha("dup-skill", entry, skills_root=tmp_path)
        assert result is False
        # Only one entry should exist
        text = (skill_dir / "gotchas.md").read_text()
        assert text.count("## Gotcha") == 1

    def test_sequential_indices(self, tmp_path):
        skill_dir = tmp_path / "idx-skill"
        skill_dir.mkdir()
        for i in range(3):
            append_gotcha("idx-skill", _make_entry(f"Error {i}", i), skills_root=tmp_path)
        text = (skill_dir / "gotchas.md").read_text()
        assert "## Gotcha 1:" in text
        assert "## Gotcha 2:" in text
        assert "## Gotcha 3:" in text

    def test_invalid_skill_name_returns_false(self, tmp_path):
        entry = _make_entry("e")
        assert append_gotcha("", entry, skills_root=tmp_path) is False
        assert append_gotcha(None, entry, skills_root=tmp_path) is False  # type: ignore

    def test_empty_title_returns_false(self, tmp_path):
        skill_dir = tmp_path / "titled-skill"
        skill_dir.mkdir()
        entry = GotchaEntry(title="", situation="s", symptom="x", solution="y")
        assert append_gotcha("titled-skill", entry, skills_root=tmp_path) is False

    def test_whitespace_only_title_returns_false(self, tmp_path):
        skill_dir = tmp_path / "ws-skill"
        skill_dir.mkdir()
        entry = GotchaEntry(title="   ", situation="s", symptom="x", solution="y")
        assert append_gotcha("ws-skill", entry, skills_root=tmp_path) is False

    def test_header_added_on_first_entry(self, tmp_path):
        skill_dir = tmp_path / "header-skill"
        skill_dir.mkdir()
        append_gotcha("header-skill", _make_entry("e"), skills_root=tmp_path)
        text = (skill_dir / "gotchas.md").read_text()
        assert "# Gotchas" in text


# ---------------------------------------------------------------------------
# list_gotchas tests
# ---------------------------------------------------------------------------


class TestListGotchas:
    def test_empty_for_missing_skill(self, tmp_path):
        assert list_gotchas("ghost", skills_root=tmp_path) == []

    def test_lists_titles(self, tmp_path):
        skill_dir = tmp_path / "list-skill"
        skill_dir.mkdir()
        for i in range(3):
            append_gotcha("list-skill", _make_entry(f"Title {i}"), skills_root=tmp_path)
        titles = list_gotchas("list-skill", skills_root=tmp_path)
        assert len(titles) == 3
        assert "Title 0" in titles
        assert "Title 1" in titles
        assert "Title 2" in titles

    def test_empty_skill_name(self, tmp_path):
        assert list_gotchas("", skills_root=tmp_path) == []


# ---------------------------------------------------------------------------
# get_gotchas_text tests
# ---------------------------------------------------------------------------


class TestGetGotchasText:
    def test_empty_for_missing(self, tmp_path):
        assert get_gotchas_text("missing", skills_root=tmp_path) == ""

    def test_returns_content(self, tmp_path):
        skill_dir = tmp_path / "text-skill"
        skill_dir.mkdir()
        append_gotcha("text-skill", _make_entry("Read error"), skills_root=tmp_path)
        text = get_gotchas_text("text-skill", skills_root=tmp_path)
        assert "Read error" in text


# ---------------------------------------------------------------------------
# list_skills_with_gotchas tests
# ---------------------------------------------------------------------------


class TestListSkillsWithGotchas:
    def test_empty_root(self, tmp_path):
        assert list_skills_with_gotchas(skills_root=tmp_path) == []

    def test_only_skills_with_nonempty_gotchas(self, tmp_path):
        # Skill with gotcha
        s1 = tmp_path / "skill-with-gotcha"
        s1.mkdir()
        append_gotcha("skill-with-gotcha", _make_entry("e"), skills_root=tmp_path)

        # Skill with empty gotchas.md
        s2 = tmp_path / "skill-empty-gotcha"
        s2.mkdir()
        (s2 / "gotchas.md").write_text("")

        # Skill without gotchas.md
        s3 = tmp_path / "skill-no-gotcha"
        s3.mkdir()

        result = list_skills_with_gotchas(skills_root=tmp_path)
        assert "skill-with-gotcha" in result
        assert "skill-empty-gotcha" not in result
        assert "skill-no-gotcha" not in result
