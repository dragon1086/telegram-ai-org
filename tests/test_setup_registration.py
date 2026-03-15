from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.setup_registration import (
    ensure_orchestration_config,
    load_canonical_organizations,
    parse_setup_identity,
    refresh_legacy_bot_configs,
    refresh_pm_identity_files,
    upsert_org_in_canonical_config,
)


def test_parse_setup_identity_uses_defaults_for_skip() -> None:
    identity = parse_setup_identity("aiorg_engineering_bot", "기본")

    assert "개발" in identity.role
    assert "Python" in identity.specialties
    assert identity.direction


def test_parse_setup_identity_supports_pipe_format() -> None:
    identity = parse_setup_identity("custom_bot", "플랫폼 엔지니어|Go,Infra|안정성을 우선한다")

    assert identity.role == "플랫폼 엔지니어"
    assert identity.specialties == ["Go", "Infra"]
    assert identity.direction == "안정성을 우선한다"


def test_ensure_orchestration_config_creates_required_profiles(tmp_path: Path) -> None:
    path = ensure_orchestration_config(tmp_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert "team_profiles" in data
    assert "engineering_delivery" in data["team_profiles"]
    assert "global_orchestrator" in data["team_profiles"]
    assert "backend_policies" in data


def test_load_canonical_organizations_migrates_legacy_entries(tmp_path: Path) -> None:
    (tmp_path / "organizations.yaml").write_text(
        """
organizations:
  - name: aiorg_engineering_bot
    description: engineering
    pm_token: "${BOT_TOKEN_AIORG_ENGINEERING_BOT}"
    group_chat_id: "${ENGINEERING_CHAT_ID}"
    engine: codex
""",
        encoding="utf-8",
    )

    data = load_canonical_organizations(tmp_path)

    assert data["schema_version"] == 2
    assert data["organizations"][0]["id"] == "aiorg_engineering_bot"
    assert data["organizations"][0]["telegram"]["token_env"] == "BOT_TOKEN_AIORG_ENGINEERING_BOT"


def test_upsert_org_registration_writes_canonical_and_exports(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BOT_TOKEN_AIORG_ENGINEERING_BOT", "123:abc")
    monkeypatch.setenv("ENGINEERING_CHAT_ID", "-1001")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    identity = parse_setup_identity(
        "aiorg_engineering_bot",
        "개발/코딩/API 구현|Python,API,버그수정|구현과 검증을 함께 제시한다",
    )
    upsert_org_in_canonical_config(
        tmp_path,
        username="aiorg_engineering_bot",
        token_env="BOT_TOKEN_AIORG_ENGINEERING_BOT",
        chat_id=-1001,
        engine="codex",
        identity=identity,
    )
    refresh_legacy_bot_configs(tmp_path)
    refresh_pm_identity_files(tmp_path)

    orgs = yaml.safe_load((tmp_path / "organizations.yaml").read_text(encoding="utf-8"))
    assert orgs["organizations"][0]["id"] == "aiorg_engineering_bot"
    assert orgs["organizations"][0]["identity"]["role"].startswith("개발")

    bot_cfg = yaml.safe_load((tmp_path / "bots" / "aiorg_engineering_bot.yaml").read_text(encoding="utf-8"))
    assert bot_cfg["org_id"] == "aiorg_engineering_bot"
    assert bot_cfg["engine"] == "codex"

    memory_file = tmp_path / ".ai-org" / "memory" / "pm_aiorg_engineering_bot.md"
    assert memory_file.exists()
    assert "전문분야" in memory_file.read_text(encoding="utf-8")
