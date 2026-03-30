#!/usr/bin/env python3
"""SM-01·TL-01 프로덕션 배포 후 실시간 KPI 알림 모니터.

SM-01 (Smart Model Router) / TL-01 (Toolset Registry) 배포 직후
핵심 KPI를 주기적으로 수집하고, Warning/Critical 임계 초과 시
텔레그램 운영 채널에 자동 알림을 발송한다.

KPI 임계값 (성장실 KPI 정의서 기준):
  - 라우팅 정확도  : Warning < 88%  / Critical < 80%
  - 툴 호출 성공률 : Warning < 95%  / Critical < 90%
  - Latency p95   : Warning > 7 s   / Critical > 10 s

사용법:
    python scripts/sm_tl_monitor.py               # 1회 점검 후 종료
    python scripts/sm_tl_monitor.py --window 30   # 최근 30분 집계 (기본 60분)
    python scripts/sm_tl_monitor.py --dry-run     # Telegram 전송 없이 콘솔 출력
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import statistics
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# ── 프로젝트 루트 설정 ──────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── 환경 변수 로드 ──────────────────────────────────────────────────────────

def _load_env() -> None:
    for env_path in (Path.home() / ".ai-org" / "config.yaml", PROJECT_ROOT / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

# ── 상수 ────────────────────────────────────────────────────────────────────

BOT_TOKEN: str = os.environ.get("BOT_TOKEN_AIORG_OPS_BOT", "") or os.environ.get("PM_BOT_TOKEN", "")
OPS_CHAT_ID: int = int(os.environ.get("OPS_BOT_CHAT_ID", os.environ.get("TELEGRAM_GROUP_CHAT_ID", "0")))
DB_PATH = Path(os.environ.get("CONTEXT_DB_PATH", "~/.ai-org/context.db")).expanduser()
DISPATCH_LOG = PROJECT_ROOT / "logs" / "collab_dispatch.jsonl"
ROUTING_LOG   = PROJECT_ROOT / "logs" / "sm01_routing.jsonl"   # SM-01 배포 후 생성됨
ALERT_LOG     = PROJECT_ROOT / "logs" / "sm_tl_monitor_alerts.jsonl"
REPORT_DIR    = PROJECT_ROOT / "reports" / "ops"

# KPI 임계값
THRESHOLDS: dict[str, dict[str, float]] = {
    "routing_accuracy": {
        "warning":  0.88,   # 88% 미만 → Warning
        "critical": 0.80,   # 80% 미만 → Critical
        "direction": -1,    # 낮을수록 나쁨
    },
    "tool_call_success": {
        "warning":  0.95,   # 95% 미만 → Warning
        "critical": 0.90,   # 90% 미만 → Critical
        "direction": -1,
    },
    "latency_p95_sec": {
        "warning":  7.0,    # 7s 초과 → Warning
        "critical": 10.0,   # 10s 초과 → Critical
        "direction": 1,     # 높을수록 나쁨
    },
}

SEVERITY_EMOJI = {"ok": "✅", "warning": "⚠️", "critical": "🚨"}
SEVERITY_LABEL = {"ok": "정상", "warning": "Warning", "critical": "Critical"}

# ── 메트릭 수집 ─────────────────────────────────────────────────────────────

def _collect_routing_accuracy(since: datetime, until: datetime) -> dict[str, Any]:
    """SM-01 라우팅 정확도 수집.

    우선순위:
    1) logs/sm01_routing.jsonl — SM-01 배포 후 기록되는 전용 로그
    2) logs/collab_dispatch.jsonl — 배포 전 대체: dispatch 성공/실패 비율
    """
    total = 0
    success = 0

    # SM-01 전용 로그 (배포 후)
    if ROUTING_LOG.exists():
        for line in ROUTING_LOG.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                ts = datetime.fromisoformat(rec.get("ts", ""))
                if not (since <= ts < until):
                    continue
                total += 1
                if rec.get("routed_correctly", False):
                    success += 1
            except (json.JSONDecodeError, ValueError):
                continue

    # 대체: collab_dispatch.jsonl
    if total == 0 and DISPATCH_LOG.exists():
        for line in DISPATCH_LOG.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                raw_ts = rec.get("ts") or rec.get("dispatched_at") or rec.get("timestamp", "")
                ts = datetime.fromisoformat(raw_ts)
                if not (since <= ts < until):
                    continue
                total += 1
                if rec.get("status", "") not in ("error", "skipped_no_chat_id", "failed"):
                    success += 1
            except (json.JSONDecodeError, ValueError):
                continue

    accuracy = (success / total) if total > 0 else None
    return {"metric": "routing_accuracy", "value": accuracy, "total": total, "success": success}


def _collect_tool_call_success(since: datetime, until: datetime) -> dict[str, Any]:
    """TL-01 툴 호출 성공률 수집 (task_history 기반)."""
    total = 0
    success = 0

    if not DB_PATH.exists():
        return {"metric": "tool_call_success", "value": None, "total": 0, "success": 0}

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
                """
                SELECT status, COUNT(*) as cnt
                FROM task_history
                WHERE created_at >= ? AND created_at < ?
                GROUP BY status
                """,
                (since.isoformat(), until.isoformat()),
            )
            for row in cur.fetchall():
                status, cnt = row
                total += cnt
                if status in ("completed", "success", "done"):
                    success += cnt

            # pm_tasks 에서도 보완
            cur2 = conn.execute(
                """
                SELECT status, COUNT(*) as cnt
                FROM pm_tasks
                WHERE created_at >= ? AND created_at < ?
                GROUP BY status
                """,
                (since.isoformat(), until.isoformat()),
            )
            for row in cur2.fetchall():
                status, cnt = row
                total += cnt
                if status in ("completed", "success", "done"):
                    success += cnt
    except Exception as e:
        print(f"[sm_tl_monitor] DB 조회 오류: {e}")
        return {"metric": "tool_call_success", "value": None, "total": 0, "success": 0}

    rate = (success / total) if total > 0 else None
    return {"metric": "tool_call_success", "value": rate, "total": total, "success": success}


def _collect_latency_p95(since: datetime, until: datetime) -> dict[str, Any]:
    """Latency p95 수집 (task_history completed_at - created_at 기반)."""
    latencies: list[float] = []

    if not DB_PATH.exists():
        return {"metric": "latency_p95_sec", "value": None, "sample_count": 0}

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
                """
                SELECT created_at, completed_at
                FROM task_history
                WHERE created_at >= ? AND created_at < ?
                  AND completed_at IS NOT NULL
                  AND status IN ('completed', 'success', 'done')
                """,
                (since.isoformat(), until.isoformat()),
            )
            for row in cur.fetchall():
                created_raw, completed_raw = row
                try:
                    t_start = datetime.fromisoformat(created_raw)
                    t_end   = datetime.fromisoformat(completed_raw)
                    elapsed = (t_end - t_start).total_seconds()
                    if elapsed >= 0:
                        latencies.append(elapsed)
                except ValueError:
                    continue
    except Exception as e:
        print(f"[sm_tl_monitor] Latency DB 오류: {e}")
        return {"metric": "latency_p95_sec", "value": None, "sample_count": 0}

    if not latencies:
        return {"metric": "latency_p95_sec", "value": None, "sample_count": 0}

    sorted_lat = sorted(latencies)
    idx = int(len(sorted_lat) * 0.95)
    p95 = sorted_lat[min(idx, len(sorted_lat) - 1)]
    return {
        "metric": "latency_p95_sec",
        "value": p95,
        "sample_count": len(latencies),
        "p50": statistics.median(sorted_lat),
        "p95": p95,
        "max": sorted_lat[-1],
    }


# ── 심각도 판정 ──────────────────────────────────────────────────────────────

def _evaluate_severity(metric_name: str, value: float | None) -> str:
    """ok / warning / critical 반환."""
    if value is None:
        return "ok"  # 데이터 없으면 알림 미발송 (배포 전 상태)

    cfg = THRESHOLDS[metric_name]
    direction = cfg["direction"]

    if direction == -1:  # 낮을수록 나쁨 (accuracy, success_rate)
        if value < cfg["critical"]:
            return "critical"
        if value < cfg["warning"]:
            return "warning"
    else:  # 높을수록 나쁨 (latency)
        if value > cfg["critical"]:
            return "critical"
        if value > cfg["warning"]:
            return "warning"

    return "ok"


# ── 메시지 포맷 ──────────────────────────────────────────────────────────────

def _pct(v: float | None) -> str:
    return f"{v * 100:.1f}%" if v is not None else "N/A"


def _sec(v: float | None) -> str:
    return f"{v:.2f}s" if v is not None else "N/A"


def _build_alert_message(
    results: list[dict[str, Any]],
    window_min: int,
    checked_at: datetime,
) -> str:
    """텔레그램 알림 메시지 생성."""
    kst = checked_at + timedelta(hours=9)
    ts_str = kst.strftime("%Y-%m-%d %H:%M KST")

    # 최고 심각도 판단
    severity_rank = {"ok": 0, "warning": 1, "critical": 2}
    max_severity = max(results, key=lambda r: severity_rank[r["severity"]])["severity"]
    header_emoji = SEVERITY_EMOJI[max_severity]

    lines = [
        f"{header_emoji} **SM-01·TL-01 KPI 알림** — {SEVERITY_LABEL[max_severity]}",
        f"📅 {ts_str} | 집계 윈도우: 최근 {window_min}분",
        "",
    ]

    for r in results:
        sev = r["severity"]
        emoji = SEVERITY_EMOJI[sev]
        label = SEVERITY_LABEL[sev]
        m = r["metric"]

        if m == "routing_accuracy":
            val_str = _pct(r.get("value"))
            threshold_str = "Warning<88% / Critical<80%"
            lines.append(f"{emoji} **라우팅 정확도 (SM-01)**: {val_str} [{label}]")
            lines.append(f"   임계값: {threshold_str} | 샘플: {r.get('total', 0)}건")
        elif m == "tool_call_success":
            val_str = _pct(r.get("value"))
            threshold_str = "Warning<95% / Critical<90%"
            lines.append(f"{emoji} **툴 호출 성공률 (TL-01)**: {val_str} [{label}]")
            lines.append(f"   임계값: {threshold_str} | 샘플: {r.get('total', 0)}건")
        elif m == "latency_p95_sec":
            val_str = _sec(r.get("value"))
            p50_str = _sec(r.get("p50"))
            threshold_str = "Warning>7s / Critical>10s"
            lines.append(f"{emoji} **Latency p95**: {val_str} (p50: {p50_str}) [{label}]")
            lines.append(f"   임계값: {threshold_str} | 샘플: {r.get('sample_count', 0)}건")

        lines.append("")

    # 대응 가이드
    if max_severity == "critical":
        lines += [
            "---",
            "🔴 **즉시 대응 필요**",
            "- 운영실 담당자 확인 후 rollback 또는 hotfix 판단",
            "- `scripts/bot_deploy_healthcheck.py` 재실행",
            "- 이상 없으면 `scripts/request_restart.sh --reason '임계값 회복'` 으로 재기동 요청",
        ]
    elif max_severity == "warning":
        lines += [
            "---",
            "🟡 **모니터링 강화 권고**",
            "- 다음 주기(5분 후)까지 추이 확인",
            "- Critical 진입 시 즉시 에스컬레이션",
        ]

    return "\n".join(lines)


# ── 텔레그램 전송 ────────────────────────────────────────────────────────────

def _send_telegram_sync(text: str) -> bool:
    """동기 Telegram 전송 (python-telegram-bot 비동기 우회)."""
    import urllib.parse
    import urllib.request

    if not BOT_TOKEN or not OPS_CHAT_ID:
        print("[sm_tl_monitor] BOT_TOKEN 또는 OPS_CHAT_ID 미설정 — 전송 건너뜀")
        return False

    # 마크다운 → HTML 변환 시도
    try:
        from core.telegram_formatting import markdown_to_html
        html_text = markdown_to_html(text)
        parse_mode = "HTML"
    except ImportError:
        html_text = text
        parse_mode = "Markdown"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": str(OPS_CHAT_ID),
        "text": html_text,
        "parse_mode": parse_mode,
        "disable_notification": "false",
    }).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                print(f"[sm_tl_monitor] Telegram 전송 완료 ({len(text)}자)")
                return True
            print(f"[sm_tl_monitor] Telegram 오류: {result}")
            return False
    except Exception as e:
        print(f"[sm_tl_monitor] Telegram 전송 실패: {e}")
        return False


# ── 알림 기록 ────────────────────────────────────────────────────────────────

def _write_alert_log(
    results: list[dict[str, Any]],
    max_severity: str,
    sent: bool,
    checked_at: datetime,
) -> None:
    ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": checked_at.isoformat(),
        "max_severity": max_severity,
        "telegram_sent": sent,
        "metrics": [
            {
                "metric": r["metric"],
                "value": r.get("value"),
                "severity": r["severity"],
            }
            for r in results
        ],
    }
    with ALERT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main(window_min: int = 60, dry_run: bool = False) -> int:
    """단일 점검 실행. 반환값: 0=정상, 1=warning, 2=critical."""
    now = datetime.now(UTC)
    since = now - timedelta(minutes=window_min)

    print(f"[sm_tl_monitor] 시작 — {now.isoformat()}")
    print(f"[sm_tl_monitor] 집계 범위: {since.isoformat()} ~ {now.isoformat()}")

    # 메트릭 수집
    raw_routing = _collect_routing_accuracy(since, now)
    raw_tool    = _collect_tool_call_success(since, now)
    raw_latency = _collect_latency_p95(since, now)

    # 심각도 평가
    results = []
    for raw in [raw_routing, raw_tool, raw_latency]:
        sev = _evaluate_severity(raw["metric"], raw.get("value"))
        results.append({**raw, "severity": sev})

    severity_rank = {"ok": 0, "warning": 1, "critical": 2}
    max_severity = max(results, key=lambda r: severity_rank[r["severity"]])["severity"]

    # 콘솔 요약
    for r in results:
        sev = r["severity"]
        m = r["metric"]
        v = r.get("value")
        val_str = _pct(v) if "accuracy" in m or "success" in m else _sec(v)
        print(f"[sm_tl_monitor]   {m}: {val_str} → {sev.upper()}")

    # Warning/Critical 이상이면 알림
    sent = False
    if max_severity in ("warning", "critical"):
        msg = _build_alert_message(results, window_min, now)
        if dry_run:
            print("\n--- [DRY-RUN] 텔레그램 알림 미리보기 ---")
            print(msg)
            print("--- END ---\n")
            sent = False
        else:
            sent = _send_telegram_sync(msg)
    else:
        print("[sm_tl_monitor] 모든 KPI 정상 — 알림 없음")

    _write_alert_log(results, max_severity, sent, now)
    print(f"[sm_tl_monitor] 완료 — max_severity={max_severity}, sent={sent}")

    return severity_rank[max_severity]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SM-01·TL-01 KPI 모니터")
    parser.add_argument("--window", type=int, default=60, help="집계 윈도우 (분, 기본 60)")
    parser.add_argument("--dry-run", action="store_true", help="Telegram 전송 없이 콘솔 출력")
    args = parser.parse_args()

    exit_code = main(window_min=args.window, dry_run=args.dry_run)
    sys.exit(exit_code)
