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
        # 각 부서 간격: 5초 (봇들이 순서대로 발언할 수 있도록)
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
            "모든 부서 보고가 완료되면 PM이 종합 보고서를 작성합니다.\n"
            "개별 보고가 누락된 부서는 다음 주 스탠드업에서 별도 보고 요청드립니다."
        )
        await send_message(bot, convergence_msg)

    print(f"[weekly_meeting] 멀티봇 토론 트리거 완료 — {now.isoformat()}")
    meeting_content = _save_meeting_log(year, week_num, date_str)

    # GoalTracker 조치사항 자동 등록 및 자율 루프 실행
    await _register_weekly_meeting_actions(meeting_content)


def _save_meeting_log(year: int, week_num: int, date_str: str) -> str:
    """주간회의 로그 저장. 저장된 마크다운 내용을 반환."""
    out_dir = PROJECT_ROOT / "docs" / "weekly"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{year}-W{week_num:02d}-weekly-meeting.md"
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
        "## 상태",
        f"- 시작: {date_str}",
        "- 종합 보고서: 각 부서 응답 후 작성 예정",
        "",
        "---",
        f"*Generated by weekly_meeting_multibot.py — {date_str}*",
    ]
    content = "\n".join(content_lines)
    out_path.write_text(content, encoding="utf-8")
    print(f"[weekly_meeting] 로그 저장: {out_path}")
    return content


async def _register_weekly_meeting_actions(meeting_content: str) -> None:
    """주간회의 요약에서 조치사항을 파싱하여 GoalTracker에 자동 등록.

    회의 종료 후 수집된 부서 보고 텍스트를 report_parser로 파싱하고
    idle→evaluate→replan→dispatch 자율 루프를 실행한다.
    """
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))

    try:
        from goal_tracker.auto_register import auto_register_from_report
        from goal_tracker.loop_runner import run_meeting_cycle

        # 조치사항 파싱 및 등록 (goal_tracker 없으면 파싱 결과만 반환)
        register_result = await auto_register_from_report(
            report_text=meeting_content,
            report_type="weekly_meeting",
            org_id="aiorg_pm_bot",
        )

        print(
            f"[weekly_meeting] GoalTracker 파싱 완료 — "
            f"조치사항 {register_result.action_items_found}개 추출"
        )

        if register_result.action_items_found == 0:
            print("[weekly_meeting] 등록할 조치사항 없음 — 자율 루프 생략")
            return

        # 자율 루프 사이클 실행 (idle→evaluate→replan→dispatch)
        loop_result = await run_meeting_cycle(
            meeting_type="weekly_meeting",
            registered_ids=register_result.registered_ids or [
                f"G-weekly-{i:03d}"
                for i in range(register_result.action_items_found)
            ],
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
