"""Canonical orchestration config loader.

Source of truth:
- organizations.yaml
- orchestration.yaml

Policy should be read from config rather than hardcoded in runtime modules.
"""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

_VALID_ENGINES = {"claude-code", "codex", "gemini-cli", "auto"}
_DEFAULT_ORGS_PATH = Path("organizations.yaml")
_DEFAULT_ORCH_PATH = Path("orchestration.yaml")


def _resolve_env(value: Any) -> Any:
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value


def _resolve_nested(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _resolve_nested(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_nested(v) for v in value]
    return _resolve_env(value)


@dataclass
class TeamProfile:
    name: str
    preferred_engine: str = "auto"
    fallback_engine: str = "claude-code"
    execution_mode: str = "sequential"
    preferred_agents: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    avoid_agents: list[str] = field(default_factory=list)
    max_team_size: int = 3
    guidance: str = ""


@dataclass
class VerificationProfile:
    name: str
    require_plan: bool = True
    require_tests: bool = True
    require_status_snapshot: bool = True
    require_feedback: bool = True


@dataclass
class PhasePolicy:
    name: str
    order: list[str] = field(default_factory=lambda: [
        "intake", "planning", "design", "implementation", "verification", "feedback",
    ])
    required_documents: dict[str, list[str]] = field(default_factory=dict)
    announce_plan_on_start: bool = True
    announce_progress: bool = True
    require_goal_feedback: bool = True


@dataclass
class CollabTrigger:
    """orchestration.yaml collab_triggers 항목 하나를 표현.

    trigger_dept 조직의 태스크가 완료되고 task_type이 trigger_task_types에
    포함되면 target_depts에 후속 태스크를 자동 생성한다.
    """

    id: str
    description: str
    trigger_dept: str
    trigger_task_types: list[str]       # 빈 리스트 = 모든 타입에 발동
    target_depts: list[str]
    message_template: str
    enabled: bool = True
    dedup_window_minutes: int = 60      # 같은 (source_task_id, target_dept) 재트리거 억제 시간

    def matches(self, dept: str, task_type: str) -> bool:
        """dept + task_type 조합이 이 트리거 조건에 해당하는지 반환."""
        if not self.enabled:
            return False
        if dept != self.trigger_dept:
            return False
        if not self.trigger_task_types:
            return True
        return task_type in self.trigger_task_types

    def render_message(
        self,
        source_dept: str,
        source_task_id: str,
        result_summary: str,
        target_role: str = "",
    ) -> str:
        """message_template의 치환 변수를 실제 값으로 채워 반환."""
        return self.message_template.format(
            source_dept=source_dept,
            source_task_id=source_task_id,
            result_summary=result_summary,
            target_role=target_role,
        )


@dataclass
class OrganizationConfig:
    id: str
    kind: str
    enabled: bool
    description: str
    telegram: dict[str, Any]
    identity: dict[str, Any]
    routing: dict[str, Any]
    execution: dict[str, Any]
    team: dict[str, Any]
    collaboration: dict[str, Any]

    @property
    def username(self) -> str:
        return self.telegram.get("username", self.id)

    @property
    def token(self) -> str:
        raw = self.telegram.get("token", "")
        if raw:
            return str(_resolve_env(raw))
        env_name = self.telegram.get("token_env", "")
        if env_name:
            return os.environ.get(str(env_name), "")
        return ""

    @property
    def chat_id(self) -> int | None:
        raw = _resolve_env(self.telegram.get("chat_id"))
        if raw in (None, ""):
            return None
        return int(raw)

    @property
    def preferred_engine(self) -> str:
        engine = self.execution.get("preferred_engine", "claude-code")
        return engine if engine in _VALID_ENGINES else "claude-code"

    @property
    def fallback_engine(self) -> str:
        engine = self.execution.get("fallback_engine", "claude-code")
        return engine if engine in _VALID_ENGINES else "claude-code"

    @property
    def dept_name(self) -> str:
        return self.identity.get("dept_name", self.id)

    @property
    def role(self) -> str:
        return self.identity.get("role", "")

    @property
    def specialties(self) -> list[str]:
        specs = list(self.identity.get("specialties", []))
        if not specs:
            role = self.identity.get("role", "")
            if role:
                specs = [s.strip() for s in role.split("/") if s.strip()]
        return specs

    @property
    def direction(self) -> str:
        return self.identity.get("direction", "")

    @property
    def instruction(self) -> str:
        return self.identity.get("instruction", "")

    @property
    def default_handler(self) -> bool:
        return bool(self.routing.get("default_handler", False))

    @property
    def can_direct_reply(self) -> bool:
        return bool(self.routing.get("can_direct_reply", False))


class OrchestrationConfig:
    def __init__(
        self,
        orgs_path: str | Path | None = None,
        orchestration_path: str | Path | None = None,
    ) -> None:
        self.orgs_path = Path(orgs_path or _DEFAULT_ORGS_PATH)
        self.orchestration_path = Path(orchestration_path or _DEFAULT_ORCH_PATH)
        self.organizations: dict[str, OrganizationConfig] = {}
        self.team_profiles: dict[str, TeamProfile] = {}
        self.verification_profiles: dict[str, VerificationProfile] = {}
        self.phase_policies: dict[str, PhasePolicy] = {}
        self.backend_policies: dict[str, dict[str, Any]] = {}
        self.session_policies: dict[str, dict[str, Any]] = {}
        self.runtime: dict[str, Any] = {}
        self.legacy_exports: dict[str, Any] = {}
        self.global_instructions: str = ""
        self.collab_triggers: list[CollabTrigger] = []

    def load(self) -> "OrchestrationConfig":
        self._load_orchestration()
        self._load_organizations()
        return self

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            logger.warning(f"config 없음: {path}")
            return {}
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return _resolve_nested(data)

    def _load_orchestration(self) -> None:
        raw = self._load_yaml(self.orchestration_path)
        self.runtime = raw.get("runtime", {})
        self.legacy_exports = raw.get("legacy_exports", {})
        self.global_instructions = raw.get("global_instructions", "")
        self.backend_policies = raw.get("backend_policies", {})
        self.session_policies = raw.get("session_policies", {})
        self.team_profiles = {
            name: TeamProfile(name=name, **cfg)
            for name, cfg in raw.get("team_profiles", {}).items()
        }
        self.verification_profiles = {
            name: VerificationProfile(name=name, **cfg)
            for name, cfg in raw.get("verification_profiles", {}).items()
        }
        self.phase_policies = {
            name: PhasePolicy(name=name, **cfg)
            for name, cfg in raw.get("phase_policies", {}).items()
        }
        self.collab_triggers = [
            CollabTrigger(
                id=item.get("id", ""),
                description=item.get("description", ""),
                trigger_dept=item.get("trigger_dept", ""),
                trigger_task_types=list(item.get("trigger_task_types", [])),
                target_depts=list(item.get("target_depts", [])),
                message_template=item.get("message_template", ""),
                enabled=bool(item.get("enabled", True)),
                dedup_window_minutes=int(item.get("dedup_window_minutes", 60)),
            )
            for item in raw.get("collab_triggers", [])
        ]

    def _merge_team(self, org_entry: dict[str, Any]) -> dict[str, Any]:
        execution = copy.deepcopy(org_entry.get("execution", {}))
        team_profile_name = execution.get("team_profile", "")
        profile = self.team_profiles.get(team_profile_name)
        merged = {
            "preferred_agents": [],
            "avoid_agents": [],
            "preferred_skills": [],
            "max_team_size": 3,
            "guidance": "",
            "execution_mode": execution.get("execution_mode", "sequential"),
        }
        if profile is not None:
            merged.update({
                "preferred_agents": list(profile.preferred_agents),
                "avoid_agents": list(profile.avoid_agents),
                "preferred_skills": list(profile.preferred_skills),
                "max_team_size": profile.max_team_size,
                "guidance": profile.guidance,
                "execution_mode": profile.execution_mode,
            })
            execution.setdefault("preferred_engine", profile.preferred_engine)
            execution.setdefault("fallback_engine", profile.fallback_engine)

        team_override = org_entry.get("team", {})
        merged.update(team_override)
        org_entry["execution"] = execution
        return merged

    def _load_organizations(self) -> None:
        raw = self._load_yaml(self.orgs_path)
        org_entries = raw.get("organizations", [])
        loaded: dict[str, OrganizationConfig] = {}
        for entry in org_entries:
            org_data = copy.deepcopy(entry)
            org_data["team"] = self._merge_team(org_data)
            org = OrganizationConfig(
                id=org_data["id"],
                kind=org_data.get("kind", "specialist"),
                enabled=bool(org_data.get("enabled", True)),
                description=org_data.get("description", ""),
                telegram=org_data.get("telegram", {}),
                identity=org_data.get("identity", {}),
                routing=org_data.get("routing", {}),
                execution=org_data.get("execution", {}),
                team=org_data.get("team", {}),
                collaboration=org_data.get("collaboration", {}),
            )
            loaded[org.id] = org
        self.organizations = loaded

    def get_org(self, org_id: str) -> OrganizationConfig | None:
        return self.organizations.get(org_id)

    def list_orgs(self) -> list[OrganizationConfig]:
        return [org for org in self.organizations.values() if org.enabled]

    def list_specialist_orgs(self) -> list[OrganizationConfig]:
        return [org for org in self.list_orgs() if org.kind == "specialist"]

    def get_phase_policy(self, name: str) -> PhasePolicy | None:
        return self.phase_policies.get(name)

    def get_verification_profile(self, name: str) -> VerificationProfile | None:
        return self.verification_profiles.get(name)

    def get_backend_policy(self, name: str) -> dict[str, Any]:
        return copy.deepcopy(self.backend_policies.get(name, {}))

    def get_session_policy(self, name: str) -> dict[str, Any]:
        return copy.deepcopy(self.session_policies.get(name, {}))

    def get_dept_map(self) -> dict[str, str]:
        return {org.id: org.dept_name for org in self.list_specialist_orgs()}

    def get_collab_triggers(
        self, trigger_dept: str, task_type: str
    ) -> list[CollabTrigger]:
        """dept + task_type 조합에 매칭되는 활성 COLLAB 트리거 목록 반환."""
        return [t for t in self.collab_triggers if t.matches(trigger_dept, task_type)]

    def get_collab_triggers_by_description(
        self, trigger_dept: str, description: str
    ) -> list[CollabTrigger]:
        """task_type 미설정 시 description 키워드로 폴백 매칭.

        trigger_task_types 목록의 키워드가 description에 포함되는지 확인.
        빈 trigger_task_types(= 모든 타입 발동)도 정상 포함.
        """
        lower_desc = description.lower()
        result = []
        for t in self.collab_triggers:
            if not t.enabled or t.trigger_dept != trigger_dept:
                continue
            if not t.trigger_task_types:
                result.append(t)
            elif any(kw.lower() in lower_desc for kw in t.trigger_task_types):
                result.append(t)
        return result

    def export_legacy_bot_yaml(self, org: OrganizationConfig) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "organization_ref": org.id,
            "username": org.username,
            "org_id": org.id,
            "token_env": org.telegram.get("token_env", ""),
            "chat_id": org.chat_id,
            "engine": org.preferred_engine,
            "dept_name": org.dept_name,
            "role": org.role,
            "instruction": org.instruction,
            "is_pm": org.kind == "orchestrator",
            "team_config": {
                "preferred_agents": org.team.get("preferred_agents", []),
                "avoid_agents": org.team.get("avoid_agents", []),
                "preferred_skills": org.team.get("preferred_skills", []),
                "max_team_size": org.team.get("max_team_size", 3),
                "guidance": org.team.get("guidance", ""),
            },
        }


_cached: OrchestrationConfig | None = None


def load_orchestration_config(
    orgs_path: str | Path | None = None,
    orchestration_path: str | Path | None = None,
    *,
    force_reload: bool = False,
) -> OrchestrationConfig:
    global _cached
    if _cached is None or force_reload:
        _cached = OrchestrationConfig(orgs_path, orchestration_path).load()
    return _cached
