"""Claude Code 세션 ID 영속 저장소."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

SESSION_DIR = Path.home() / ".ai-org" / "sessions"
DEFAULT_TELEGRAM_VERBOSITY = 1

# 세션 자동 로테이션 기본값 (환경변수로 오버라이드 가능)
SESSION_MAX_AGE_SEC: int = int(os.environ.get("SESSION_MAX_AGE_SEC", str(6 * 3600)))  # 6시간
SESSION_MAX_CONTEXT_PCT: int = int(os.environ.get("SESSION_MAX_CONTEXT_PCT", "80"))   # 80%
SESSION_MAX_MESSAGES: int = int(os.environ.get("SESSION_MAX_MESSAGES", "50"))         # 50턴


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
        self.update_runtime(session_id=session_id)

    def get_msg_count(self) -> int:
        return self.load().get("msg_count", 0)

    def get_telegram_verbosity(self) -> int:
        raw = self.load().get("telegram_verbosity", DEFAULT_TELEGRAM_VERBOSITY)
        try:
            level = int(raw)
        except (TypeError, ValueError):
            return DEFAULT_TELEGRAM_VERBOSITY
        return max(0, min(2, level))

    def set_telegram_verbosity(self, level: int) -> int:
        clamped = max(0, min(2, int(level)))
        data = self.load()
        data["telegram_verbosity"] = clamped
        data["updated_at"] = datetime.now(UTC).isoformat()
        self._data = data
        self.path.write_text(json.dumps(self._data, indent=2))
        return clamped

    def update_runtime(
        self,
        *,
        session_id: str | None = None,
        engine: str | None = None,
        backend: str | None = None,
        execution_mode: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        context_percent: int | None = None,
        usage_source: str | None = None,
        output_chars: int | None = None,
        increment_messages: bool = False,
    ) -> None:
        data = self.load()
        if session_id is not None:
            # 새 세션 ID가 기존과 다를 때만 생성 시각 갱신
            if session_id != data.get("session_id"):
                data["session_created_at"] = datetime.now(UTC).isoformat()
            data["session_id"] = session_id
        if engine is not None:
            data["engine"] = engine
        if backend is not None:
            data["backend"] = backend
        if execution_mode is not None:
            data["execution_mode"] = execution_mode
        if input_tokens is not None:
            data["input_tokens"] = input_tokens
        if output_tokens is not None:
            data["output_tokens"] = output_tokens
        if total_tokens is not None:
            data["total_tokens"] = total_tokens
        if context_percent is not None:
            data["context_percent"] = context_percent
        if usage_source is not None:
            data["usage_source"] = usage_source
        if output_chars is not None:
            data["output_chars"] = output_chars
        if increment_messages:
            data["msg_count"] = int(data.get("msg_count", 0) or 0) + 1
        data["updated_at"] = datetime.now(UTC).isoformat()
        self._data = data
        self.path.write_text(json.dumps(self._data, indent=2))

    def mark_compacted(self, *, reason: str = "") -> None:
        data = self.load()
        data["compact_count"] = int(data.get("compact_count", 0) or 0) + 1
        data["last_compacted_at"] = datetime.now(UTC).isoformat()
        if reason:
            data["last_compact_reason"] = reason
        data["updated_at"] = datetime.now(UTC).isoformat()
        self._data = data
        self.path.write_text(json.dumps(self._data, indent=2))

    def should_emit_alert(self, health: str, cooldown_minutes: int = 30) -> bool:
        if health not in {"warning", "compact_recommended", "stale"}:
            return False
        data = self.load()
        last_health = data.get("last_alerted_health")
        last_at_raw = data.get("last_alerted_at")
        if last_health != health:
            return True
        if not last_at_raw:
            return True
        try:
            last_at = datetime.fromisoformat(last_at_raw)
            if last_at.tzinfo is None:
                last_at = last_at.replace(tzinfo=UTC)
        except Exception:
            return True
        age_minutes = (datetime.now(UTC) - last_at).total_seconds() / 60
        return age_minutes >= cooldown_minutes

    def mark_alerted(self, health: str) -> None:
        data = self.load()
        data["last_alerted_health"] = health
        data["last_alerted_at"] = datetime.now(UTC).isoformat()
        data["updated_at"] = datetime.now(UTC).isoformat()
        self._data = data
        self.path.write_text(json.dumps(self._data, indent=2))

    def should_rotate(self) -> tuple[bool, str]:
        """세션 자동 로테이션 필요 여부 판단.

        Returns:
            (True, reason) if rotation needed, (False, "") otherwise.
        """
        data = self.load()
        if not data.get("session_id"):
            return False, ""

        # 1) 나이 체크
        created_raw = data.get("session_created_at")
        if created_raw:
            try:
                created_at = datetime.fromisoformat(created_raw)
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC)
                age_sec = (datetime.now(UTC) - created_at).total_seconds()
                if age_sec > SESSION_MAX_AGE_SEC:
                    return True, f"age={int(age_sec//3600)}h (max={SESSION_MAX_AGE_SEC//3600}h)"
            except Exception:
                pass

        # 2) 컨텍스트 사용률 체크
        ctx_pct = data.get("context_percent")
        if ctx_pct is not None and int(ctx_pct) >= SESSION_MAX_CONTEXT_PCT:
            return True, f"context_percent={ctx_pct}% (max={SESSION_MAX_CONTEXT_PCT}%)"

        # 3) 메시지 수 체크
        msg_count = int(data.get("msg_count", 0) or 0)
        if msg_count >= SESSION_MAX_MESSAGES:
            return True, f"msg_count={msg_count} (max={SESSION_MAX_MESSAGES})"

        return False, ""

    def clear_session_id(self) -> None:
        """session_id만 제거 (다음 호출이 새 세션으로 시작되도록)."""
        data = self.load()
        data.pop("session_id", None)
        data.pop("session_created_at", None)
        data["updated_at"] = datetime.now(UTC).isoformat()
        self._data = data
        self.path.write_text(json.dumps(self._data, indent=2))

    def reset(self, preserve_metrics: bool = False) -> None:
        """세션 초기화 (새 대화 시작)."""
        data = self.load()
        preserved_preferences = {
            "telegram_verbosity": data.get("telegram_verbosity", DEFAULT_TELEGRAM_VERBOSITY),
        }
        if preserve_metrics:
            preserved = {
                "compact_count": data.get("compact_count", 0),
                "last_compacted_at": data.get("last_compacted_at"),
                "last_compact_reason": data.get("last_compact_reason"),
                "updated_at": datetime.now(UTC).isoformat(),
                **preserved_preferences,
            }
            self._data = preserved
            self.path.write_text(json.dumps(self._data, indent=2))
            return
        self._data = preserved_preferences
        self.path.write_text(json.dumps(self._data, indent=2))
