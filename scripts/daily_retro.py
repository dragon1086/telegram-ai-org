#!/usr/bin/env python3
"""일일 회고 스크립트 — 매일 23:30 KST (UTC 14:30).

오늘 완료 run 집계 → SharedMemory 저장 → Telegram 전송 → MD 저장.
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


# ── ContextDB 쿼리 ────────────────────────────────────────────────────────

def get_today_tasks() -> list[dict]:
    """오늘 완료된 태스크 목록."""
    if not DB_PATH.exists():
        return []
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        # pm_tasks
        cur = conn.execute(
            """
            SELECT id, description, assigned_dept, status, result,
                   created_at, updated_at
            FROM pm_tasks
            WHERE status IN ('completed', 'failed')
              AND updated_at >= ? AND updated_at < ?
            ORDER BY updated_at
            """,
            (today_start.isoformat(), today_end.isoformat()),
        )
        pm = [dict(r) for r in cur.fetchall()]

        # task_history
        cur2 = conn.execute(
            """
            SELECT task_id, assigned_to, status, result, created_at, completed_at
            FROM task_history
            WHERE completed_at >= ? AND completed_at < ?
            ORDER BY completed_at
            """,
            (today_start.isoformat(), today_end.isoformat()),
        )
        hist = [dict(r) for r in cur2.fetchall()]
    return pm + hist


# ── SharedMemory 저장 ─────────────────────────────────────────────────────

def save_to_shared_memory(retro_data: dict) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if MEMORY_PATH.exists():
        try:
            existing = json.loads(MEMORY_PATH.read_text())
        except Exception:
            pass
    retro_ns = existing.setdefault("retro", {})
    date_key = datetime.now(UTC).strftime("%Y-%m-%d")
    retro_ns[date_key] = retro_data
    MEMORY_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
    print(f"[retro] SharedMemory 저장 완료: retro/{date_key}")


# ── 메시지 생성 ───────────────────────────────────────────────────────────

async def _llm_insights(tasks: list[dict]) -> str | None:
    """PMDecisionClient로 태스크 분석 → 3가지 인사이트 생성."""
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        from core.pm_decision import PMDecisionClient
    except ImportError:
        print("[retro] PMDecisionClient 없음 — LLM 인사이트 건너뜀")
        return None

    completed = [t for t in tasks if t.get("status") == "completed"]
    failed = [t for t in tasks if t.get("status") == "failed"]

    task_summary = ""
    for t in completed[:15]:
        desc = t.get("description") or t.get("task_id", "")
        task_summary += f"- [completed] {desc[:100]}\n"
    for t in failed[:10]:
        desc = t.get("description") or t.get("task_id", "")
        result = t.get("result", "")[:100]
        task_summary += f"- [failed] {desc[:100]} | reason: {result}\n"

    if not task_summary:
        return None

    prompt = (
        f"오늘 AI 에이전트 팀이 수행한 태스크 목록:\n\n{task_summary}\n\n"
        "위 내용을 분석해서 정확히 3가지를 한국어로 간결하게 답해줘:\n"
        "1. 오늘 가장 잘한 것 (한 줄)\n"
        "2. 실패 원인 & 패턴 (한 줄, 실패가 없으면 '실패 없음')\n"
        "3. 내일 실험할 것 (한 줄)\n\n"
        "각 항목은 번호와 함께 한 줄로 답해."
    )

    try:
        client = PMDecisionClient("aiorg_pm_bot", engine="claude-code")
        return await asyncio.wait_for(
            client.complete(prompt),
            timeout=30.0,
        )
    except Exception as e:
        print(f"[retro] LLM 인사이트 생성 실패: {e}")
        return None


def build_retro(tasks: list[dict], llm_insight: str | None = None) -> tuple[str, str, dict]:
    now = datetime.now(UTC)
    date_str = now.strftime("%Y-%m-%d")

    completed = [t for t in tasks if t.get("status") == "completed"]
    failed = [t for t in tasks if t.get("status") == "failed"]
    total = len(tasks)

    retro_data = {
        "date": date_str,
        "total": total,
        "completed": len(completed),
        "failed": len(failed),
        "tasks": tasks[:20],  # 최대 20개 저장
    }
    if llm_insight:
        retro_data["llm_insight"] = llm_insight

    lines_tg = [
        f"🌙 *일일 회고 — {date_str}*",
        "",
        f"📋 오늘 처리: *{total}건* (완료 {len(completed)}, 실패 {len(failed)})",
        "",
    ]
    lines_md = [
        f"# 작업 회고 — {date_str}",
        "",
        f"## 오늘 완료된 태스크: {len(completed)}건",
        "",
    ]

    # 완료 항목
    for t in completed[:10]:
        desc = t.get("description") or t.get("task_id", "")
        dept = t.get("assigned_dept") or t.get("assigned_to", "")
        lines_tg.append(f"✅ {desc[:50]} _({dept})_")
        lines_md.append(f"- {desc} ({dept}) ✅")

    if len(completed) > 10:
        lines_tg.append(f"  ... 외 {len(completed) - 10}건")

    # 실패 항목
    if failed:
        lines_tg.append("")
        lines_tg.append(f"⚠️ 실패: {len(failed)}건")
        lines_md += ["", f"## 실패 태스크: {len(failed)}건", ""]
        for t in failed:
            desc = t.get("description") or t.get("task_id", "")
            lines_md.append(f"- {desc} ❌")

    if not tasks:
        lines_tg.append("_(오늘 완료된 태스크 없음)_")

    # LLM 인사이트 추가
    if llm_insight:
        lines_tg += [
            "",
            "🧠 *AI 인사이트*",
            llm_insight,
        ]
        lines_md += [
            "",
            "## AI 인사이트",
            "",
            llm_insight,
        ]

    lines_tg += ["", "내일도 화이팅! 💪"]
    lines_md += [
        "",
        "---",
        f"*자동 생성: {now.isoformat()}*",
    ]
    return "\n".join(lines_tg), "\n".join(lines_md), retro_data


# ── Telegram 전송 ─────────────────────────────────────────────────────────

async def send_telegram(text: str) -> None:
    try:
        from telegram import Bot
        bot = Bot(token=BOT_TOKEN)
        async with bot:
            await bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=text,
                parse_mode="Markdown",
            )
        print(f"[retro] Telegram 전송 완료 ({len(text)}자)")
    except Exception as e:
        print(f"[retro] Telegram 전송 실패: {e}")


# ── 파일 저장 ─────────────────────────────────────────────────────────────

def save_markdown(content: str) -> Path:
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    out_dir = PROJECT_ROOT / "docs" / "retros"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date_str}.md"
    out_path.write_text(content, encoding="utf-8")
    print(f"[retro] 저장: {out_path}")
    return out_path


# ── 메인 ──────────────────────────────────────────────────────────────────

async def main() -> None:
    print(f"[retro] 시작 — {datetime.now(UTC).isoformat()}")

    tasks = get_today_tasks()
    print(f"[retro] 오늘 태스크: {len(tasks)}건")

    # LLM 인사이트 생성
    llm_insight = await _llm_insights(tasks)
    if llm_insight:
        print(f"[retro] LLM 인사이트 생성 완료")

    tg_msg, md_content, retro_data = build_retro(tasks, llm_insight=llm_insight)
    save_to_shared_memory(retro_data)
    save_markdown(md_content)

    if BOT_TOKEN:
        await send_telegram(tg_msg)
    else:
        print("[retro] PM_BOT_TOKEN 없음 — Telegram 전송 건너뜀")
        print(tg_msg)

    print(f"[retro] 완료 — {datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
