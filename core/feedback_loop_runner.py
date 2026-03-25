"""피드백 루프 오케스트레이터 — 건강 리포트 수신부터 자가개선 완료까지 전 과정을 관리.

흐름:
    1. 건강 리포트 수신 (CodeHealthReport / dict / 텍스트)
    2. HealthReportParser → ImprovementItem 목록 생성
    3. ImprovementQueue → 우선순위 큐 생성 및 실행
    4. CodeHealthMonitor 재스캔 → 해소된 항목 확인
    5. 미해소 항목이 있으면 큐에 재적재 또는 알림 발송
    6. max_iterations 초과 시 루프 종료

사용법:
    from core.feedback_loop_runner import FeedbackLoopRunner
    runner = FeedbackLoopRunner(dry_run=False)
    summary = runner.run(health_report)
    print(summary.format())
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from core.health_report_parser import HealthReportParser, ImprovementItem
from core.improvement_queue import ImprovementQueue, QueueRunLog

# ------------------------------------------------------------------
# 설정
# ------------------------------------------------------------------

def _load_loop_config() -> dict:
    config_path = Path(__file__).parent.parent / "improvement_thresholds.yaml"
    try:
        import yaml  # type: ignore
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("feedback_loop", {})
    except Exception:
        return {}


# ------------------------------------------------------------------
# 결과 데이터 클래스
# ------------------------------------------------------------------

@dataclass
class LoopIterationResult:
    """단일 이터레이션(실행+재스캔) 결과."""
    iteration: int
    items_before: int           # 실행 전 항목 수
    queue_log: QueueRunLog
    items_after: int            # 재스캔 후 잔존 항목 수
    resolved_items: list[str]   # 해소된 항목 설명
    unresolved_items: list[ImprovementItem]  # 미해소 항목


@dataclass
class FeedbackLoopSummary:
    """전체 피드백 루프 실행 결과 요약."""
    started_at: str
    finished_at: str
    total_iterations: int
    initial_item_count: int
    final_unresolved_count: int
    iteration_results: list[LoopIterationResult]
    alert_sent: bool = False

    def format(self) -> str:
        lines = [
            "♻️ *자가개선 피드백 루프 완료*",
            f"초기 항목: {self.initial_item_count}개 | "
            f"반복: {self.total_iterations}회 | "
            f"미해소: {self.final_unresolved_count}개",
        ]
        for r in self.iteration_results:
            resolved_str = ", ".join(r.resolved_items[:3]) or "없음"
            lines.append(
                f"\n*이터레이션 {r.iteration}*: "
                f"{r.items_before}→{r.items_after}개 "
                f"(해소: {resolved_str})"
            )
            lines.append(
                f"  큐 결과: ✅{r.queue_log.succeeded} ❌{r.queue_log.failed} ⏭️{r.queue_log.skipped}"
            )
        if self.final_unresolved_count > 0:
            lines.append(f"\n⚠️ 미해소 항목 {self.final_unresolved_count}개 — 수동 검토 필요")
        else:
            lines.append("\n✅ 모든 항목 해소 완료")
        if self.alert_sent:
            lines.append("📨 미해소 알림 발송됨")
        return "\n".join(lines)


# ------------------------------------------------------------------
# 메인 오케스트레이터
# ------------------------------------------------------------------

class FeedbackLoopRunner:
    """건강 리포트 → 개선 실행 → 재스캔 → 피드백 루프."""

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        cfg = _load_loop_config()
        self.max_iterations: int = int(cfg.get("max_iterations", 3))
        self.rescan_delay: float = float(cfg.get("rescan_delay_seconds", 2))
        self.unresolved_alert: bool = bool(cfg.get("unresolved_alert", True))
        self._parser = HealthReportParser()

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def run(self, report: Any) -> FeedbackLoopSummary:
        """건강 리포트를 수신하여 전체 피드백 루프를 실행한다.

        Args:
            report: CodeHealthReport dataclass, dict, 또는 텍스트 문자열

        Returns:
            FeedbackLoopSummary — 루프 전체 결과 요약
        """
        started_at = datetime.now(timezone.utc).isoformat()
        logger.info("[FeedbackLoopRunner] 피드백 루프 시작")

        # 1단계: 초기 파싱
        items = self._parser.parse(report)
        initial_count = len(items)
        logger.info(f"[FeedbackLoopRunner] 초기 항목 {initial_count}개")

        if not items:
            logger.info("[FeedbackLoopRunner] 개선 항목 없음 — 종료")
            return FeedbackLoopSummary(
                started_at=started_at,
                finished_at=datetime.now(timezone.utc).isoformat(),
                total_iterations=0,
                initial_item_count=0,
                final_unresolved_count=0,
                iteration_results=[],
            )

        iteration_results: list[LoopIterationResult] = []
        current_items = items

        # 2단계: 최대 N회 반복
        for iteration in range(1, self.max_iterations + 1):
            logger.info(
                f"[FeedbackLoopRunner] 이터레이션 {iteration}/{self.max_iterations} "
                f"— {len(current_items)}개 항목"
            )

            # 큐 생성 및 실행
            queue = ImprovementQueue(dry_run=self.dry_run)
            queue.enqueue(current_items)
            queue_log = queue.run_all()

            # 재스캔 (잠시 대기 후)
            if self.rescan_delay > 0 and not self.dry_run:
                time.sleep(self.rescan_delay)

            rescanned_items = self._rescan()
            resolved, unresolved = self._diff(current_items, rescanned_items)

            iter_result = LoopIterationResult(
                iteration=iteration,
                items_before=len(current_items),
                queue_log=queue_log,
                items_after=len(unresolved),
                resolved_items=[self._item_label(i) for i in resolved],
                unresolved_items=unresolved,
            )
            iteration_results.append(iter_result)

            logger.info(
                f"[FeedbackLoopRunner] 이터레이션 {iteration} 완료 — "
                f"해소 {len(resolved)}개, 미해소 {len(unresolved)}개"
            )

            if not unresolved:
                logger.info("[FeedbackLoopRunner] 모든 항목 해소 — 루프 종료")
                break

            current_items = unresolved

        # 3단계: 미해소 항목 알림
        alert_sent = False
        final_unresolved = iteration_results[-1].unresolved_items if iteration_results else []
        if final_unresolved and self.unresolved_alert:
            self._send_unresolved_alert(final_unresolved)
            alert_sent = True

        summary = FeedbackLoopSummary(
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            total_iterations=len(iteration_results),
            initial_item_count=initial_count,
            final_unresolved_count=len(final_unresolved),
            iteration_results=iteration_results,
            alert_sent=alert_sent,
        )
        logger.info(f"[FeedbackLoopRunner] {summary.format()}")
        return summary

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    def _rescan(self) -> list[ImprovementItem]:
        """CodeHealthMonitor를 재호출하여 현재 상태 재스캔."""
        try:
            from core.code_health import CodeHealthMonitor
            monitor = CodeHealthMonitor()
            report = monitor.scan()
            return self._parser.parse(report)
        except Exception as e:
            logger.warning(f"[FeedbackLoopRunner] 재스캔 실패: {e}")
            return []

    def _diff(
        self,
        before: list[ImprovementItem],
        after: list[ImprovementItem],
    ) -> tuple[list[ImprovementItem], list[ImprovementItem]]:
        """재스캔 전후를 비교하여 (해소된 항목, 미해소 항목) 반환.

        파일 경로 또는 에러 패턴 명이 재스캔 결과에 없으면 해소된 것으로 판단.
        """
        after_keys = {self._item_key(i) for i in after}
        resolved = [i for i in before if self._item_key(i) not in after_keys]
        unresolved = [i for i in before if self._item_key(i) in after_keys]

        # 해소된 항목 마킹
        for item in resolved:
            item.resolved = True

        return resolved, unresolved

    @staticmethod
    def _item_key(item: ImprovementItem) -> str:
        """항목 동일성 키 — (issue_type, target)."""
        target = item.file_path or item.error_pattern or "unknown"
        return f"{item.issue_type}::{target}"

    @staticmethod
    def _item_label(item: ImprovementItem) -> str:
        return item.file_path or item.error_pattern or "unknown"

    def _send_unresolved_alert(self, items: list[ImprovementItem]) -> None:
        """미해소 항목을 ImprovementBus 신호로 변환하여 알림 발송."""
        try:
            from core.improvement_bus import ImprovementBus, ImprovementSignal, SignalKind
            signals = []
            for item in items:
                signals.append(ImprovementSignal(
                    kind=SignalKind.CODE_SMELL,
                    priority=item.priority,
                    target=item.file_path or item.error_pattern or "unknown",
                    evidence=item.detail,
                    suggested_action=f"[미해소] {item.suggested_action}",
                ))
            bus = ImprovementBus(dry_run=self.dry_run)
            bus.run(signals)
            logger.info(f"[FeedbackLoopRunner] 미해소 알림 {len(signals)}개 발송")
        except Exception as e:
            logger.error(f"[FeedbackLoopRunner] 미해소 알림 실패: {e}")
