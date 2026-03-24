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
        group_chat_hub=None,
        goal_tracker=None,
        pm_orchestrator=None,
        pm_chat_id: int = 0,
    ) -> None:
        """
        Args:
            send_text: Telegram 메시지 전송 코루틴 (TelegramRelay.send_text 또는 동일 시그니처).
            execute_callback: 사용자 태스크 실행 코루틴 (태스크 설명 → 결과 문자열). 없으면 알림만.
            claim_manager: ClaimManager 인스턴스. 제공 시 매시간 파일 정리 잡 등록.
            context_db: ContextDB 인스턴스. 미제공 시 weekly_bot_business_retro에서 자동 생성.
            group_chat_hub: GroupChatHub 인스턴스. 제공 시 주간회의·회고를 그룹 허브로 실행.
            goal_tracker: GoalTracker 인스턴스. 회의 조치사항을 목표로 등록할 때 사용.
            pm_orchestrator: PMOrchestrator 인스턴스. broadcast_meeting_start 전달에 사용.
            pm_chat_id: PM 채팅방 ID. 회의 결과 요약 전송 대상.
        """
        self._send_text = send_text
        self._execute_callback = execute_callback
        self._claim_manager = claim_manager
        self._context_db = context_db
        self._group_chat_hub = group_chat_hub  # GroupChatHub | None
        self._goal_tracker = goal_tracker       # GoalTracker | None
        self._pm_orchestrator = pm_orchestrator # PMOrchestrator | None
        self._pm_chat_id = pm_chat_id
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
        # ── 자가개선 잡 ──────────────────────────────────────────────────────
        self.scheduler.add_job(
            self._code_health_daily,
            CronTrigger(hour=1, minute=0, timezone=KST),
            id="code_health_daily", misfire_grace_time=1800,
            replace_existing=True,
        )
        self.scheduler.add_job(
            self._self_improve_pipeline_daily,
            CronTrigger(hour=1, minute=17, timezone=KST),
            id="self_improve_pipeline_daily", misfire_grace_time=1800,
            replace_existing=True,
        )
        self.scheduler.add_job(
            self._improvement_bus_daily,
            CronTrigger(hour=2, minute=0, timezone=KST),
            id="improvement_bus_daily", misfire_grace_time=1800,
            replace_existing=True,
        )
        self.scheduler.add_job(
            self._skill_improve_weekly,
            CronTrigger(day_of_week="sun", hour=22, minute=0, timezone=KST),
            id="skill_improve_weekly", misfire_grace_time=3600,
            replace_existing=True,
        )
        self.scheduler.add_job(
            self._arch_advisor_monthly,
            CronTrigger(day=1, hour=9, minute=0, timezone=KST),
            id="arch_advisor_monthly", misfire_grace_time=7200,
            replace_existing=True,
        )
        self.scheduler.add_job(
            self._routing_optimizer_daily,
            CronTrigger(hour=3, minute=0, timezone=KST),
            id="routing_optimizer_daily", misfire_grace_time=1800,
            replace_existing=True,
        )

    # ── 잡 구현 ──────────────────────────────────────────────────────────────

    # ── 전 조직 브로드캐스트 회의 ─────────────────────────────────────────────

    async def broadcast_meeting_start(
        self,
        meeting_type: str,
        topic: str,
        collect_timeout_sec: float = 120.0,
    ) -> list[dict]:
        """전 조직에 회의 참여 메시지를 브로드캐스트하고 응답을 수집.

        동작:
        1. PMOrchestrator.dispatch()를 통해 각 KNOWN_DEPTS 조직에 "회의 참여" 태스크 배분.
        2. 각 조직 봇이 TaskPoller로 태스크 수신 → 상태 보고 실행 → ContextDB에 결과 저장.
        3. collect_timeout_sec 동안 결과를 수집하여 반환.
        4. 수집된 조치사항을 GoalTracker.start_goal()로 등록.

        GroupChatHub에 참가자가 있으면 TurnManager 방식으로도 병행 실행.

        Args:
            meeting_type: "daily_retro" | "weekly_standup" | "friday_retro".
            topic: 회의 주제 설명.
            collect_timeout_sec: 응답 수집 최대 대기 시간(초).

        Returns:
            [{org_id, dept_name, report, action_items}] 형태의 응답 목록.
        """
        from core.constants import KNOWN_DEPTS

        logger.info(f"[OrgScheduler] broadcast_meeting_start: type={meeting_type}")

        # ── Step 1: GroupChatHub 참가자가 있으면 TurnManager로 실행 ──────────
        if self._group_chat_hub is not None and self._group_chat_hub.participant_ids:
            logger.info(
                f"[OrgScheduler] GroupChatHub 참가자 {len(self._group_chat_hub.participant_ids)}명 "
                f"→ start_meeting 실행"
            )
            await self._group_chat_hub.start_meeting(topic=topic)

        # ── Step 2: PMOrchestrator로 각 조직에 회의 참여 태스크 배분 ──────────
        responses: list[dict] = []
        if self._pm_orchestrator is None:
            logger.warning("[OrgScheduler] pm_orchestrator 미연결 — 직접 태스크 배분 불가")
            await self._safe_send(
                f"📢 [{meeting_type}] 전 조직 참여 요청 (자동 배분 미연결)\n"
                f"주제: {topic}\n"
                f"각 조직은 상태 보고 및 조치사항을 채팅에 공유해주세요."
            )
            return responses

        # 회의 참여 태스크 생성
        meeting_prompt = (
            f"[{meeting_type.upper()}] {topic}\n\n"
            f"담당 조직의 현재 상태를 아래 형식으로 보고해주세요:\n\n"
            f"## 완료 항목\n- (이번 기간 완료된 주요 작업)\n\n"
            f"## 진행 중\n- (현재 진행 중인 작업)\n\n"
            f"## 조치사항 (Action Items)\n- (다음 기간 반드시 처리할 항목, 각 줄 ACTION: 으로 시작)\n\n"
            f"간결하게 작성하세요 (최대 500자)."
        )

        try:
            from core.pm_orchestrator import SubTask
            subtasks = [
                SubTask(
                    assigned_dept=org_id,
                    description=meeting_prompt,
                    expected_output=f"{dept_name} 상태 보고 및 조치사항",
                    rationale=f"{meeting_type} 회의 참여",
                    priority="medium",
                    depends_on=[],
                )
                for org_id, dept_name in KNOWN_DEPTS.items()
            ]

            # 부모 태스크 임시 생성
            import uuid as _uuid
            parent_task_id = f"MEETING-{meeting_type}-{_uuid.uuid4().hex[:8]}"
            await self._pm_orchestrator._db.create_pm_task(
                task_id=parent_task_id,
                description=f"[{meeting_type}] {topic}",
                assigned_dept="pm",
                chat_id=self._pm_chat_id,
            )

            task_ids = await self._pm_orchestrator.dispatch(
                parent_task_id=parent_task_id,
                subtasks=subtasks,
                chat_id=self._pm_chat_id,
            )
            logger.info(f"[OrgScheduler] 회의 태스크 배분 완료: {len(task_ids)}개")

            # ── Step 3: 결과 수집 (타임아웃 대기) ──────────────────────────
            responses = await self._collect_meeting_responses(
                parent_task_id=parent_task_id,
                task_ids=task_ids,
                timeout_sec=collect_timeout_sec,
            )

        except Exception as e:
            logger.error(f"[OrgScheduler] broadcast_meeting_start 배분 실패: {e}")
            await self._safe_send(f"⚠️ [회의 브로드캐스트] 오류: {e}")

        # ── Step 4: 조치사항 → GoalTracker 등록 ──────────────────────────────
        if self._goal_tracker is not None and responses:
            await self._register_action_items(responses, meeting_type)

        return responses

    async def _collect_meeting_responses(
        self,
        parent_task_id: str,
        task_ids: list[str],
        timeout_sec: float = 120.0,
    ) -> list[dict]:
        """배분된 태스크 결과를 ContextDB에서 수집."""
        if not task_ids or self._pm_orchestrator is None:
            return []

        db = self._pm_orchestrator._db
        terminal = {"done", "failed", "cancelled"}
        poll_interval = 5.0
        waited = 0.0
        results: list[dict] = []

        while waited < timeout_sec:
            await asyncio.sleep(poll_interval)
            waited += poll_interval

            all_done = True
            results = []
            for tid in task_ids:
                task = await db.get_pm_task(tid)
                if not task:
                    all_done = False
                    continue
                if task.get("status") not in terminal:
                    all_done = False
                else:
                    results.append({
                        "org_id": task.get("assigned_dept", ""),
                        "report": task.get("result", ""),
                        "status": task.get("status", ""),
                    })

            if all_done:
                break

        logger.info(f"[OrgScheduler] 회의 응답 수집: {len(results)}개 / {len(task_ids)}개 배분")
        return results

    async def _register_action_items(
        self,
        responses: list[dict],
        meeting_type: str,
    ) -> None:
        """회의 응답에서 조치사항(ACTION:으로 시작하는 줄)을 추출해 GoalTracker에 등록."""
        if self._goal_tracker is None:
            return

        from core.constants import KNOWN_DEPTS
        registered = 0

        for resp in responses:
            org_id = resp.get("org_id", "")
            report = resp.get("report", "")
            if not report:
                continue

            # "ACTION:" 패턴 추출
            action_lines = [
                line.strip().lstrip("- •").strip()
                for line in report.splitlines()
                if line.strip().upper().startswith("ACTION:")
            ]
            for action in action_lines:
                # "ACTION:" 접두어 제거
                description = action.split(":", 1)[-1].strip()
                if len(description) < 5:
                    continue
                try:
                    dept_name = KNOWN_DEPTS.get(org_id, org_id)
                    goal_id = await self._goal_tracker.start_goal(
                        title=f"[{meeting_type}] {dept_name} 조치사항",
                        description=description,
                        meta={
                            "source": meeting_type,
                            "org_id": org_id,
                            "auto_registered": True,
                        },
                        chat_id=self._pm_chat_id,
                    )
                    logger.info(f"[OrgScheduler] 조치사항 GoalTracker 등록: {goal_id} — {description[:60]}")
                    registered += 1
                except Exception as e:
                    logger.warning(f"[OrgScheduler] 조치사항 등록 실패 ({org_id}): {e}")

        if registered:
            await self._safe_send(
                f"📌 [{meeting_type}] 조치사항 {registered}개를 GoalTracker에 자동 등록했습니다."
            )

    async def _post_meeting_summary(
        self,
        responses: list[dict],
        meeting_type: str,
        topic: str,
    ) -> None:
        """회의 종료 후 수집된 응답 요약을 PM 채널에 전송."""
        if not responses:
            await self._safe_send(
                f"📋 [{meeting_type}] 회의 완료. 응답 수집 결과 없음 (타임아웃 또는 오류)."
            )
            return

        from core.constants import KNOWN_DEPTS
        lines = [f"## {meeting_type.upper()} 종합 보고"]
        for resp in responses:
            org_id = resp.get("org_id", "?")
            dept_name = KNOWN_DEPTS.get(org_id, org_id)
            report = resp.get("report", "(응답 없음)")
            lines.append(f"\n### {dept_name}")
            lines.append(report[:400])

        summary = "\n".join(lines)
        await self._safe_send(summary)

    def register_dept_bot_with_hub(
        self,
        org_id: str,
        speak_callback,
        domain_keywords: list[str] | None = None,
    ) -> None:
        """부서 봇을 GroupChatHub에 참가자로 등록.

        workers.yaml 기반 봇이 시작될 때 이 메서드를 호출하면
        회의/회고 시 자동으로 발언 기회를 얻는다.

        Args:
            org_id: 봇 조직 ID (예: "aiorg_engineering_bot").
            speak_callback: async (topic, context) -> str | None 형태의 콜백.
            domain_keywords: 이 봇의 전문 영역 키워드.
        """
        if self._group_chat_hub is None:
            logger.warning(f"[OrgScheduler] GroupChatHub 미연결 — {org_id} 등록 불가")
            return
        self._group_chat_hub.register_participant(
            bot_id=org_id,
            speak_callback=speak_callback,
            domain_keywords=domain_keywords,
        )
        logger.info(f"[OrgScheduler] {org_id} GroupChatHub 등록 완료")

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
            # Phase 3: 전 조직 브로드캐스트 — 상태 보고 + 조치사항 수집
            topic = "일일 회고 — 오늘의 완료 항목, 진행 중인 작업, 내일 조치사항 공유"
            responses = await self.broadcast_meeting_start(
                meeting_type="daily_retro",
                topic=topic,
                collect_timeout_sec=90.0,
            )
            if responses:
                await self._post_meeting_summary(responses, "daily_retro", topic)

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
            # Phase 3: 전 조직 브로드캐스트 — 주간 계획 + 조치사항 수집
            topic = "주간 스탠드업 — 이번 주 계획 및 지난 주 성과 공유"
            responses = await self.broadcast_meeting_start(
                meeting_type="weekly_standup",
                topic=topic,
                collect_timeout_sec=120.0,
            )
            if responses:
                await self._post_meeting_summary(responses, "weekly_standup", topic)
            # GroupChatHub 연동: 그룹방에서 멀티봇 자율 참가 회의 실행 (참가자 있을 때만)
            if self._group_chat_hub is not None and self._group_chat_hub.participant_ids:
                logger.info("[OrgScheduler] GroupChatHub를 통한 멀티봇 주간 스탠드업 실행")
                await self._group_chat_hub.start_meeting(
                    topic=topic,
                    participants=self._group_chat_hub.participant_ids,
                )
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
            # Phase 3: 전 조직 브로드캐스트 — 주간 회고 + 조치사항 수집
            topic = "주간 회고 — 이번 주 잘한 점, 개선점, 다음 주 액션 아이템"
            responses = await self.broadcast_meeting_start(
                meeting_type="friday_retro",
                topic=topic,
                collect_timeout_sec=120.0,
            )
            if responses:
                await self._post_meeting_summary(responses, "friday_retro", topic)
            # GroupChatHub 연동: 그룹방에서 멀티봇 자율 참가 회고 실행 (참가자 있을 때만)
            if self._group_chat_hub is not None and self._group_chat_hub.participant_ids:
                logger.info("[OrgScheduler] GroupChatHub를 통한 멀티봇 주간 회고 실행")
                await self._group_chat_hub.start_meeting(
                    topic=topic,
                    participants=self._group_chat_hub.participant_ids,
                )
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

    async def _code_health_daily(self) -> None:
        """매일 01:00 KST — 코드 건강도 스캔 → improvement_bus 신호 발송."""
        logger.info("[OrgScheduler] code_health_daily 시작")
        try:
            from core.code_health import CodeHealthMonitor
            monitor = CodeHealthMonitor()
            report = monitor.scan()
            if report.critical_count > 0:
                await self._safe_send(report.summary())
        except Exception as e:
            logger.error(f"[OrgScheduler] code_health_daily 실패: {e}")

    async def _self_improve_pipeline_daily(self) -> None:
        """매일 01:17 KST — 자가 개선 파이프라인 실행 + 모니터링 로그 저장 + 실패 알림."""
        logger.info("[OrgScheduler] self_improve_pipeline_daily 시작")
        try:
            import asyncio
            from pathlib import Path
            proc = await asyncio.create_subprocess_exec(
                str(Path(__file__).parent.parent / ".venv" / "bin" / "python"),
                "scripts/run_self_improve_pipeline.py",
                cwd=str(Path(__file__).parent.parent),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
            if proc.returncode == 0:
                logger.info("[OrgScheduler] self_improve_pipeline 완료 (exit=0)")
            else:
                output = (stdout + stderr).decode(errors="replace")[-800:]
                logger.warning(f"[OrgScheduler] self_improve_pipeline 실패 (exit={proc.returncode})\n{output}")
                await self._safe_send(
                    f"⚠️ 자가 개선 파이프라인 실패 (exit={proc.returncode})\n"
                    f"```\n{output}\n```"
                )
        except Exception as e:
            logger.error(f"[OrgScheduler] self_improve_pipeline_daily 실패: {e}")

    async def _improvement_bus_daily(self) -> None:
        """매일 02:00 KST — ImprovementBus 신호 수집 및 보고."""
        logger.info("[OrgScheduler] improvement_bus_daily 시작")
        try:
            from core.improvement_bus import ImprovementBus
            bus = ImprovementBus()
            signals = bus.collect_signals()
            report = bus.run(signals)
            # 신호가 있을 때만 Telegram 보고 (우선순위 7 이상)
            high_priority = [s for s in report.signals if s.priority >= 7]
            if high_priority:
                await self._safe_send(bus.format_report(report))
        except Exception as e:
            logger.error(f"[OrgScheduler] improvement_bus_daily 실패: {e}")

    async def _skill_improve_weekly(self) -> None:
        """매주 일요일 22:00 KST — 스킬 eval 점수 측정 → 자동 개선 → 보고."""
        logger.info("[OrgScheduler] skill_improve_weekly 시작")
        try:
            import asyncio as _asyncio
            from core.eval_runner import EvalRunner
            from core.skill_auto_improver import SkillAutoImprover
            runner = EvalRunner()
            results = runner.score_all_skills()
            if not results:
                logger.info("[OrgScheduler] eval.json 있는 스킬 없음, 스킵")
                return
            msg = runner.format_results(results)
            improver = SkillAutoImprover()
            improved_lines: list[str] = []
            loop = _asyncio.get_event_loop()
            for r in results:
                imp_result = await loop.run_in_executor(None, improver.improve, r.skill_name)
                if imp_result and imp_result.improved:
                    improved_lines.append(
                        f"  • {r.skill_name}: {imp_result.original_score:.1f} → {imp_result.best_score:.1f}"
                    )
            if improved_lines:
                msg += "\n\n*자동 개선 적용*\n" + "\n".join(improved_lines)
            await self._safe_send(msg)
        except Exception as e:
            logger.error(f"[OrgScheduler] skill_improve_weekly 실패: {e}")

    async def _arch_advisor_monthly(self) -> None:
        """매월 1일 09:00 KST — 아키텍처 건강 리포트 생성."""
        logger.info("[OrgScheduler] arch_advisor_monthly 시작")
        try:
            import asyncio
            import subprocess
            import sys
            from pathlib import Path
            script = Path(__file__).parent.parent / "scripts" / "arch_advisor.py"
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    [sys.executable, str(script)],
                    capture_output=True, text=True, timeout=60,
                ),
            )
            if result.stdout:
                await self._safe_send(result.stdout)
        except Exception as e:
            logger.error(f"[OrgScheduler] arch_advisor_monthly 실패: {e}")

    async def _routing_optimizer_daily(self) -> None:
        """매일 03:00 KST — RoutingOptimizer 제안 생성 및 Telegram 보고."""
        logger.info("[OrgScheduler] routing_optimizer_daily 시작")
        try:
            from core.routing_optimizer import RoutingOptimizer
            from core.routing_approval_store import RoutingApprovalStore
            opt = RoutingOptimizer()
            proposal = opt.generate_proposal()
            if proposal:
                store = RoutingApprovalStore()
                store.save({
                    "keyword_additions": proposal.keyword_additions,
                    "rationale": proposal.rationale,
                    "current_accuracy": proposal.current_accuracy,
                    "estimated_gain": proposal.estimated_gain,
                })
                msg = opt.format_for_telegram(proposal)
                msg += "\n\n*승인:* `/routing_approve`  *거절:* `/routing_reject`"
                await self._safe_send(msg)
        except Exception as e:
            logger.error(f"[OrgScheduler] routing_optimizer_daily 실패: {e}")

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
