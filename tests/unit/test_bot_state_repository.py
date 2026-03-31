"""Unit tests for core/repositories/bot_state_repository.py.

Tests cover:
  - Feature flag off: all operations are safe no-ops.
  - Feature flag on: initialize, update_state, get_state, get_all_alive, mark_dead.
  - Edge cases: missing bot_id, empty state, double update, mark_dead non-existent.
"""
from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# Helpers — force flag value per test
# ---------------------------------------------------------------------------


def _make_repo(enabled: bool, db_path: str = ":memory:"):
    """Return a fresh BotStateRepository with the given flag value."""
    os.environ["ENABLE_REPOSITORY_PATTERN"] = "1" if enabled else "0"
    # Re-import to pick up the flag at module level (env var matters at import time
    # for the module-level constant, but the class reads it at call time via the
    # global ENABLE_REPOSITORY_PATTERN re-checked each method).
    import sys
    mod_name = "core.repositories.bot_state_repository"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    from core.repositories.bot_state_repository import BotStateRepository
    return BotStateRepository(db_path=db_path)


# ---------------------------------------------------------------------------
# Flag=off tests
# ---------------------------------------------------------------------------


class TestBotStateRepositoryDisabled:
    def setup_method(self):
        self.repo = _make_repo(enabled=False)

    @pytest.mark.asyncio
    async def test_initialize_is_noop(self):
        # Should not raise
        await self.repo.initialize()

    @pytest.mark.asyncio
    async def test_update_state_is_noop(self):
        await self.repo.initialize()
        await self.repo.update_state("bot1", {"is_alive": True})

    @pytest.mark.asyncio
    async def test_get_state_returns_none(self):
        await self.repo.initialize()
        result = await self.repo.get_state("bot1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_alive_returns_empty(self):
        await self.repo.initialize()
        result = await self.repo.get_all_alive()
        assert result == []

    @pytest.mark.asyncio
    async def test_mark_dead_is_noop(self):
        await self.repo.initialize()
        await self.repo.mark_dead("bot1")  # must not raise


# ---------------------------------------------------------------------------
# Flag=on tests
# ---------------------------------------------------------------------------


class TestBotStateRepositoryEnabled:
    """Flag=on: aiosqlite :memory: 를 사용하는 테스트.

    _shared_conn 을 닫지 않으면 aiosqlite 백그라운드 스레드가 남아
    pytest 프로세스가 종료되지 않는다 (hang). 각 테스트 종료 시 정리한다.
    """

    def setup_method(self):
        self.repo = _make_repo(enabled=True)

    async def _close_repo(self):
        """aiosqlite :memory: 연결의 백그라운드 스레드를 정리한다."""
        conn = getattr(self.repo, "_shared_conn", None)
        if conn is not None:
            await conn.close()
            self.repo._shared_conn = None

    @pytest.mark.asyncio
    async def test_initialize_creates_table(self):
        await self.repo.initialize()
        try:
            result = await self.repo.get_all_alive()
            assert isinstance(result, list)
        finally:
            await self._close_repo()

    @pytest.mark.asyncio
    async def test_update_and_get_state(self):
        await self.repo.initialize()
        try:
            await self.repo.update_state("bot_a", {"is_alive": True, "version": "1.0"})
            state = await self.repo.get_state("bot_a")
            assert state is not None
            assert state["bot_id"] == "bot_a"
            assert state["is_alive"] is True
            assert state["state"]["version"] == "1.0"
        finally:
            await self._close_repo()

    @pytest.mark.asyncio
    async def test_get_state_missing_returns_none(self):
        await self.repo.initialize()
        try:
            result = await self.repo.get_state("nonexistent_bot")
            assert result is None
        finally:
            await self._close_repo()

    @pytest.mark.asyncio
    async def test_update_state_overwrites(self):
        await self.repo.initialize()
        try:
            await self.repo.update_state("bot_b", {"is_alive": True, "v": 1})
            await self.repo.update_state("bot_b", {"is_alive": True, "v": 2})
            state = await self.repo.get_state("bot_b")
            assert state["state"]["v"] == 2
        finally:
            await self._close_repo()

    @pytest.mark.asyncio
    async def test_get_all_alive_returns_alive_bots(self):
        await self.repo.initialize()
        try:
            await self.repo.update_state("alive_bot", {"is_alive": True})
            await self.repo.update_state("dead_bot", {"is_alive": False})
            alive = await self.repo.get_all_alive()
            alive_ids = {r["bot_id"] for r in alive}
            assert "alive_bot" in alive_ids
            assert "dead_bot" not in alive_ids
        finally:
            await self._close_repo()

    @pytest.mark.asyncio
    async def test_mark_dead_sets_is_alive_false(self):
        await self.repo.initialize()
        try:
            await self.repo.update_state("victim", {"is_alive": True})
            await self.repo.mark_dead("victim")
            state = await self.repo.get_state("victim")
            assert state is not None
            assert state["is_alive"] is False
        finally:
            await self._close_repo()

    @pytest.mark.asyncio
    async def test_mark_dead_nonexistent_is_noop(self):
        await self.repo.initialize()
        try:
            await self.repo.mark_dead("ghost_bot")
        finally:
            await self._close_repo()

    @pytest.mark.asyncio
    async def test_update_state_empty_dict(self):
        await self.repo.initialize()
        try:
            await self.repo.update_state("minimal_bot", {})
            state = await self.repo.get_state("minimal_bot")
            assert state is not None
            assert isinstance(state["state"], dict)
        finally:
            await self._close_repo()

    @pytest.mark.asyncio
    async def test_multiple_bots(self):
        await self.repo.initialize()
        try:
            for i in range(5):
                await self.repo.update_state(f"bot_{i}", {"is_alive": True, "index": i})
            alive = await self.repo.get_all_alive()
            assert len(alive) == 5
        finally:
            await self._close_repo()
