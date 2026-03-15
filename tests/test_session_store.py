from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import core.session_store as session_store_mod
from core.session_store import SessionStore


def test_reset_preserves_compact_metrics(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(session_store_mod, "SESSION_DIR", tmp_path / ".sessions")
    store = SessionStore("global")
    store.update_runtime(session_id="abc", increment_messages=True)
    store.mark_compacted(reason="manual")
    store.reset(preserve_metrics=True)

    data = store.load()
    assert data.get("compact_count") == 1
    assert data.get("last_compact_reason") == "manual"
    assert data.get("session_id") is None


def test_alert_cooldown_and_state_tracking(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(session_store_mod, "SESSION_DIR", tmp_path / ".sessions")
    store = SessionStore("global")

    assert store.should_emit_alert("warning", cooldown_minutes=30) is True
    store.mark_alerted("warning")
    assert store.should_emit_alert("warning", cooldown_minutes=30) is False
    assert store.should_emit_alert("compact_recommended", cooldown_minutes=30) is True


def test_telegram_verbosity_persists_and_is_clamped(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(session_store_mod, "SESSION_DIR", tmp_path / ".sessions")
    store = SessionStore("global")

    assert store.get_telegram_verbosity() == 1
    assert store.set_telegram_verbosity(9) == 2

    reloaded = SessionStore("global")
    assert reloaded.get_telegram_verbosity() == 2


def test_reset_preserves_telegram_preferences(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(session_store_mod, "SESSION_DIR", tmp_path / ".sessions")
    store = SessionStore("global")
    store.set_telegram_verbosity(0)
    store.update_runtime(session_id="abc", increment_messages=True)

    store.reset()

    data = store.load()
    assert data.get("session_id") is None
    assert data.get("msg_count") is None
    assert data.get("telegram_verbosity") == 0
