#!/usr/bin/env python3
# ruff: noqa: E402
"""운영실 rollout monitor.

manual trigger 기준으로 daily_goal_pipeline / harness-audit 상태를 반복 점검하고
COLLAB 디스패치 로그, 목표 STALE 여부, 알림 조건을 운영 산출물로 남긴다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import daily_goal_pipeline as goal_pipeline
from scripts import run_harness_audit as harness_audit

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "ops_rollout.yaml"


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"ops rollout config not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _read_collab_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _write_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _render_alert_rules(cfg: dict[str, Any]) -> str:
    lines = [
        "# 알림 조건 정의서",
        "",
        f"- 기준 시각: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%SZ')}",
        "",
    ]
    for rule in cfg.get("monitoring", {}).get("alert_rules", []):
        lines.extend([
            f"## {rule.get('id', 'unknown')}",
            f"- Severity: {rule.get('severity', 'unknown')}",
            f"- Condition: {rule.get('condition', '-')}",
            f"- Action: {rule.get('action', '-')}",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def _collect_cycle(
    *,
    cycle_no: int,
    cfg: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    started_at = datetime.now(UTC).isoformat()
    guide_path = goal_pipeline._find_progress_guide()
    goals: list[dict[str, Any]] = []
    if guide_path is not None:
        goals = goal_pipeline._parse_goals(guide_path.read_text(encoding="utf-8"))
        goal_pipeline._save_goal_snapshot(goals)

    collab_count = harness_audit._count_collab_usage(days=7)
    audit_report = harness_audit._build_audit_report(goals, collab_count)
    audit_path = output_dir / f"cycle-{cycle_no:02d}-harness-audit.md"
    audit_path.write_text(audit_report, encoding="utf-8")

    pipeline_report = goal_pipeline._build_pipeline_message(goals) if goals else "활성 목표 없음"
    pipeline_path = output_dir / f"cycle-{cycle_no:02d}-goal-pipeline.md"
    pipeline_path.write_text(pipeline_report, encoding="utf-8")

    collab_log_path = PROJECT_ROOT / cfg["monitoring"]["collab_dispatch_log"]
    collab_events = _read_collab_events(collab_log_path)
    dispatch_prefix = cfg["monitoring"].get("dispatch_task_prefix", "")
    recent_events = [event for event in collab_events if event.get("ts", "")[:10] == started_at[:10]]
    rollout_events = [
        event for event in recent_events
        if not dispatch_prefix or str(event.get("task_id", "")).startswith(dispatch_prefix)
    ]
    dispatch_success = sum(1 for event in rollout_events if event.get("status") == "dispatched")
    dispatch_errors = sum(
        1 for event in rollout_events if event.get("status") in {"error", "skipped_no_chat_id"}
    )

    stale_goal_ids = [goal["id"] for goal in goals if goal.get("is_stale")]
    alerts: list[str] = []
    if guide_path is None:
        alerts.append("missing_progress_guide")
    if stale_goal_ids:
        alerts.append("stale_goal_detected")
    if collab_count == 0:
        alerts.append("collab_inactive")
    if dispatch_errors:
        alerts.append("collab_dispatch_error")

    cycle = {
        "cycle": cycle_no,
        "started_at": started_at,
        "progress_guide_path": str(guide_path) if guide_path else "",
        "goal_count": len(goals),
        "stale_goal_ids": stale_goal_ids,
        "collab_count_7d": collab_count,
        "collab_dispatch_events_today": len(rollout_events),
        "collab_dispatch_success_today": dispatch_success,
        "collab_dispatch_errors_today": dispatch_errors,
        "goal_pipeline_report": str(pipeline_path.relative_to(PROJECT_ROOT)),
        "harness_audit_report": str(audit_path.relative_to(PROJECT_ROOT)),
        "alerts": alerts,
        "infra_baseline_version": os.environ.get("INFRA_BASELINE_VERSION", "unknown"),
    }
    return cycle


def _write_summary(path: Path, cycles: list[dict[str, Any]], cfg: dict[str, Any]) -> None:
    monitoring = cfg.get("monitoring", {})
    min_cycles = int(monitoring.get("min_iter_cycles", 2))
    lines = [
        "# Iter Loop Summary",
        "",
        f"- 기준 시각: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%SZ')}",
        f"- 수행 cycle: {len(cycles)}회 (기준 {min_cycles}회)",
        "",
        "| Cycle | Goal | Stale | COLLAB(7d) | Dispatch Success | Alerts |",
        "|------|------|-------|-------------|------------------|--------|",
    ]
    for cycle in cycles:
        lines.append(
            "| {cycle} | {goal_count} | {stale_count} | {collab} | {dispatch} | {alerts} |".format(
                cycle=cycle["cycle"],
                goal_count=cycle["goal_count"],
                stale_count=len(cycle["stale_goal_ids"]),
                collab=cycle["collab_count_7d"],
                dispatch=cycle["collab_dispatch_success_today"],
                alerts=", ".join(cycle["alerts"]) or "-",
            )
        )
    lines.extend([
        "",
        "## 판단",
        f"- Iter loop 최소 기준 충족: {'YES' if len(cycles) >= min_cycles else 'NO'}",
        f"- STALE 목표 감지: {'YES' if any(cycle['stale_goal_ids'] for cycle in cycles) else 'NO'}",
        f"- COLLAB dispatch 오류 감지: {'YES' if any(cycle['collab_dispatch_errors_today'] for cycle in cycles) else 'NO'}",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ops rollout monitor")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--cycles", type=int, default=2)
    parser.add_argument("--sleep-sec", type=float, default=0.0)
    args = parser.parse_args()

    cfg = _load_config(Path(args.config))
    monitoring = cfg.get("monitoring", {})
    history_path = PROJECT_ROOT / monitoring.get("history_log", "reports/ops/iter-loop-history.jsonl")
    summary_path = PROJECT_ROOT / monitoring.get("summary_report", "reports/ops/iter-loop-summary.md")
    alert_conditions_path = PROJECT_ROOT / monitoring.get("alert_conditions_report", "reports/ops/alert-conditions.md")
    output_dir = history_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    alert_conditions_path.write_text(_render_alert_rules(cfg), encoding="utf-8")

    cycles: list[dict[str, Any]] = []
    for cycle_no in range(1, args.cycles + 1):
        cycle = _collect_cycle(cycle_no=cycle_no, cfg=cfg, output_dir=output_dir)
        _write_jsonl(history_path, cycle)
        cycles.append(cycle)
        print(
            f"[ops_rollout_monitor] cycle={cycle_no} goals={cycle['goal_count']} "
            f"stale={len(cycle['stale_goal_ids'])} collab={cycle['collab_count_7d']} "
            f"dispatch_success={cycle['collab_dispatch_success_today']}"
        )
        if cycle_no < args.cycles and args.sleep_sec > 0:
            time.sleep(args.sleep_sec)

    _write_summary(summary_path, cycles, cfg)
    print(f"[ops_rollout_monitor] history={history_path}")
    print(f"[ops_rollout_monitor] summary={summary_path}")
    print(f"[ops_rollout_monitor] alert_conditions={alert_conditions_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
