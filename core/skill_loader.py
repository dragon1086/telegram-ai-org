"""스킬 로더 — organizations.yaml의 preferred_skills를 읽어 스킬 내용을 반환."""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"
ORGS_FILE = PROJECT_ROOT / "organizations.yaml"

_orgs_cache: list[dict] | None = None


_yaml_data_cache: dict | None = None


def _load_yaml_data() -> dict:
    global _yaml_data_cache
    if _yaml_data_cache is not None:
        return _yaml_data_cache
    try:
        _yaml_data_cache = yaml.safe_load(ORGS_FILE.read_text()) or {}
    except Exception as e:
        logger.warning(f"organizations.yaml 로드 실패: {e}")
        _yaml_data_cache = {}
    return _yaml_data_cache


def _load_orgs() -> list[dict]:
    global _orgs_cache
    if _orgs_cache is not None:
        return _orgs_cache
    _orgs_cache = _load_yaml_data().get("organizations", [])
    return _orgs_cache


def get_common_skills() -> list[str]:
    """organizations.yaml 최상위 common_skills 반환."""
    return _load_yaml_data().get("common_skills", [])


def get_preferred_skills(org_id: str) -> list[str]:
    """봇 org_id의 preferred_skills + common_skills 병합 반환 (중복 제거)."""
    per_bot: list[str] = []
    for org in _load_orgs():
        if org.get("id") == org_id:
            per_bot = org.get("team", {}).get("preferred_skills", [])
            break
    common = get_common_skills()
    # common 먼저, per_bot 뒤에 — 중복 제거
    seen: set[str] = set()
    merged: list[str] = []
    for name in common + per_bot:
        if name not in seen:
            seen.add(name)
            merged.append(name)
    return merged


def load_skill_content(skill_name: str) -> str | None:
    """스킬 디렉토리에서 SKILL.md의 본문(frontmatter 제외) 반환."""
    skill_file = SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_file.exists():
        return None
    try:
        text = skill_file.read_text()
        # frontmatter 제거
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                return parts[2].strip()
        return text.strip()
    except Exception as e:
        logger.warning(f"스킬 {skill_name} 로드 실패: {e}")
        return None


def build_skill_context(org_id: str, task_description: str = "") -> str:
    """봇에 매핑된 스킬들의 요약을 시스템 프롬프트용 텍스트로 반환.

    전체 스킬 내용이 아닌, 스킬명 + 핵심 설명만 주입하여
    컨텍스트 부담을 최소화한다.
    """
    skill_names = get_preferred_skills(org_id)
    if not skill_names:
        return ""

    lines = ["## 사용 가능한 스킬"]
    for name in skill_names:
        skill_file = SKILLS_DIR / name / "SKILL.md"
        if not skill_file.exists():
            continue
        try:
            text = skill_file.read_text()
            # frontmatter에서 description 추출
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    fm = yaml.safe_load(parts[1])
                    desc = fm.get("description", name)
                    lines.append(f"- **/{name}**: {desc}")
        except Exception:
            lines.append(f"- **/{name}**")

    if len(lines) == 1:  # 헤더만 있음
        return ""
    lines.append("")
    lines.append("태스크와 관련된 스킬이 있으면 해당 스킬의 절차를 따라 실행하라.")
    return "\n".join(lines)


def invalidate_cache() -> None:
    """organizations.yaml 캐시 무효화 (핫 리로드 용)."""
    global _orgs_cache, _yaml_data_cache
    _orgs_cache = None
    _yaml_data_cache = None
