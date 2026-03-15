"""Registration helpers for canonical bot setup."""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core.orchestration_config import load_orchestration_config


DEFAULT_ORCHESTRATION_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "runtime": {
        "docs_root": "docs/orchestration-v2",
        "run_state_root": ".ai-org/runs",
    },
    "phase_policies": {
        "default": {
            "order": ["intake", "planning", "design", "implementation", "verification", "feedback"],
            "required_documents": {
                "intake": ["request-brief.md"],
                "planning": ["plan.md"],
                "design": ["design.md"],
                "implementation": ["implementation.md"],
                "verification": ["verification.md"],
                "feedback": ["feedback.md"],
            },
            "announce_plan_on_start": True,
            "announce_progress": True,
            "require_goal_feedback": True,
        },
    },
    "backend_policies": {
        "orchestrator_default": {
            "direct_reply": "resume_session",
            "local_execution": "resume_session",
            "delegated_execution": "tmux_batch",
            "long_running": "tmux_batch",
        },
        "specialist_default": {
            "direct_reply": "ephemeral",
            "local_execution": "resume_session",
            "delegated_execution": "tmux_batch",
            "long_running": "tmux_batch",
        },
    },
    "session_policies": {
        "orchestrator_default": {
            "max_messages_before_compact": 80,
            "warn_threshold_percent": 70,
            "compact_threshold_percent": 80,
            "stale_after_minutes": 180,
        },
        "specialist_default": {
            "max_messages_before_compact": 50,
            "warn_threshold_percent": 70,
            "compact_threshold_percent": 80,
            "stale_after_minutes": 180,
        },
    },
    "team_profiles": {
        "global_orchestrator": {
            "preferred_engine": "codex",
            "fallback_engine": "claude-code",
            "execution_mode": "sequential",
            "preferred_agents": ["planner", "architect", "writer"],
            "preferred_skills": [],
            "avoid_agents": [],
            "max_team_size": 3,
            "guidance": "전체 조율과 사용자 응답 품질을 우선한다.",
        },
        "research_strategy": {
            "preferred_engine": "codex",
            "fallback_engine": "claude-code",
            "execution_mode": "sequential",
            "preferred_agents": ["analyst", "writer"],
            "preferred_skills": [],
            "avoid_agents": [],
            "max_team_size": 3,
            "guidance": "출처와 비교 기준을 명확히 남긴다.",
        },
        "engineering_delivery": {
            "preferred_engine": "codex",
            "fallback_engine": "claude-code",
            "execution_mode": "sequential",
            "preferred_agents": ["executor", "debugger"],
            "preferred_skills": [],
            "avoid_agents": [],
            "max_team_size": 3,
            "guidance": "구현과 검증을 함께 수행한다.",
        },
        "design_strategy": {
            "preferred_engine": "claude-code",
            "fallback_engine": "codex",
            "execution_mode": "sequential",
            "preferred_agents": ["designer", "writer"],
            "preferred_skills": [],
            "avoid_agents": [],
            "max_team_size": 3,
            "guidance": "사용자 경험과 전달 명확성을 우선한다.",
        },
        "product_strategy": {
            "preferred_engine": "claude-code",
            "fallback_engine": "codex",
            "execution_mode": "sequential",
            "preferred_agents": ["planner", "analyst"],
            "preferred_skills": [],
            "avoid_agents": [],
            "max_team_size": 3,
            "guidance": "요구사항과 우선순위를 구조화한다.",
        },
        "growth_strategy": {
            "preferred_engine": "claude-code",
            "fallback_engine": "codex",
            "execution_mode": "sequential",
            "preferred_agents": ["analyst", "writer"],
            "preferred_skills": [],
            "avoid_agents": [],
            "max_team_size": 3,
            "guidance": "가설, 지표, 메시지 전달을 명확히 한다.",
        },
        "ops_delivery": {
            "preferred_engine": "codex",
            "fallback_engine": "claude-code",
            "execution_mode": "sequential",
            "preferred_agents": ["executor", "verifier"],
            "preferred_skills": [],
            "avoid_agents": [],
            "max_team_size": 3,
            "guidance": "운영 안정성과 검증 체크리스트를 우선한다.",
        },
    },
    "verification_profiles": {
        "orchestrator_default": {
            "require_plan": True,
            "require_tests": True,
            "require_status_snapshot": True,
            "require_feedback": True,
        },
        "specialist_default": {
            "require_plan": True,
            "require_tests": True,
            "require_status_snapshot": True,
            "require_feedback": True,
        },
    },
    "legacy_exports": {
        "bots_dir": "bots",
    },
}


