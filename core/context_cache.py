"""ContextDB 캐시 레이어 — SharedMemory를 인메모리 캐시로 활용.

읽기: SharedMemory → miss 시 ContextDB fallback
쓰기: ContextDB + SharedMemory 동시 write-through

사용 예:
    cache = ContextCache(db=context_db, mem=shared_memory)
    await cache.write("slot-1", "proj-1", "summary", "내용")
    result = await cache.read("slot-1")   # 캐시 hit 시 DB 조회 없음
    await cache.invalidate("slot-1")       # 캐시만 삭제
    await cache.warm_up(["slot-1", "slot-2"])  # 시작 시 캐시 워밍업
"""
from __future__ import annotations

import time
from typing import Any

from loguru import logger

from core.context_db import ContextDB
from core.shared_memory import SharedMemory

_CACHE_NS = "ctx_cache"          # SharedMemory 네임스페이스
_META_SUFFIX = ":_meta"          # 캐시 메타데이터 키 접미사 (캐시 시각)


class ContextCache:
    """SharedMemory 기반 ContextDB write-through 캐시.

    Args:
        db: ContextDB 인스턴스
        mem: SharedMemory 인스턴스
        ttl_sec: 캐시 항목 유효 시간 (초, None = 무제한)
    """

    def __init__(
        self,
        db: ContextDB,
        mem: SharedMemory,
        ttl_sec: float | None = 300.0,  # 기본 5분
    ) -> None:
        self._db = db
        self._mem = mem
        self._ttl = ttl_sec
        self._hit = 0
        self._miss = 0

    # ------------------------------------------------------------------
    # 쓰기 (write-through)

    async def write(
        self,
        slot_id: str,
        project_id: str,
        slot_type: str,
        content: str,
    ) -> None:
        """ContextDB와 SharedMemory에 동시 저장."""
        # 1. DB 영속화
        await self._db.write_context(slot_id, project_id, slot_type, content)

        # 2. 캐시 갱신
        payload = {
            "id": slot_id,
            "project_id": project_id,
            "slot_type": slot_type,
            "content": content,
        }
        await self._mem.set(_CACHE_NS, slot_id, payload)
        await self._mem.set(_CACHE_NS, slot_id + _META_SUFFIX, time.monotonic())
        logger.debug(f"ContextCache 쓰기: {slot_id}")

    # ------------------------------------------------------------------
    # 읽기 (read-through)

    async def read(self, slot_id: str) -> dict | None:
        """캐시 → DB 순으로 조회."""
        # 1. 캐시 확인
        cached = await self._mem.get(_CACHE_NS, slot_id)
        if cached is not None:
            if self._is_valid(slot_id, await self._mem.get(_CACHE_NS, slot_id + _META_SUFFIX)):
                self._hit += 1
                logger.debug(f"ContextCache HIT: {slot_id} (hit={self._hit})")
                return cached
            # TTL 만료 → 캐시 삭제 후 DB로
            await self._mem.delete(_CACHE_NS, slot_id)
            await self._mem.delete(_CACHE_NS, slot_id + _META_SUFFIX)

        # 2. DB fallback + 캐시 충전
        self._miss += 1
        row = await self._db.read_context(slot_id)
        if row:
            await self._mem.set(_CACHE_NS, slot_id, row)
            await self._mem.set(_CACHE_NS, slot_id + _META_SUFFIX, time.monotonic())
            logger.debug(f"ContextCache MISS→DB: {slot_id} (miss={self._miss})")
        return row

    # ------------------------------------------------------------------
    # 캐시 관리

    async def invalidate(self, slot_id: str) -> None:
        """특정 슬롯 캐시 무효화 (DB는 유지)."""
        await self._mem.delete(_CACHE_NS, slot_id)
        await self._mem.delete(_CACHE_NS, slot_id + _META_SUFFIX)
        logger.debug(f"ContextCache 무효화: {slot_id}")

    async def warm_up(self, slot_ids: list[str]) -> int:
        """시작 시 지정 슬롯들을 DB에서 읽어 캐시에 로드.

        Returns:
            실제로 로드된 슬롯 수
        """
        loaded = 0
        for slot_id in slot_ids:
            row = await self._db.read_context(slot_id)
            if row:
                await self._mem.set(_CACHE_NS, slot_id, row)
                await self._mem.set(_CACHE_NS, slot_id + _META_SUFFIX, time.monotonic())
                loaded += 1
        logger.info(f"ContextCache 워밍업 완료: {loaded}/{len(slot_ids)} 슬롯 로드")
        return loaded

    def stats(self) -> dict[str, Any]:
        """캐시 히트율 통계."""
        total = self._hit + self._miss
        hit_rate = self._hit / total if total else 0.0
        return {
            "hit": self._hit,
            "miss": self._miss,
            "total": total,
            "hit_rate": round(hit_rate, 3),
            "ttl_sec": self._ttl,
        }

    # ------------------------------------------------------------------
    # 내부

    def _is_valid(self, slot_id: str, cached_at: float | None) -> bool:
        """TTL 유효성 확인."""
        if self._ttl is None:
            return True
        if cached_at is None:
            return False
        return (time.monotonic() - cached_at) < self._ttl
