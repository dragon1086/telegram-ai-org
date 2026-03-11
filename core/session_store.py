"""Claude Code 세션 ID 영속 저장소."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

SESSION_DIR = Path.home() / ".ai-org" / "sessions"


class SessionStore:
    def __init__(self, org_id: str = "global") -> None:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        self.path = SESSION_DIR / f"pm_{org_id}.json"
        self._data: dict = {}

    def load(self) -> dict:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
            except Exception:
                self._data = {}
        return self._data

    def get_session_id(self) -> str | None:
        return self.load().get("session_id")

    def save_session_id(self, session_id: str) -> None:
        self._data = {
            "session_id": session_id,
            "updated_at": datetime.now().isoformat(),
            "msg_count": self._data.get("msg_count", 0) + 1,
        }
        self.path.write_text(json.dumps(self._data, indent=2))

    def get_msg_count(self) -> int:
        return self.load().get("msg_count", 0)

    def reset(self) -> None:
        """세션 초기화 (새 대화 시작)."""
        self._data = {}
        if self.path.exists():
            self.path.unlink()
