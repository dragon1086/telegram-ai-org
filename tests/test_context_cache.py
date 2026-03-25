"""ContextCache — SharedMemory 기반 ContextDB 캐시 레이어 테스트."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.context_cache import ContextCache
from core.shared_memory import SharedMemory

# ------------------------------------------------------------------
# 픽스처

@pytest.fixture
def mem():
    return SharedMemory(bus=None)


@pytest.fixture
def mock_db():
    """ContextDB 목 — aiosqlite 없이 테스트."""
    db = MagicMock()
    db.write_context = AsyncMock()
    db.read_context = AsyncMock(return_value=None)
    return db


@pytest.fixture
def cache(mock_db, mem):
    return ContextCache(db=mock_db, mem=mem, ttl_sec=60.0)


# ------------------------------------------------------------------
# 테스트

class TestContextCacheWrite:
    @pytest.mark.asyncio
    async def test_write_calls_db_and_cache(self, cache, mock_db, mem):
        """write()는 DB와 캐시 양쪽에 저장해야 한다."""
        await cache.write("s1", "proj1", "summary", "테스트 내용")

        mock_db.write_context.assert_called_once_with("s1", "proj1", "summary", "테스트 내용")
        cached = await mem.get("ctx_cache", "s1")
        assert cached is not None
        assert cached["content"] == "테스트 내용"
        assert cached["slot_type"] == "summary"


class TestContextCacheRead:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self, cache, mock_db):
        """캐시 hit 시 DB read_context가 호출되지 않아야 한다."""
        await cache.write("s2", "proj1", "summary", "캐시 내용")
        mock_db.read_context.reset_mock()

        result = await cache.read("s2")

        assert result is not None
        assert result["content"] == "캐시 내용"
        mock_db.read_context.assert_not_called()
        assert cache.stats()["hit"] == 1

    @pytest.mark.asyncio
    async def test_cache_miss_falls_back_to_db(self, cache, mock_db):
        """캐시 miss 시 DB에서 조회 후 캐시에 저장해야 한다."""
        mock_db.read_context.return_value = {
            "id": "s3",
            "project_id": "proj1",
            "slot_type": "result",
            "content": "DB 내용",
            "version": 1,
            "updated_at": "2026-03-22",
        }

        result = await cache.read("s3")

        assert result is not None
        assert result["content"] == "DB 내용"
        mock_db.read_context.assert_called_once_with("s3")
        assert cache.stats()["miss"] == 1

    @pytest.mark.asyncio
    async def test_read_returns_none_for_missing(self, cache, mock_db):
        """DB에도 없으면 None을 반환해야 한다."""
        mock_db.read_context.return_value = None
        result = await cache.read("nonexistent")
        assert result is None


class TestContextCacheInvalidate:
    @pytest.mark.asyncio
    async def test_invalidate_removes_from_cache_only(self, cache, mock_db, mem):
        """invalidate()는 캐시만 삭제하고 DB 쓰기 횟수에 영향 없어야 한다."""
        await cache.write("s4", "proj1", "summary", "삭제 테스트")
        await cache.invalidate("s4")

        cached = await mem.get("ctx_cache", "s4")
        assert cached is None
        assert mock_db.write_context.call_count == 1  # write 시 1회만


class TestContextCacheWarmUp:
    @pytest.mark.asyncio
    async def test_warm_up_loads_from_db(self, cache, mock_db, mem):
        """warm_up()은 DB 데이터를 캐시에 적재해야 한다. s6는 DB에 없어 미로드."""
        db_data = {
            "id": "s5",
            "project_id": "proj1",
            "slot_type": "context",
            "content": "워밍업 내용",
            "version": 1,
            "updated_at": "2026-03-22",
        }
        # s5 → 데이터 있음, s6 → None
        mock_db.read_context.side_effect = lambda sid: (
            db_data if sid == "s5" else None
        )

        loaded = await cache.warm_up(["s5", "s6"])

        assert loaded == 1
        cached = await mem.get("ctx_cache", "s5")
        assert cached is not None


class TestContextCacheStats:
    @pytest.mark.asyncio
    async def test_stats_tracks_hit_miss(self, cache, mock_db):
        """stats()는 hit/miss/hit_rate를 정확히 반환해야 한다."""
        await cache.write("s7", "proj1", "summary", "통계 테스트")
        await cache.read("s7")           # hit
        await cache.read("s7")           # hit
        await cache.read("nonexistent7") # miss

        stats = cache.stats()
        assert stats["hit"] == 2
        assert stats["miss"] == 1
        assert stats["hit_rate"] == pytest.approx(2 / 3, rel=1e-3)
