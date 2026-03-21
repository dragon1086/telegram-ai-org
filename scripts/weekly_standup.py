#!/usr/bin/env python3
"""주간 회의 스크립트 — 매주 월요일 09:00 KST (UTC 00:00).

지난 주 완료 태스크 집계 → 봇별 기여 요약 → Telegram 전송 → MD 저장.
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


# ── ContextDB 쿼리 ────────────────────────────────────────────────────────

def get_last_week_tasks() -> list[dict]:
    """지난 주 완료 태스크 목록."""
    if not DB_PATH.exists():
        return []
    now = datetime.now(UTC)
    week_start = now - timedelta(days=now.weekday() + 7)  # 지난 월요일
    week_end = week_start + timedelta(days=7)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT id, description, assigned_dept, status, result,
                   created_at, updated_at
            FROM pm_tasks
            WHERE status = 'completed'
              AND updated_at >= ? AND updated_at < ?
            ORDER BY assigned_dept, updated_at
            """,
            (week_start.isoformat(), week_end.isoformat()),
        )
        return [dict(r) for r in cur.fetchall()]


def get_task_history_last_week() -> list[dict]:
    """task_history 테이블에서 지난 주 완료 항목."""
    if not DB_PATH.exists():
        return []
    now = datetime.now(UTC)
    week_start = now - timedelta(days=now.weekday() + 7)
    week_end = week_start + timedelta(days=7)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT task_id, assigned_to, status, result, created_at, completed_at
            FROM task_history
            WHERE status = 'completed'
              AND completed_at >= ? AND completed_at < ?
            ORDER BY assigned_to, completed_at
            """,
            (week_start.isoformat(), week_end.isoformat()),
        )
        return [dict(r) for r in cur.fetchall()]


# ── Phase 2 헬퍼 ──────────────────────────────────────────────────────────

def get_weekly_mvp(by_bot: dict[str, list[str]]) -> str:
    """완료 태스크 가장 많은 봇을 MVP로 선정."""
    if not by_bot:
        return "_(데이터 없음)_"
    mvp = max(by_bot.items(), key=lambda x: len(x[1]))
    return f"🏆 *{mvp[0]}* ({len(mvp[1])}건 완료)"


def get_lesson_summary() -> str:
    """LessonMemory에서 이번 주 반복 실패 TOP 3."""
    try:
        from core.lesson_memory import LessonMemory
        lm = LessonMemory()
        stats = lm.get_category_stats()
        if not stats:
            return "_(이번 주 기록된 실패 없음)_"
        top3 = sorted(stats.items(), key=lambda x: x[1], reverse=True)[:3]
        lines = [f"• {cat} ({cnt}회)" for cat, cnt in top3]
        return "\n".join(lines)
    except Exception:
        return "_(lesson_memory 조회 실패)_"


def get_weekly_plan_items() -> list[str]:
    """이번 주 목표 아이템 (RetroReport action_items 기반)."""
    try:
        from core.retro_memory import RetroMemory
        rm = RetroMemory()
        report = rm.generate_weekly_report(week_offset=-1)
        return report.action_items[:3]
    except Exception:
        return ["지난주 데이터 없음 — 새로운 목표를 설정하세요"]


# ── 메시지 생성 ───────────────────────────────────────────────────────────

def build_standup_message(tasks: list[dict], hist: list[dict]) -> tuple[str, str]:
    """Telegram 메시지 + Markdown 내용 반환."""
    now = datetime.now(UTC)
    week_num = now.isocalendar()[1]
    year = now.year

    # 봇별 집계
    by_bot: dict[str, list[str]] = {}
    for t in tasks:
        dept = t.get("assigned_dept") or "unknown"
        desc = t.get("description", "")[:80]
        by_bot.setdefault(dept, []).append(desc)

    for h in hist:
        bot = h.get("assigned_to") or "unknown"
        tid = h.get("task_id", "")[:12]
        by_bot.setdefault(bot, []).append(f"[{tid}] 완료")

    total = len(tasks) + len(hist)

    lines_tg = [
        f"📅 *주간 회의 — {year} W{week_num:02d}*",
        f"📊 지난 주 완료 태스크: *{total}건*",
        "",
    ]
    lines_md = [
        f"# 주간 회의 — {year} W{week_num:02d} ({now.strftime('%Y-%m-%d')})",
        "",
        f"## 완료 태스크 요약: {total}건",
        "",
    ]

    if not by_bot:
        lines_tg.append("_(이번 주 완료 태스크 없음)_")
        lines_md.append("_(이번 주 완료 태스크 없음)_")
    else:
        for bot, items in sorted(by_bot.items()):
            lines_tg.append(f"🤖 *{bot}*: {len(items)}건")
            lines_md.append(f"## {bot}")
            for item in items[:5]:
                lines_md.append(f"- {item}")
            if len(items) > 5:
                lines_md.append(f"- ... 외 {len(items) - 5}건")
            lines_md.append("")

    # Phase 2: MVP, 실패 패턴, 목표
    mvp_text = get_weekly_mvp(by_bot)
    lesson_text = get_lesson_summary()
    plan_items = get_weekly_plan_items()

    plan_lines_tg = []
    for i, item in enumerate(plan_items[:3], 1):
        plan_lines_tg.append(f"{i}. {item}")

    lines_tg += [
        "",
        "🏆 *이번 주 MVP*",
        mvp_text,
        "",
        "💡 *반복 실패 패턴*",
        lesson_text,
        "",
        "🎯 *이번 주 목표*",
        *plan_lines_tg,
        "",
        "✅ 이번 주도 화이팅! 🚀",
    ]

    plan_lines_md = [f"{i}. {item}" for i, item in enumerate(plan_items[:3], 1)]
    lines_md += [
        "## 이번 주 MVP",
        mvp_text,
        "",
        "## 반복 실패 패턴",
        lesson_text,
        "",
        "## 이번 주 목표",
        *plan_lines_md,
        "",
        "---",
        f"*자동 생성: {now.isoformat()}*",
    ]
    return "\n".join(lines_tg), "\n".join(lines_md)


# ── Telegram 전송 ─────────────────────────────────────────────────────────

async def send_telegram(text: str) -> None:
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core.telegram_formatting import markdown_to_html
        from telegram import Bot
        bot = Bot(token=BOT_TOKEN)
        async with bot:
            await bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=markdown_to_html(text),
                parse_mode="HTML",
            )
        print(f"[standup] Telegram 전송 완료 ({len(text)}자)")
    except Exception as e:
        print(f"[standup] Telegram 전송 실패: {e}")


# ── 파일 저장 ─────────────────────────────────────────────────────────────

def save_markdown(content: str) -> Path:
    now = datetime.now(UTC)
    week_num = now.isocalendar()[1]
    year = now.year
    out_dir = PROJECT_ROOT / "docs" / "standups"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{year}-W{week_num:02d}.md"
    out_path.write_text(content, encoding="utf-8")
    print(f"[standup] 저장: {out_path}")
    return out_path


# ── 메인 ──────────────────────────────────────────────────────────────────

async def main() -> None:
    print(f"[standup] 시작 — {datetime.now(UTC).isoformat()}")

    tasks = get_last_week_tasks()
    hist = get_task_history_last_week()
    print(f"[standup] 집계: pm_tasks={len(tasks)}, task_history={len(hist)}")

    tg_msg, md_content = build_standup_message(tasks, hist)
    save_markdown(md_content)

    if BOT_TOKEN:
        await send_telegram(tg_msg)
    else:
        print("[standup] PM_BOT_TOKEN 없음 — Telegram 전송 건너뜀")
        print(tg_msg)

    print(f"[standup] 완료 — {datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
