"""공유 메모리 — 봇 간 세션 상태 공유.

네임스페이스 기반 키-값 스토어.
선택적으로 JSON 파일에 영속화.
MessageBus MEMORY_UPDATE 이벤트와 통합.

캐시 레이어:
    context_db 옵션 활성화 시, 읽기/쓰기 경로에 인메모리 캐시를 삽입한다.
    - 읽기: 캐시 히트(TTL 내) → 즉시 반환 / 미스 → context_db 조회 후 캐시 적재
    - 쓰기: 캐시 + context_db 동시 기록
    - 무효화: TTL 만료 또는 invalidate() 명시적 호출

사용 예:
    mem = SharedMemory(bus=bus, persist_path=Path(".omc/shared_memory.json"))
    await mem.set("dev_bot", "last_result", {"files": ["a.py", "b.py"]})
    val = await mem.get("dev_bot", "last_result")
    snapshot = await mem.get_namespace("dev_bot")

    # context_db 캐시 레이어 활성화
    from core.context_db import ContextDB
    db = ContextDB(); await db.initialize()
    mem = SharedMemory(context_db=db, cache_ttl=300.0)
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from core.message_bus import Event, EventType, MessageBus

if TYPE_CHECKING:
    from core.context_db import ContextDB


# context_db 슬롯 ID 생성 규칙: "{namespace}/{key}"
def _slot_id(namespace: str, key: str) -> str:
    return f"{namespace}/{key}"


class SharedMemory:
    """봇 간 공유 인메모리 상태 저장소.

    - 네임스페이스(봇 이름)별 키-값 저장
    - asyncio.Lock으로 동시성 안전
    - persist_path 지정 시 JSON 파일에 자동 저장/로드
    - 값 변경마다 MEMORY_UPDATE 이벤트 발행
    - context_db 지정 시 인메모리 캐시 → context_db 2-tier 저장 활성화
    """

    def __init__(
        self,
        bus: MessageBus | None = None,
        persist_path: Path | None = None,
        context_db: "ContextDB | None" = None,
        cache_ttl: float = 300.0,
    ) -> None:
        """
        Args:
            bus: MessageBus 인스턴스 (MEMORY_UPDATE 이벤트 발행용).
            persist_path: JSON 파일 영속화 경로.
            context_db: ContextDB 인스턴스. 지정 시 캐시 레이어 활성화.
            cache_ttl: 캐시 항목 유효 시간(초). 0이면 TTL 비활성(명시적 삭제만).
        """
        self._store: dict[str, dict[str, Any]] = {}
        self._bus = bus
        self._persist_path = persist_path
        self._lock = asyncio.Lock()

        # 캐시 레이어
        self._context_db = context_db
        self._cache_ttl = cache_ttl
        # _cache_ts[namespace][key] = 캐시에 적재된 시각 (time.monotonic())
        self._cache_ts: dict[str, dict[str, float]] = {}

        if persist_path and persist_path.exists():
            self._load_from_disk()

    # ------------------------------------------------------------------
    # 캐시 유효성 헬퍼

    def _is_cache_valid(self, namespace: str, key: str) -> bool:
        """캐시 히트 여부 확인 (TTL 검사 포함)."""
        ns_ts = self._cache_ts.get(namespace, {})
        if key not in ns_ts:
            return False
        if self._cache_ttl <= 0:
            return True  # TTL 비활성: 명시적 삭제 전까지 유효
        return (time.monotonic() - ns_ts[key]) < self._cache_ttl

    def _mark_cached(self, namespace: str, key: str) -> None:
        """캐시 타임스탬프 갱신."""
        self._cache_ts.setdefault(namespace, {})[key] = time.monotonic()

    def _evict_cache(self, namespace: str, key: str) -> None:
        """특정 키 캐시 무효화."""
        self._cache_ts.get(namespace, {}).pop(key, None)
        self._store.get(namespace, {}).pop(key, None)

    def _evict_namespace(self, namespace: str) -> None:
        """네임스페이스 전체 캐시 무효화."""
        self._cache_ts.pop(namespace, None)
        self._store.pop(namespace, None)

    # ------------------------------------------------------------------
    # 디스크 I/O

    def _load_from_disk(self) -> None:
        try:
            raw = self._persist_path.read_text(encoding="utf-8")  # type: ignore[union-attr]
            self._store = json.loads(raw)
            logger.info(
                f"SharedMemory: 디스크 로드 완료 "
                f"({len(self._store)} 네임스페이스, {self._persist_path})"
            )
        except Exception as e:
            logger.warning(f"SharedMemory 로드 실패: {e}")

    async def _save_to_disk(self) -> None:
        if not self._persist_path:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._persist_path.write_text(
                json.dumps(self._store, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"SharedMemory 저장 실패: {e}")

    # ------------------------------------------------------------------
    # context_db I/O

    async def _db_write(self, namespace: str, key: str, value: Any) -> None:
        """context_db에 값 기록 (context_slots 테이블 사용)."""
        if not self._context_db:
            return
        try:
            # project_id = namespace, slot_type = key, content = JSON
            await self._context_db.write_context(
                slot_id=_slot_id(namespace, key),
                project_id=namespace,
                slot_type=key,
                content=json.dumps(value, ensure_ascii=False),
            )
        except Exception as e:
            logger.warning(f"SharedMemory context_db 쓰기 실패 {namespace}/{key}: {e}")

    async def _db_delete(self, namespace: str, key: str) -> None:
        """context_db에서 슬롯 삭제."""
        if not self._context_db:
            return
        try:
            await self._context_db.delete_context(_slot_id(namespace, key))
        except Exception as e:
            logger.warning(f"SharedMemory context_db 삭제 실패 {namespace}/{key}: {e}")

    async def _db_delete_namespace(self, namespace: str) -> None:
        """context_db에서 네임스페이스 전체 삭제."""
        if not self._context_db:
            return
        try:
            await self._context_db.delete_project_contexts(namespace)
        except Exception as e:
            logger.warning(f"SharedMemory context_db 네임스페이스 삭제 실패 {namespace}: {e}")

    async def _db_read(self, namespace: str, key: str) -> Any:
        """context_db에서 값 조회. 없으면 None."""
        if not self._context_db:
            return None
        try:
            row = await self._context_db.read_context(_slot_id(namespace, key))
            if row is None:
                return None
            return json.loads(row["content"])
        except Exception as e:
            logger.warning(f"SharedMemory context_db 읽기 실패 {namespace}/{key}: {e}")
            return None

    # ------------------------------------------------------------------
    # 쓰기

    async def set(self, namespace: str, key: str, value: Any) -> None:
        """값 저장. 캐시 + context_db(활성화 시) + 디스크에 기록.
        저장 후 MEMORY_UPDATE 이벤트 발행.
        """
        async with self._lock:
            self._store.setdefault(namespace, {})[key] = value
            self._mark_cached(namespace, key)
            await self._save_to_disk()
            await self._db_write(namespace, key, value)

        if self._bus:
            await self._bus.publish(Event(
                type=EventType.MEMORY_UPDATE,
                source=namespace,
                data={"namespace": namespace, "key": key, "value": value},
            ))
        logger.debug(f"SharedMemory 설정: {namespace}/{key}")

    async def update(self, namespace: str, updates: dict[str, Any]) -> None:
        """여러 키를 한 번에 업데이트. 개별 set() 대비 이벤트 발행은 1회."""
        async with self._lock:
            self._store.setdefault(namespace, {}).update(updates)
            for key, value in updates.items():
                self._mark_cached(namespace, key)
                await self._db_write(namespace, key, value)
            await self._save_to_disk()

        if self._bus:
            await self._bus.publish(Event(
                type=EventType.MEMORY_UPDATE,
                source=namespace,
                data={"namespace": namespace, "keys": list(updates.keys())},
            ))

    async def delete(self, namespace: str, key: str) -> None:
        """특정 키 삭제 (캐시 + context_db + 영속 저장소)."""
        async with self._lock:
            if namespace in self._store:
                self._store[namespace].pop(key, None)
            self._evict_cache(namespace, key)
            await self._save_to_disk()
            await self._db_delete(namespace, key)

    async def clear_namespace(self, namespace: str) -> None:
        """네임스페이스 전체 삭제 (캐시 + context_db 포함)."""
        async with self._lock:
            self._evict_namespace(namespace)
            await self._save_to_disk()
            await self._db_delete_namespace(namespace)
        logger.info(f"SharedMemory: 네임스페이스 삭제 — {namespace}")

    # ------------------------------------------------------------------
    # 읽기

    async def get(self, namespace: str, key: str, default: Any = None) -> Any:
        """값 조회.

        1. 캐시 히트(TTL 내) → 즉시 반환
        2. 캐시 미스 → context_db 조회 → 히트 시 캐시 적재 후 반환
        3. context_db도 없으면 default 반환
        """
        async with self._lock:
            # 1) 캐시 히트
            if self._is_cache_valid(namespace, key):
                value = self._store.get(namespace, {}).get(key, default)
                logger.debug(f"SharedMemory 캐시 히트: {namespace}/{key}")
                return value

            # 2) 캐시 미스 → context_db 조회
            db_value = await self._db_read(namespace, key)
            if db_value is not None:
                logger.debug(f"SharedMemory 캐시 미스 → context_db 로드: {namespace}/{key}")
                self._store.setdefault(namespace, {})[key] = db_value
                self._mark_cached(namespace, key)
                return db_value

            # 3) 기존 _store에 있으면 반환 (캐시 TS 없는 경우 — 디스크 로드 직후 등)
            return self._store.get(namespace, {}).get(key, default)

    async def get_namespace(self, namespace: str) -> dict[str, Any]:
        """네임스페이스 전체 조회."""
        async with self._lock:
            return dict(self._store.get(namespace, {}))

    async def get_all(self) -> dict[str, dict[str, Any]]:
        """전체 스토어 조회."""
        async with self._lock:
            return {ns: dict(data) for ns, data in self._store.items()}

    async def exists(self, namespace: str, key: str) -> bool:
        async with self._lock:
            return key in self._store.get(namespace, {})

    async def list_namespaces(self) -> list[str]:
        async with self._lock:
            return list(self._store.keys())

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """현재 상태 동기 스냅샷 (읽기 전용 복사본)."""
        return {ns: dict(data) for ns, data in self._store.items()}

    # ------------------------------------------------------------------
    # 캐시 무효화 (명시적)

    async def invalidate(self, namespace: str, key: str) -> None:
        """특정 키를 캐시에서 제거 (context_db 데이터는 유지).

        다음 get() 호출 시 context_db에서 새로 로드한다.
        """
        async with self._lock:
            ns_ts = self._cache_ts.get(namespace, {})
            ns_ts.pop(key, None)
            self._store.get(namespace, {}).pop(key, None)
        logger.debug(f"SharedMemory 캐시 무효화: {namespace}/{key}")

    async def invalidate_namespace(self, namespace: str) -> None:
        """네임스페이스 전체를 캐시에서 제거 (context_db 데이터는 유지).

        다음 get() 호출 시 context_db에서 새로 로드한다.
        """
        async with self._lock:
            self._cache_ts.pop(namespace, None)
            self._store.pop(namespace, None)
        logger.debug(f"SharedMemory 네임스페이스 캐시 무효화: {namespace}")

    def cache_stats(self) -> dict[str, Any]:
        """현재 캐시 상태 통계 반환 (디버그용)."""
        now = time.monotonic()
        stats: dict[str, Any] = {
            "namespaces": len(self._cache_ts),
            "total_keys": sum(len(v) for v in self._cache_ts.values()),
            "ttl": self._cache_ttl,
            "context_db_enabled": self._context_db is not None,
        }
        if self._cache_ttl > 0:
            expired = sum(
                1
                for ns_ts in self._cache_ts.values()
                for ts in ns_ts.values()
                if (now - ts) >= self._cache_ttl
            )
            stats["expired_keys"] = expired
        return stats