@dataclass
class SetupIdentity:
    role: str
    specialties: list[str]
    direction: str
    dept_name: str
    display_name: str
    instruction: str
    guidance: str


def _slug_to_label(org_id: str) -> str:
    return org_id.replace("_bot", "").replace("_", " ").strip().title()


def profile_bundle_for_org(org_id: str) -> dict[str, Any]:
    lowered = org_id.lower()
    if lowered in {"global", "aiorg_pm_bot"} or lowered.endswith("_pm_bot"):
        return {
            "kind": "orchestrator",
            "team_profile": "global_orchestrator",
            "verification_profile": "orchestrator_default",
            "backend_policy": "orchestrator_default",
            "session_policy": "orchestrator_default",
            "can_direct_reply": True,
        }
    if "research" in lowered or "insight" in lowered or "reference" in lowered:
        profile = "research_strategy"
    elif "engineering" in lowered or "dev" in lowered or "code" in lowered:
        profile = "engineering_delivery"
    elif "design" in lowered or "ux" in lowered or "ui" in lowered:
        profile = "design_strategy"
    elif "product" in lowered or "plan" in lowered or "prd" in lowered:
        profile = "product_strategy"
    elif "growth" in lowered or "marketing" in lowered:
        profile = "growth_strategy"
    elif "ops" in lowered or "infra" in lowered:
        profile = "ops_delivery"
    else:
        profile = "research_strategy"
    return {
        "kind": "specialist",
        "team_profile": profile,
        "verification_profile": "specialist_default",
        "backend_policy": "specialist_default",
        "session_policy": "specialist_default",
        "can_direct_reply": False,
    }


def default_identity_for_org(org_id: str) -> SetupIdentity:
    lowered = org_id.lower()
    if "research" in lowered or "insight" in lowered or "reference" in lowered:
        return SetupIdentity(
            role="시장조사/레퍼런스 조사/문서 요약/경쟁사 분석",
            specialties=["시장조사", "레퍼런스조사", "문서요약", "경쟁사분석"],
            direction="출처 기반으로 정리하고 비교 관점을 명확히 제시한다.",
            dept_name="리서치실",
            display_name="Research",
            instruction="시장·레퍼런스·경쟁사 조사 결과를 출처 기반으로 구조화해 정리하세요.",
            guidance="조사 범위, 출처, 비교표, 핵심 인사이트를 반드시 남긴다.",
        )
    if "engineering" in lowered or "dev" in lowered or "code" in lowered:
        return SetupIdentity(
            role="개발/코딩/API 구현/버그 수정",
            specialties=["Python", "API", "버그수정"],
            direction="구현과 검증 결과를 함께 제시하고 불필요한 장황함을 줄인다.",
            dept_name="개발실",
            display_name="Engineering",
            instruction="기술적 관점에서 분석하고 구현 또는 수정 작업을 수행하세요.",
            guidance="항상 테스트와 검증 근거를 남긴다.",
        )
    if "design" in lowered or "ux" in lowered or "ui" in lowered:
        return SetupIdentity(
            role="UX 설계/UI 디자인/프로토타이핑",
            specialties=["UX", "UI", "프로토타입"],
            direction="사용자가 바로 이해할 수 있는 구조와 표현을 우선한다.",
            dept_name="디자인실",
            display_name="Design",
            instruction="사용자 경험과 인터페이스 관점에서 명확한 설계를 제시하세요.",
            guidance="가독성과 설명 구조를 우선한다.",
        )
    if "product" in lowered or "plan" in lowered or "prd" in lowered:
        return SetupIdentity(
            role="제품기획/요구사항 정의/우선순위 정리",
            specialties=["기획", "PRD", "우선순위"],
            direction="요구사항, 가정, 우선순위를 분리해 명확히 설명한다.",
            dept_name="기획실",
            display_name="Product",
            instruction="요구사항과 우선순위를 구조화해 설명하세요.",
            guidance="범위, 목표, 비목표를 구분한다.",
        )
    if "growth" in lowered or "marketing" in lowered:
        return SetupIdentity(
            role="마케팅/성장실험/카피라이팅",
            specialties=["마케팅", "성장실험", "카피"],
            direction="메시지와 지표를 함께 다루고 실험 가설을 명확히 한다.",
            dept_name="성장실",
            display_name="Growth",
            instruction="성장과 마케팅 관점에서 실행 가능한 아이디어를 제시하세요.",
            guidance="가설, 타깃, KPI를 빠뜨리지 않는다.",
        )
    if "ops" in lowered or "infra" in lowered:
        return SetupIdentity(
            role="운영/배포/인프라/모니터링",
            specialties=["운영", "배포", "인프라"],
            direction="안정성, 롤백, 검증 체크리스트를 우선한다.",
            dept_name="운영실",
            display_name="Ops",
            instruction="운영 안정성과 검증 절차를 포함해 설명하세요.",
            guidance="롤백과 모니터링 지점을 같이 남긴다.",
        )
    return SetupIdentity(
        role=f"{_slug_to_label(org_id)} 역할",
        specialties=[],
        direction="사용자가 바로 실행하거나 이해할 수 있는 답을 우선한다.",
        dept_name=_slug_to_label(org_id),
        display_name=_slug_to_label(org_id),
        instruction="요청을 분석하고 처리하세요.",
        guidance="핵심 내용부터 설명하고 필요 시만 부연한다.",
    )


