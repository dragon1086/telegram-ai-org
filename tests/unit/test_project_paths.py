from pathlib import Path

import core.autonomous_loop as autonomous_loop
from core.orchestration_config import load_orchestration_config
from project_paths import get_project_root, project_path


def test_get_project_root_prefers_explicit_env(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "orchestration.yaml").write_text("runtime: {}\n")
    monkeypatch.setenv("AIMESH_PROJECT_ROOT", str(tmp_path))

    assert get_project_root() == tmp_path.resolve()
    assert project_path("orchestration.yaml") == tmp_path.resolve() / "orchestration.yaml"


def test_get_project_root_falls_back_to_cwd(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "organizations.yaml").write_text("organizations: []\n")
    monkeypatch.delenv("AIMESH_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)

    assert get_project_root() == tmp_path.resolve()


def test_load_loop_config_uses_project_root_env(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "orchestration.yaml").write_text(
        "autonomous_loop:\n  idle_sleep_sec: 12\n  max_dispatch: 7\n"
    )
    monkeypatch.setenv("AIMESH_PROJECT_ROOT", str(tmp_path))

    cfg = autonomous_loop.load_loop_config()

    assert cfg["idle_sleep_sec"] == 12
    assert cfg["max_dispatch"] == 7


def test_load_orchestration_config_uses_project_root_env(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "organizations.yaml").write_text(
        "organizations:\n  - id: demo\n    enabled: true\n    kind: specialist\n"
        "    description: demo\n    telegram: {}\n    identity: {}\n"
        "    routing: {}\n    execution: {}\n    team: {}\n    collaboration: {}\n"
    )
    (tmp_path / "orchestration.yaml").write_text("team_profiles: {}\n")
    monkeypatch.setenv("AIMESH_PROJECT_ROOT", str(tmp_path))

    cfg = load_orchestration_config(force_reload=True)

    assert cfg.get_org("demo") is not None
