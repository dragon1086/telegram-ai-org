"""Organization session registry for Telegram-visible session management."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core.orchestration_config import load_orchestration_config
from core.session_manager import SessionManager
from core.session_store import SessionStore


def _parse_iso(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt
    except Exception:
        return None


class SessionRegistry:
    def __init__(self, session_manager: SessionManager | None = None) -> None:
        self.session_manager = session_manager or SessionManager()
        self.cfg = load_orchestration_config()

    def list_sessions(self) -> list[dict[str, Any]]:
        tmux_status = self.session_manager.status()
        tmux_sessions = set(tmux_status.get("sessions", []))
        items: list[dict[str, Any]] = []
        now = datetime.now(UTC)

        for org in self.cfg.list_orgs():
            store = SessionStore(org.id)
            data = store.load()
            session_policy = self.cfg.get_session_policy(org.execution.get("session_policy", ""))
            msg_count = int(data.get("msg_count", 0) or 0)
            max_messages = int(session_policy.get("max_messages_before_compact", 50) or 50)
            stale_after = int(session_policy.get("stale_after_minutes", 180) or 180)
            estimated_pct = min(100, int((msg_count / max_messages) * 100)) if max_messages > 0 else 0
            actual_pct = data.get("context_percent")
            approx_pct = int(actual_pct) if isinstance(actual_pct, int) else estimated_pct
            updated_at = _parse_iso(data.get("updated_at"))
            age_minutes = int((now - updated_at).total_seconds() // 60) if updated_at else None
            tmux_name_fn = getattr(self.session_manager, "session_name", lambda team_id: "")
            shell_name_fn = getattr(self.session_manager, "shell_session_name", lambda team_id: "")
            tmux_name = tmux_name_fn(org.id)
            shell_name = shell_name_fn(org.id)
            active_tmux = tmux_name in tmux_sessions or shell_name in tmux_sessions

            if approx_pct >= int(session_policy.get("compact_threshold_percent", 80) or 80):
                health = "compact_recommended"
            elif approx_pct >= int(session_policy.get("warn_threshold_percent", 70) or 70):
                health = "warning"
            elif age_minutes is not None and age_minutes >= stale_after and not active_tmux and msg_count > 0:
                health = "stale"
            elif active_tmux or msg_count > 0:
                health = "active"
            else:
                health = "idle"

            items.append({
                "org_id": org.id,
                "kind": org.kind,
                "engine": data.get("engine") or org.preferred_engine,
                "backend": data.get("backend") or org.execution.get("backend_policy", ""),
                "session_id": data.get("session_id"),
                "msg_count": msg_count,
                "context_percent": approx_pct,
                "estimated_context_percent": estimated_pct,
                "health": health,
                "last_updated_at": data.get("updated_at"),
                "age_minutes": age_minutes,
                "compact_count": int(data.get("compact_count", 0) or 0),
                "last_compacted_at": data.get("last_compacted_at"),
                "tmux_active": active_tmux,
                "session_policy": org.execution.get("session_policy", ""),
                "usage_source": data.get("usage_source", "estimate"),
                "input_tokens": int(data.get("input_tokens", 0) or 0),
                "output_tokens": int(data.get("output_tokens", 0) or 0),
                "total_tokens": int(data.get("total_tokens", 0) or 0),
                "output_chars": int(data.get("output_chars", 0) or 0),
                "stale_after_minutes": stale_after,
            })

        items = sorted(
            items,
            key=lambda item: (
                self._health_priority(item["health"]),
                item["context_percent"],
                item["msg_count"],
                item["org_id"],
            ),
            reverse=True,
        )
        for item in items:
            item["next_action"] = self._next_action(item)
        return items

    @staticmethod
    def _health_priority(health: str) -> int:
        order = {
            "compact_recommended": 5,
            "warning": 4,
            "stale": 3,
            "active": 2,
            "idle": 1,
        }
        return order.get(health, 0)

    @staticmethod
    def _health_icon(health: str) -> str:
        icons = {
            "compact_recommended": "🟥",
            "warning": "🟧",
            "stale": "🟨",
            "active": "🟩",
            "idle": "⬜",
        }
        return icons.get(health, "·")

    @staticmethod
    def _next_action(item: dict[str, Any]) -> str:
        health = item["health"]
        if health == "compact_recommended":
            return f"/compact {item['org_id']}"
        if health == "warning":
            return "prepare compact"
        if health == "stale":
            return f"/reset-session {item['org_id']}"
        if health == "active":
            return "monitor"
        return "none"

    def get_session(self, org_id: str) -> dict[str, Any] | None:
        for item in self.list_sessions():
            if item["org_id"] == org_id:
                return item
        return None

    def format_summary(self) -> str:
        lines = ["🧠 세션 현황", "org                state            ctx   usage       age   next"]
        for item in self.list_sessions():
            tmux_icon = "🪟" if item["tmux_active"] else "·"
            health = f"{self._health_icon(item['health'])} {item['health']}"
            usage_hint = (
                f"tok={item['total_tokens']}" if item["total_tokens"] else f"msg={item['msg_count']}"
            )
            age_hint = f"{item['age_minutes']}m" if item["age_minutes"] is not None else "-"
            lines.append(
                f"{tmux_icon} {item['org_id']:<18} {health:<16} {item['context_percent']:>3}%  {usage_hint:<10} {age_hint:>5}  {item['next_action']}"
            )
        return "\n".join(lines)

    def format_detail(self, org_id: str) -> str:
        item = self.get_session(org_id)
        if item is None:
            return f"알 수 없는 조직: {org_id}"
        return "\n".join([
            f"🧠 {org_id} 세션 상세",
            f"- health: {self._health_icon(item['health'])} {item['health']}",
            f"- engine: {item['engine']}",
            f"- backend: {item['backend']}",
            f"- session_id: {item['session_id'] or '-'}",
            f"- msg_count: {item['msg_count']}",
            f"- context_percent: {item['context_percent']}%",
            f"- estimated_context_percent: {item['estimated_context_percent']}%",
            f"- stale_after_minutes: {item['stale_after_minutes']}",
            f"- next_action: {item['next_action']}",
            f"- compact_count: {item['compact_count']}",
            f"- last_compacted_at: {item['last_compacted_at'] or '-'}",
            f"- last_updated_at: {item['last_updated_at'] or '-'}",
            f"- age_minutes: {item['age_minutes'] if item['age_minutes'] is not None else '-'}",
            f"- tmux_active: {item['tmux_active']}",
            f"- session_policy: {item['session_policy'] or '-'}",
            f"- usage_source: {item['usage_source']}",
            f"- input_tokens: {item['input_tokens']}",
            f"- output_tokens: {item['output_tokens']}",
            f"- total_tokens: {item['total_tokens']}",
            f"- output_chars: {item['output_chars']}",
        ])

    def collect_alert_candidates(self) -> list[dict[str, Any]]:
        return [
            item for item in self.list_sessions()
            if item["health"] in {"warning", "compact_recommended", "stale"}
        ]
