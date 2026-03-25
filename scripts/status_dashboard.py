#!/usr/bin/env python3
"""status_dashboard.py — 현재 시스템 운영 상태를 터미널에 출력.

사용법:
    python scripts/status_dashboard.py
    python scripts/status_dashboard.py --json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))


async def _get_db_stats() -> dict:
    """ContextDB에서 태스크 통계 조회."""
    try:
        import aiosqlite
        db_path = PROJECT_DIR / ".ai-org" / "pm_tasks.db"
        if not db_path.exists():
            # Try alternate location
            db_path = PROJECT_DIR / "pm_tasks.db"
        if not db_path.exists():
            return {}

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            # 활성 부모 태스크
            cursor = await db.execute(
                "SELECT status, COUNT(*) as cnt FROM pm_tasks "
                "WHERE parent_id IS NULL GROUP BY status"
            )
            parent_rows = await cursor.fetchall()
            parent_stats = {r["status"]: r["cnt"] for r in parent_rows}

            # 최근 1시간 완료 태스크
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM pm_tasks "
                "WHERE status='done' AND parent_id IS NOT NULL "
                "AND updated_at > datetime('now', '-1 hour')"
            )
            row = await cursor.fetchone()
            recent_done = row["cnt"] if row else 0

            # 최근 1시간 실패 태스크
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM pm_tasks "
                "WHERE status='failed' AND parent_id IS NOT NULL "
                "AND updated_at > datetime('now', '-1 hour')"
            )
            row = await cursor.fetchone()
            recent_failed = row["cnt"] if row else 0

            # stale 태스크 (assigned 5분+)
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM pm_tasks "
                "WHERE status='assigned' "
                "AND created_at < datetime('now', '-5 minutes')"
            )
            row = await cursor.fetchone()
            stale_count = row["cnt"] if row else 0

            return {
                "parent_tasks": parent_stats,
                "recent_done_1h": recent_done,
                "recent_failed_1h": recent_failed,
                "stale_subtasks": stale_count,
            }
    except Exception as e:
        return {"error": str(e)}


def _get_bot_status() -> list[dict]:
    """health_check.py를 임포트하여 봇 상태 조회."""
    try:
        sys.path.insert(0, str(PROJECT_DIR / "scripts"))
        from health_check import check_all_bots
        return check_all_bots()
    except Exception as e:
        return [{"error": str(e)}]


def _get_log_tail(log_path: Path, lines: int = 5) -> list[str]:
    try:
        if not log_path.exists():
            return []
        with open(log_path) as f:
            all_lines = f.readlines()
        return [line.rstrip() for line in all_lines[-lines:]]
    except Exception:
        return []


async def _build_report(as_json: bool = False) -> None:
    db_stats, bot_status = await asyncio.gather(
        _get_db_stats(),
        asyncio.to_thread(_get_bot_status),
    )

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    if as_json:
        print(json.dumps({
            "timestamp": now,
            "bots": bot_status,
            "tasks": db_stats,
        }, indent=2, ensure_ascii=False))
        return

    # ── Header ──────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  📊 AI-Org Status Dashboard  [{now}]")
    print(f"{'='*60}")

    # ── Bot Status ──────────────────────────────────────────
    print("\n🤖 Bot Status")
    print(f"  {'Bot':<32} {'Status'}")
    print(f"  {'-'*45}")
    up_count = 0
    for bot in bot_status:
        if "error" in bot:
            print(f"  ERROR: {bot['error']}")
            break
        icon = "✅" if bot["alive"] else "❌"
        short_id = bot["org_id"].replace("aiorg_", "").replace("_bot", "")
        print(f"  {icon} {short_id:<30} {bot['status']}")
        if bot["alive"]:
            up_count += 1
    total_bots = len([b for b in bot_status if "error" not in b])
    print(f"\n  → {up_count}/{total_bots} 봇 운영 중")

    # ── Task Stats ──────────────────────────────────────────
    print("\n📋 Task Stats (past 1h)")
    if "error" in db_stats:
        print(f"  DB 접근 오류: {db_stats['error']}")
    else:
        parent = db_stats.get("parent_tasks", {})
        active = sum(parent.get(s, 0) for s in ("running", "assigned", "pending"))
        done_total = parent.get("done", 0)
        failed_total = parent.get("failed", 0)
        needs_review = parent.get("needs_review", 0)
        print(f"  활성 부모 태스크:     {active}")
        print(f"  완료 (전체):          {done_total}")
        print(f"  실패 (전체):          {failed_total}")
        if needs_review:
            print(f"  검토 필요:            {needs_review}  ⚠️")
        print(f"  최근 1h 완료:         {db_stats.get('recent_done_1h', 0)}")
        print(f"  최근 1h 실패:         {db_stats.get('recent_failed_1h', 0)}")
        stale = db_stats.get("stale_subtasks", 0)
        stale_flag = " ⚠️" if stale > 0 else ""
        print(f"  Stale 서브태스크:     {stale}{stale_flag}")

    # ── Watchdog Log ────────────────────────────────────────
    watchdog_log = Path.home() / ".ai-org" / "watchdog.log"
    recent_logs = _get_log_tail(watchdog_log, 3)
    if recent_logs:
        print("\n📡 Watchdog (최근 로그)")
        for line in recent_logs:
            print(f"  {line}")

    print(f"\n{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-Org 운영 상태 대시보드")
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    args = parser.parse_args()
    asyncio.run(_build_report(as_json=args.json))


if __name__ == "__main__":
    main()
