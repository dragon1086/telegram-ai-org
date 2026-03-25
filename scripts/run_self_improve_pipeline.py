#!/usr/bin/env python3
"""자가 개선 파이프라인 실행기 — 건강 스캔 → 개선 → 재스캔 → 로그 → 알림.

흐름:
    1. baseline 스냅샷 저장 (개선 실행 전 스캔)
    2. FeedbackLoopRunner 실행 (실제 개선 수행)
    3. post-run 스냅샷 저장 (개선 후 재스캔)
    4. diff 계산 → comparison-{run_id}.json 저장
    5. self-improve-history.jsonl append
    6. 실패 조건 평가 → 실패 시 ImprovementBus 알림 발송

사용법:
    python scripts/run_self_improve_pipeline.py
    python scripts/run_self_improve_pipeline.py --dry-run
    python scripts/run_self_improve_pipeline.py --history      # 이력만 출력
    python scripts/run_self_improve_pipeline.py --history-n 5  # 최근 5건

크론 등록 (매일 새벽 4시 7분):
    7 4 * * * cd /path/to/telegram-ai-org && .venv/bin/python scripts/run_self_improve_pipeline.py >> logs/self-improve/cron.log 2>&1
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from loguru import logger  # noqa: E402

from core.self_improve_monitor import SelfImproveMonitor  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="자가 개선 파이프라인 실행기")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 개선 없이 로그 저장만 시뮬레이션",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="실행 이력만 출력 (파이프라인 실행 안 함)",
    )
    parser.add_argument(
        "--history-n",
        type=int,
        default=10,
        metavar="N",
        help="이력 출력 건수 (기본: 10)",
    )
    return parser.parse_args()


def run_pipeline(dry_run: bool = False) -> int:
    """메인 파이프라인 실행. 반환값: 종료 코드 (0=성공, 1=실패)."""
    monitor = SelfImproveMonitor(dry_run=dry_run)
    run_id = SelfImproveMonitor.new_run_id()

    logger.info(f"[Pipeline] 자가 개선 파이프라인 시작 — run_id={run_id}")
    started_at = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Step 1: baseline 스냅샷
    # ------------------------------------------------------------------
    try:
        logger.info("[Pipeline] Step 1: baseline 스캔")
        baseline = monitor.capture_snapshot("baseline", run_id)
        baseline_path = monitor.save_snapshot(baseline)
        logger.info(f"[Pipeline] baseline 저장 완료: {baseline_path}")
    except Exception as e:
        logger.error(f"[Pipeline] baseline 스캔 실패: {e}")
        _record_error(monitor, run_id, f"baseline 스캔 오류: {e}")
        return 1

    # baseline에 이슈가 없으면 파이프라인 스킵
    if baseline.total_issues() == 0:
        logger.info("[Pipeline] 이슈 없음 — 파이프라인 스킵")
        _record_clean(monitor, run_id, baseline, str(baseline_path), dry_run)
        return 0

    # ------------------------------------------------------------------
    # Step 2: FeedbackLoopRunner 실행 (실제 개선)
    # ------------------------------------------------------------------
    pipeline_error = ""
    try:
        logger.info("[Pipeline] Step 2: FeedbackLoopRunner 실행")
        from core.code_health import CodeHealthMonitor
        from core.feedback_loop_runner import FeedbackLoopRunner

        code_monitor = CodeHealthMonitor()
        health_report = code_monitor.scan()

        runner = FeedbackLoopRunner(dry_run=dry_run)
        loop_summary = runner.run(health_report)
        logger.info(f"[Pipeline] 개선 루프 완료:\n{loop_summary.format()}")
    except Exception as e:
        pipeline_error = str(e)
        logger.error(f"[Pipeline] FeedbackLoopRunner 실패: {e}")

    # ------------------------------------------------------------------
    # Step 3: post-run 스냅샷
    # ------------------------------------------------------------------
    try:
        logger.info("[Pipeline] Step 3: post-run 스캔")
        post_run = monitor.capture_snapshot("post_run", run_id)
        post_run_path = monitor.save_snapshot(post_run)
        logger.info(f"[Pipeline] post-run 저장 완료: {post_run_path}")
    except Exception as e:
        logger.error(f"[Pipeline] post-run 스캔 실패: {e}")
        pipeline_error = pipeline_error or f"post-run 스캔 오류: {e}"
        # post-run 실패 시 baseline만으로 비교 불가 — 오류 기록
        _record_error(monitor, run_id, pipeline_error)
        return 1

    # ------------------------------------------------------------------
    # Step 4: diff 계산 + comparison 로그 저장
    # ------------------------------------------------------------------
    diff = monitor.compute_diff(
        baseline,
        post_run,
        baseline_path=str(baseline_path),
        post_run_path=str(post_run_path),
        error_message=pipeline_error,
    )
    comparison_path = monitor.save_comparison_log(diff)
    logger.info(f"[Pipeline] 비교 로그 저장: {comparison_path}")
    logger.info(f"[Pipeline] {diff.summary_line()}")

    # ------------------------------------------------------------------
    # Step 5: 실패 감지 + 알림
    # ------------------------------------------------------------------
    is_failure, failure_reason = monitor.is_failure(diff)
    alert_sent = False

    if is_failure:
        logger.warning(f"[Pipeline] 실패 감지: {failure_reason}")
        monitor.send_failure_alert(diff, failure_reason)
        alert_sent = True
    else:
        logger.info("[Pipeline] 실패 조건 미충족 — 알림 생략")

    # ------------------------------------------------------------------
    # Step 6: history append
    # ------------------------------------------------------------------
    monitor.append_history(
        diff,
        failure_reason=failure_reason if is_failure else None,
        alert_sent=alert_sent,
    )

    # 결과 요약 출력
    _print_run_summary(run_id, started_at, diff, alert_sent, is_failure)

    return 1 if is_failure else 0


def _record_error(monitor: SelfImproveMonitor, run_id: str, error_msg: str) -> None:
    """파이프라인 오류 발생 시 최소 이력 기록."""
    from datetime import datetime, timezone

    from core.self_improve_monitor import SCHEMA_VERSION, ScanDiff, ScanSnapshot
    now = datetime.now(timezone.utc).isoformat()

    _empty_snap = ScanSnapshot(
        schema_version=SCHEMA_VERSION,
        snapshot_type="baseline",
        run_id=run_id,
        captured_at=now,
        total_files=0,
        warn_count=0,
        critical_count=0,
        items=[],
    )
    diff = ScanDiff(
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
        compared_at=now,
        baseline_path="",
        post_run_path="",
        baseline_issue_count=0,
        post_run_issue_count=0,
        resolved_count=0,
        new_count=0,
        improvement_rate=0.0,
        status="error",
        error_message=error_msg,
    )
    monitor.save_comparison_log(diff)
    monitor.send_failure_alert(diff, error_msg)
    monitor.append_history(diff, failure_reason=error_msg, alert_sent=True)


def _record_clean(
    monitor: SelfImproveMonitor,
    run_id: str,
    baseline: "ScanSnapshot",  # noqa: F821
    baseline_path: str,
    dry_run: bool,
) -> None:
    """이슈 0건 — clean run 이력 기록."""
    from datetime import datetime, timezone

    from core.self_improve_monitor import SCHEMA_VERSION, ScanDiff
    now = datetime.now(timezone.utc).isoformat()

    diff = ScanDiff(
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
        compared_at=now,
        baseline_path=baseline_path,
        post_run_path="",
        baseline_issue_count=0,
        post_run_issue_count=0,
        resolved_count=0,
        new_count=0,
        improvement_rate=1.0,
        status="improved",
    )
    monitor.save_comparison_log(diff)
    monitor.append_history(diff, failure_reason=None, alert_sent=False)
    logger.info("[Pipeline] clean run 이력 저장 완료")


def _print_run_summary(
    run_id: str,
    started_at: str,
    diff: "ScanDiff",  # noqa: F821
    alert_sent: bool,
    is_failure: bool,
) -> None:
    from datetime import datetime, timezone
    finished_at = datetime.now(timezone.utc).isoformat()
    status_icon = "❌ 실패" if is_failure else "✅ 성공"
    print(
        f"\n{'='*60}\n"
        f"자가 개선 파이프라인 완료\n"
        f"{'='*60}\n"
        f"run_id      : {run_id}\n"
        f"시작        : {started_at[:19]} UTC\n"
        f"완료        : {finished_at[:19]} UTC\n"
        f"결과        : {status_icon}\n"
        f"baseline    : {diff.baseline_issue_count}건\n"
        f"post-run    : {diff.post_run_issue_count}건\n"
        f"해소        : {diff.resolved_count}건\n"
        f"신규        : {diff.new_count}건\n"
        f"개선율      : {diff.improvement_rate * 100:.0f}%\n"
        f"상태        : {diff.status}\n"
        f"알림 발송   : {'예' if alert_sent else '아니오'}\n"
        f"{'='*60}\n"
    )


def main() -> None:
    args = parse_args()

    if args.history:
        monitor = SelfImproveMonitor()
        print(monitor.print_history_summary(last_n=args.history_n))
        return

    exit_code = run_pipeline(dry_run=args.dry_run)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
