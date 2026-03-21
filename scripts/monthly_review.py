#!/usr/bin/env python3
"""월간 성과 리뷰 스크립트 — 매월 1일 10:00 KST (UTC 01:00).

지난 달 회고 집계 → 핵심 지표 트렌드 → ROADMAP.md 업데이트 제안 → Telegram 보고.
"""
from __future__ import annotations

import asyncio
import json
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
MEMORY_PATH = Path(os.environ.get("SHARED_MEMORY_PATH", "~/.ai-org/shared_memory.json")).expanduser()


# ── 지난 달 범위 계산 ─────────────────────────────────────────────────────

def last_month_range() -> tuple[datetime, datetime, str]:
    now = datetime.now(UTC)
    first_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_end = first_this_month
    last_month_start = (first_this_month - timedelta(days=1)).replace(day=1)
    label = last_month_start.strftime("%Y-%m")
    return last_month_start, last_month_end, label


# ── 회고 파일 집계 ────────────────────────────────────────────────────────

def aggregate_retros(month_label: str) -> list[dict]:
    """docs/retros/ 에서 지난 달 회고 파일 집계."""
    retro_dir = PROJECT_ROOT / "docs" / "retros"
    if not retro_dir.exists():
        return []
    retros = []
    for f in sorted(retro_dir.glob(f"{month_label}-*.md")):
        retros.append({"date": f.stem, "content": f.read_text(encoding="utf-8")})
    return retros


def aggregate_retros_from_memory(month_label: str) -> dict:
    """SharedMemory retro 네임스페이스에서 월간 데이터 집계."""
    if not MEMORY_PATH.exists():
        return {}
    try:
        data = json.loads(MEMORY_PATH.read_text())
    except Exception:
        return {}
    retro_ns = data.get("retro", {})
    monthly: dict = {"total": 0, "completed": 0, "failed": 0}
    for date_key, entry in retro_ns.items():
        if date_key.startswith(month_label):
            monthly["total"] += entry.get("total", 0)
            monthly["completed"] += entry.get("completed", 0)
            monthly["failed"] += entry.get("failed", 0)
    return monthly


# ── DB 집계 ───────────────────────────────────────────────────────────────

