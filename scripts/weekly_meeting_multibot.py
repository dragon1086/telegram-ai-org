#!/usr/bin/env python3
"""주간회의 멀티봇 토론 — ST-G2-03 구현.

PM 봇이 사회자 역할로 주간회의를 진행한다:
1. 회의 시작 선언 (PM 봇)
2. 각 부서 봇에게 COLLAB 요청 (봇끼리 채팅)
3. 각 부서 봇이 자율적으로 주간 현황 보고
4. PM이 종합 보고서 작성

실행: python scripts/weekly_meeting_multibot.py
크론: 매주 월요일 09:03 KST (UTC 일요일 00:03)
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime
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

# 부서 응답 수집 대기 시간 (초) — 환경변수로 조정 가능
COLLECT_TIMEOUT_SEC = int(os.environ.get("WEEKLY_COLLECT_TIMEOUT_SEC", "180"))
# Telethon 세션 파일 (e2e 테스트와 공유)
SESSION_FILE = PROJECT_ROOT / ".e2e_session"

# 참여 부서 목록 (순서 = 발언 순서)
DEPARTMENTS = [
    {"id": "aiorg_engineering_bot", "name": "🔧 개발실", "emoji": "🔧"},
    {"id": "aiorg_ops_bot",         "name": "⚙️ 운영실", "emoji": "⚙️"},
    {"id": "aiorg_design_bot",      "name": "🎨 디자인실", "emoji": "🎨"},
    {"id": "aiorg_product_bot",     "name": "📋 기획실", "emoji": "📋"},
    {"id": "aiorg_growth_bot",      "name": "📈 성장실", "emoji": "📈"},
    {"id": "aiorg_research_bot",    "name": "🔍 리서치실", "emoji": "🔍"},
]

WEEKLY_REPORT_TEMPLATE = """\
[주간회의 보고 요청]
발신: aiorg_pm_bot
요청: {dept_name} 주간 현황 보고 (200자 이내)
📎 맥락: 주간회의 진행 중. 아래 형식으로 보고해주세요.

