#!/usr/bin/env python3
"""일일 메트릭 보고 스크립트 — 매일 08:00 KST (UTC 23:00 전날).

ContextDB에서 어제 지표 집계 → Telegram 전송.
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

# ── 환경 설정 ─────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent


def _load_env() -> None:
    for env_path in (Path.home() / ".ai-org" / "config.yaml", PROJECT_ROOT / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

BOT_TOKEN = os.environ.get("PM_BOT_TOKEN", "")
GROUP_CHAT_ID = int(os.environ.get("TELEGRAM_GROUP_CHAT_ID", "-5203707291"))
DB_PATH = Path(os.environ.get("CONTEXT_DB_PATH", "~/.ai-org/context.db")).expanduser()


# ── 지표 수집 ─────────────────────────────────────────────────────────────

def collect_metrics(since: datetime, until: datetime) -> dict:
    """since ~ until 범위의 지표 수집."""
    metrics: dict = {
        "period_start": since.isoformat(),
        "period_end": until.isoformat(),
        "total_tasks": 0,
        "completed_tasks": 0,
        "failed_tasks": 0,
        "task_completion_rate": 0.0,
        "avg_duration_sec": 0.0,
        "bot_utilization": {},
        "retry_count": 0,
        "error_rate": 0.0,
    }

    if not DB_PATH.exists():
        return metrics

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        # pm_tasks 집계
        cur = conn.execute(
            """
            SELECT status, assigned_dept, COUNT(*) as cnt
            FROM pm_tasks
            WHERE created_at >= ? AND created_at < ?
            GROUP BY status, assigned_dept
            """,
            (since.isoformat(), until.isoformat()),
        )
        for row in cur.fetchall():
            status = row["status"]
            dept = row["assigned_dept"] or "unknown"
            cnt = row["cnt"]
            metrics["total_tasks"] += cnt
            if status == "completed":
                metrics["completed_tasks"] += cnt
                metrics["bot_utilization"][dept] = (
                    metrics["bot_utilization"].get(dept, 0) + cnt
                )
            elif status == "failed":
                metrics["failed_tasks"] += cnt

        # task_history 보완
        cur2 = conn.execute(
            """
            SELECT assigned_to, status,
                   AVG(
                     CAST((julianday(COALESCE(completed_at, created_at))
                          - julianday(created_at)) * 86400 AS INTEGER)
                   ) as avg_sec
            FROM task_history
            WHERE created_at >= ? AND created_at < ?
            GROUP BY assigned_to, status
            """,
            (since.isoformat(), until.isoformat()),
        )
        durations = []
        for row in cur2.fetchall():
            if row["avg_sec"] and row["avg_sec"] > 0:
                durations.append(row["avg_sec"])
            if row["status"] == "completed" and row["assigned_to"]:
                bot = row["assigned_to"]
                metrics["bot_utilization"][bot] = (
                    metrics["bot_utilization"].get(bot, 0) + 1
                )

        if durations:
            metrics["avg_duration_sec"] = sum(durations) / len(durations)

    total = metrics["total_tasks"]
    if total > 0:
        metrics["task_completion_rate"] = (
            metrics["completed_tasks"] / total * 100
        )
        metrics["error_rate"] = metrics["failed_tasks"] / total * 100

    return metrics


# ── 메시지 생성 ───────────────────────────────────────────────────────────

def build_metrics_message(metrics: dict, date_str: str) -> str:
    total = metrics["total_tasks"]
    completed = metrics["completed_tasks"]
    failed = metrics["failed_tasks"]
    rate = metrics["task_completion_rate"]
    avg_sec = metrics["avg_duration_sec"]
    error_rate = metrics["error_rate"]
    bot_util = metrics["bot_utilization"]

    avg_min = avg_sec / 60 if avg_sec > 0 else 0

    lines = [
        f"📊 *일일 메트릭 — {date_str}*",
        "",
        f"✅ 완료율: *{rate:.1f}%* ({completed}/{total})",
        f"⏱ 평균 시간: *{avg_min:.1f}분*",
        f"❌ 오류율: *{error_rate:.1f}%* ({failed}건)",
        "",
    ]

    if bot_util:
        lines.append("🤖 *봇별 처리량*")
        for bot, cnt in sorted(bot_util.items(), key=lambda x: -x[1]):
            lines.append(f"  • {bot}: {cnt}건")
        lines.append("")

    if total == 0:
        lines.append("_(어제 처리된 태스크 없음)_")

    lines.append("📈 오늘도 순항 중!")
    return "\n".join(lines)


# ── Telegram 전송 ─────────────────────────────────────────────────────────

async def send_telegram(text: str) -> None:
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from telegram import Bot

        from core.telegram_formatting import markdown_to_html
        bot = Bot(token=BOT_TOKEN)
        async with bot:
            await bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=markdown_to_html(text),
                parse_mode="HTML",
            )
        print(f"[metrics] Telegram 전송 완료 ({len(text)}자)")
    except Exception as e:
        print(f"[metrics] Telegram 전송 실패: {e}")


# ── 메인 ──────────────────────────────────────────────────────────────────

async def main() -> None:
    now = datetime.now(UTC)
    # 08:00 KST 실행이므로 "어제" KST = "전날 UTC 15:00 ~ 오늘 UTC 15:00" 근사
    # 단순하게 지난 24시간 집계
    since = now - timedelta(hours=24)
    date_str = (now + timedelta(hours=9)).strftime("%Y-%m-%d")  # KST 날짜

    print(f"[metrics] 시작 — {now.isoformat()}")
    print(f"[metrics] 집계 범위: {since.isoformat()} ~ {now.isoformat()}")

    metrics = collect_metrics(since, now)
    print(f"[metrics] total={metrics['total_tasks']}, completed={metrics['completed_tasks']}")

    msg = build_metrics_message(metrics, date_str)

    if BOT_TOKEN:
        await send_telegram(msg)
    else:
        print("[metrics] PM_BOT_TOKEN 없음 — Telegram 전송 건너뜀")
        print(msg)

    print(f"[metrics] 완료 — {datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
