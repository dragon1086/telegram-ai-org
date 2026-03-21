"""대기 중인 RoutingProposal 저장소."""
from __future__ import annotations
import json
from pathlib import Path

_DEFAULT_PATH = Path(__file__).parent.parent / "data" / "routing_approval.json"


class RoutingApprovalStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, proposal_dict: dict) -> None:
        self._path.write_text(json.dumps(proposal_dict, ensure_ascii=False, indent=2))

    def load_pending(self) -> dict | None:
        if not self._path.exists():
            return None
        try:
            return json.loads(self._path.read_text())
        except Exception:
            return None

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()
