from __future__ import annotations

import os
from pathlib import Path


_ROOT_ENV_VAR = "AIMESH_PROJECT_ROOT"
_ROOT_MARKERS = ("orchestration.yaml", "organizations.yaml", "pyproject.toml")


def _looks_like_project_root(path: Path) -> bool:
    return any((path / marker).exists() for marker in _ROOT_MARKERS)


def get_project_root(anchor: str | Path | None = None) -> Path:
    candidates: list[Path] = []

    env_root = os.environ.get(_ROOT_ENV_VAR, "").strip()
    if env_root:
        candidates.append(Path(env_root).expanduser())

    candidates.append(Path.cwd())

    if anchor is not None:
        anchor_path = Path(anchor).expanduser().resolve()
        if anchor_path.is_file():
            anchor_path = anchor_path.parent
        candidates.extend(anchor_path.parents)
        candidates.append(anchor_path)

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if _looks_like_project_root(resolved):
            return resolved

    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path.cwd().resolve()


def project_path(*parts: str, anchor: str | Path | None = None) -> Path:
    return get_project_root(anchor=anchor).joinpath(*parts)
