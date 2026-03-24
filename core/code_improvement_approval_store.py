"""코드 자동 수정 승인 게이트 저장소.

SelfCodeImprover 실행 전 Rocky의 승인을 요구하기 위한 대기 큐.
RoutingApprovalStore 패턴을 따른다.

상태 흐름:
    pending  → (Rocky 승인) → approved  → SelfCodeImprover.fix() 실행
    pending  → (Rocky 거부) → rejected  → 스킵
    pending  → (24h 경과)  → expired   → 자동 만료

저장 경로: data/code_improvement_approval.json
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_DEFAULT_PATH = Path(__file__).parent.parent / "data" / "code_improvement_approval.json"


class CodeImprovementApprovalStore:
    """pending / approved / rejected 코드 수정 신호 저장소."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 읽기
    # ------------------------------------------------------------------

    def _load(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, list) else []
        except Exception:
            return []

    # ------------------------------------------------------------------
    # 쓰기
    # ------------------------------------------------------------------

    def _save(self, items: list[dict]) -> None:
        self._path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def enqueue(self, signal_dict: dict) -> str:
        """신호를 pending 상태로 큐에 추가. 생성된 approval_id 반환."""
        items = self._load()
        approval_id = uuid.uuid4().hex[:12]
        items.append(
            {
                "approval_id": approval_id,
                "status": "pending",
                "queued_at": datetime.now(timezone.utc).isoformat(),
                "signal": signal_dict,
            }
        )
        self._save(items)
        return approval_id

    def approve(self, approval_id: str) -> bool:
        """approval_id 항목을 approved 상태로 전환. 성공 여부 반환."""
        items = self._load()
        for item in items:
            if item["approval_id"] == approval_id:
                item["status"] = "approved"
                item["decided_at"] = datetime.now(timezone.utc).isoformat()
                self._save(items)
                return True
        return False

    def reject(self, approval_id: str) -> bool:
        """approval_id 항목을 rejected 상태로 전환. 성공 여부 반환."""
        items = self._load()
        for item in items:
            if item["approval_id"] == approval_id:
                item["status"] = "rejected"
                item["decided_at"] = datetime.now(timezone.utc).isoformat()
                self._save(items)
                return True
        return False

    def get_status(self, approval_id: str) -> str | None:
        """approval_id의 현재 상태 반환. 없으면 None."""
        for item in self._load():
            if item["approval_id"] == approval_id:
                return item["status"]
        return None

    def list_pending(self) -> list[dict]:
        """pending 상태 항목 전체 반환."""
        return [i for i in self._load() if i["status"] == "pending"]

    def list_approved(self) -> list[dict]:
        """approved 상태 항목 전체 반환."""
        return [i for i in self._load() if i["status"] == "approved"]

    def mark_executed(self, approval_id: str) -> None:
        """실행 완료 처리 — executed 상태로 전환."""
        items = self._load()
        for item in items:
            if item["approval_id"] == approval_id:
                item["status"] = "executed"
                item["executed_at"] = datetime.now(timezone.utc).isoformat()
                self._save(items)
                return

    def clear_executed(self) -> int:
        """executed 상태 항목 정리. 제거된 항목 수 반환."""
        items = self._load()
        before = len(items)
        items = [i for i in items if i["status"] != "executed"]
        self._save(items)
        return before - len(items)

    def expire_old_pending(self, hours: int = 24) -> list[dict]:
        """pending 상태에서 hours 시간 초과한 항목을 expired로 전환. 만료된 항목 반환."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        items = self._load()
        expired: list[dict] = []
        for item in items:
            if item["status"] == "pending" and item.get("queued_at", "") < cutoff:
                item["status"] = "expired"
                item["expired_at"] = datetime.now(timezone.utc).isoformat()
                expired.append(item)
        if expired:
            self._save(items)
        return expired

    def list_expired(self) -> list[dict]:
        """expired 상태 항목 전체 반환."""
        return [i for i in self._load() if i["status"] == "expired"]
