#!/usr/bin/env python3
"""RETRO-21~26 GoalTracker 백필 스크립트.

2026-03-30 일일회고에서 발굴된 6개 ACTION(RETRO-21~26)이
GoalTracker 등록 없이 MEMORY.md pending 상태로만 존재하는 문제를 해결.

근본 원인:
    - 2026-03-30 retro 실행 시점에 _register_retro_actions()에
      registrar=None (미주입) 상태였으므로 GoalTracker 등록이 생략됨.
    - 이후 2026-03-31 daily_retro.py 패치로 registrar 주입 경로 활성화됨.
    - 이 스크립트는 누락된 6개 ACTION을 소급 등록 + dispatch.

실행:
    .venv/bin/python scripts/retro_backfill.py

    Telegram 전송 없이 드라이런:
    .venv/bin/python scripts/retro_backfill.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

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

# ── RETRO-21~26 ACTION 정의 ─────────────────────────────────────────────────
# 2026-03-30 일일회고에서 발굴된 6개 ACTION.
# retro 파일에서 일부 truncation 발생 → 맥락 기반 복원.

RETRO_ACTIONS: list[dict] = [
    {
        "retro_id":    "RETRO-21",
        "org_id":      "aiorg_engineering_bot",
        "org_name":    "개발실",
        "action_desc": "진단→액션 자동 연결 파이프라인 구현",
        "context":     "회고 ACTION이 GoalTracker에 자동 등록→봇 dispatch되는 파이프라인 부재. "
                       "daily_retro 결과가 매번 pending으로 쌓이는 근본 원인 해소.",
        "priority":    "high",
    },
    {
        "retro_id":    "RETRO-22",
        "org_id":      "aiorg_ops_bot",
        "org_name":    "운영실",
        "action_desc": '도구가 "실행을 강제"하는 메커니즘 구현 — pre-flight 미통과 시 배포 차단 연동',
        "context":     "infra-baseline·pre-flight 도구는 있으나 실제 배포를 막지 않음. "
                       "도구가 실행 게이트가 되도록 강제 연결.",
        "priority":    "high",
    },
    {
        "retro_id":    "RETRO-23",
        "org_id":      "aiorg_design_bot",
        "org_name":    "디자인실",
        "action_desc": '"보이는 것"이 "막는 것"이 되는 UI 실행 블로킹 패턴 적용',
        "context":     "DAG 시각화·E2E 로그 헤더 UI는 완성됐으나 실제 배포 블로킹과 미연결. "
                       "진단 가시화 → 실행 차단 UI 패턴 설계 필요.",
        "priority":    "medium",
    },
    {
        "retro_id":    "RETRO-24",
        "org_id":      "aiorg_product_bot",
        "org_name":    "기획실",
        "action_desc": '"정책 문서"가 "실행 게이트"가 되는 정책→게이트 연결 PRD 작성',
        "context":     "RETRO-12 자동화 정책 스펙은 완성됐으나 실행 게이트와 미연결. "
                       "정책 준수 여부를 실행 전 강제 검증하는 구조 PRD.",
        "priority":    "medium",
    },
    {
        "retro_id":    "RETRO-25",
        "org_id":      "aiorg_growth_bot",
        "org_name":    "성장실",
        "action_desc": '"측정됐다"가 "개선됐다"가 되는 지표→실행 자동 연결 구현',
        "context":     "RETRO-19 infra_baseline_version 필드로 지표 추적은 됐으나 "
                       "이상치 발생 시 개선 액션이 자동 생성되지 않음. 지표→액션 연결 파이프라인.",
        "priority":    "medium",
    },
    {
        "retro_id":    "RETRO-26",
        "org_id":      "aiorg_research_bot",
        "org_name":    "리서치실",
        "action_desc": '"레퍼런스가 의사결정을 강제"하는 연구→실행 연결 파이프라인 구현',
        "context":     "RETRO-20 출처 19개 레퍼런스 분석은 완성됐으나 의사결정 시 참조 강제 미연결. "
                       "리서치 산출물이 실제 의사결정 게이트로 작동하는 구조 설계.",
        "priority":    "medium",
    },
]


# ── GoalTracker 백필 등록 ───────────────────────────────────────────────────

async def _bootstrap_registrar():
    """GoalTracker + MeetingActionRegistrar 초기화 (일일회고 패턴 동일)."""
    try:
        from core.claim_manager import ClaimManager
        from core.context_db import ContextDB
        from core.goal_tracker import GoalTracker
        from core.memory_manager import MemoryManager
        from core.pm_orchestrator import PMOrchestrator
        from core.task_graph import TaskGraph
        from goal_tracker.registrar import MeetingActionRegistrar

        async def _noop_send(*_args, **_kwargs) -> None:
            return None

        db = ContextDB()
        await db.initialize()
        orchestrator = PMOrchestrator(
            context_db=db,
            task_graph=TaskGraph(db),
            claim_manager=ClaimManager(),
            memory=MemoryManager("aiorg_pm_bot"),
            org_id="aiorg_pm_bot",
            telegram_send_func=_noop_send,
        )
        tracker = GoalTracker(
            context_db=db,
            orchestrator=orchestrator,
            telegram_send_func=_noop_send,
            org_id="aiorg_pm_bot",
        )
        registrar = MeetingActionRegistrar(
            goal_tracker=tracker,
            org_id="aiorg_pm_bot",
        )
        print("[backfill] GoalTracker registrar 초기화 완료")
        return registrar
    except Exception as e:
        print(f"[backfill] registrar 초기화 실패 (GoalTracker 없이 진행): {e}")
        return None


async def _register_to_goal_tracker(registrar) -> list[str]:
    """RETRO-21~26 를 GoalTracker에 등록, goal_id 목록 반환."""
    if registrar is None:
        print("[backfill] registrar 없음 — GoalTracker 등록 생략")
        return [a["retro_id"] for a in RETRO_ACTIONS]

    from goal_tracker.action_parser import ActionItem
    from goal_tracker.meeting_handler import MeetingEvent, MeetingType

    action_items = [
        ActionItem(
            description=a["action_desc"],
            assigned_dept=a["org_id"],
            priority=a["priority"],
            source_text=f"[{a['retro_id']}] {a['context']}",
            confidence=1.0,
            tags=[a["retro_id"]],
        )
        for a in RETRO_ACTIONS
    ]

    event = MeetingEvent(
        meeting_type=MeetingType.DAILY_RETRO,
        chat_id=GROUP_CHAT_ID,
        message_text="RETRO-21~26 backfill — 2026-03-30 일일회고 소급 등록",
        sender_org="aiorg_pm_bot",
        action_items=action_items,
        metadata={"date": "2026-03-30", "source": "retro_backfill"},
    )

    try:
        registered_ids = await registrar.register_from_event(event)
        print(f"[backfill] GoalTracker 등록 완료: {registered_ids}")
        return registered_ids or [a["retro_id"] for a in RETRO_ACTIONS]
    except Exception as e:
        print(f"[backfill] GoalTracker 등록 실패: {e}")
        return [a["retro_id"] for a in RETRO_ACTIONS]


# ── Telegram COLLAB dispatch ────────────────────────────────────────────────

def _build_collab_message() -> str:
    """RETRO-21~26 를 각 조직에 위임하는 COLLAB 태그 메시지 생성."""
    today = date.today().isoformat()
    lines = [
        "📬 **[회고 파이프라인] RETRO-21~26 소급 dispatch**",
        f"2026-03-30 일일회고 ACTION 6건 → 담당 조직 배분 ({today} 실행)",
        "",
    ]

    for a in RETRO_ACTIONS:
        collab_tag = (
            f"[COLLAB:{a['action_desc']}"
            f"|맥락: {a['retro_id']} 2026-03-30 회고 ACTION. {a['context'][:80]}]"
        )
        lines.append(f"**{a['retro_id']}** → {a['org_name']}")
        lines.append(collab_tag)
        lines.append("")

    lines.append("---")
    lines.append(f"*retro_backfill.py 자동 생성: {datetime.now(timezone.utc).isoformat()}*")
    return "\n".join(lines)


async def _send_collab_dispatch(dry_run: bool = False) -> None:
    """COLLAB 태그 메시지를 그룹 채팅에 전송."""
    msg = _build_collab_message()

    if dry_run:
        print("\n[dry-run] COLLAB dispatch 메시지:\n")
        print(msg)
        print("\n[dry-run] 실제 전송 생략")
        return

    if not BOT_TOKEN:
        print("[backfill] PM_BOT_TOKEN 없음 — Telegram 전송 생략")
        print("메시지 내용:")
        print(msg)
        return

    try:
        from telegram import Bot

        from core.telegram_formatting import markdown_to_html
        async with Bot(token=BOT_TOKEN) as bot:
            await bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=markdown_to_html(msg),
                parse_mode="HTML",
            )
            print(f"[backfill] COLLAB dispatch 전송 완료 → chat_id={GROUP_CHAT_ID}")
    except ImportError:
        print("[backfill] telegram 패키지 없음 — 텍스트 출력만")
        print(msg)
    except Exception as e:
        print(f"[backfill] Telegram 전송 실패: {e}")
        print("메시지 내용:")
        print(msg)


# ── loop_runner dispatch ────────────────────────────────────────────────────

async def _run_loop_cycle(registered_ids: list[str], dry_run: bool = False) -> None:
    """GoalTracker 상태머신 사이클 실행 (IDLE→EVALUATE→REPLAN→DISPATCH→IDLE)."""
    try:
        from goal_tracker.loop_runner import run_meeting_cycle

        async def _dispatch_fn(task_ids: list[str]) -> None:
            if dry_run:
                print(f"[dry-run] dispatch: {task_ids}")
                return
            await _send_collab_dispatch(dry_run=False)

        result = await run_meeting_cycle(
            meeting_type="daily_retro",
            registered_ids=registered_ids,
            dispatch_func=_dispatch_fn,
        )
        print(
            f"[backfill] 자율 루프 완료: states={result.states_visited}, "
            f"dispatched={result.dispatched_count}개"
        )
    except ImportError as e:
        print(f"[backfill] loop_runner 없음 — 직접 dispatch: {e}")
        await _send_collab_dispatch(dry_run=dry_run)


# ── 메인 ────────────────────────────────────────────────────────────────────

async def main(dry_run: bool = False) -> None:
    print(f"[backfill] RETRO-21~26 소급 파이프라인 시작 (dry_run={dry_run})")
    print(f"[backfill] 대상: {[a['retro_id'] for a in RETRO_ACTIONS]}")

    # Step 1: GoalTracker 등록
    registrar = await _bootstrap_registrar()
    registered_ids = await _register_to_goal_tracker(registrar)

    # Step 2: 상태머신 사이클 + dispatch
    await _run_loop_cycle(registered_ids, dry_run=dry_run)

    print(f"\n[backfill] 완료 — {datetime.now(timezone.utc).isoformat()}")
    print("다음 조치: MEMORY.md RETRO-21~26 상태를 in_progress로 업데이트 필요")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RETRO-21~26 GoalTracker 백필 + dispatch")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Telegram 전송 없이 메시지 내용만 출력",
    )
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
