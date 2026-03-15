"""OrgScheduler — pm_bot 내장 APScheduler 기반 스케줄러.

외부 크론/OpenClaw 없이 pm_bot 프로세스 자체가 회의·회고를 자율 실행.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable, Coroutine, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

KST = "Asia/Seoul"


class OrgScheduler:
    """매일/매주 정기 회의·회고를 자율 실행하는 내장 스케줄러."""

    def __init__(self, send_text: Callable[[str], Coroutine[Any, Any, None]]) -> None:
        """
        Args:
            send_text: Telegram 메시지 전송 코루틴 (TelegramRelay.send_text 또는 동일 시그니처).
        """
        self._send_text = send_text
        self.scheduler = AsyncIOScheduler(timezone=KST)
        self._register_jobs()

    # ── 잡 등록 ──────────────────────────────────────────────────────────────

    def _register_jobs(self) -> None:
        self.scheduler.add_job(
            self.morning_standup,
            CronTrigger(hour=9, minute=0, timezone=KST),
            id="morning_standup",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.daily_retro,
            CronTrigger(hour=23, minute=30, timezone=KST),
            id="daily_retro",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.weekly_standup,
            CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=KST),
            id="weekly_standup",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.friday_retro,
            CronTrigger(day_of_week="fri", hour=18, minute=0, timezone=KST),
            id="friday_retro",
            replace_existing=True,
        )

    # ── 잡 구현 ──────────────────────────────────────────────────────────────

    async def morning_standup(self) -> None:
        """매일 09:00 KST — 아침 목표 회의."""
        logger.info("[OrgScheduler] morning_standup 시작")
        try:
            from scripts.morning_goals import main as _morning_main
            # morning_goals.main()은 내부에서 Telegram 전송까지 처리
            await _morning_main()
        except Exception as e:
            logger.error(f"[OrgScheduler] morning_standup 실패: {e}")
            await self._safe_send(f"⚠️ [스케줄러] 아침 목표 생성 중 오류 발생: {e}")

    async def daily_retro(self) -> None:
        """매일 23:30 KST — 저녁 회고."""
        logger.info("[OrgScheduler] daily_retro 시작")
        try:
            from scripts.daily_retro import main as _retro_main
            await _retro_main()
        except Exception as e:
            logger.error(f"[OrgScheduler] daily_retro 실패: {e}")
            await self._safe_send(f"⚠️ [스케줄러] 일일 회고 중 오류 발생: {e}")

    async def weekly_standup(self) -> None:
        """매주 월요일 09:00 KST — 주간 회의."""
        logger.info("[OrgScheduler] weekly_standup 시작")
        try:
            from scripts.weekly_standup import main as _weekly_main
            await _weekly_main()
        except Exception as e:
            logger.error(f"[OrgScheduler] weekly_standup 실패: {e}")
            await self._safe_send(f"⚠️ [스케줄러] 주간 회의 중 오류 발생: {e}")

    async def friday_retro(self) -> None:
        """매주 금요일 18:00 KST — 주간 회고."""
        logger.info("[OrgScheduler] friday_retro 시작")
        try:
            from scripts.daily_retro import (
                get_today_tasks,
                _llm_insights,
                build_retro,
                save_markdown,
                save_to_shared_memory,
            )
            from datetime import datetime, timedelta, timezone, UTC

            # 이번 주 월요일부터 오늘까지 태스크 집계
            tasks = get_today_tasks()  # 오늘 기준 — 주간 집계는 별도 구현
            llm_insight = await _llm_insights(tasks)
            tg_msg, md_content, retro_data = build_retro(tasks, llm_insight=llm_insight)

            # 주간 회고임을 명시
            now_kst = datetime.now(timezone(timedelta(hours=9)))
            header = f"📅 *주간 회고 — {now_kst.strftime('%Y년 %m월 %d일')}*\n\n"
            await self._safe_send(header + tg_msg)

            save_to_shared_memory({**retro_data, "type": "weekly_retro"})
            save_markdown(md_content)
        except Exception as e:
            logger.error(f"[OrgScheduler] friday_retro 실패: {e}")
            await self._safe_send(f"⚠️ [스케줄러] 주간 회고 중 오류 발생: {e}")

    # ── 헬퍼 ─────────────────────────────────────────────────────────────────

    async def _safe_send(self, text: str) -> None:
        try:
            await self._send_text(text)
        except Exception as e:
            logger.error(f"[OrgScheduler] Telegram 전송 실패: {e}")

    # ── 라이프사이클 ─────────────────────────────────────────────────────────

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
            jobs = self.scheduler.get_jobs()
            logger.info(f"[OrgScheduler] 시작됨 — {len(jobs)}개 잡 등록: {[j.id for j in jobs]}")

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("[OrgScheduler] 종료됨")

    def get_job_ids(self) -> list[str]:
        return [j.id for j in self.scheduler.get_jobs()]
