"""SharedMemory 캐시 레이어 단위 테스트.

검증 시나리오:
1. 캐시 히트 — set() 후 get()이 context_db 호출 없이 캐시에서 반환
2. 캐시 미스 — 캐시 없을 때 context_db에서 로드 후 캐시 적재
3. TTL 만료 무효화 — TTL 경과 후 캐시 미스로 context_db 재조회
4. 명시적 무효화 — invalidate() 후 캐시 미스로 context_db 재조회
5. 네임스페이스 무효화 — invalidate_namespace() 전체 제거
6. delete() — 캐시 + 타임스탬프 모두 제거
7. clear_namespace() — 네임스페이스 전체 삭제
8. context_db 없이 기존 동작 유지
9. cache_stats() 반환값 검증
10. update() 여러 키 동시 캐시 적재
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.shared_memory import SharedMemory, _slot_id

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_mock_db(stored: dict | None = None) -> MagicMock:
    """context_db Mock 생성. stored dict를 백엔드 저장소로 사용."""
    _backend: dict = stored if stored is not None else {}
    db = MagicMock()

    async def write_context(slot_id: str, project_id: str, slot_type: str, content: str) -> None:
        import json
        _backend[slot_id] = json.loads(content)

    async def read_context(slot_id: str) -> dict | None:
        import json
        val = _backend.get(slot_id)
        if val is None:
            return None
        return {"content": json.dumps(val)}

    async def delete_context(slot_id: str) -> None:
        _backend.pop(slot_id, None)

    async def delete_project_contexts(project_id: str) -> None:
        keys = [k for k in list(_backend.keys()) if k.startswith(f"{project_id}/")]
        for k in keys:
            _backend.pop(k, None)

    db.write_context = write_context
    db.read_context = read_context
    db.delete_context = delete_context
    db.delete_project_contexts = delete_project_contexts
    db._backend = _backend
    return db


@pytest.fixture
def mock_db():
    return make_mock_db()


# ---------------------------------------------------------------------------
# 1. 캐시 히트
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_hit_no_db_call(mock_db):
    """set() 이후 get()이 캐시에서 반환 — context_db.read_context 호출 없음."""
    mem = SharedMemory(context_db=mock_db, cache_ttl=60.0)
    await mem.set("ns", "key", "value_a")

    # read_context를 spy로 감싸 호출 여부 확인
    original_read = mock_db.read_context
    call_count = 0

    async def counting_read(slot_id):
        nonlocal call_count
        call_count += 1
        return await original_read(slot_id)

    mock_db.read_context = counting_read

    result = await mem.get("ns", "key")
    assert result == "value_a"
    assert call_count == 0, "캐시 히트 시 context_db.read_context가 호출되면 안 됨"


# ---------------------------------------------------------------------------
# 2. 캐시 미스 → context_db 로드
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_miss_loads_from_db(mock_db):
    """캐시가 없을 때 context_db에서 값을 로드하고 캐시에 적재."""
    # context_db에 직접 데이터 삽입 (캐시 우회)
    mock_db._backend[_slot_id("ns", "key")] = {"data": 42}

    mem = SharedMemory(context_db=mock_db, cache_ttl=60.0)
    result = await mem.get("ns", "key")
    assert result == {"data": 42}

    # 이후 get()은 캐시 히트여야 함
    original_read = mock_db.read_context
    call_count = 0

    async def counting_read(slot_id):
        nonlocal call_count
        call_count += 1
        return await original_read(slot_id)

    mock_db.read_context = counting_read
    result2 = await mem.get("ns", "key")
    assert result2 == {"data": 42}
    assert call_count == 0, "두 번째 get()은 캐시 히트여야 함"


# ---------------------------------------------------------------------------
# 3. TTL 만료 무효화
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ttl_expiry_triggers_db_reload(mock_db):
    """TTL 경과 후 캐시 미스로 context_db 재조회."""
    mem = SharedMemory(context_db=mock_db, cache_ttl=0.05)  # 50ms TTL
    await mem.set("ns", "key", "old_value")

    # TTL 경과 시뮬레이션 — 캐시 타임스탬프를 과거로 조작
    mem._cache_ts["ns"]["key"] = time.monotonic() - 1.0  # 1초 전

    # context_db에는 새 값이 있다고 가정
    mock_db._backend[_slot_id("ns", "key")] = "new_value"

    result = await mem.get("ns", "key")
    assert result == "new_value", "TTL 만료 후 context_db에서 새 값을 로드해야 함"


# ---------------------------------------------------------------------------
# 4. 명시적 무효화 (invalidate)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalidate_triggers_db_reload(mock_db):
    """invalidate() 후 get()이 context_db에서 새 값 로드."""
    mem = SharedMemory(context_db=mock_db, cache_ttl=60.0)
    await mem.set("ns", "key", "original")

    # context_db에 업데이트된 값 삽입
    mock_db._backend[_slot_id("ns", "key")] = "updated"

    await mem.invalidate("ns", "key")

    result = await mem.get("ns", "key")
    assert result == "updated", "invalidate() 후 context_db 새 값을 반환해야 함"


# ---------------------------------------------------------------------------
# 5. 네임스페이스 전체 무효화 (invalidate_namespace)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalidate_namespace(mock_db):
    """invalidate_namespace() 후 모든 키가 캐시 미스."""
    mem = SharedMemory(context_db=mock_db, cache_ttl=60.0)
    await mem.set("ns", "k1", "v1")
    await mem.set("ns", "k2", "v2")

    await mem.invalidate_namespace("ns")

    # 캐시 타임스탬프 제거 확인
    assert "ns" not in mem._cache_ts
    # _store에서도 제거
    assert "ns" not in mem._store


# ---------------------------------------------------------------------------
# 6. delete() — 캐시 + 타임스탬프 제거
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_removes_cache_and_ts(mock_db):
    """delete() 후 캐시 타임스탬프가 제거되고 get()은 default 반환."""
    mem = SharedMemory(context_db=mock_db, cache_ttl=60.0)
    await mem.set("ns", "key", "some_val")

    assert mem._is_cache_valid("ns", "key")

    await mem.delete("ns", "key")

    assert not mem._is_cache_valid("ns", "key"), "delete() 후 캐시가 무효화되어야 함"
    result = await mem.get("ns", "key", default="NONE")
    # context_db에도 없으므로 default 반환
    assert result == "NONE"


# ---------------------------------------------------------------------------
# 7. clear_namespace() — 네임스페이스 전체 삭제
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clear_namespace(mock_db):
    """clear_namespace() 후 해당 네임스페이스의 모든 캐시 및 스토어 제거."""
    mem = SharedMemory(context_db=mock_db, cache_ttl=60.0)
    await mem.set("ns", "k1", 1)
    await mem.set("ns", "k2", 2)

    await mem.clear_namespace("ns")

    assert "ns" not in mem._store
    assert "ns" not in mem._cache_ts


# ---------------------------------------------------------------------------
# 8. context_db 없이 기존 동작 유지
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_context_db_backward_compat():
    """context_db 없이 기존 SharedMemory 동작이 그대로 유지됨."""
    mem = SharedMemory()
    await mem.set("ns", "key", "hello")
    result = await mem.get("ns", "key")
    assert result == "hello"

    await mem.delete("ns", "key")
    result2 = await mem.get("ns", "key", default="gone")
    assert result2 == "gone"


# ---------------------------------------------------------------------------
# 9. cache_stats()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_stats(mock_db):
    """cache_stats()가 올바른 통계를 반환한다."""
    mem = SharedMemory(context_db=mock_db, cache_ttl=60.0)
    await mem.set("ns1", "k1", 1)
    await mem.set("ns1", "k2", 2)
    await mem.set("ns2", "k1", 3)

    stats = mem.cache_stats()
    assert stats["namespaces"] == 2
    assert stats["total_keys"] == 3
    assert stats["context_db_enabled"] is True
    assert stats["ttl"] == 60.0
    assert stats["expired_keys"] == 0


@pytest.mark.asyncio
async def test_cache_stats_expired(mock_db):
    """TTL 만료된 키가 expired_keys에 반영된다."""
    mem = SharedMemory(context_db=mock_db, cache_ttl=60.0)
    await mem.set("ns", "key", "val")

    # 타임스탬프를 과거로 조작
    mem._cache_ts["ns"]["key"] = time.monotonic() - 120.0

    stats = mem.cache_stats()
    assert stats["expired_keys"] == 1


# ---------------------------------------------------------------------------
# 10. update() — 여러 키 동시 캐시 적재
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_marks_all_keys_cached(mock_db):
    """update()로 여러 키를 한 번에 저장하면 모두 캐시에 적재됨."""
    mem = SharedMemory(context_db=mock_db, cache_ttl=60.0)
    await mem.update("ns", {"a": 1, "b": 2, "c": 3})

    assert mem._is_cache_valid("ns", "a")
    assert mem._is_cache_valid("ns", "b")
    assert mem._is_cache_valid("ns", "c")

    # get()이 캐시 히트
    assert await mem.get("ns", "a") == 1
    assert await mem.get("ns", "b") == 2
    assert await mem.get("ns", "c") == 3


# ---------------------------------------------------------------------------
# 11. TTL=0 (무제한) — 명시적 삭제 전까지 유효
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ttl_zero_never_expires(mock_db):
    """cache_ttl=0이면 항상 캐시 히트 (명시적 삭제 전까지)."""
    mem = SharedMemory(context_db=mock_db, cache_ttl=0)
    await mem.set("ns", "key", "persistent")

    # 타임스탬프를 매우 오래된 값으로 설정해도 TTL=0이므로 유효
    mem._cache_ts["ns"]["key"] = time.monotonic() - 99999.0

    call_count = 0
    original_read = mock_db.read_context

    async def counting_read(slot_id):
        nonlocal call_count
        call_count += 1
        return await original_read(slot_id)

    mock_db.read_context = counting_read

    result = await mem.get("ns", "key")
    assert result == "persistent"
    assert call_count == 0, "TTL=0이면 영구 캐시 히트여야 함"
