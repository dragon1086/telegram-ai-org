from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.orchestration_config import load_orchestration_config
from core.session_registry import SessionRegistry
from core.session_store import SessionStore
import core.session_store as session_store_mod


class _FakeSessionManager:
    def status(self):
        return {"tmux": False, "sessions": []}


def test_session_registry_reports_context_budget(tmp_path: Path, monkeypatch) -> None:
    orgs_path = tmp_path / "organizations.yaml"
    orch_path = tmp_path / "orchestration.yaml"
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
      token_env: PM_BOT_TOKEN
      chat_id: 1
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
      backend_policy: orchestrator_default
      session_policy: orchestrator_default
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
backend_policies:
  orchestrator_default:
    direct_reply: ephemeral
session_policies:
  orchestrator_default:
    max_messages_before_compact: 10
    warn_threshold_percent: 70
    compact_threshold_percent: 80
phase_policies:
  default:
    order: [intake, planning, verification]
""",
        encoding="utf-8",
    )
    load_orchestration_config(orgs_path, orch_path, force_reload=True)

    monkeypatch.setattr(session_store_mod, "SESSION_DIR", tmp_path / ".sessions")
    store = SessionStore("global")
    store.update_runtime(
        engine="codex",
        backend="ephemeral",
        execution_mode="sequential",
        total_tokens=1234,
        context_percent=83,
        usage_source="runner_event",
    )
    for _ in range(8):
        store.update_runtime(increment_messages=True)

    registry = SessionRegistry(_FakeSessionManager())
    item = registry.get_session("global")

    assert item is not None
    assert item["context_percent"] == 83
    assert item["health"] == "compact_recommended"
    assert item["total_tokens"] == 1234
    assert item["usage_source"] == "runner_event"


def test_session_registry_marks_stale_and_sorts_by_priority(tmp_path: Path, monkeypatch) -> None:
    orgs_path = tmp_path / "organizations.yaml"
    orch_path = tmp_path / "orchestration.yaml"
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
      token_env: PM_BOT_TOKEN
      chat_id: 1
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
      backend_policy: orchestrator_default
      session_policy: orchestrator_default
    team: {}
    collaboration: {}
  - id: aiorg_engineering_bot
    enabled: true
    kind: specialist
    description: eng
    telegram:
      username: aiorg_engineering_bot
      token_env: BOT_TOKEN_AIORG_ENGINEERING_BOT
      chat_id: 1
    identity:
      dept_name: 개발실
      role: 개발
      specialties: [python]
      direction: build
      instruction: do
    routing:
      default_handler: false
      can_direct_reply: false
    execution:
      preferred_engine: codex
      team_profile: specialist_default
      verification_profile: specialist_default
      phase_policy: default
      backend_policy: specialist_default
      session_policy: specialist_default
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
  specialist_default:
    preferred_engine: codex
verification_profiles:
  orchestrator_default:
    require_plan: true
  specialist_default:
    require_plan: true
backend_policies:
  orchestrator_default:
    direct_reply: ephemeral
  specialist_default:
    direct_reply: ephemeral
session_policies:
  orchestrator_default:
    max_messages_before_compact: 50
    warn_threshold_percent: 70
    compact_threshold_percent: 80
    stale_after_minutes: 180
  specialist_default:
    max_messages_before_compact: 20
    warn_threshold_percent: 70
    compact_threshold_percent: 80
    stale_after_minutes: 1
phase_policies:
  default:
    order: [intake, planning, verification]
""",
        encoding="utf-8",
    )
    load_orchestration_config(orgs_path, orch_path, force_reload=True)

    monkeypatch.setattr(session_store_mod, "SESSION_DIR", tmp_path / ".sessions")
    global_store = SessionStore("global")
    global_store.update_runtime(increment_messages=True)
    eng_store = SessionStore("aiorg_engineering_bot")
    eng_store.update_runtime(increment_messages=True)
    data = eng_store.load()
    data["updated_at"] = "2020-01-01T00:00:00+00:00"
    eng_store.path.write_text(__import__("json").dumps(data), encoding="utf-8")

    registry = SessionRegistry(_FakeSessionManager())
    items = registry.list_sessions()

    assert items[0]["org_id"] == "aiorg_engineering_bot"
    assert items[0]["health"] == "stale"
    summary = registry.format_summary()
    assert "stale" in summary
