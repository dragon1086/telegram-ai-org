"""자가 개선 모니터 — 파이프라인 실행 전/후 스캔 비교·저장·알림·이력 추적.

흐름:
    1. baseline 스냅샷 저장 (개선 실행 전)
    2. post-run 스냅샷 저장 (개선 실행 후)
    3. diff 계산 → 비교 로그 저장 (logs/self-improve/YYYY-MM-DD/)
    4. self-improve-history.jsonl append
    5. 실패 조건 평가 → 조건 충족 시 알림 발송

로그 디렉토리 구조:
    logs/
      self-improve/
        YYYY-MM-DD/
          baseline-{run_id}.json
          post-run-{run_id}.json
          comparison-{run_id}.json
        self-improve-history.jsonl

사용법:
    from core.self_improve_monitor import SelfImproveMonitor
    monitor = SelfImproveMonitor()

    run_id = monitor.new_run_id()
    baseline = monitor.capture_snapshot("baseline", run_id)
    monitor.save_snapshot(baseline)
    # ... 개선 파이프라인 실행 ...
    post = monitor.capture_snapshot("post_run", run_id)
    monitor.save_snapshot(post)
    diff = monitor.compute_diff(baseline, post)
    monitor.save_comparison_log(diff)
    monitor.append_history(diff)
    if monitor.is_failure(diff):
        monitor.send_failure_alert(diff)
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# 경로 상수
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
SELF_IMPROVE_LOG_ROOT = REPO_ROOT / "logs" / "self-improve"
HISTORY_FILE = SELF_IMPROVE_LOG_ROOT / "self-improve-history.jsonl"

# ---------------------------------------------------------------------------
# 실패 감지 임계값 (improvement_thresholds.yaml fallback)
# ---------------------------------------------------------------------------

DEFAULT_MIN_IMPROVEMENT_RATE = 0.0   # 0% 이상이면 일단 통과 (개선 항목 0건 조건 별도)
DEFAULT_MAX_FAILURE_RATE = 0.8       # 이슈 잔존율 80% 초과 시 실패
DEFAULT_REGRESSION_PENALTY = 0       # 신규 이슈 > 해소 이슈 시 실패

# ---------------------------------------------------------------------------
# 로그 스키마 — 데이터클래스
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "1.0"


@dataclass
class ScanSnapshot:
    """단일 스캔 결과 스냅샷 (baseline / post_run).

    Schema:
        schema_version: str         — "1.0"
        snapshot_type: str          — "baseline" | "post_run"
        run_id: str                 — UUID (baseline·post_run 연결 키)
        captured_at: str            — ISO8601 UTC
        total_files: int
        warn_count: int
        critical_count: int
        items: list[dict]           — ImprovementItem 직렬화 목록
    """
    schema_version: str
    snapshot_type: str          # "baseline" | "post_run"
    run_id: str
    captured_at: str
    total_files: int
    warn_count: int
    critical_count: int
    items: list[dict] = field(default_factory=list)

    def total_issues(self) -> int:
        return len(self.items)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScanDiff:
    """baseline vs post_run 비교 결과.

    Schema:
        schema_version: str
        run_id: str
        compared_at: str            — ISO8601 UTC
        baseline_path: str          — 저장된 baseline JSON 경로
        post_run_path: str          — 저장된 post_run JSON 경로
        baseline_issue_count: int
        post_run_issue_count: int
        resolved_count: int         — 해소된 항목 수
        new_count: int              — 신규 발생 항목 수
        improvement_rate: float     — 0.0~1.0 (해소 / baseline)
        resolved_items: list[dict]  — 해소된 항목
        new_items: list[dict]       — 신규 발생 항목
        unresolved_items: list[dict]— 미해소 항목
        status: str                 — "improved" | "unchanged" | "regressed" | "error"
        error_message: str          — 오류 발생 시 메시지
    """
    schema_version: str
    run_id: str
    compared_at: str
    baseline_path: str
    post_run_path: str
    baseline_issue_count: int
    post_run_issue_count: int
    resolved_count: int
    new_count: int
    improvement_rate: float
    resolved_items: list[dict] = field(default_factory=list)
    new_items: list[dict] = field(default_factory=list)
    unresolved_items: list[dict] = field(default_factory=list)
    status: str = "unchanged"       # "improved" | "unchanged" | "regressed" | "error"
    error_message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def summary_line(self) -> str:
        icon = {"improved": "✅", "unchanged": "➖", "regressed": "🔻", "error": "❌"}.get(
            self.status, "❓"
        )
        rate_pct = f"{self.improvement_rate * 100:.0f}%"
        return (
            f"{icon} [{self.status.upper()}] "
            f"baseline {self.baseline_issue_count}건 → post-run {self.post_run_issue_count}건 "
            f"(해소 {self.resolved_count}, 신규 {self.new_count}, 개선율 {rate_pct})"
        )


@dataclass
class HistoryEntry:
    """self-improve-history.jsonl 한 줄 — 실행 이력 항목.

    Schema:
        run_id: str
        executed_at: str            — ISO8601 UTC
        status: str                 — "success" | "failure" | "no_change" | "error"
        baseline_issues: int
        post_run_issues: int
        improvement_rate: float
        resolved_count: int
        new_count: int
        failure_reason: str | None
        alert_sent: bool
        comparison_log_path: str
    """
    run_id: str
    executed_at: str
    status: str
    baseline_issues: int
    post_run_issues: int
    improvement_rate: float
    resolved_count: int
    new_count: int
    failure_reason: str | None
    alert_sent: bool
    comparison_log_path: str

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# 실패 감지 조건 정의
# ---------------------------------------------------------------------------

class FailureCondition:
    """실패 감지 조건 목록 (우선순위 순)."""

    @staticmethod
    def check(diff: ScanDiff) -> tuple[bool, str]:
        """(is_failure, reason) 반환.

        조건 (OR):
          1. status == "error"         — 파이프라인 실행 자체 오류
          2. new_count > resolved_count — 회귀: 신규 이슈 > 해소 이슈
          3. improvement_rate == 0.0 AND baseline_issue_count > 0
                                       — 개선 항목 0건 (변화 없음 + 이슈 존재)
          4. 잔존율 > MAX_FAILURE_RATE  — (post_run / baseline) > 0.8
        """
        if diff.status == "error":
            return True, f"파이프라인 실행 오류: {diff.error_message}"

        if diff.new_count > diff.resolved_count:
            return True, (
                f"회귀 감지 — 신규 이슈 {diff.new_count}건 > 해소 이슈 {diff.resolved_count}건"
            )

        if diff.baseline_issue_count > 0 and diff.improvement_rate == 0.0:
            return True, (
                f"개선 항목 0건 — baseline {diff.baseline_issue_count}건 이슈 모두 미해소"
            )

        if diff.baseline_issue_count > 0:
            survival_rate = diff.post_run_issue_count / diff.baseline_issue_count
            if survival_rate > DEFAULT_MAX_FAILURE_RATE:
                return True, (
                    f"잔존율 {survival_rate * 100:.0f}% > 임계값 "
                    f"{DEFAULT_MAX_FAILURE_RATE * 100:.0f}% "
                    f"(해소율 {diff.improvement_rate * 100:.0f}%)"
                )

        return False, ""


# ---------------------------------------------------------------------------
# 메인 모니터 클래스
# ---------------------------------------------------------------------------

class SelfImproveMonitor:
    """자가 개선 파이프라인 모니터 — 로그 저장·비교·알림·이력 관리."""

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._ensure_dirs()

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    @staticmethod
    def new_run_id() -> str:
        """고유 run_id 생성 (UUID4 short)."""
        return uuid.uuid4().hex[:12]

    def capture_snapshot(
        self,
        snapshot_type: str,
        run_id: str,
        report: Any = None,
    ) -> ScanSnapshot:
        """CodeHealthMonitor 스캔 결과 → ScanSnapshot.

        Args:
            snapshot_type: "baseline" | "post_run"
            run_id: new_run_id()로 생성한 식별자
            report: 이미 스캔된 CodeHealthReport를 전달하면 재스캔 생략.
                    None이면 내부에서 CodeHealthMonitor().scan() 호출.
        """
        if report is None:
            report = self._do_scan()

        items = self._extract_items(report)

        # 파일 수·warn/critical 카운트
        total_files = getattr(report, "total_files", 0)
        warn_count = getattr(report, "warn_count", 0)
        critical_count = getattr(report, "critical_count", 0)

        snapshot = ScanSnapshot(
            schema_version=SCHEMA_VERSION,
            snapshot_type=snapshot_type,
            run_id=run_id,
            captured_at=datetime.now(timezone.utc).isoformat(),
            total_files=total_files,
            warn_count=warn_count,
            critical_count=critical_count,
            items=items,
        )
        logger.info(
            f"[SelfImproveMonitor] {snapshot_type} 스냅샷 캡처 — "
            f"{len(items)}개 이슈 (run_id={run_id})"
        )
        return snapshot

    def save_snapshot(self, snapshot: ScanSnapshot) -> Path:
        """스냅샷을 날짜별 디렉토리에 JSON으로 저장."""
        date_dir = self._date_dir(snapshot.captured_at)
        file_name = f"{snapshot.snapshot_type}-{snapshot.run_id}.json"
        path = date_dir / file_name

        if not self.dry_run:
            path.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2))
        logger.info(f"[SelfImproveMonitor] 스냅샷 저장 → {path}")
        return path

    def compute_diff(
        self,
        baseline: ScanSnapshot,
        post_run: ScanSnapshot,
        baseline_path: str = "",
        post_run_path: str = "",
        error_message: str = "",
    ) -> ScanDiff:
        """baseline vs post_run 비교 → ScanDiff 생성."""
        # 항목 키: issue_type::target
        def _key(item: dict) -> str:
            target = item.get("file_path") or item.get("error_pattern") or "unknown"
            return f"{item.get('issue_type', '?')}::{target}"

        before_keys = {_key(i): i for i in baseline.items}
        after_keys = {_key(i): i for i in post_run.items}

        resolved = [v for k, v in before_keys.items() if k not in after_keys]
        new_items = [v for k, v in after_keys.items() if k not in before_keys]
        unresolved = [v for k, v in before_keys.items() if k in after_keys]

        baseline_count = len(baseline.items)
        resolved_count = len(resolved)
        new_count = len(new_items)
        post_run_count = len(post_run.items)

        improvement_rate = (
            resolved_count / baseline_count if baseline_count > 0 else 0.0
        )

        if error_message:
            status = "error"
        elif new_count > resolved_count:
            status = "regressed"
        elif resolved_count > 0:
            status = "improved"
        elif new_count == 0 and resolved_count == 0:
            status = "unchanged"
        else:
            status = "unchanged"

        diff = ScanDiff(
            schema_version=SCHEMA_VERSION,
            run_id=baseline.run_id,
            compared_at=datetime.now(timezone.utc).isoformat(),
            baseline_path=baseline_path,
            post_run_path=post_run_path,
            baseline_issue_count=baseline_count,
            post_run_issue_count=post_run_count,
            resolved_count=resolved_count,
            new_count=new_count,
            improvement_rate=round(improvement_rate, 4),
            resolved_items=resolved,
            new_items=new_items,
            unresolved_items=unresolved,
            status=status,
            error_message=error_message,
        )
        logger.info(f"[SelfImproveMonitor] diff 계산 완료 — {diff.summary_line()}")
        return diff

    def save_comparison_log(self, diff: ScanDiff) -> Path:
        """diff를 날짜별 디렉토리에 comparison-{run_id}.json으로 저장."""
        date_dir = self._date_dir(diff.compared_at)
        path = date_dir / f"comparison-{diff.run_id}.json"

        if not self.dry_run:
            path.write_text(json.dumps(diff.to_dict(), ensure_ascii=False, indent=2))
        logger.info(f"[SelfImproveMonitor] 비교 로그 저장 → {path}")
        return path

    def append_history(
        self,
        diff: ScanDiff,
        *,
        failure_reason: str | None = None,
        alert_sent: bool = False,
    ) -> None:
        """self-improve-history.jsonl에 실행 이력을 append."""
        if diff.status == "improved":
            hist_status = "success"
        elif diff.status == "error":
            hist_status = "error"
        elif diff.status == "regressed":
            hist_status = "failure"
        elif diff.improvement_rate == 0.0 and diff.baseline_issue_count > 0:
            hist_status = "no_change"
        else:
            hist_status = "success"

        entry = HistoryEntry(
            run_id=diff.run_id,
            executed_at=diff.compared_at,
            status=hist_status,
            baseline_issues=diff.baseline_issue_count,
            post_run_issues=diff.post_run_issue_count,
            improvement_rate=diff.improvement_rate,
            resolved_count=diff.resolved_count,
            new_count=diff.new_count,
            failure_reason=failure_reason,
            alert_sent=alert_sent,
            comparison_log_path=str(
                self._date_dir(diff.compared_at) / f"comparison-{diff.run_id}.json"
            ),
        )

        if not self.dry_run:
            with HISTORY_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        logger.info(
            f"[SelfImproveMonitor] 이력 추가 → {HISTORY_FILE.name} "
            f"(run_id={diff.run_id}, status={hist_status})"
        )

    def is_failure(self, diff: ScanDiff) -> tuple[bool, str]:
        """(is_failure, reason) — FailureCondition 위임."""
        return FailureCondition.check(diff)

    def send_failure_alert(self, diff: ScanDiff, reason: str) -> None:
        """실패 감지 시 ImprovementBus를 통해 알림 발송.

        알림 메시지 포함 항목:
          - 실행 시각 (run_id / compared_at)
          - 실패 원인 요약
          - 비교 diff 핵심 지표 (baseline→post-run, 개선율)
        """
        alert_body = self._build_alert_message(diff, reason)
        logger.warning(f"[SelfImproveMonitor] 실패 알림 발송:\n{alert_body}")

        if self.dry_run:
            logger.info("[SelfImproveMonitor] dry_run: 알림 발송 생략")
            return

        try:
            from core.improvement_bus import ImprovementBus, ImprovementSignal, SignalKind

            signal = ImprovementSignal(
                kind=SignalKind.CODE_SMELL,
                priority=9,
                target=f"self-improve-pipeline::{diff.run_id}",
                evidence={
                    "run_id": diff.run_id,
                    "baseline_issues": diff.baseline_issue_count,
                    "post_run_issues": diff.post_run_issue_count,
                    "improvement_rate": diff.improvement_rate,
                    "resolved_count": diff.resolved_count,
                    "new_count": diff.new_count,
                    "status": diff.status,
                    "failure_reason": reason,
                },
                suggested_action=alert_body,
            )
            bus = ImprovementBus(dry_run=False)
            bus.run([signal])
            logger.info("[SelfImproveMonitor] 실패 알림 ImprovementBus 전달 완료")
        except Exception as e:
            logger.error(f"[SelfImproveMonitor] 알림 발송 실패: {e}")

    # ------------------------------------------------------------------
    # 이력 조회 유틸리티
    # ------------------------------------------------------------------

    def read_history(self, last_n: int = 20) -> list[dict]:
        """self-improve-history.jsonl에서 최근 N건 이력 반환."""
        if not HISTORY_FILE.exists():
            return []
        lines = HISTORY_FILE.read_text(encoding="utf-8").strip().splitlines()
        entries = []
        for line in lines:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries[-last_n:]

    def print_history_summary(self, last_n: int = 10) -> str:
        """최근 N건 이력의 텍스트 요약."""
        entries = self.read_history(last_n)
        if not entries:
            return "📭 이력 없음"

        lines = [f"📊 *자가 개선 이력 (최근 {len(entries)}건)*\n"]
        for e in reversed(entries):
            icon = {"success": "✅", "failure": "❌", "no_change": "➖", "error": "💥"}.get(
                e.get("status", "?"), "❓"
            )
            rate = f"{e.get('improvement_rate', 0) * 100:.0f}%"
            ts = e.get("executed_at", "")[:16].replace("T", " ")
            lines.append(
                f"{icon} {ts} | "
                f"{e.get('baseline_issues', 0)}→{e.get('post_run_issues', 0)}건 | "
                f"개선율 {rate} | "
                f"run={e.get('run_id', '?')}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        SELF_IMPROVE_LOG_ROOT.mkdir(parents=True, exist_ok=True)

    def _date_dir(self, iso_ts: str) -> Path:
        """ISO8601 타임스탬프에서 날짜 추출 → logs/self-improve/YYYY-MM-DD/ 반환."""
        date_str = iso_ts[:10]  # "YYYY-MM-DD"
        d = SELF_IMPROVE_LOG_ROOT / date_str
        if not self.dry_run:
            d.mkdir(parents=True, exist_ok=True)
        return d

    def _do_scan(self) -> Any:
        """CodeHealthMonitor().scan() 호출."""
        try:
            from core.code_health import CodeHealthMonitor
            monitor = CodeHealthMonitor()
            return monitor.scan()
        except Exception as e:
            logger.error(f"[SelfImproveMonitor] 스캔 실패: {e}")
            raise

    def _extract_items(self, report: Any) -> list[dict]:
        """CodeHealthReport → ImprovementItem list → dict list."""
        try:
            from core.health_report_parser import HealthReportParser
            parser = HealthReportParser()
            items = parser.parse(report)
            result = []
            for item in items:
                result.append({
                    "issue_type": item.issue_type,
                    "severity": item.severity,
                    "priority": item.priority,
                    "suggested_action": item.suggested_action,
                    "file_path": item.file_path,
                    "error_pattern": item.error_pattern,
                    "detail": item.detail,
                    "resolved": item.resolved,
                })
            return result
        except Exception as e:
            logger.error(f"[SelfImproveMonitor] 항목 추출 실패: {e}")
            return []

    @staticmethod
    def _build_alert_message(diff: ScanDiff, reason: str) -> str:
        """실패 알림 메시지 생성."""
        rate_pct = f"{diff.improvement_rate * 100:.0f}%"
        lines = [
            "🚨 *자가 개선 파이프라인 실패 알림*",
            "",
            f"• 실행 시각: `{diff.compared_at[:19].replace('T', ' ')} UTC`",
            f"• run_id: `{diff.run_id}`",
            f"• 실패 원인: {reason}",
            "",
            "*비교 지표*",
            f"  baseline 이슈: {diff.baseline_issue_count}건",
            f"  post-run 이슈: {diff.post_run_issue_count}건",
            f"  해소: {diff.resolved_count}건 | 신규: {diff.new_count}건",
            f"  개선율: {rate_pct}",
            f"  상태: `{diff.status}`",
        ]
        if diff.unresolved_items:
            lines.append("")
            lines.append("*미해소 항목 (상위 3건):*")
            for item in diff.unresolved_items[:3]:
                target = item.get("file_path") or item.get("error_pattern") or "unknown"
                lines.append(f"  - [{item.get('severity', '?')}] {target}")
        return "\n".join(lines)
