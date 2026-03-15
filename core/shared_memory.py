"""공유 메모리 — 봇 간 세션 상태 공유.

네임스페이스 기반 키-값 스토어.
선택적으로 JSON 파일에 영속화.
MessageBus MEMORY_UPDATE 이벤트와 통합.

사용 예:
    mem = SharedMemory(bus=bus, persist_path=Path(".omc/shared_memory.json"))
    await mem.set("dev_bot", "last_result", {"files": ["a.py", "b.py"]})
    val = await mem.get("dev_bot", "last_result")
    snapshot = await mem.get_namespace("dev_bot")
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from loguru import logger

from core.message_bus import MessageBus, Event, EventType


class SharedMemory:
    """봇 간 공유 인메모리 상태 저장소.

    - 네임스페이스(봇 이름)별 키-값 저장
    - asyncio.Lock으로 동시성 안전
    - persist_path 지정 시 JSON 파일에 자동 저장/로드
    - 값 변경마다 MEMORY_UPDATE 이벤트 발행
    """

    def __init__(
        self,
        bus: MessageBus | None = None,
        persist_path: Path | None = None,
    ) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._bus = bus
        self._persist_path = persist_path
        self._lock = asyncio.Lock()

        if persist_path and persist_path.exists():
            self._load_from_disk()

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
    # 쓰기

    async def set(self, namespace: str, key: str, value: Any) -> None:
        """값 저장. 저장 후 MEMORY_UPDATE 이벤트 발행."""
        async with self._lock:
            self._store.setdefault(namespace, {})[key] = value
            await self._save_to_disk()

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
            await self._save_to_disk()

        if self._bus:
            await self._bus.publish(Event(
                type=EventType.MEMORY_UPDATE,
                source=namespace,
                data={"namespace": namespace, "keys": list(updates.keys())},
            ))

    async def delete(self, namespace: str, key: str) -> None:
        """특정 키 삭제."""
        async with self._lock:
            if namespace in self._store:
                self._store[namespace].pop(key, None)
            await self._save_to_disk()

    async def clear_namespace(self, namespace: str) -> None:
        """네임스페이스 전체 삭제."""
        async with self._lock:
            self._store.pop(namespace, None)
            await self._save_to_disk()
        logger.info(f"SharedMemory: 네임스페이스 삭제 — {namespace}")

    # ------------------------------------------------------------------
    # 읽기

    async def get(self, namespace: str, key: str, default: Any = None) -> Any:
        """값 조회. 없으면 default 반환."""
        async with self._lock:
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
