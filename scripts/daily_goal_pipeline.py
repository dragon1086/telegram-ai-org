#!/usr/bin/env python3
"""일일 목표 파이프라인 — 매일 09:05 KST (UTC 00:05).

pm_progress_guide.md의 IN_PROGRESS 목표를 읽고:
1. STALE 목표 감지 (3일 이상 진척 없음) → 알림
2. TODO 서브태스크 자동 배분 신호를 Telegram에 전송
3. harness-audit 목표 진척률 섹션 데이터 갱신

이 스크립트는 PM 봇에게 "iter 재개" 메시지를 보내는 트리거 역할을 한다.
실제 태스크 실행은 PM 봇이 pm-progress-tracker 스킬로 처리한다.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

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

# PM 진척관리 파일 위치 (claude projects memory)
PROGRESS_GUIDE_PATHS = [
    Path.home() / ".claude" / "projects" / "-Users-rocky-telegram-ai-org" / "memory" / "pm_progress_guide.md",
    PROJECT_ROOT / "memory" / "pm_progress_guide.md",
]


# ── 목표 파싱 ─────────────────────────────────────────────────────────────

def _find_progress_guide() -> Path | None:
    for p in PROGRESS_GUIDE_PATHS:
        if p.exists():
            return p
    return None


def _parse_goals(content: str) -> list[dict]:
    """pm_progress_guide.md에서 IN_PROGRESS 목표 파싱."""
    goals = []
    # 목표 블록 추출: ### [GOAL-XXX] 로 시작하는 섹션
    goal_blocks = re.split(r"### \[(GOAL-\d+)\]", content)
    for i in range(1, len(goal_blocks), 2):
        goal_id = goal_blocks[i]
        block = goal_blocks[i + 1] if i + 1 < len(goal_blocks) else ""

        # 현재상태 추출
        state_match = re.search(r"현재상태:\s*(\w+)", block)
        state = state_match.group(1) if state_match else "UNKNOWN"

        if state not in ("IN_PROGRESS", "TODO"):
            continue

        # 목표명 추출
        name_match = re.search(r'목표명:\s*"?([^"\n]+)"?', block)
        name = name_match.group(1).strip() if name_match else goal_id

        # 마지막 이터레이션 날짜 추출
        iter_dates = re.findall(r"날짜:\s*(\d{4}-\d{2}-\d{2})", block)
        last_iter_date = iter_dates[-1] if iter_dates else None

        # TODO 서브태스크 수
        todo_tasks = re.findall(r"상태:\s*TODO", block)
        in_progress_tasks = re.findall(r"상태:\s*IN_PROGRESS", block)
        done_tasks = re.findall(r"상태:\s*DONE", block)
        total_tasks = len(todo_tasks) + len(in_progress_tasks) + len(done_tasks)
        completion_pct = int(len(done_tasks) / total_tasks * 100) if total_tasks > 0 else 0

        # STALE 판정: 마지막 iter가 3일 이상 전
        is_stale = False
        if last_iter_date:
            try:
                last_dt = datetime.strptime(last_iter_date, "%Y-%m-%d").replace(tzinfo=UTC)
                days_since = (datetime.now(UTC) - last_dt).days
                is_stale = days_since >= 3
            except ValueError:
                pass
        elif state == "IN_PROGRESS":
            is_stale = True  # 날짜 기록 없으면 stale

        goals.append({
            "id": goal_id,
            "name": name,
            "state": state,
            "completion_pct": completion_pct,
            "total_tasks": total_tasks,
            "done_tasks": len(done_tasks),
            "todo_tasks": len(todo_tasks),
            "last_iter_date": last_iter_date,
            "is_stale": is_stale,
        })

    return goals


# ── 보고 메시지 생성 ──────────────────────────────────────────────────────

def _build_pipeline_message(goals: list[dict]) -> str:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    lines = [
        f"## 🔄 일일 목표 파이프라인 — {today}",
        "",
        "PM 봇에게: **pm-progress-tracker 스킬을 실행하고 아래 목표들의 다음 iter를 즉시 착수하세요.**",
        "",
        "### 활성 목표 현황",
    ]

    has_stale = False
    for g in goals:
        stale_mark = " ⚠️ **STALE**" if g["is_stale"] else ""
        last_date = g["last_iter_date"] or "기록 없음"
        lines.append(
            f"- **{g['id']}** {g['name']}{stale_mark}\n"
            f"  달성률: {g['completion_pct']}% ({g['done_tasks']}/{g['total_tasks']}) | "
            f"마지막 iter: {last_date} | 잔여 TODO: {g['todo_tasks']}개"
        )
        if g["is_stale"]:
            has_stale = True

    lines.append("")

    if has_stale:
        lines.append("### ⚠️ 조치 필요")
        lines.append("STALE 목표가 감지됐습니다. PM 봇은 즉시 해당 목표의 iter를 재개하고")
        lines.append("잔여 TODO 서브태스크를 [TEAM:...] / [COLLAB:...] 태그로 배분하세요.")
        lines.append("")

    todo_goals = [g for g in goals if g["todo_tasks"] > 0]
    if todo_goals:
        lines.append("### 📋 자동 배분 대상 (TODO 서브태스크 보유)")
        for g in todo_goals:
            lines.append(f"- {g['id']}: {g['todo_tasks']}개 서브태스크 대기 중")

    lines.append("")
    lines.append("> 이 메시지는 `daily_goal_pipeline.py` 크론이 자동 생성합니다.")
    lines.append("> PM 봇은 이 트리거를 받으면 사용자 확인 없이 즉시 iter를 진행해야 합니다.")

    return "\n".join(lines)


# ── 목표 진척률 스냅샷 저장 ───────────────────────────────────────────────

def _save_goal_snapshot(goals: list[dict]) -> None:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    out_dir = PROJECT_ROOT / "docs" / "goal_snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{today}-goal-snapshot.md"

    lines = [f"# 목표 진척률 스냅샷 — {today}", ""]
    for g in goals:
        lines.append(f"## {g['id']} — {g['name']}")
        lines.append(f"- 상태: {g['state']}")
        lines.append(f"- 달성률: {g['completion_pct']}% ({g['done_tasks']}/{g['total_tasks']})")
        lines.append(f"- 마지막 iter: {g['last_iter_date'] or '기록 없음'}")
        lines.append(f"- STALE: {'YES' if g['is_stale'] else 'NO'}")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[goal_pipeline] 스냅샷 저장: {out_path}")


# ── Telegram 전송 ─────────────────────────────────────────────────────────

async def send_telegram(text: str) -> None:
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from core.telegram_formatting import markdown_to_html
        from telegram import Bot
        bot = Bot(token=BOT_TOKEN)
        async with bot:
            await bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=markdown_to_html(text),
                parse_mode="HTML",
            )
        print(f"[goal_pipeline] Telegram 전송 완료 ({len(text)}자)")
    except Exception as e:
        print(f"[goal_pipeline] Telegram 전송 실패: {e}")


# ── 메인 ─────────────────────────────────────────────────────────────────

async def main() -> None:
    print(f"[goal_pipeline] 시작: {datetime.now(UTC).isoformat()}")

    guide_path = _find_progress_guide()
    if guide_path is None:
        print("[goal_pipeline] pm_progress_guide.md 파일을 찾을 수 없음. 스킵.")
        return

    content = guide_path.read_text(encoding="utf-8")
    goals = _parse_goals(content)

    if not goals:
        print("[goal_pipeline] 활성 목표 없음. 종료.")
        return

    print(f"[goal_pipeline] 활성 목표 {len(goals)}개 발견")
    for g in goals:
        stale = "⚠️ STALE" if g["is_stale"] else "OK"
        print(f"  {g['id']}: {g['completion_pct']}% ({stale})")

    # 스냅샷 저장 (harness-audit에서 참조)
    _save_goal_snapshot(goals)

    # Telegram 파이프라인 트리거 전송
    msg = _build_pipeline_message(goals)
    await send_telegram(msg)

    print(f"[goal_pipeline] 완료: {datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
