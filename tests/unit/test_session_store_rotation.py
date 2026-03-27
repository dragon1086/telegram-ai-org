"""SessionStore 자동 로테이션 로직 단위 테스트."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.session_store import (
    SESSION_MAX_AGE_SEC,
    SESSION_MAX_CONTEXT_PCT,
    SESSION_MAX_MESSAGES,
    SessionStore,
)


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SessionStore:
    monkeypatch.setattr("core.session_store.SESSION_DIR", tmp_path)
    s = SessionStore("test_org")
    return s


def _write_session(store: SessionStore, *, session_id: str = "abc-123", **kwargs: object) -> None:
    """헬퍼: 세션 파일에 직접 데이터 기록."""
    data = {"session_id": session_id, **kwargs}
    store.path.write_text(json.dumps(data))


class TestShouldRotate:
    def test_no_session_id_returns_false(self, store: SessionStore) -> None:
        ok, reason = store.should_rotate()
        assert ok is False
        assert reason == ""

    def test_fresh_session_returns_false(self, store: SessionStore) -> None:
        _write_session(
            store,
            session_created_at=datetime.now(UTC).isoformat(),
            msg_count=5,
            context_percent=30,
        )
        ok, _ = store.should_rotate()
        assert ok is False

    # --- 나이 조건 ---
    def test_age_exceeded_returns_true(self, store: SessionStore) -> None:
        old_ts = (datetime.now(UTC) - timedelta(seconds=SESSION_MAX_AGE_SEC + 1)).isoformat()
        _write_session(store, session_created_at=old_ts)
        ok, reason = store.should_rotate()
        assert ok is True
        assert "age=" in reason

    def test_age_just_under_limit_returns_false(self, store: SessionStore) -> None:
        recent_ts = (datetime.now(UTC) - timedelta(seconds=SESSION_MAX_AGE_SEC - 60)).isoformat()
        _write_session(store, session_created_at=recent_ts)
        ok, _ = store.should_rotate()
        assert ok is False

    # --- context_percent 조건 ---
    def test_context_percent_at_limit_returns_true(self, store: SessionStore) -> None:
        _write_session(store, context_percent=SESSION_MAX_CONTEXT_PCT)
        ok, reason = store.should_rotate()
        assert ok is True
        assert "context_percent" in reason

    def test_context_percent_below_limit_returns_false(self, store: SessionStore) -> None:
        _write_session(store, context_percent=SESSION_MAX_CONTEXT_PCT - 1)
        ok, _ = store.should_rotate()
        assert ok is False

    # --- msg_count 조건 ---
    def test_msg_count_at_limit_returns_true(self, store: SessionStore) -> None:
        _write_session(store, msg_count=SESSION_MAX_MESSAGES)
        ok, reason = store.should_rotate()
        assert ok is True
        assert "msg_count" in reason

    def test_msg_count_below_limit_returns_false(self, store: SessionStore) -> None:
        _write_session(store, msg_count=SESSION_MAX_MESSAGES - 1)
        ok, _ = store.should_rotate()
        assert ok is False


class TestClearSessionId:
    def test_clears_session_id_and_created_at(self, store: SessionStore) -> None:
        _write_session(
            store,
            session_created_at=datetime.now(UTC).isoformat(),
            msg_count=10,
        )
        store.clear_session_id()
        data = store.load()
        assert data.get("session_id") is None
        assert data.get("session_created_at") is None
        # 다른 필드는 보존
        assert data.get("msg_count") == 10

    def test_get_session_id_returns_none_after_clear(self, store: SessionStore) -> None:
        _write_session(store)
        store.clear_session_id()
        assert store.get_session_id() is None


class TestSessionCreatedAt:
    def test_new_session_id_sets_created_at(self, store: SessionStore) -> None:
        before = datetime.now(UTC)
        store.update_runtime(session_id="new-session-id")
        data = store.load()
        assert "session_created_at" in data
        created = datetime.fromisoformat(data["session_created_at"])
        assert created >= before

    def test_same_session_id_does_not_reset_created_at(self, store: SessionStore) -> None:
        old_ts = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        _write_session(store, session_created_at=old_ts)
        # 동일 session_id로 update_runtime 호출
        store.update_runtime(session_id="abc-123")
        data = store.load()
        assert data.get("session_created_at") == old_ts  # 갱신되지 않아야 함
