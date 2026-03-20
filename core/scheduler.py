"""OrgScheduler — pm_bot 내장 APScheduler 기반 스케줄러.

외부 크론/OpenClaw 없이 pm_bot 프로세스 자체가 회의·회고를 자율 실행.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Callable, Coroutine, Any, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from core.user_schedule_store import UserSchedule, UserScheduleStore

logger = logging.getLogger(__name__)

KST = "Asia/Seoul"


class OrgScheduler:
    """매일/매주 정기 회의·회고를 자율 실행하는 내장 스케줄러."""

    def __init__(
        self,
        send_text: Callable[[str], Coroutine[Any, Any, None]],
        execute_callback: Optional[Callable[[str], Coroutine[Any, Any, str]]] = None,
        claim_manager=None,
        context_db=None,
    ) -> None:
        """
        Args:
            send_text: Telegram 메시지 전송 코루틴 (TelegramRelay.send_text 또는 동일 시그니처).
            execute_callback: 사용자 태스크 실행 코루틴 (태스크 설명 → 결과 문자열). 없으면 알림만.
            claim_manager: ClaimManager 인스턴스. 제공 시 매시간 파일 정리 잡 등록.
            context_db: ContextDB 인스턴스. 미제공 시 weekly_bot_business_retro에서 자동 생성.
        """
        self._send_text = send_text
        self._execute_callback = execute_callback
        self._claim_manager = claim_manager
        self._context_db = context_db
        self.scheduler = AsyncIOScheduler(timezone=KST)
        self._register_jobs()

    # ── 잡 등록 ──────────────────────────────────────────────────────────────

    def _register_jobs(self) -> None:
        self.scheduler.add_job(
            self.morning_standup,
            CronTrigger(hour=9, minute=0, timezone=KST),
            id="morning_standup", misfire_grace_time=300,
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.daily_retro,
            CronTrigger(hour=23, minute=30, timezone=KST),
            id="daily_retro", misfire_grace_time=300,
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.weekly_standup,
            CronTrigger(day_of_week="mon", hour=9, minute=5, timezone=KST),
            id="weekly_standup", misfire_grace_time=300,
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.friday_retro,
            CronTrigger(day_of_week="fri", hour=18, minute=0, timezone=KST),
            id="friday_retro", misfire_grace_time=300,
            replace_existing=True,
        )
        if self._claim_manager is not None:
            self.scheduler.add_job(
                self._cleanup_claims,
                CronTrigger(hour="*", timezone=KST),
                id="claim_cleanup", misfire_grace_time=3600,
                replace_existing=True,
            )
        # 주 1회 오래된 대화 이력 정리
        self.scheduler.add_job(
            lambda: asyncio.create_task(self._cleanup_old_conversations()),
            "interval", weeks=1, id="conversation_cleanup",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self._weekly_bot_business_retro,
            CronTrigger(day_of_week="mon", hour=9, minute=10, timezone=KST),
            id="weekly_bot_business_retro",
            misfire_grace_time=300,
            replace_existing=True,
        )

    # ── 잡 구현 ──────────────────────────────────────────────────────────────

    async def morning_standup(self) -> None:
        """매일 09:00 KST — 아침 목표 회의."""
        logger.info("[OrgScheduler] morning_standup 시작")
        try:
            from scripts.morning_goals import main as _morning_main
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
            tasks = []  # Phase 3에서 참조 — 여기서 초기화
            # Phase 2: RetroMemory에 저장
            try:
                from core.retro_memory import RetroMemory, RetroEntry
                from scripts.daily_retro import get_today_tasks
                from datetime import date
                tasks = get_today_tasks()
                total = len(tasks)
                success = sum(1 for t in tasks if t.get("status") == "completed")
                rm = RetroMemory()
                rm.save_daily(RetroEntry(
                    date=date.today().isoformat(),
                    best_thing=f"오늘 {success}/{total}건 완료",
                    failure_summary=f"실패 {total - success}건",
                    experiment="내일 개선 방향 탐색",
                    task_count=total,
                    success_count=success,
                ))
            except Exception as e2:
                logger.warning(f"[OrgScheduler] RetroMemory 저장 실패 (무시): {e2}")
            # Phase 3: CollaborationTracker + AgentPersonaMemory 업데이트
            try:
                from core.collaboration_tracker import CollaborationTracker
                from core.agent_persona_memory import AgentPersonaMemory
                apm = AgentPersonaMemory()
                ct = CollaborationTracker(persona_memory=None)  # synergy는 update_from_task로만 일원화
                # 오늘 완료된 태스크의 협업 기록
                for task in tasks:
                    if task.get("status") == "completed":
                        task_id = task.get("id", "")
                        participants = task.get("participants", [])
                        task_type = task.get("type", "general")
                        if participants and len(participants) > 1:
                            _tid = task_id or str(uuid.uuid4())[:8]
                            await asyncio.get_event_loop().run_in_executor(
                                None, ct.record, _tid, participants, task_type, True
                            )
                        elif task.get("assigned_to"):
                            await asyncio.get_event_loop().run_in_executor(
                                None, apm.update_from_task, task["assigned_to"], task_type, True
                            )
            except Exception as e2:
                logger.warning(f"[OrgScheduler] Phase3 CollaborationTracker 저장 실패 (무시): {e2}")
        except Exception as e:
            logger.error(f"[OrgScheduler] daily_retro 실패: {e}")
            await self._safe_send(f"⚠️ [스케줄러] 일일 회고 중 오류 발생: {e}")

    async def weekly_standup(self) -> None:
        """매주 월요일 09:00 KST — 주간 회의."""
        logger.info("[OrgScheduler] weekly_standup 시작")
        try:
            from scripts.weekly_standup import main as _weekly_main
            await _weekly_main()
            # Phase 2: LessonMemory 교훈 통계
            try:
                from core.lesson_memory import LessonMemory
                lm = LessonMemory()
                loop = asyncio.get_event_loop()
                stats = await loop.run_in_executor(None, lm.get_category_stats)
                if stats:
                    top = sorted(stats.items(), key=lambda x: x[1], reverse=True)[:3]
                    summary = ", ".join(f"{c}:{n}" for c, n in top)
                    logger.info(f"[OrgScheduler] 이번 주 실패 패턴: {summary}")
            except Exception as e2:
                logger.warning(f"[OrgScheduler] LessonMemory 조회 실패: {e2}")
            # Phase 3: Top performers + Weekly MVP
            try:
                from core.agent_persona_memory import AgentPersonaMemory
                from core.shoutout_system import ShoutoutSystem
                apm = AgentPersonaMemory()
                ss = ShoutoutSystem()
                _loop = asyncio.get_event_loop()
                top = await _loop.run_in_executor(None, lambda: apm.get_top_performers(n=3))
                if top:
                    perf_lines = "\n".join(f"  • {a}: {r:.0%}" for a, r in top)
                    await self._safe_send(f"🏆 *이번 주 Top Performers*\n{perf_lines}")
                mvp = await _loop.run_in_executor(None, ss.weekly_mvp)
                if mvp:
                    await self._safe_send(f"🎉 *이번 주 MVP (칭찬왕)*: {mvp}")
            except Exception as e2:
                logger.warning(f"[OrgScheduler] Phase3 performers 조회 실패: {e2}")
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
            from datetime import datetime, timedelta, timezone

            # 이번 주 월요일부터 오늘까지 태스크 집계
            tasks = get_today_tasks()  # 오늘 기준 — 주간 집계는 별도 구현
            llm_insight = await _llm_insights(tasks)
            tg_msg, md_content, retro_data = build_retro(tasks, llm_insight=llm_insight)

            # 주간 회고임을 명시
            now_kst = datetime.now(timezone(timedelta(hours=9)))
            header = f"📅 *주간 회고 — {now_kst.strftime('%Y년 %m월 %d일')}*\n\n"
            tg_msg = header + tg_msg
            # Phase 2: RetroReport 추가
            try:
                from core.retro_memory import RetroMemory
                rm = RetroMemory()
                report = rm.generate_weekly_report()
                retro_summary = rm.format_telegram(report)
                tg_msg = tg_msg + "\n\n" + retro_summary
            except Exception as e2:
                logger.warning(f"[OrgScheduler] RetroReport 생성 실패: {e2}")
            # Phase 3: BotCharacterEvolution + 자동 MVP Shoutout
            try:
                from core.bot_character_evolution import BotCharacterEvolution
                from core.shoutout_system import ShoutoutSystem
                from core.agent_persona_memory import AgentPersonaMemory
                bce = BotCharacterEvolution()
                ss = ShoutoutSystem()
                apm = AgentPersonaMemory()
                # 모든 에이전트 캐릭터 진화
                evolutions = bce.evolve_all()
                if evolutions:
                    summaries = [bce.get_evolution_summary(e["agent_id"]) for e in evolutions[:3]]
                    evolution_text = "🌱 *캐릭터 성장 업데이트*\n" + "\n".join(f"  • {s}" for s in summaries)
                    tg_msg = tg_msg + "\n\n" + evolution_text
                # Weekly MVP 자동 칭찬
                mvp = ss.weekly_mvp()
                top_performers = apm.get_top_performers(n=1)
                if not mvp and top_performers:
                    mvp = top_performers[0][0]
                if mvp:
                    all_agents = [e["agent_id"] for e in evolutions] if evolutions else []
                    ss.auto_shoutout(
                        task_id="weekly_retro",
                        winner=mvp,
                        reason="이번 주 최고 성과를 거둔 팀원입니다!",
                        all_participants=all_agents,
                    )
            except Exception as e2:
                logger.warning(f"[OrgScheduler] Phase3 evolution 실패 (무시): {e2}")
            await self._safe_send(tg_msg)

            save_to_shared_memory({**retro_data, "type": "weekly_retro"})
            save_markdown(md_content)
        except Exception as e:
            logger.error(f"[OrgScheduler] friday_retro 실패: {e}")
            await self._safe_send(f"⚠️ [스케줄러] 주간 회고 중 오류 발생: {e}")

    # ── 사용자 정의 스케줄 ────────────────────────────────────────────────

    def load_user_schedules(self, store: "UserScheduleStore") -> None:
        """앱 시작 시 저장된 사용자 스케줄 복원."""
        for sched in store.get_enabled():
            try:
                self._add_user_job(sched)
                logger.info(f"[OrgScheduler] 사용자 스케줄 복원: ID={sched.id}, cron={sched.cron_expr}")
            except Exception as e:
                logger.error(f"[OrgScheduler] 사용자 스케줄 복원 실패 ID={sched.id}: {e}")

    def add_user_job(self, sched: "UserSchedule") -> None:
        """동적 job 추가 (중복 ID 안전 처리)."""
        self._add_user_job(sched)
        logger.info(f"[OrgScheduler] 사용자 job 추가: ID={sched.id}, cron={sched.cron_expr}")

    def _add_user_job(self, sched: "UserSchedule") -> None:
        job_id = f"user_schedule_{sched.id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        self.scheduler.add_job(
            self._run_user_task,
            CronTrigger.from_crontab(sched.cron_expr, timezone=KST),
            args=[sched],
            id=job_id,
            misfire_grace_time=300,
            replace_existing=True,
        )

    def remove_user_job(self, schedule_id: int) -> None:
        """동적 job 제거."""
        job_id = f"user_schedule_{schedule_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"[OrgScheduler] 사용자 job 제거: ID={schedule_id}")

    async def _run_user_task(self, sched: "UserSchedule") -> None:
        """사용자 정의 태스크 실행."""
        logger.info(f"[OrgScheduler] 사용자 스케줄 실행: {sched.task_description}")
        try:
            await self._safe_send(f"⏰ 예약 태스크 시작: {sched.task_description}")
            if self._execute_callback:
                result = await self._execute_callback(sched.task_description)
                await self._safe_send(f"✅ 예약 완료:\n{result[:2000]}")
            else:
                await self._safe_send(f"📋 예약된 태스크: {sched.task_description}\n(실행 엔진 미연결)")
        except Exception as e:
            logger.error(f"[OrgScheduler] 사용자 스케줄 실패 ID={sched.id}: {e}")
            await self._safe_send(f"❌ 예약 태스크 실패: {sched.task_description}\n{e}")

    # ── 헬퍼 ─────────────────────────────────────────────────────────────────

    async def _retryable_job(self, job_fn, max_retries: int = 3, backoff_base: int = 60) -> None:
        """지수 백오프 재시도로 잡 함수 실행. max_retries 초과 시 에러 로깅 후 종료."""
        for attempt in range(max_retries):
            try:
                await job_fn()
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(
                        f"[OrgScheduler] {getattr(job_fn, '__name__', str(job_fn))} "
                        f"{max_retries}회 시도 후 최종 실패: {e}"
                    )
                    return
                wait = backoff_base * (2 ** attempt)
                logger.warning(
                    f"[OrgScheduler] {getattr(job_fn, '__name__', str(job_fn))} "
                    f"실패 (시도 {attempt + 1}/{max_retries}), {wait}s 후 재시도: {e}"
                )
                await asyncio.sleep(wait)

    async def _cleanup_claims(self) -> None:
        """ClaimManager 파일 정기 정리 (매시간)."""
        try:
            if self._claim_manager is not None:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._claim_manager.cleanup_old_claims)
                logger.info("[OrgScheduler] claim 파일 정리 완료")
        except Exception as e:
            logger.warning(f"[OrgScheduler] claim 파일 정리 실패 (무시): {e}")

    async def _cleanup_old_conversations(self) -> None:
        """오래된 대화 이력 정리 (주 1회) — context_db 연결 시 실제 삭제 구현."""
        logger.warning("[OrgScheduler] _cleanup_old_conversations: context_db 미연결 상태. 무시.")

    async def _check_inactivity(self) -> None:
        """비활성 감지 — message_bus 연결 시 INACTIVITY_DETECTED 이벤트 발행."""
        logger.warning("[OrgScheduler] _check_inactivity: message_bus 미연결 상태로 호출됨. 무시.")

    async def _fire_daily_insight(self) -> None:
        """일일 인사이트 — message_bus 연결 시 DAILY_INSIGHT 이벤트 발행."""
        logger.warning("[OrgScheduler] _fire_daily_insight: message_bus 미연결 상태로 호출됨. 무시.")

    async def _weekly_bot_business_retro(self) -> None:
        """매주 월요일 09:10 KST — 봇 비즈니스 회고."""
        logger.info("[OrgScheduler] weekly_bot_business_retro 시작")
        try:
            from core.bot_business_retro import BotBusinessRetro
            db = self._context_db
            if db is None:
                from core.context_db import ContextDB
                db = ContextDB()
                await db.initialize()
            retro = BotBusinessRetro(db)
            results = await retro.generate_weekly()
            if results:
                msg = retro.format_telegram(results)
                await self._safe_send(msg)
            else:
                logger.info("[OrgScheduler] 봇 성과 데이터 없음, 회고 스킵")
        except Exception as e:
            logger.error(f"[OrgScheduler] weekly_bot_business_retro 실패: {e}")

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