**보고 형식**:
1. 이번 주 주요 완료 사항 (1~2개)
2. 진행 중인 작업
3. 블로커/이슈 (없으면 없음)
4. 다음 주 계획 (1개)
"""


async def send_message(bot, text: str, delay_sec: float = 0) -> None:
    """지연 후 메시지 전송."""
    if delay_sec > 0:
        await asyncio.sleep(delay_sec)
    try:
        from core.telegram_formatting import markdown_to_html
        html_text = markdown_to_html(text)
    except Exception:
        html_text = text
    try:
        await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=html_text,
            parse_mode="HTML",
        )
    except Exception as e:
        print(f"[weekly_meeting] 전송 실패: {e}")


async def run_weekly_meeting() -> None:
    """주간회의 멀티봇 토론 실행."""
    if not BOT_TOKEN:
        print("[weekly_meeting] PM_BOT_TOKEN 없음 — 실행 불가")
        return

    from telegram import Bot
    now = datetime.now(UTC)
    week_num = now.isocalendar()[1]
    year = now.year
    date_str = now.strftime("%Y-%m-%d")

    async with Bot(token=BOT_TOKEN) as bot:
        # ── Step 1: 회의 시작 선언 (PM 사회자)
        opening = (
            f"## 🏢 주간회의 — {year} W{week_num:02d} ({date_str})\n\n"
            f"안녕하세요 팀 여러분! PM 봇입니다.\n"
            f"이번 주 주간회의를 시작하겠습니다.\n\n"
            f"**의제**:\n"
            f"1. 지난 주 완료 사항 공유\n"
            f"2. 진행 중 작업 현황\n"
            f"3. 블로커/이슈 공유\n"
            f"4. 이번 주 목표 설정\n\n"
            f"각 부서 순서대로 보고 부탁드립니다. 🚀"
        )
        await send_message(bot, opening)
        print("[weekly_meeting] 회의 시작 선언 완료")

        # ── Step 2: 각 부서에 COLLAB 요청 (봇끼리 토론 유도)
        # 각 부서 간격: 3초 (봇들이 순서대로 발언할 수 있도록)
        try:
            from core.collab_request import make_collab_request_v2
        except ImportError:
            make_collab_request_v2 = None  # type: ignore[assignment]

        for i, dept in enumerate(DEPARTMENTS):
            if make_collab_request_v2 is not None:
                collab_msg = make_collab_request_v2(
                    task=f"{dept['name']} 주간 현황 보고 (200자 이내)",
                    from_org="aiorg_pm_bot",
                    context=(
                        f"{year} W{week_num:02d} 주간회의. "
                        f"완료사항·진행중·블로커·다음주계획 각 1~2줄."
                    ),
                    target_mentions=[dept["id"]],
                )
            else:
                collab_msg = (
                    f"🙋 도와줄 조직 찾아요!\n"
                    f"발신: aiorg_pm_bot\n"
                    f"요청: {dept['name']} 주간 현황 보고 (200자 이내)\n"
                    f"대상조직: {dept['id']}\n"
                    f"📎 맥락: {year} W{week_num:02d} 주간회의. "
                    f"완료사항·진행중·블로커·다음주계획 각 1~2줄."
                )
            await send_message(bot, collab_msg, delay_sec=3.0 * i)
            print(f"[weekly_meeting] {dept['name']} COLLAB 요청 전송")

        # ── Step 3: 토론 수렴 대기 신호
        await asyncio.sleep(3.0 * len(DEPARTMENTS) + 2)
        convergence_msg = (
            "⏱️ **각 부서 보고 수렴 중...**\n\n"
            f"모든 부서 보고를 {COLLECT_TIMEOUT_SEC}초간 수집합니다.\n"
            "개별 보고가 누락된 부서는 다음 주 스탠드업에서 별도 보고 요청드립니다."
        )
        await send_message(bot, convergence_msg)

    print(f"[weekly_meeting] 멀티봇 토론 트리거 완료 — {now.isoformat()}")

    # ── Step 4: 부서 응답 수집 (TelethonListenerHelper 기반, 120~300s 대기)
    # convergence 메시지 전송 후 min_id 기준으로 새 응답만 수집
    collected_responses = await _collect_dept_responses(COLLECT_TIMEOUT_SEC)
    if not collected_responses:
        print(
            f"[weekly_meeting] ⚠️  응답 수집 결과 0건 "
            f"(COLLECT_TIMEOUT_SEC={COLLECT_TIMEOUT_SEC}s) — "
            "Telethon 인증 없거나 부서 응답 없음"
        )
        # 응답 0건 시 Telegram 경고 알림 (비치명적)
        await _notify_zero_responses(year, week_num)

    meeting_content = _save_meeting_log(year, week_num, date_str, collected_responses)

    # ── Step 5: GoalTracker 조치사항 자동 등록 및 자율 루프 실행 (2026-03-30: bot 인스턴스 전달 추가)
    await _register_weekly_meeting_actions(meeting_content, bot_token=BOT_TOKEN)


def _save_meeting_log(
    year: int,
    week_num: int,
    date_str: str,
    collected_msgs: list | None = None,
) -> str:
    """주간회의 로그 저장. 저장된 마크다운 내용을 반환.

    Args:
        collected_msgs: TelethonListenerHelper로 수집한 CollectedMessage 리스트.
                        None 또는 빈 리스트면 "응답 없음" 섹션으로 기록.
    """
    out_dir = PROJECT_ROOT / "docs" / "weekly"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{year}-W{week_num:02d}-weekly-meeting.md"

    collected_msgs = collected_msgs or []

    # 부서 응답 섹션 구성
    if collected_msgs:
        response_lines = ["## 부서 응답 수집 결과", ""]
        for msg in collected_msgs:
            bot_label = msg.bot or "unknown"
            response_lines.append(f"### [{bot_label}]")
            response_lines.append(msg.text.strip())
            response_lines.append("")
    else:
        response_lines = [
            "## 부서 응답 수집 결과",
            "",
            "> ⚠️ 응답 수집 결과 없음 — Telethon 미설정이거나 부서 응답 시간 초과",
            "",
        ]

    content_lines = [
        f"# 주간회의 — {year} W{week_num:02d} ({date_str})",
        "",
        "## 참석 부서",
        *[f"- {d['name']}" for d in DEPARTMENTS],
        "",
        "## 진행 방식",
        "- PM 봇이 사회자로 회의 시작 선언",
        "- 각 부서에 COLLAB 요청으로 주간 현황 보고 수집",
        "- 부서별 보고 수렴 후 PM이 종합 보고서 작성",
        "",
        *response_lines,
        "## 상태",
        f"- 시작: {date_str}",
        f"- 수집 응답 수: {len(collected_msgs)}건",
        "- 종합 보고서: 수집 완료" if collected_msgs else "- 종합 보고서: 응답 부재로 미작성",
        "",
        "---",
        f"*Generated by weekly_meeting_multibot.py — {date_str}*",
    ]
    content = "\n".join(content_lines)
    out_path.write_text(content, encoding="utf-8")
    print(f"[weekly_meeting] 로그 저장: {out_path} ({len(collected_msgs)}건 응답 포함)")
    return content


async def _collect_dept_responses(collect_sec: int = COLLECT_TIMEOUT_SEC) -> list:
    """TelethonListenerHelper 기반 부서 응답 수집.

    COLLAB 발송 완료 후 호출하여 ``collect_sec`` 초 동안 봇 응답을 수집한다.
    내부적으로 Telethon 클라이언트를 생성·연결하고 min_id 기준으로
    새 메시지만 필터링하여 cross-contamination을 방지한다.

    Telethon 인증 세션이 없거나 환경변수가 없으면 빈 리스트를 반환한다.

    Returns:
        list[CollectedMessage]: 수집된 봇 메시지 목록.
    """
    api_id_str = os.environ.get("TELEGRAM_API_ID", "")
    api_hash = os.environ.get("TELEGRAM_API_HASH", "")

    if not api_id_str or not api_hash:
        print("[weekly_meeting] TELEGRAM_API_ID/HASH 미설정 — Telethon 수집 생략")
        return []

    if not SESSION_FILE.exists() and not Path(str(SESSION_FILE) + ".session").exists():
        print(f"[weekly_meeting] Telethon 세션 파일 없음 ({SESSION_FILE}) — 수집 생략")
        return []

    try:
        api_id = int(api_id_str)
    except ValueError:
        print(f"[weekly_meeting] TELEGRAM_API_ID 파싱 실패 ({api_id_str!r}) — 수집 생략")
        return []

    try:
        from telethon import TelegramClient, events  # type: ignore[import-untyped]  # noqa: PLC0415

        from scripts.telethon_listener import TelethonListenerHelper  # noqa: PLC0415
    except ImportError as e:
        print(f"[weekly_meeting] telethon 모듈 없음 — 수집 생략 ({e})")
        return []

    collected: list = []
    stop_flag: list[bool] = [False]
    client = None
    handler = None

    try:
        client = TelegramClient(str(SESSION_FILE), api_id, api_hash)
        await client.connect()

        if not await client.is_user_authorized():
            print("[weekly_meeting] Telethon 인증 만료/없음 — 수집 생략")
            await client.disconnect()
            return []

        helper = TelethonListenerHelper(client)
        chat_entity = GROUP_CHAT_ID

        # COLLAB 발송 이후 메시지만 수집하도록 현재 최신 ID 기록
        min_id = await helper.record_min_id(chat_entity)
        print(f"[weekly_meeting] Telethon min_id={min_id} 기록 완료 — 수집 시작")

        handler = helper.make_handler(
            chat_entity,
            collected,
            stop_flag,
            bot_only=True,
        )
        client.add_event_handler(handler, events.NewMessage(chats=chat_entity))

        print(f"[weekly_meeting] 부서 응답 수집 대기 — {collect_sec}초")
        await asyncio.sleep(collect_sec)

    except Exception as e:
        print(f"[weekly_meeting] Telethon 응답 수집 오류 (비치명적): {e}")
    finally:
        # 핸들러 정리 및 클라이언트 연결 해제
        stop_flag[0] = True
        try:
            if client is not None and handler is not None:
                from telethon import events as _ev  # type: ignore[import-untyped]
                client.remove_event_handler(handler, _ev.NewMessage(chats=GROUP_CHAT_ID))
        except Exception:
            pass
        try:
            if client is not None:
                await client.disconnect()
        except Exception:
            pass

    print(f"[weekly_meeting] 응답 수집 완료 — {len(collected)}건")
    return collected


async def _notify_zero_responses(year: int, week_num: int) -> None:
    """부서 응답 0건 시 Telegram 경고 알림 (비치명적)."""
    if not BOT_TOKEN:
        return
    try:
        from telegram import Bot
        msg = (
            f"⚠️ **주간회의 응답 수집 실패** — {year} W{week_num:02d}\n\n"
            f"부서 COLLAB 요청 후 {COLLECT_TIMEOUT_SEC}초 대기했으나 응답을 수집하지 못했습니다.\n"
            "가능한 원인:\n"
            "- Telethon 세션 파일 없음 또는 인증 만료\n"
            "- 부서 봇 응답 지연 (수집 시간 초과)\n"
            "- `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` 환경변수 미설정\n\n"
            "다음 주 회의 전 `WEEKLY_COLLECT_TIMEOUT_SEC` 값을 늘리거나 Telethon 재인증을 확인해주세요."
        )
        async with Bot(token=BOT_TOKEN) as bot:
            await send_message(bot, msg)
    except Exception as e:
        print(f"[weekly_meeting] 경고 알림 전송 실패 (비치명적): {e}")


async def _bootstrap_registrar():
    """GoalTracker + MeetingActionRegistrar 인스턴스를 생성하여 반환.

    goal_tracker_stage_runner._bootstrap_tracker() 패턴을 따라 독립 실행 가능한
    GoalTracker를 생성하고, 이를 MeetingActionRegistrar에 주입한다.

    Returns:
        MeetingActionRegistrar | None: 초기화 성공 시 registrar, 실패 시 None.
    """
    try:
        from core.claim_manager import ClaimManager
        from core.context_db import ContextDB
        from core.goal_tracker import GoalTracker
        from core.memory_manager import MemoryManager
        from core.pm_orchestrator import PMOrchestrator
        from core.task_graph import TaskGraph
        from goal_tracker.registrar import MeetingActionRegistrar

        async def _noop_send(*_args: object, **_kwargs: object) -> None:
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
        print("[weekly_meeting] GoalTracker registrar 초기화 완료")
        return registrar

    except Exception as e:
        print(f"[weekly_meeting] registrar 초기화 실패 (파싱만 수행): {e}")
        return None


async def _register_weekly_meeting_actions(
    meeting_content: str,
    bot_token: str = "",
) -> None:
    """주간회의 요약에서 조치사항을 파싱하여 GoalTracker에 자동 등록.

    회의 종료 후 수집된 부서 보고 텍스트를 report_parser로 파싱하고
    idle→evaluate→replan→dispatch 자율 루프를 실행한다.

    2026-03-30: dispatch_func 주입 추가 — noop 대신 실제 COLLAB 전송
    2026-03-30: MeetingActionRegistrar 연결 — 등록 경로 활성화
    2026-03-30: 수렴 실패 시 Telegram 경고 발송 추가
    """
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))

    # ── 빈 meeting_content 감지 ───────────────────────────────────────────
    is_empty_template = (
        "각 부서 응답 후 작성 예정" in meeting_content
        or len(meeting_content.strip()) < 200
    )
    if is_empty_template:
        warn_msg = (
            "⚠️ **주간회의 응답 수렴 실패 감지**\n\n"
            "부서 보고가 수집되지 않아 회의록이 빈 템플릿 상태입니다.\n"
            "- 원인: Telethon 리스너 미연결 또는 응답 수집 타임아웃\n"
            "- 영향: GoalTracker 조치사항 등록이 빈 내용 기반으로 실행됩니다\n"
            "- 조치: 각 부서 수동 보고 후 PM에게 종합 보고 요청 필요"
        )
        print("[weekly_meeting] ⚠️ 빈 meeting_content 감지 — Telegram 경고 발송")
        if bot_token:
            try:
                from telegram import Bot
                async with Bot(token=bot_token) as warn_bot:
                    from core.telegram_formatting import markdown_to_html
                    await warn_bot.send_message(
                        chat_id=GROUP_CHAT_ID,
                        text=markdown_to_html(warn_msg),
                        parse_mode="HTML",
                    )
            except Exception as e:
                print(f"[weekly_meeting] 경고 메시지 전송 실패: {e}")

    try:
        from goal_tracker.auto_register import auto_register_from_report
        from goal_tracker.loop_runner import run_meeting_cycle

        # 2026-03-30: _bootstrap_registrar()로 GoalTracker 연결된 registrar 획득
        # 실패 시 None 반환 → auto_register_from_report는 registrar=None으로도 동작 (파싱/로깅)
        registrar = await _bootstrap_registrar()

        # 조치사항 파싱 및 등록 (registrar 주입으로 GoalTracker 연결 경로 활성화)
        register_result = await auto_register_from_report(
            report_text=meeting_content,
            report_type="weekly_meeting",
            org_id="aiorg_pm_bot",
            registrar=registrar,  # 2026-03-30: _bootstrap_registrar() 결과 주입
        )

        print(
            f"[weekly_meeting] GoalTracker 파싱 완료 — "
            f"조치사항 {register_result.action_items_found}개 추출"
        )

        # 실제로 등록된 항목이 없으면 자율 루프 실행 불필요
        if register_result.registered_count == 0:
            print("[weekly_meeting] 등록된 조치사항 없음 — 자율 루프 생략")
            return

        # 2026-03-30: dispatch_func 주입 — noop 대신 실제 COLLAB 전송 함수
        async def _dispatch_to_telegram(task_ids: list[str]) -> None:
            """등록된 task_id를 Telegram COLLAB 요청으로 발송."""
            if not bot_token:
                print(f"[weekly_meeting] dispatch: bot_token 없음 — {len(task_ids)}개 noop")
                return
            try:
                from telegram import Bot
                async with Bot(token=bot_token) as dispatch_bot:
                    from core.telegram_formatting import markdown_to_html
                    dispatch_summary = "\n".join(f"  - {t}" for t in task_ids[:10])
                    msg = (
                        f"📬 **주간회의 조치사항 배분**\n\n"
                        f"GoalTracker 자율 루프 dispatch 완료:\n"
                        f"{dispatch_summary}"
                        + (f"\n  ... 외 {len(task_ids) - 10}개" if len(task_ids) > 10 else "")
                    )
                    await dispatch_bot.send_message(
                        chat_id=GROUP_CHAT_ID,
                        text=markdown_to_html(msg),
                        parse_mode="HTML",
                    )
                    print(f"[weekly_meeting] dispatch 완료 — {len(task_ids)}개 Telegram 전송")
            except Exception as e:
                print(f"[weekly_meeting] dispatch Telegram 전송 실패: {e}")

        # 자율 루프 사이클 실행 (idle→evaluate→replan→dispatch)
        # 2026-03-30: dispatch_func 주입 추가 (기존: None → noop)
        loop_result = await run_meeting_cycle(
            meeting_type="weekly_meeting",
            registered_ids=register_result.registered_ids or [
                f"G-weekly-{i:03d}"
                for i in range(register_result.action_items_found)
            ],
            dispatch_func=_dispatch_to_telegram,  # 2026-03-30: dispatch_func 추가
        )

        print(
            f"[weekly_meeting] 자율 루프 완료 — "
            f"states={loop_result.states_visited}, "
            f"dispatched={loop_result.dispatched_count}개"
        )

        if loop_result.error:
            print(f"[weekly_meeting] 자율 루프 경고: {loop_result.error}")

    except ImportError as e:
        print(f"[weekly_meeting] GoalTracker 모듈 없음 — 등록 생략 ({e})")
    except Exception as e:
        print(f"[weekly_meeting] GoalTracker 등록 실패 (비치명적): {e}")


async def main() -> None:
    print(f"[weekly_meeting] 시작 — {datetime.now(UTC).isoformat()}")
    await run_weekly_meeting()
    print(f"[weekly_meeting] 완료 — {datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
