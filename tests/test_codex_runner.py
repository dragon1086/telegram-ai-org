from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.codex_runner import CodexRunner


def test_prefers_explicit_path_as_workdir(tmp_path: Path) -> None:
    repo_dir = tmp_path / "openclaw"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    nested_dir = repo_dir / "src"
    nested_dir.mkdir()

    runner = CodexRunner(workdir=str(tmp_path / "fallback"))

    resolved = runner._resolve_workdir(
        f"{nested_dir} 디렉토리에서 openclaw 에러를 재현하고 고쳐줘",
    )

    assert resolved == str(repo_dir)


def test_falls_back_to_named_repo_search(tmp_path: Path, monkeypatch) -> None:
    repo_dir = tmp_path / "Downloads" / "openclaw"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()
    monkeypatch.setenv("CODEX_REPO_SEARCH_ROOTS", str(tmp_path / "Downloads"))

    runner = CodexRunner(workdir=str(tmp_path / "fallback"))

    resolved = runner._resolve_workdir(
        "로컬에 있는 openclaw 리파지토리에서 원인 분석해줘",
    )

    assert resolved == str(repo_dir)


def test_uses_default_workdir_when_no_repo_match(tmp_path: Path) -> None:
    fallback = tmp_path / "fallback"
    fallback.mkdir()
    runner = CodexRunner(workdir=str(fallback))

    resolved = runner._resolve_workdir("권한 이슈를 정리해줘")

    assert resolved == str(fallback)
