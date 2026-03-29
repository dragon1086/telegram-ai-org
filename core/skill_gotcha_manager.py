"""Skill Gotcha Manager — manages gotcha entries for skills.

Inspired by harness gotchas.md pattern.  Provides structured, programmatic
access to per-skill gotcha files so that the error-gotcha skill and automated
tooling can append/read/list gotcha entries consistently.

Design notes:
  - gotchas.md is stored alongside SKILL.md in each skill directory.
  - Auto-append logic is idempotent: identical entries are not duplicated.
  - No modification to existing skill files unless explicitly called.
  - Type hints throughout.

Self-review:
  ① Logic: append_gotcha() reads existing content, checks for duplicates by
     title, then appends — correct.
  ② Edge cases: missing skills dir, missing gotchas.md (auto-created),
     duplicate title, empty/None inputs.
  ③ Compat: no existing code changed; new standalone module.
  ④ Global state: none — functions operate on filesystem only.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

SKILLS_ROOT = Path(__file__).parent.parent / "skills"

_GOTCHA_HEADER = "# Gotchas\n\n> 자동 추가된 재발 방지 항목 (error-gotcha 스킬 / skill_gotcha_manager.py)\n\n"

_ENTRY_TITLE_RE = re.compile(r"^##\s+Gotcha\s+\d+:\s+(.+)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class GotchaEntry:
    """A single gotcha entry.

    Attributes:
        title: Short title (e.g. "NameError in session_manager import").
        situation: When/how the error occurs.
        symptom: What the user/system observes.
        solution: Concrete action to prevent recurrence.
        added_at: ISO date string of when this entry was added.
    """

    title: str
    situation: str
    symptom: str
    solution: str
    added_at: str = field(default_factory=lambda: date.today().isoformat())

    def to_markdown(self, index: int) -> str:
        """Render the entry as a gotchas.md markdown section."""
        return (
            f"## Gotcha {index}: {self.title}\n"
            f"**상황**: {self.situation}\n"
            f"**증상**: {self.symptom}\n"
            f"**해결**: {self.solution}\n"
            f"**추가일**: {self.added_at}\n"
        )


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def _gotchas_path(skill_name: str, skills_root: Optional[Path] = None) -> Path:
    root = skills_root or SKILLS_ROOT
    return root / skill_name / "gotchas.md"


def _load_gotchas_text(skill_name: str, skills_root: Optional[Path] = None) -> str:
    """Return the current gotchas.md content, or empty string if absent."""
    path = _gotchas_path(skill_name, skills_root)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("skill_gotcha_manager: cannot read %s: %s", path, exc)
        return ""


def _existing_titles(text: str) -> set[str]:
    """Extract existing gotcha titles from gotchas.md content."""
    return {m.group(1).strip() for m in _ENTRY_TITLE_RE.finditer(text)}


def _next_index(text: str) -> int:
    """Return the next sequential gotcha index (1-based)."""
    matches = list(re.finditer(r"^##\s+Gotcha\s+(\d+):", text, re.MULTILINE))
    if not matches:
        return 1
    last_idx = max(int(m.group(1)) for m in matches)
    return last_idx + 1


def append_gotcha(
    skill_name: str,
    entry: GotchaEntry,
    skills_root: Optional[Path] = None,
) -> bool:
    """Append *entry* to the gotchas.md file for *skill_name*.

    If the gotchas.md file does not exist it is created.
    Entries with a duplicate title are silently skipped (idempotent).

    Args:
        skill_name: Directory name under skills/ (e.g. "engineering-review").
        entry: The GotchaEntry to append.
        skills_root: Override default skills root.

    Returns:
        True if appended, False if skipped (duplicate or error).

    Edge cases:
        - skill_name is empty/None → logs warning, returns False.
        - entry.title is empty → logs warning, returns False.
        - Skill directory does not exist → creates gotchas.md anyway (loose coupling).
    """
    if not skill_name or not isinstance(skill_name, str):
        logger.warning("append_gotcha: invalid skill_name %r — skipped", skill_name)
        return False
    if not entry.title or not entry.title.strip():
        logger.warning("append_gotcha: empty entry title — skipped")
        return False

    path = _gotchas_path(skill_name, skills_root)
    existing_text = _load_gotchas_text(skill_name, skills_root)

    # Duplicate detection
    if entry.title.strip() in _existing_titles(existing_text):
        logger.debug(
            "append_gotcha: duplicate title '%s' in %s — skipped", entry.title, skill_name
        )
        return False

    idx = _next_index(existing_text)
    new_block = entry.to_markdown(idx) + "\n"

    if not existing_text:
        content = _GOTCHA_HEADER + new_block
    else:
        content = existing_text.rstrip("\n") + "\n\n" + new_block

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info("append_gotcha: added Gotcha %d to %s/gotchas.md", idx, skill_name)
        return True
    except OSError as exc:
        logger.error("append_gotcha: cannot write %s: %s", path, exc)
        return False


def list_gotchas(
    skill_name: str,
    skills_root: Optional[Path] = None,
) -> List[str]:
    """Return the list of gotcha titles for *skill_name*.

    Args:
        skill_name: Directory name under skills/.
        skills_root: Override default skills root.

    Returns:
        List of title strings, ordered as they appear in gotchas.md.
        Empty list if no gotchas.md exists or skill_name is invalid.
    """
    if not skill_name:
        return []
    text = _load_gotchas_text(skill_name, skills_root)
    return [m.group(1).strip() for m in _ENTRY_TITLE_RE.finditer(text)]


def get_gotchas_text(
    skill_name: str,
    skills_root: Optional[Path] = None,
) -> str:
    """Return the raw gotchas.md content for *skill_name*, or empty string."""
    if not skill_name:
        return ""
    return _load_gotchas_text(skill_name, skills_root)


def list_skills_with_gotchas(skills_root: Optional[Path] = None) -> List[str]:
    """Return skill names that have a non-empty gotchas.md file.

    Args:
        skills_root: Override default skills root.

    Returns:
        Sorted list of skill directory names.
    """
    root = skills_root or SKILLS_ROOT
    if not root.exists():
        return []
    return sorted(
        d.name
        for d in root.iterdir()
        if d.is_dir() and (d / "gotchas.md").exists() and (d / "gotchas.md").stat().st_size > 0
    )