def collect_monthly_db_metrics(since: datetime, until: datetime) -> dict:
    metrics = {"total": 0, "completed": 0, "failed": 0, "by_dept": {}}
    if not DB_PATH.exists():
        return metrics
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT assigned_dept, status, COUNT(*) as cnt
            FROM pm_tasks
            WHERE created_at >= ? AND created_at < ?
            GROUP BY assigned_dept, status
            """,
            (since.isoformat(), until.isoformat()),
        )
        for row in cur.fetchall():
            dept = row["assigned_dept"] or "unknown"
            status = row["status"]
            cnt = row["cnt"]
            metrics["total"] += cnt
            if status == "completed":
                metrics["completed"] += cnt
                metrics["by_dept"][dept] = metrics["by_dept"].get(dept, 0) + cnt
            elif status == "failed":
                metrics["failed"] += cnt
    return metrics


# ── ROADMAP.md 업데이트 제안 ──────────────────────────────────────────────

def generate_roadmap_suggestion(month_label: str, metrics: dict, retro_count: int) -> str:
    """ROADMAP.md에 추가할 월간 요약 섹션 생성."""
    rate = (
        metrics["completed"] / metrics["total"] * 100
        if metrics["total"] > 0
        else 0
    )
    next_month = (
        datetime.strptime(month_label, "%Y-%m").replace(day=1)
        + timedelta(days=32)
    ).replace(day=1).strftime("%Y-%m")

    lines = [
        f"## {month_label} 월간 성과",
        "",
        f"- 완료율: {rate:.1f}% ({metrics['completed']}/{metrics['total']})",
        f"- 회고 기록: {retro_count}일",
        f"- 실패 태스크: {metrics['failed']}건",
        "",
        f"## {next_month} 계획 (자동 초안)",
        "",
        "- [ ] 이전 달 실패 태스크 원인 분석 및 재시도",
        "- [ ] 봇 간 P2P 협업 비율 향상",
        "- [ ] 신규 자동화 시나리오 발굴",
        "",
    ]
    return "\n".join(lines)


def update_roadmap(suggestion: str, month_label: str) -> None:
    roadmap_path = PROJECT_ROOT / "ROADMAP.md"
    marker = f"## {month_label} 월간 성과"
    if roadmap_path.exists():
        content = roadmap_path.read_text(encoding="utf-8")
        if marker in content:
            print(f"[monthly] ROADMAP.md에 {month_label} 섹션 이미 존재 — 건너뜀")
            return
        content = content + "\n\n" + suggestion
    else:
        content = f"# ROADMAP\n\n{suggestion}"
    roadmap_path.write_text(content, encoding="utf-8")
    print("[monthly] ROADMAP.md 업데이트 완료")


# ── 메시지 생성 ───────────────────────────────────────────────────────────

def build_monthly_message(month_label: str, metrics: dict, retro_count: int) -> str:
    total = metrics["total"]
    completed = metrics["completed"]
    failed = metrics["failed"]
    rate = completed / total * 100 if total > 0 else 0
    by_dept = metrics.get("by_dept", {})

    lines = [
        f"📅 *월간 리뷰 — {month_label}*",
        "",
        f"✅ 완료율: *{rate:.1f}%* ({completed}/{total})",
        f"❌ 실패: {failed}건",
        f"📝 회고 기록: {retro_count}일",
        "",
    ]

    if by_dept:
        lines.append("🤖 *봇별 기여*")
        for dept, cnt in sorted(by_dept.items(), key=lambda x: -x[1]):
            lines.append(f"  • {dept}: {cnt}건")
        lines.append("")

    lines += [
        "📋 ROADMAP.md 업데이트 완료",
        "🚀 다음 달도 함께 성장합시다!",
        "",
        "_(승인 필요 항목 있으면 회신 부탁드립니다)_",
    ]
    return "\n".join(lines)


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
        print(f"[monthly] Telegram 전송 완료 ({len(text)}자)")
    except Exception as e:
        print(f"[monthly] Telegram 전송 실패: {e}")


# ── 파일 저장 ─────────────────────────────────────────────────────────────

def save_monthly_md(content: str, month_label: str) -> Path:
    out_dir = PROJECT_ROOT / "docs" / "monthly"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{month_label}.md"
    out_path.write_text(content, encoding="utf-8")
    print(f"[monthly] 저장: {out_path}")
    return out_path


# ── 메인 ──────────────────────────────────────────────────────────────────

async def main() -> None:
    now = datetime.now(UTC)
    since, until, month_label = last_month_range()

    print(f"[monthly] 시작 — {now.isoformat()}")
    print(f"[monthly] 집계 대상: {month_label} ({since.date()} ~ {until.date()})")

    # 데이터 수집
    retros = aggregate_retros(month_label)
    mem_metrics = aggregate_retros_from_memory(month_label)
    db_metrics = collect_monthly_db_metrics(since, until)

    # 병합 (DB 우선, memory 보완)
    merged = {
        "total": max(db_metrics["total"], mem_metrics.get("total", 0)),
        "completed": max(db_metrics["completed"], mem_metrics.get("completed", 0)),
        "failed": max(db_metrics["failed"], mem_metrics.get("failed", 0)),
        "by_dept": db_metrics.get("by_dept", {}),
    }
    retro_count = len(retros)

    print(f"[monthly] 집계: total={merged['total']}, completed={merged['completed']}, retros={retro_count}")

    # ROADMAP 업데이트
    suggestion = generate_roadmap_suggestion(month_label, merged, retro_count)
    update_roadmap(suggestion, month_label)

    # 월간 MD 생성
    md_content = f"# 월간 리뷰 — {month_label}\n\n{suggestion}"
    if retros:
        md_content += "\n\n## 일별 회고 목록\n\n"
        for r in retros:
            md_content += f"- {r['date']}\n"
    save_monthly_md(md_content, month_label)

    # Telegram 전송
    tg_msg = build_monthly_message(month_label, merged, retro_count)
    if BOT_TOKEN:
        await send_telegram(tg_msg)
    else:
        print("[monthly] PM_BOT_TOKEN 없음 — Telegram 전송 건너뜀")
        print(tg_msg)

    print(f"[monthly] 완료 — {datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
