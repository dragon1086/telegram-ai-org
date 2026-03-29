"""Skill Validator — validates skill SKILL.md files for required structure.

Inspired by harness skill quality checklist patterns.
Standalone module; does NOT modify skill files or global state.

Feature: no feature flag needed (pure read-only validation).
         Can be called from CI, harness-audit skill, or interactively.

Required fields validated:
  - YAML frontmatter with: name, description, allowed-tools
  - Markdown body with at least one of: triggers section or ## steps header
  - Output format section (## 출력 or ## Output)

Self-review:
  ① Logic: parses frontmatter via split("---"), checks required keys — correct.
  ② Edge cases: missing file, empty file, malformed YAML, missing frontmatter.
  ③ Compat: no existing interfaces touched; new standalone module.
  ④ Global state: none; all functions are pure/read-only.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKILLS_ROOT = Path(__file__).parent.parent / "skills"

# Frontmatter keys that every skill MUST have.
REQUIRED_FRONTMATTER_KEYS: List[str] = ["name", "description", "allowed-tools"]

# At least one of these markdown section patterns must appear in the body.
REQUIRED_BODY_PATTERNS: List[re.Pattern] = [
    re.compile(r"(?i)^#{1,3}\s+(step|단계|procedure|실행)", re.MULTILINE),
    re.compile(r"(?i)trigger", re.MULTILINE),
    re.compile(r"(?i)^#{1,3}\s+(trigger|트리거)", re.MULTILINE),
]

# Output format section pattern.
OUTPUT_SECTION_PATTERN = re.compile(
    r"(?i)^#{1,3}\s+(출력|output|결과|result)", re.MULTILINE
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ValidationIssue:
    """A single validation issue for a skill file."""

    level: str  # "error" | "warning"
    message: str


@dataclass
class SkillValidationResult:
    """Aggregated result of validating one skill."""

    skill_name: str
    skill_path: Path
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True if there are no errors (warnings are allowed)."""
        return not any(i.level == "error" for i in self.issues)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.level == "warning"]

    def summary(self) -> str:
        status = "PASS" if self.is_valid else "FAIL"
        parts = [f"[{status}] {self.skill_name}"]
        for issue in self.issues:
            parts.append(f"  [{issue.level.upper()}] {issue.message}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Core validation logic
# ---------------------------------------------------------------------------


def _parse_frontmatter(text: str) -> tuple[Optional[Dict[str, str]], str]:
    """Split SKILL.md content into frontmatter dict and body text.

    Returns:
        (frontmatter_dict_or_None, body_text)
    """
    if not text.startswith("---"):
        return None, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        # Malformed: opening --- but no closing ---
        return None, text

    raw_fm = parts[1].strip()
    body = parts[2].strip()

    # Minimal YAML key:value parsing (avoids importing yaml for this simple case)
    fm: Dict[str, str] = {}
    for line in raw_fm.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip().strip('"').strip("'")

    return fm, body


def validate_skill_file(skill_path: Path) -> SkillValidationResult:
    """Validate a single SKILL.md file.

    Args:
        skill_path: Path to the SKILL.md file.

    Returns:
        SkillValidationResult with any discovered issues.
    """
    skill_name = skill_path.parent.name if skill_path.name == "SKILL.md" else skill_path.stem
    result = SkillValidationResult(skill_name=skill_name, skill_path=skill_path)

    # ── File existence ───────────────────────────────────────────────────────
    if not skill_path.exists():
        result.issues.append(ValidationIssue("error", f"File not found: {skill_path}"))
        return result

    try:
        text = skill_path.read_text(encoding="utf-8")
    except OSError as exc:
        result.issues.append(ValidationIssue("error", f"Cannot read file: {exc}"))
        return result

    if not text.strip():
        result.issues.append(ValidationIssue("error", "File is empty"))
        return result

    # ── Frontmatter ──────────────────────────────────────────────────────────
    frontmatter, body = _parse_frontmatter(text)

    if frontmatter is None:
        result.issues.append(
            ValidationIssue("error", "Missing YAML frontmatter (file must start with ---)")
        )
    else:
        for key in REQUIRED_FRONTMATTER_KEYS:
            if key not in frontmatter or not frontmatter[key]:
                result.issues.append(
                    ValidationIssue("error", f"Frontmatter missing required key: '{key}'")
                )

        # Warn if description is suspiciously short
        desc = frontmatter.get("description", "")
        if desc and len(desc) < 10:
            result.issues.append(
                ValidationIssue("warning", f"Description too short ({len(desc)} chars): '{desc}'")
            )

    # ── Body content ─────────────────────────────────────────────────────────
    if not body:
        result.issues.append(ValidationIssue("error", "Skill body (after frontmatter) is empty"))
        return result

    # Check for at least one procedure/trigger pattern
    has_procedure = any(pat.search(body) for pat in REQUIRED_BODY_PATTERNS)
    if not has_procedure:
        result.issues.append(
            ValidationIssue(
                "warning",
                "No trigger/step/procedure section found. Add '## Steps' or '## Triggers'.",
            )
        )

    # Check for output format section
    if not OUTPUT_SECTION_PATTERN.search(body):
        result.issues.append(
            ValidationIssue(
                "warning",
                "No output format section found. Consider adding '## Output' or '## 출력 형식'.",
            )
        )

    return result


def validate_skill(skill_name: str, skills_root: Optional[Path] = None) -> SkillValidationResult:
    """Validate a named skill under the skills root directory.

    Args:
        skill_name: Directory name under skills/ (e.g. "harness-audit").
        skills_root: Override the default skills root.

    Returns:
        SkillValidationResult.
    """
    root = skills_root or SKILLS_ROOT
    skill_path = root / skill_name / "SKILL.md"
    return validate_skill_file(skill_path)


def validate_all_skills(skills_root: Optional[Path] = None) -> List[SkillValidationResult]:
    """Validate all skills found under the skills root.

    Args:
        skills_root: Override the default skills root.

    Returns:
        List of SkillValidationResult, one per skill directory that contains SKILL.md.
    """
    root = skills_root or SKILLS_ROOT
    results: List[SkillValidationResult] = []

    if not root.exists():
        logger.warning("validate_all_skills: skills root not found: %s", root)
        return results

    for skill_dir in sorted(root.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists():
            results.append(validate_skill_file(skill_file))
        else:
            # Directory without SKILL.md is a warning
            results.append(
                SkillValidationResult(
                    skill_name=skill_dir.name,
                    skill_path=skill_file,
                    issues=[ValidationIssue("warning", "Directory has no SKILL.md")],
                )
            )

    return results


def audit_report(results: List[SkillValidationResult]) -> str:
    """Format a human-readable audit report from a list of validation results.

    Args:
        results: Output of validate_all_skills() or a subset.

    Returns:
        Multi-line string report.
    """
    if not results:
        return "No skills found to validate."

    passing = [r for r in results if r.is_valid]
    failing = [r for r in results if not r.is_valid]

    lines: List[str] = [
        "=== Skill Validation Report ===",
        f"Total: {len(results)}  |  Pass: {len(passing)}  |  Fail: {len(failing)}",
        "",
    ]

    if failing:
        lines.append("--- Failures ---")
        for r in failing:
            lines.append(r.summary())
            lines.append("")

    if passing:
        lines.append("--- Passing ---")
        for r in passing:
            lines.append(f"[PASS] {r.skill_name}")
        lines.append("")

    return "\n".join(lines)
