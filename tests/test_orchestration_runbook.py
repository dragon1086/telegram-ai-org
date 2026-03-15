from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.orchestration_runbook import OrchestrationRunbook


def test_runbook_create_and_advance(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "organizations.yaml").write_text(
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
    team: {}
    collaboration: {}
""",
        encoding="utf-8",
    )
    (tmp_path / "orchestration.yaml").write_text(
        """
schema_version: 1
runtime:
  docs_root: docs/orchestration-v2
  run_state_root: .ai-org/runs
phase_policies:
  default:
    order: [intake, planning, verification]
    required_documents:
      intake: [request-brief.md]
      planning: [plan.md]
      verification: [verification.md]
team_profiles:
  global_orchestrator:
    preferred_engine: codex
verification_profiles:
  orchestrator_default:
    require_plan: true
""",
        encoding="utf-8",
    )

    runbook = OrchestrationRunbook(tmp_path)
    state = runbook.create_run("global", "로그인 버그 수정")
    run_id = state["run_id"]

    assert state["current_phase"] == "intake"
    assert (tmp_path / ".ai-org" / "runs" / run_id / "state.json").exists()
    assert (tmp_path / "docs" / "orchestration-v2" / "runs" / run_id / "request-brief.md").exists()

    state = runbook.advance_phase(run_id, note="planning started")
    assert state["current_phase"] == "planning"
    assert (tmp_path / "docs" / "orchestration-v2" / "runs" / run_id / "plan.md").exists()
