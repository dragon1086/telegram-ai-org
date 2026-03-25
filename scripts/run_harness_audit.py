#!/usr/bin/env python3
"""harness-audit 자동 실행 스크립트 — 매주 금요일 17:05 KST (UTC 08:05).

시스템 전체 건강도 + 목표 진척률 + COLLAB 활성도를 점검하고
STALE 목표 감지 시 PM 봇에게 즉시 iter 재개 트리거를 보낸다.

동작:
1. pm_progress_guide.md 파싱 → 목표별 달성률·STALE 여부 판정
2. logs/ 분석 → 최근 7일 COLLAB 사용 횟수 집계
3. 감사 결과를 docs/audits/YYYY-MM-DD-harness-audit.md 저장
4. Telegram 그룹 채팅에 감사 리포트 전송
5. STALE 감지 시 → PM 봇에 iter 재개 메시지 전송 (auto-trigger)
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


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

PROGRESS_GUIDE_PATHS = [
    Path.home() / ".claude" / "projects" / "-Users-rocky-telegram-ai-org" / "memory" / "pm_progress_guide.md",
    PROJECT_ROOT / "memory" / "pm_progress_guide.md",
]

COLLAB_PATTERNS = [
    r"COLLAB_PREFIX",
    r"🙋 도와줄",
    r"\[COLLAB:",
]


# ── 목표 파싱 ─────────────────────────────────────────────────────────────

def _find_progress_guide() -> Path | None:
    for p in PROGRESS_GUIDE_PATHS:
        if p.exists():
            return p
    return None


def _parse_goals(content: str) -> list[dict]:
    goals = []
    goal_blocks = re.split(r"### \[(GOAL-\d+)\]", content)
    for i in range(1, len(goal_blocks), 2):
        goal_id = goal_blocks[i]
        block = goal_blocks[i + 1] if i + 1 < len(goal_blocks) else ""

        state_match = re.search(r"현재상태:\s*(\w+)", block)
        state = state_match.group(1) if state_match else "UNKNOWN"
        if state not in ("IN_PROGRESS", "TODO"):
            continue

        name_match = re.search(r'목표명:\s*"?([^"\n]+)"?', block)
        name = name_match.group(1).strip() if name_match else goal_id

        iter_dates = re.findall(r"날짜:\s*(\d{4}-\d{2}-\d{2})", block)
        last_iter_date = iter_dates[-1] if iter_dates else None

        todo_tasks = re.findall(r"상태:\s*TODO", block)
        in_progress_tasks = re.findall(r"상태:\s*IN_PROGRESS", block)
        done_tasks = re.findall(r"상태:\s*DONE", block)
        total_tasks = len(todo_tasks) + len(in_progress_tasks) + len(done_tasks)
        completion_pct = int(len(done_tasks) / total_tasks * 100) if total_tasks > 0 else 0

        is_stale = False
        if last_iter_date:
            try:
                last_dt = datetime.strptime(last_iter_date, "%Y-%m-%d").replace(tzinfo=UTC)
                days_since = (datetime.now(UTC) - last_dt).days
                is_stale = days_since >= 3
            except ValueError:
                pass
        elif state == "IN_PROGRESS":
            is_stale = True

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


# ── COLLAB 활성도 집계 ────────────────────────────────────────────────────

def _count_collab_usage(days: int = 7) -> int:
    """최근 N일간 COLLAB 사용 횟수 집계."""
    logs_dir = PROJECT_ROOT / "logs"
    if not logs_dir.exists():
        return 0

    count = 0
    cutoff = datetime.now(UTC) - timedelta(days=days)

    for log_file in logs_dir.glob("*.log"):
        try:
            # 최근 수정된 파일만 검사
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime, tz=UTC)
            if mtime < cutoff:
                continue
            content = log_file.read_text(encoding="utf-8", errors="ignore")
            for pattern in COLLAB_PATTERNS:
                count += len(re.findall(pattern, content))
        except Exception:
            continue

    dispatch_log = logs_dir / "collab_dispatch.jsonl"
    if dispatch_log.exists():
        try:
            for line in dispatch_log.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                ts = payload.get("ts", "")
                if not ts:
                    continue
                event_dt = datetime.fromisoformat(ts)
                if event_dt.tzinfo is None:
                    event_dt = event_dt.replace(tzinfo=UTC)
                if event_dt >= cutoff:
                    count += 1
        except Exception:
            pass
    return count


# ── 감사 리포트 생성 ──────────────────────────────────────────────────────

def _build_audit_report(goals: list[dict], collab_count: int) -> str:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    stale_goals = [g for g in goals if g["is_stale"]]

    # COLLAB 상태 판정
    if collab_count == 0:
        collab_status = "❌ COLLAB_INACTIVE"
        collab_note = "⚠️ 이번 iter에서 COLLAB 태그 의무 사용"
    elif collab_count < 4:
        collab_status = "⚠️ COLLAB_LOW"
        collab_note = f"최근 7일 {collab_count}회 — 더 적극적으로 COLLAB 활용 필요"
    else:
        collab_status = "✅ COLLAB_HEALTHY"
        collab_note = f"최근 7일 {collab_count}회"

    # 목표 상태 판정
    goal_status = "✅ ON_TRACK" if not stale_goals else f"⚠️ STALE ({len(stale_goals)}개)"

    lines = [
        f"## 🔬 Harness Audit Report — {today}",
        "",
        "| 영역 | 상태 |",
        "|------|------|",
        f"| 목표 진척률 | {goal_status} |",
        f"| 협업 활성도 | {collab_status} |",
        "",
        "### 목표별 현황",
    ]

    for g in goals:
        stale_mark = " ⚠️ **STALE**" if g["is_stale"] else " ✅"
        last_date = g["last_iter_date"] or "기록 없음"
        lines.append(
            f"- **{g['id']}** {g['name']}{stale_mark}\n"
            f"  달성률: {g['completion_pct']}% ({g['done_tasks']}/{g['total_tasks']}) | "
            f"마지막 iter: {last_date}"
        )

    lines.extend([
        "",
        f"### 협업 활성도: {collab_note}",
        "",
    ])

    if stale_goals:
        lines.extend([
            "### ⚠️ STALE 자동 재개 체인 발동",
            "",
            "아래 목표들이 3일 이상 진척 없어 자동 iter 재개를 트리거합니다:",
        ])
        for g in stale_goals:
            lines.append(f"- {g['id']}: {g['name']} ({g['completion_pct']}% 달성)")
        lines.extend([
            "",
            "**자동 배분 실행**:",
            "- 개발실 담당 → [TEAM:engineering-senior-developer] 즉시 착수",
            "- 운영실 담당 → [COLLAB:ST-11 v1.0.0 릴리스 착수|맥락: harness-audit STALE 감지, 자동 재개]",
            "- 목표 재개 메시지를 PM 봇에 전송",
        ])

    if collab_count == 0:
        lines.extend([
            "",
            "### ⚠️ COLLAB_INACTIVE — 즉시 조치 필요",
            "",
            "다음 iter에서 반드시 [COLLAB:...] 태그를 사용하세요.",
            "다부서 태스크가 있으면 무조건 COLLAB으로 위임합니다.",
        ])

    lines.extend([
        "",
        f"> 이 리포트는 `run_harness_audit.py`가 자동 생성합니다. ({today})",
    ])

    return "\n".join(lines)


def _build_auto_resume_message(stale_goals: list[dict]) -> str:
    """STALE 목표 자동 재개 메시지 (PM 봇 트리거용)."""
    lines = [
        "## 🔄 [harness-audit] 자율 iter 자동 재개",
        "",
        "harness-audit이 STALE 목표를 감지했습니다.",
        "**PM 봇은 pm-progress-tracker 스킬을 실행하고 즉시 iter를 재개하세요.**",
        "",
        "### STALE 목표 목록",
    ]
    for g in stale_goals:
        lines.append(
            f"- **{g['id']}** {g['name']}\n"
            f"  달성률: {g['completion_pct']}% | 마지막 iter: {g['last_iter_date'] or '기록 없음'}"
        )
    lines.extend([
        "",
        "### 자동 배분 대상",
        "- ST-09 완료 시 → ST-08 리팩토링 착수 (개발실)",
        "- ST-09 완료 시 → [COLLAB:ST-11 v1.0.0 릴리스 준비|맥락: ST-09 완료, 운영실 배포 준비 착수]",
        "",
        "> 사용자 확인 없이 즉시 실행. 자율 실행 원칙.",
    ])
    return "\n".join(lines)


# ── Telegram 전송 ─────────────────────────────────────────────────────────

async def send_telegram(text: str) -> None:
    try:
        from telegram import Bot

        from core.telegram_formatting import markdown_to_html
        bot = Bot(token=BOT_TOKEN)
        async with bot:
            await bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=markdown_to_html(text),
                parse_mode="HTML",
            )
        print(f"[harness_audit] Telegram 전송 완료 ({len(text)}자)")
    except Exception as e:
        print(f"[harness_audit] Telegram 전송 실패: {e}")


# ── 스냅샷 저장 ───────────────────────────────────────────────────────────

def _save_audit_report(report: str) -> Path:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    out_dir = PROJECT_ROOT / "docs" / "audits"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{today}-harness-audit.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"[harness_audit] 감사 리포트 저장: {out_path}")
    return out_path


# ── 메인 ─────────────────────────────────────────────────────────────────

async def main() -> None:
    print(f"[harness_audit] 시작: {datetime.now(UTC).isoformat()}")

    guide_path = _find_progress_guide()
    goals: list[dict] = []
    if guide_path:
        content = guide_path.read_text(encoding="utf-8")
        goals = _parse_goals(content)
        print(f"[harness_audit] 활성 목표 {len(goals)}개")
    else:
        print("[harness_audit] pm_progress_guide.md 없음")

    collab_count = _count_collab_usage(days=7)
    print(f"[harness_audit] COLLAB 사용 횟수 (7일): {collab_count}")

    report = _build_audit_report(goals, collab_count)
    _save_audit_report(report)

    if BOT_TOKEN:
        await send_telegram(report)
        stale_goals = [g for g in goals if g["is_stale"]]
        if stale_goals:
            resume_msg = _build_auto_resume_message(stale_goals)
            await send_telegram(resume_msg)
            print(f"[harness_audit] STALE {len(stale_goals)}개 — 자동 재개 트리거 전송")
    else:
        print("[harness_audit] PM_BOT_TOKEN 없음 — Telegram 전송 스킵")
        print(report)

    print(f"[harness_audit] 완료: {datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
