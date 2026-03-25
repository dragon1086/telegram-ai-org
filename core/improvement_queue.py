"""개선 작업 큐 — ImprovementItem 목록을 우선순위 큐로 관리하고
액션 디스패처를 통해 순서대로 실행한다.

사용법:
    from core.improvement_queue import ImprovementQueue
    queue = ImprovementQueue(dry_run=False)
    queue.enqueue(items)
    results = queue.run_all()
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    pass

from core.health_report_parser import ImprovementItem
from core.improvement_actions import (
    ActionResult,
    FixErrorPatternAction,
    LogOnlyAction,
    SplitLargeFileAction,
)

# ------------------------------------------------------------------
# 설정 로드
# ------------------------------------------------------------------

def _load_auto_actions() -> dict[str, str]:
    """improvement_thresholds.yaml의 auto_actions 섹션 로드."""
    config_path = Path(__file__).parent.parent / "improvement_thresholds.yaml"
    try:
        import yaml  # type: ignore
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("auto_actions", {})
    except Exception:
        return {}


# 기본 액션 매핑 (yaml 로드 실패 시 폴백)
_DEFAULT_ACTION_MAP: dict[str, str] = {
    "file_size_critical": "split_large_file",
    "file_size_warn": "log_only",
    "error_pattern": "fix_error_pattern",
}


# ------------------------------------------------------------------
# 큐 항목 (heapq 정렬용)
# ------------------------------------------------------------------

@dataclass(order=True)
class _QueueEntry:
    """우선순위 큐 항목. priority는 내림차순이므로 부호 반전."""
    neg_priority: int              # -item.priority (작을수록 먼저)
    seq: int                       # FIFO 동점 처리용 시퀀스
    item: ImprovementItem = field(compare=False)


# ------------------------------------------------------------------
# 실행 로그 포맷
# ------------------------------------------------------------------

@dataclass
class QueueRunLog:
    """큐 실행 결과 로그."""
    started_at: str
    finished_at: str
    total_items: int
    succeeded: int
    failed: int
    skipped: int
    results: list[ActionResult]

    def summary(self) -> str:
        lines = [
            "🔧 *개선 큐 실행 결과*",
            f"총 {self.total_items}개 | ✅ {self.succeeded} | ❌ {self.failed} | ⏭️ {self.skipped}",
            f"시작: {self.started_at[:19]}Z | 종료: {self.finished_at[:19]}Z",
        ]
        if self.results:
            lines.append("\n*실행 내역:*")
            for r in self.results[:10]:
                lines.append(f"  {r}")
            if len(self.results) > 10:
                lines.append(f"  ... 외 {len(self.results) - 10}개")
        return "\n".join(lines)


# ------------------------------------------------------------------
# 메인 큐 클래스
# ------------------------------------------------------------------

class ImprovementQueue:
    """ImprovementItem을 우선순위 큐로 관리하고 순서대로 실행한다."""

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._heap: list[_QueueEntry] = []
        self._seq = 0
        self._action_map = {**_DEFAULT_ACTION_MAP, **_load_auto_actions()}

    # ------------------------------------------------------------------
    # 큐 관리
    # ------------------------------------------------------------------

    def enqueue(self, items: list[ImprovementItem]) -> None:
        """ImprovementItem 목록을 큐에 추가 (priority 내림차순)."""
        for item in items:
            entry = _QueueEntry(
                neg_priority=-item.priority,
                seq=self._seq,
                item=item,
            )
            heapq.heappush(self._heap, entry)
            self._seq += 1
        logger.info(f"[ImprovementQueue] {len(items)}개 항목 추가 (총 큐 크기: {len(self._heap)})")

    def size(self) -> int:
        return len(self._heap)

    def clear(self) -> None:
        self._heap.clear()
        self._seq = 0

    def peek_all(self) -> list[ImprovementItem]:
        """큐의 모든 항목을 우선순위 순서로 반환 (큐 유지)."""
        return [e.item for e in sorted(self._heap)]

    # ------------------------------------------------------------------
    # 실행
    # ------------------------------------------------------------------

    def run_all(self) -> QueueRunLog:
        """큐의 모든 항목을 순서대로 실행하고 로그를 반환한다."""
        started_at = datetime.now(timezone.utc).isoformat()
        results: list[ActionResult] = []
        succeeded = failed = skipped = 0

        while self._heap:
            entry = heapq.heappop(self._heap)
            item = entry.item
            target_label = item.file_path or item.error_pattern or "unknown"

            logger.info(
                f"[ImprovementQueue] 실행 중 (priority={item.priority}): "
                f"{item.issue_type} → {target_label}"
            )

            action = self._build_action(item.issue_type)
            if action is None:
                logger.warning(f"[ImprovementQueue] 알 수 없는 issue_type={item.issue_type!r} — 스킵")
                skipped += 1
                results.append(ActionResult(
                    action_name="unknown",
                    target=target_label,
                    success=False,
                    dry_run=self.dry_run,
                    message=f"액션 미정의: {item.issue_type}",
                ))
                continue

            try:
                result = action.run(item)
                results.append(result)
                if result.success:
                    succeeded += 1
                    logger.info(f"[ImprovementQueue] 성공: {result}")
                else:
                    failed += 1
                    logger.warning(f"[ImprovementQueue] 실패: {result}")
            except Exception as e:
                failed += 1
                logger.error(f"[ImprovementQueue] 예외 발생 {target_label}: {e}")
                results.append(ActionResult(
                    action_name=getattr(action, "name", "unknown"),
                    target=target_label,
                    success=False,
                    dry_run=self.dry_run,
                    message=f"예외: {e}",
                ))

        finished_at = datetime.now(timezone.utc).isoformat()
        log = QueueRunLog(
            started_at=started_at,
            finished_at=finished_at,
            total_items=succeeded + failed + skipped,
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            results=results,
        )
        logger.info(
            f"[ImprovementQueue] 실행 완료 — "
            f"total={log.total_items}, ok={succeeded}, fail={failed}, skip={skipped}"
        )
        return log

    # ------------------------------------------------------------------
    # 내부
    # ------------------------------------------------------------------

    def _build_action(self, issue_type: str):
        """issue_type → 액션 인스턴스 반환."""
        action_name = self._action_map.get(issue_type)
        registry = {
            "split_large_file": SplitLargeFileAction,
            "fix_error_pattern": FixErrorPatternAction,
            "log_only": LogOnlyAction,
        }
        cls = registry.get(action_name or "")
        if cls is None:
            return None
        return cls(dry_run=self.dry_run)
