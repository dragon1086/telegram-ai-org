from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

import scripts.setup_wizard as setup_wizard


def test_save_all_writes_canonical_registration(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(setup_wizard, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(setup_wizard, "CONFIG_DIR", tmp_path / ".ai-org")
    monkeypatch.setattr(setup_wizard, "CONFIG_FILE", tmp_path / ".ai-org" / "config.yaml")
    monkeypatch.setattr(setup_wizard, "ORGANIZATIONS_FILE", tmp_path / "organizations.yaml")
    monkeypatch.setattr(setup_wizard, "AGENT_HINTS_FILE", tmp_path / "agent_hints.yaml")
    monkeypatch.setattr(setup_wizard, "WORKERS_FILE", tmp_path / "workers.yaml")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    orgs = [
        {
            "org_id": "global",
            "description": "총괄 PM",
            "pm_token": "global-token",
            "group_chat_id": "-1001",
            "engine": "codex",
            "identity": {
                "role": "총괄 PM",
                "specialties": ["조율", "전략"],
                "direction": "핵심 내용을 먼저 설명한다",
            },
        },
        {
            "org_id": "aiorg_engineering_bot",
            "description": "개발실",
            "pm_token": "eng-token",
            "group_chat_id": "-1002",
            "engine": "claude-code",
            "identity": {
                "role": "개발/코딩/API 구현",
                "specialties": ["Python", "API"],
                "direction": "구현과 검증을 함께 제시한다",
            },
        },
    ]

    setup_wizard.save_all(orgs, "sequential", {"claude": "/bin/claude", "codex": "/bin/codex"}, "codex")

    orgs_data = yaml.safe_load((tmp_path / "organizations.yaml").read_text(encoding="utf-8"))
    assert orgs_data["schema_version"] == 2
    assert orgs_data["organizations"][0]["id"] == "global"
    assert orgs_data["organizations"][1]["id"] == "aiorg_engineering_bot"
    assert orgs_data["organizations"][1]["identity"]["role"].startswith("개발")

    orchestration_data = yaml.safe_load((tmp_path / "orchestration.yaml").read_text(encoding="utf-8"))
    assert "team_profiles" in orchestration_data
    assert "engineering_delivery" in orchestration_data["team_profiles"]

    config_text = (tmp_path / ".ai-org" / "config.yaml").read_text(encoding="utf-8")
    assert "PM_BOT_TOKEN=global-token" in config_text
    assert "BOT_TOKEN_AIORG_ENGINEERING_BOT=eng-token" in config_text

    exported = yaml.safe_load((tmp_path / "bots" / "aiorg_engineering_bot.yaml").read_text(encoding="utf-8"))
    assert exported["org_id"] == "aiorg_engineering_bot"


def test_load_existing_orgs_reads_canonical_ids(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(setup_wizard, "ORGANIZATIONS_FILE", tmp_path / "organizations.yaml")
    (tmp_path / "organizations.yaml").write_text(
        """
schema_version: 2
organizations:
  - id: global
    description: total
  - id: aiorg_engineering_bot
    description: engineering
""",
        encoding="utf-8",
    )

    orgs = setup_wizard.load_existing_orgs()

    assert orgs == [
        {"name": "global", "description": "total"},
        {"name": "aiorg_engineering_bot", "description": "engineering"},
    ]
