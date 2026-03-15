"""Document-backed run/phase state for orchestration v2."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.orchestration_config import PhasePolicy, load_orchestration_config


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _safe_slug(text: str, limit: int = 48) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in text).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return (cleaned[:limit] or "run").strip("-") or "run"


@dataclass
class RunbookPaths:
    run_dir: Path
    docs_dir: Path
    state_file: Path


class OrchestrationRunbook:
    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root)
        cfg = load_orchestration_config(
            self.repo_root / "organizations.yaml",
            self.repo_root / "orchestration.yaml",
            force_reload=True,
        )
        runtime = cfg.runtime
        self.state_root = self.repo_root / runtime.get("run_state_root", ".ai-org/runs")
        self.docs_root = self.repo_root / runtime.get("docs_root", "docs/orchestration-v2") / "runs"
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.docs_root.mkdir(parents=True, exist_ok=True)

    def _paths(self, run_id: str) -> RunbookPaths:
        run_dir = self.state_root / run_id
        docs_dir = self.docs_root / run_id
        return RunbookPaths(run_dir, docs_dir, run_dir / "state.json")

    def create_run(self, org_id: str, request: str, phase_policy_name: str = "default") -> dict[str, Any]:
        cfg = load_orchestration_config()
        phase_policy = cfg.get_phase_policy(phase_policy_name) or PhasePolicy(name=phase_policy_name)
        run_id = f"run-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{_safe_slug(request)}"
        paths = self._paths(run_id)
        paths.run_dir.mkdir(parents=True, exist_ok=True)
        paths.docs_dir.mkdir(parents=True, exist_ok=True)

        phases = []
        for idx, phase in enumerate(phase_policy.order):
            phases.append({
                "name": phase,
                "status": "active" if idx == 0 else "pending",
                "started_at": _utcnow() if idx == 0 else None,
                "completed_at": None,
            })

        state = {
            "run_id": run_id,
            "org_id": org_id,
            "request": request,
            "phase_policy": phase_policy.name,
            "status": "active",
            "current_phase": phase_policy.order[0],
            "phases": phases,
            "created_at": _utcnow(),
            "updated_at": _utcnow(),
        }
        self._write_json(paths.state_file, state)
        self._ensure_phase_docs(paths.docs_dir, phase_policy, phase_policy.order[0], request)
        self._write_index(paths.docs_dir, state)
        return state

    def append_note(
        self,
        run_id: str,
        title: str,
        content: str,
        *,
        phase_name: str | None = None,
    ) -> None:
        state = self.get_state(run_id)
        cfg = load_orchestration_config(
            self.repo_root / "organizations.yaml",
            self.repo_root / "orchestration.yaml",
            force_reload=True,
        )
        phase_policy = cfg.get_phase_policy(state["phase_policy"]) or PhasePolicy(name=state["phase_policy"])
        target_phase = phase_name or state["current_phase"]
        doc_path = self._phase_doc_path(self._paths(run_id).docs_dir, phase_policy, target_phase)
        entry = (
            f"\n## {title}\n"
            f"- at: {_utcnow()}\n\n"
            f"{content.strip() or '-'}\n"
        )
        if doc_path.exists():
            doc_path.write_text(doc_path.read_text(encoding="utf-8") + entry, encoding="utf-8")
        else:
            doc_path.write_text(f"# {target_phase}\n{entry}", encoding="utf-8")

    def advance_phase(self, run_id: str, note: str = "") -> dict[str, Any]:
        state = self.get_state(run_id)
        cfg = load_orchestration_config()
        phase_policy = cfg.get_phase_policy(state["phase_policy"]) or PhasePolicy(name=state["phase_policy"])
        current_idx = next(i for i, phase in enumerate(state["phases"]) if phase["name"] == state["current_phase"])
        state["phases"][current_idx]["status"] = "completed"
        state["phases"][current_idx]["completed_at"] = _utcnow()

        if current_idx + 1 >= len(state["phases"]):
            state["status"] = "completed"
            state["updated_at"] = _utcnow()
            self._write_json(self._paths(run_id).state_file, state)
            self._write_index(self._paths(run_id).docs_dir, state, note=note)
            return state

        next_phase = state["phases"][current_idx + 1]
        next_phase["status"] = "active"
        next_phase["started_at"] = _utcnow()
        state["current_phase"] = next_phase["name"]
        state["updated_at"] = _utcnow()

        paths = self._paths(run_id)
        self._write_json(paths.state_file, state)
        self._ensure_phase_docs(paths.docs_dir, phase_policy, next_phase["name"], state["request"], note=note)
        self._write_index(paths.docs_dir, state, note=note)
        return state

    def get_state(self, run_id: str) -> dict[str, Any]:
        state_path = self._paths(run_id).state_file
        return json.loads(state_path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _ensure_phase_docs(
        self,
        docs_dir: Path,
        phase_policy: PhasePolicy,
        phase_name: str,
        request: str,
        note: str = "",
    ) -> None:
        required = phase_policy.required_documents.get(phase_name, [])
        for filename in required:
            path = docs_dir / filename
            if path.exists():
                continue
            path.write_text(
                f"# {phase_name}\n\n## Request\n{request}\n\n## Note\n{note or '-'}\n",
                encoding="utf-8",
            )
        if not required:
            path = docs_dir / f"{phase_name}.md"
            if not path.exists():
                path.write_text(
                    f"# {phase_name}\n\n## Request\n{request}\n\n## Note\n{note or '-'}\n",
                    encoding="utf-8",
                )

    def _phase_doc_path(self, docs_dir: Path, phase_policy: PhasePolicy, phase_name: str) -> Path:
        required = phase_policy.required_documents.get(phase_name, [])
        if required:
            return docs_dir / required[0]
        return docs_dir / f"{phase_name}.md"

    def _write_index(self, docs_dir: Path, state: dict[str, Any], note: str = "") -> None:
        lines = [
            f"# {state['run_id']}",
            "",
            f"- org: {state['org_id']}",
            f"- status: {state['status']}",
            f"- current_phase: {state['current_phase']}",
            f"- request: {state['request']}",
            "",
            "## phases",
        ]
        for phase in state["phases"]:
            lines.append(f"- {phase['name']}: {phase['status']}")
        if note:
            lines.extend(["", "## note", note])
        (docs_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
