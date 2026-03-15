from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.orchestration_config import load_orchestration_config


def test_load_orchestration_config_merges_team_profiles(tmp_path: Path) -> None:
    orgs_path = tmp_path / "organizations.yaml"
    orch_path = tmp_path / "orchestration.yaml"

    orgs_path.write_text(
        """
schema_version: 2
organizations:
  - id: engineering
    enabled: true
    kind: specialist
    description: engineering
    telegram:
      username: engineering_bot
      token_env: TEST_ENGINEERING_TOKEN
      chat_id: 123
    identity:
      dept_name: 개발실
      role: 개발
      specialties: [Python]
      direction: 빠르게 구현
      instruction: 구현해라
    routing:
      default_handler: false
      can_direct_reply: false
    execution:
      preferred_engine: codex
      team_profile: engineering_delivery
      verification_profile: specialist_default
      phase_policy: default
    team:
      preferred_agents: [executor, architect]
      guidance: org override guidance
    collaboration:
      peers: []
""",
        encoding="utf-8",
    )
    orch_path.write_text(
        """
schema_version: 1
phase_policies:
  default:
    order: [intake, planning, implementation, verification, feedback]
backend_policies:
  specialist_default:
    direct_reply: ephemeral
    local_execution: resume_session
team_profiles:
  engineering_delivery:
    preferred_engine: claude-code
    fallback_engine: codex
    execution_mode: structured_team
    preferred_agents: [executor, debugger]
    preferred_skills: [org-execution]
    max_team_size: 3
    guidance: profile guidance
verification_profiles:
  specialist_default:
    require_plan: true
    require_tests: true
legacy_exports:
  bots_dir: bots
""",
        encoding="utf-8",
    )

    cfg = load_orchestration_config(orgs_path, orch_path, force_reload=True)
    org = cfg.get_org("engineering")

    assert org is not None
    assert org.preferred_engine == "codex"
    assert org.team["preferred_agents"] == ["executor", "architect"]
    assert org.team["preferred_skills"] == ["org-execution"]
    assert org.team["guidance"] == "org override guidance"
    assert cfg.get_backend_policy("specialist_default")["local_execution"] == "resume_session"

    exported = cfg.export_legacy_bot_yaml(org)
    assert exported["org_id"] == "engineering"
    assert exported["team_config"]["preferred_agents"] == ["executor", "architect"]


def test_token_env_name_resolves_from_environment(tmp_path: Path, monkeypatch) -> None:
    orgs_path = tmp_path / "organizations.yaml"
    orch_path = tmp_path / "orchestration.yaml"
    monkeypatch.setenv("TEST_REAL_TOKEN", "123456:ABCDEF")

    orgs_path.write_text(
        """
schema_version: 2
organizations:
  - id: global
    enabled: true
    kind: orchestrator
    description: global
    telegram:
      username: aiorg_pm_bot
      token_env: TEST_REAL_TOKEN
      chat_id: 123
    identity:
      dept_name: PM
      role: PM
      specialties: [coordination]
      direction: direct
      instruction: do things
    routing:
      default_handler: true
      can_direct_reply: true
    execution:
      preferred_engine: codex
      team_profile: global_orchestrator
      verification_profile: orchestrator_default
      phase_policy: default
    team: {}
    collaboration: {}
""",
        encoding="utf-8",
    )
    orch_path.write_text(
        """
schema_version: 1
team_profiles:
  global_orchestrator:
    preferred_engine: codex
verification_profiles:
  orchestrator_default:
    require_plan: true
phase_policies:
  default:
    order: [intake, planning]
""",
        encoding="utf-8",
    )

    cfg = load_orchestration_config(orgs_path, orch_path, force_reload=True)
    org = cfg.get_org("global")

    assert org is not None
    assert org.token == "123456:ABCDEF"