def parse_setup_identity(org_id: str, raw: str) -> SetupIdentity:
    default = default_identity_for_org(org_id)
    text = (raw or "").strip()
    if not text or text.lower() in {"기본", "default", "skip"}:
        return default

    parts = [part.strip() for part in text.split("|")]
    role = parts[0] if len(parts) >= 1 and parts[0] else default.role
    specialties = (
        [item.strip() for item in parts[1].split(",") if item.strip()]
        if len(parts) >= 2 and parts[1]
        else list(default.specialties)
    )
    direction = parts[2] if len(parts) >= 3 and parts[2] else default.direction
    return SetupIdentity(
        role=role,
        specialties=specialties,
        direction=direction,
        dept_name=default.dept_name,
        display_name=default.display_name,
        instruction=default.instruction,
        guidance=default.guidance,
    )


def upsert_runtime_env_var(project_root: Path, key: str, value: str) -> None:
    for path in (project_root / ".env", Path.home() / ".ai-org" / "config.yaml"):
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        new_lines = [line for line in lines if not line.startswith(f"{key}=")]
        new_lines.append(f"{key}={value}")
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _extract_env_name(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    match = re.fullmatch(r"\$\{([^}]+)\}", raw.strip())
    return match.group(1) if match else None


def _deep_merge_missing(target: dict[str, Any], default: dict[str, Any]) -> dict[str, Any]:
    for key, value in default.items():
        if key not in target:
            target[key] = copy.deepcopy(value)
            continue
        if isinstance(target[key], dict) and isinstance(value, dict):
            _deep_merge_missing(target[key], value)
    return target


def ensure_orchestration_config(project_root: Path) -> Path:
    path = project_root / "orchestration.yaml"
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        data = {}
    merged = _deep_merge_missing(data, copy.deepcopy(DEFAULT_ORCHESTRATION_CONFIG))
    path.write_text(yaml.safe_dump(merged, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _canonical_root() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "source_of_truth": {
            "docs_root": "docs/orchestration-v2",
            "orchestration_config": "orchestration.yaml",
        },
        "organizations": [],
    }


def _legacy_org_to_canonical(entry: dict[str, Any]) -> dict[str, Any]:
    org_id = entry.get("id") or entry.get("name")
    bundle = profile_bundle_for_org(org_id)
    identity = default_identity_for_org(org_id)
    token_env = _extract_env_name(entry.get("pm_token"))
    chat_id = entry.get("group_chat_id")
    return {
        "id": org_id,
        "enabled": True,
        "kind": bundle["kind"],
        "description": entry.get("description", f"{org_id} org"),
        "telegram": {
            "username": org_id,
            **({"token_env": token_env} if token_env else {"token": entry.get("pm_token", "")}),
            "chat_id": chat_id,
        },
        "identity": {
            "dept_name": identity.dept_name,
            "display_name": identity.display_name,
            "role": identity.role,
            "specialties": identity.specialties,
            "direction": identity.direction,
            "instruction": identity.instruction,
        },
        "routing": {
            "default_handler": bundle["kind"] == "orchestrator",
            "can_direct_reply": bundle["can_direct_reply"],
            "confidence_threshold": 5,
            "orchestration_mode": "skill_cli",
        },
        "execution": {
            "preferred_engine": entry.get("engine", "claude-code"),
            "fallback_engine": "claude-code",
            "team_profile": bundle["team_profile"],
            "verification_profile": bundle["verification_profile"],
            "phase_policy": "default",
            "backend_policy": bundle["backend_policy"],
            "session_policy": bundle["session_policy"],
        },
        "team": {
            "preferred_agents": [],
            "avoid_agents": [],
            "preferred_skills": [],
            "max_team_size": 3,
            "guidance": identity.guidance,
        },
        "collaboration": {
            "peers": [],
            "announce_plan": True,
            "announce_progress": True,
            "brainstorming_mode": "structured",
        },
    }


def load_canonical_organizations(project_root: Path) -> dict[str, Any]:
    orgs_path = project_root / "organizations.yaml"
    if not orgs_path.exists():
        return _canonical_root()
    data = yaml.safe_load(orgs_path.read_text(encoding="utf-8")) or {}
    root = _canonical_root()
    org_entries = data.get("organizations", [])
    converted: list[dict[str, Any]] = []
    for entry in org_entries:
        if "id" in entry:
            converted.append(entry)
        elif "name" in entry:
            converted.append(_legacy_org_to_canonical(entry))
    root["organizations"] = converted
    if "source_of_truth" in data:
        root["source_of_truth"] = data["source_of_truth"]
    return root


def upsert_org_in_canonical_config(
    project_root: Path,
    *,
    username: str,
    token_env: str,
    chat_id: int,
    engine: str,
    identity: SetupIdentity,
) -> dict[str, Any]:
    ensure_orchestration_config(project_root)
    data = load_canonical_organizations(project_root)
    bundle = profile_bundle_for_org(username)

    org_entry = {
        "id": username,
        "enabled": True,
        "kind": bundle["kind"],
        "description": f"{username} org",
        "telegram": {
            "username": username,
            "token_env": token_env,
            "chat_id": chat_id,
        },
        "identity": {
            "dept_name": identity.dept_name,
            "display_name": identity.display_name,
            "role": identity.role,
            "specialties": list(identity.specialties),
            "direction": identity.direction,
            "instruction": identity.instruction,
        },
        "routing": {
            "default_handler": False,
            "can_direct_reply": bundle["can_direct_reply"],
            "confidence_threshold": 5,
            "orchestration_mode": "skill_cli",
        },
        "execution": {
            "preferred_engine": engine,
            "fallback_engine": "claude-code" if engine != "claude-code" else "codex",
            "team_profile": bundle["team_profile"],
            "verification_profile": bundle["verification_profile"],
            "phase_policy": "default",
            "backend_policy": bundle["backend_policy"],
            "session_policy": bundle["session_policy"],
        },
        "team": {
            "preferred_agents": [],
            "avoid_agents": [],
            "max_team_size": 3,
            "preferred_skills": [],
            "guidance": identity.guidance,
        },
        "collaboration": {
            "peers": [],
            "announce_plan": True,
            "announce_progress": True,
            "brainstorming_mode": "structured",
        },
    }

    orgs = data.setdefault("organizations", [])
    for idx, existing in enumerate(orgs):
        if existing.get("id") == username:
            orgs[idx] = org_entry
            break
    else:
        orgs.append(org_entry)

    orgs_path = project_root / "organizations.yaml"
    orgs_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return org_entry


def refresh_legacy_bot_configs(project_root: Path) -> None:
    cfg = load_orchestration_config(
        project_root / "organizations.yaml",
        project_root / "orchestration.yaml",
        force_reload=True,
    )
    target_dir = project_root / "bots"
    target_dir.mkdir(parents=True, exist_ok=True)
    for org in cfg.list_orgs():
        export = cfg.export_legacy_bot_yaml(org)
        export.setdefault("comment", "generated from canonical orchestration config")
        (target_dir / f"{org.id}.yaml").write_text(
            yaml.safe_dump(export, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )


def refresh_pm_identity_files(project_root: Path) -> None:
    cfg = load_orchestration_config(
        project_root / "organizations.yaml",
        project_root / "orchestration.yaml",
        force_reload=True,
    )
    target_dir = Path.home() / ".ai-org" / "memory"
    target_dir.mkdir(parents=True, exist_ok=True)
    for org in cfg.list_orgs():
        lines = [
            "## [CORE] PM 정체성",
            f"- 봇명: @{org.username} ({org.id})",
            f"- 역할: {org.role}",
            f"- 전문분야: {', '.join(org.specialties)}",
            f"- 방향성: {org.direction}",
        ]
        if org.team.get("preferred_agents"):
            lines.append(f"- 선호 에이전트: {', '.join(org.team['preferred_agents'])}")
        (target_dir / f"pm_{org.id}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

