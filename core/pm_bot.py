# DEPRECATED: TelegramRelay로 교체됨. main.py는 TelegramRelay를 사용합니다.
"""PM Bot — 오케스트레이터."""
from __future__ import annotations

import json
import os

from loguru import logger
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from core.completion import CompletionProtocol
from core.llm_router import LLMRouter
from core.task_planner import ExecutionPlan, TaskPlanner
from core.worker_health import WorkerHealthMonitor
from core.project_memory import ProjectMemory, TaskRecord
from core.context_db import ContextDB
from core.message_schema import OrgMessage
from core.task_manager import TaskManager, TaskStatus
from core.worker_registry import WorkerRegistry
from core.agent_catalog import AgentCatalog
from core.dynamic_team_builder import DynamicTeamBuilder
from core.pm_decision import PMDecisionClient
from tools.claude_code_runner import ClaudeCodeRunner


def _extract_root_task_id(sub_id: str) -> str:
    """'task_p0_t1' 형식에서 root task ID 추출. '_p'가 없으면 그대로 반환."""
    if "_p" in sub_id:
        return sub_id.rsplit("_p", 1)[0]
    return sub_id


class PMBot:
    """PM Bot: 유저 요청 → 태스크 분해 → WorkerRegistry에서 적합한 워커 선택 → 할당."""

    def __init__(self) -> None:
        self.token = os.environ["PM_BOT_TOKEN"]
        self.group_chat_id = int(os.environ["TELEGRAM_GROUP_CHAT_ID"])
        self.org_id = os.environ.get("PM_ORG_NAME", "global")
        self.task_manager = TaskManager()
        self.context_db = ContextDB()
        self.app: Application | None = None
        self.completion: CompletionProtocol | None = None

        # 동적 워커 레지스트리
        self.registry = WorkerRegistry()
        self.workers = self.registry.load()
        self._decision_client = PMDecisionClient(org_id=self.org_id)
        self.router = LLMRouter(decision_client=self._decision_client)
        self.planner = TaskPlanner(decision_client=self._decision_client)
        self.health = WorkerHealthMonitor()
        # 워커 상태 모니터에 등록
        for w in self.workers:
            self.health.register(w.name)
        self.memory = ProjectMemory()
        # 동적 팀 빌더 (새 아키텍처)
        self.agent_catalog = AgentCatalog()
        self.agent_catalog.load()
        self.team_builder = DynamicTeamBuilder(
            catalog=self.agent_catalog,
            decision_client=self._decision_client,
        )
        self.runner = ClaudeCodeRunner()
        # 태스크별 실행 계획 및 Phase 상태 추적
        self._plans: dict[str, ExecutionPlan] = {}
        self._phase_idx: dict[str, int] = {}
        self._phase_pending: dict[str, set[str]] = {}

    async def _execute_with_dynamic_team(self, task: str) -> str:
        """DynamicTeamBuilder로 팀 구성 → ClaudeCodeRunner로 실행."""
        team_config = await self.team_builder.build_team(task)
        announcement = self.team_builder.format_team_announcement(team_config)
        await self.send_text(announcement)

        from core.dynamic_team_builder import ExecutionMode
        agent_names = [p.name for p in team_config.agents]

        # 엔진 우선 분기: codex가 명시되면 Codex CLI로 라우팅
        if team_config.engine == "codex":
            logger.info(f"[pm_bot] 엔진=codex → run_codex()")
            return await self.runner.run_codex(task, org_id=self.org_id, agents=agent_names)

        if team_config.execution_mode == ExecutionMode.structured_team:
            return await self.runner.run_structured_team(task, agent_names)
        elif team_config.execution_mode == ExecutionMode.agent_teams:
            return await self.runner.run_agent_teams(task, agent_names)
        else:
            persona = agent_names[0] if agent_names else None
            return await self.runner.run_single(task, persona)

    async def _select_workers(self, task_description: str) -> list[str]:
        """LLM으로 태스크 분석 → 최적 워커 자율 선택."""
        available = self.registry.list_workers()
        if not available:
            logger.warning("등록된 워커 없음 — 태스크 할당 불가")
            return []

        try:
            handles = await self.router.route_simple(task_description, available)
            if handles:
                logger.info(f"LLM 워커 선택: {handles}")
                return handles
        except Exception as e:
            logger.warning(f"LLM 라우팅 실패, 키워드 폴백: {e}")

        # 폴백: 키워드 매칭
        task_lower = task_description.lower()
        for worker in available:
            desc_lower = worker["description"].lower()
            keywords = [kw.strip() for kw in desc_lower.replace(",", " ").split() if len(kw) > 2]
            if any(kw in task_lower for kw in keywords):
                return [worker["handle"]]
        return [available[0]["handle"]]

    async def send_org_message(self, msg: OrgMessage) -> None:
        """구조화된 OrgMessage를 그룹에 전송."""
        if self.app is None:
            raise RuntimeError("봇이 초기화되지 않음")
        await self.app.bot.send_message(
            chat_id=self.group_chat_id,
            text=msg.to_telegram_text(),
        )

    async def send_text(self, text: str) -> None:
        """일반 텍스트 메시지 전송."""
        if self.app is None:
            raise RuntimeError("봇이 초기화되지 않음")
        await self.app.bot.send_message(chat_id=self.group_chat_id, text=text)

    async def handle_user_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """유저 메시지 처리 → TaskPlanner로 Phase 분해 → Phase 1 발행."""
        if update.message is None or update.effective_user is None:
            return

        user_text = update.message.text or ""
        user_name = update.effective_user.username or "unknown"

        # 봇 메시지 무시
        if "[TO:" in user_text and "[FROM:" in user_text:
            return

        logger.info(f"유저 메시지 수신: @{user_name}: {user_text[:100]}")

        # 동적 팀 모드: /run 또는 /execute 명령으로 직접 Claude Code 실행
        if user_text.startswith(("/run ", "/execute ")):
            direct_task = user_text.split(" ", 1)[1].strip()
            await self.send_text(f"⚡ 동적 팀 모드로 실행: {direct_task[:100]}...")
            result = await self._execute_with_dynamic_team(direct_task)
            await self.send_text(f"✅ 완료:\n{result[:3000]}")
            return

        workers = self.registry.list_workers()
        if not workers:
            # 대화형 질문은 Claude Code 실행 없이 직접 응답
            conversational_kw = ['뭐야','뭔가요','인가요','알려줘','설명해줘','어때','어떤','뭐임','뭐지','맞나','맞아','왜','어떻게','했어','됐어']
            action_kw = ['만들어','작성해','구현해','분석해','개발해','생성해','수정해','고쳐','보고서','빌드']
            if len(user_text) < 60 and any(k in user_text for k in conversational_kw) and not any(k in user_text for k in action_kw):
                await self.send_text('💬 구체적인 작업을 말씀해주세요.\n예: "프리즘 인사이트 주간 보고서 작성해줘"')
                return

            # 워커 봇 없음 → 동적 에이전트 팀으로 자동 전환
            logger.info("워커 봇 없음 → 동적 팀 모드로 자동 전환")
            await self.send_text(f"🤖 AI 팀 구성 중...")
            result = await self._execute_with_dynamic_team(user_text)
            await self.send_text(f"✅ 완료:\n{result[:3000]}")
            return

        # RAG 컨텍스트로 플래너에 과거 태스크 이력 제공
        planning_ctx = self.memory.get_planning_context(user_text)

        # TaskPlanner로 실행 계획 수립
        plan = await self.planner.plan(user_text, workers, context=planning_ctx)
        if not plan.phases:
            await self.send_text("❌ 실행 계획을 수립하지 못했습니다.")
            return

        logger.info(f"실행 계획: {plan.summary} | Phase {len(plan.phases)}개")

        # 태스크 생성 (전체 계획 단위)
        all_worker_handles = list({t.worker_name for ph in plan.phases for t in ph.tasks})
        task = await self.task_manager.create_task(
            description=user_text,
            assigned_to=all_worker_handles,
        )

        # Context DB에 저장
        await self.context_db.create_project(task.id, f"Task {task.id}")
        await self.context_db.write_context(
            slot_id=f"{task.id}_request",
            project_id=task.id,
            slot_type="user_request",
            content=user_text,
        )

        # 계획 상태 저장
        self._plans[task.id] = plan
        self._phase_idx[task.id] = 0

        # Phase 1 발행
        await self._dispatch_phase(task.id, phase_index=0)
        await self.task_manager.update_status(task.id, TaskStatus.RUNNING)

    async def _dispatch_phase(self, task_id: str, phase_index: int) -> None:
        """지정된 Phase의 태스크를 워커에게 발행."""
        plan = self._plans.get(task_id)
        if plan is None or phase_index >= len(plan.phases):
            return

        phase = plan.phases[phase_index]
        pending: set[str] = set()

        for i, subtask in enumerate(phase.tasks):
            sub_id = f"{task_id}_p{phase_index}_t{i}"
            assign_msg = OrgMessage(
                to=[subtask.worker_name],
                from_="@pm_bot",
                task_id=sub_id,
                msg_type="assign",
                content=subtask.instruction,
                context_ref=f"{task_id}_request",
            )
            await self.send_org_message(assign_msg)
            pending.add(sub_id)
            logger.info(f"Phase {phase_index} 태스크 발행: {sub_id} → {subtask.worker_name}")

        self._phase_pending[task_id] = pending
        mode = "병렬" if phase.parallel else "순차"
        logger.info(f"Phase {phase_index} ({mode}) 발행 완료: {len(pending)}개 태스크")

    async def handle_bot_report(self, org_msg: OrgMessage) -> None:
        """Worker 봇의 보고 처리 + Phase 완료 시 다음 Phase 발행.

        실패 보고 시 리트라이/DLQ 로직 적용.
        """
        sub_id = org_msg.task_id
        root_task_id = _extract_root_task_id(sub_id)
        worker_name = org_msg.from_

        if org_msg.msg_type == "report":
            # 성공/실패 판별 (content에 '실패' 또는 'error' 포함 시 실패)
            is_success = not any(
                kw in (org_msg.content or "").lower()
                for kw in ("실패", "error", "failed", "❌")
            )

            # 워커 헬스 업데이트
            self.health.mark_done(worker_name.lstrip("@"), is_success)

            # 프로젝트 메모리에 태스크 기록
            task_obj = self.task_manager.get_task(root_task_id)
            if task_obj:
                self.memory.record_task(TaskRecord(
                    task_id=sub_id,
                    description=task_obj.description[:200],
                    assigned_to=[worker_name.lstrip("@")],
                    result=org_msg.content[:500] if org_msg.content else None,
                    success=is_success,
                    duration_sec=0.0,
                ))

            # 실패 시 리트라이 또는 DLQ
            if not is_success:
                self.health.record_attempt(sub_id)
                if self.health.should_retry(sub_id):
                    delay = self.health.get_retry_delay(sub_id)
                    logger.info(f"태스크 리트라이 예약: {sub_id} ({delay:.1f}s 후)")
                    asyncio.create_task(self._retry_subtask(sub_id, root_task_id, delay))
                    return  # 리트라이 대기 — Phase 완료 판정 보류
                else:
                    self.health.move_to_dlq(sub_id, worker_name, f"최대 시도 초과: {org_msg.content[:100]}")

            # Phase 추적 업데이트
            if root_task_id in self._phase_pending:
                self._phase_pending[root_task_id].discard(sub_id)
                if not self._phase_pending[root_task_id]:
                    next_idx = self._phase_idx.get(root_task_id, 0) + 1
                    plan = self._plans.get(root_task_id)
                    if plan and next_idx < len(plan.phases):
                        self._phase_idx[root_task_id] = next_idx
                        logger.info(f"Phase {next_idx - 1} 완료 → Phase {next_idx} 시작")
                        await self._dispatch_phase(root_task_id, next_idx)
                    else:
                        task = self.task_manager.get_task(root_task_id)
                        if task:
                            await self.task_manager.update_status(root_task_id, TaskStatus.DONE, result=org_msg.content)
                            if self.completion:
                                await self.completion.initiate_completion(task)
                        self._plans.pop(root_task_id, None)
                        self._phase_idx.pop(root_task_id, None)
                        self._phase_pending.pop(root_task_id, None)
            else:
                task = self.task_manager.get_task(sub_id)
                if task is None:
                    logger.warning(f"알 수 없는 태스크 ID: {sub_id}")
                    return
                await self.task_manager.update_status(sub_id, TaskStatus.DONE, result=org_msg.content)
                if self.completion:
                    await self.completion.initiate_completion(task)

        elif org_msg.msg_type == "ack":
            if self.completion:
                await self.completion.receive_ack(sub_id, org_msg.from_)

    async def _retry_subtask(self, sub_id: str, root_task_id: str, delay: float) -> None:
        """지연 후 실패한 서브태스크 재발행."""
        await asyncio.sleep(delay)
        plan = self._plans.get(root_task_id)
        if plan is None:
            return

        # sub_id에서 phase/task 인덱스 추출
        import re as _re
        m = _re.search(r"_p(\d+)_t(\d+)$", sub_id)
        if not m:
            return
        p_idx, t_idx = int(m.group(1)), int(m.group(2))
        if p_idx >= len(plan.phases) or t_idx >= len(plan.phases[p_idx].tasks):
            return

        subtask = plan.phases[p_idx].tasks[t_idx]
        assign_msg = OrgMessage(
            to=[subtask.worker_name],
            from_="@pm_bot",
            task_id=sub_id,
            msg_type="assign",
            content=subtask.instruction,
            context_ref=f"{root_task_id}_request",
        )
        await self.send_org_message(assign_msg)
        logger.info(f"리트라이 발행: {sub_id} → {subtask.worker_name}")

    async def handle_group_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """그룹 내 모든 메시지 감청."""
        if update.message is None:
            return
        text = update.message.text or ""

        org_msg = OrgMessage.parse_telegram_text(text)
        if org_msg and org_msg.from_ != "@pm_bot":
            await self.handle_bot_report(org_msg)
            return

        await self.handle_user_message(update, context)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            agents = self.catalog.list_agents() if hasattr(self, "catalog") else []
            agent_names = ", ".join(a.name for a in agents[:8])
            more = f" 외 {len(agents)-8}개" if len(agents) > 8 else ""
            await update.message.reply_text(
                f"🤖 **PM Bot 온라인**\n\n"
                f"무엇이든 말씀하세요. 요청에 맞는 AI 전문가 팀을 자동으로 구성합니다.\n\n"
                f"🧠 사용 가능한 전문가:\n"
                f"  {agent_names}{more}\n\n"
                f"💬 사용 예시:\n"
                f"  • 프리즘 인사이트 주간 보고서 작성해줘\n"
                f"  • FastAPI 서버 구현해줘\n"
                f"  • 코드 보안 리뷰해줘\n\n"
                f"/run <태스크> — 직접 실행\n"
                f"/status — 진행 상태 확인",
                parse_mode="Markdown"
            )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """워커 상태 + 프로젝트 메모리 요약 출력."""
        if update.message:
            health_report = self.health.get_status_report()
            recent = self.memory.get_recent_context(5)
            stats = self.memory.worker_stats
            stats_text = "\n".join(
                f"  {w}: 완료{v['done']} 실패{v['fail']} 평균{v['avg_sec']:.0f}s"
                for w, v in stats.items()
            ) or "  (기록 없음)"
            text = f"{health_report}\n\n📈 **누적 태스크**: {self.memory.total_tasks}개\n{stats_text}"
            if recent:
                text += f"\n\n{recent}"
            await update.message.reply_text(text, parse_mode="Markdown")

    async def _handle_run_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """동적 팀 모드로 Claude Code 직접 실행."""
        if update.message is None:
            return
        args = context.args
        if not args:
            await update.message.reply_text("사용법: /run <태스크 설명>")
            return
        task = " ".join(args)
        await update.message.reply_text(f"⚡ 동적 팀 빌딩 중...")
        result = await self._execute_with_dynamic_team(task)
        await update.message.reply_text(f"✅ 결과:\n{result[:3000]}")

    async def _post_init(self, application: "Application") -> None:
        """봇 시작 후 비동기 초기화."""
        await self.context_db.initialize()
        logger.info("ContextDB 초기화 완료")

    def build(self) -> Application:
        """애플리케이션 빌드."""
        self.app = Application.builder().token(self.token).post_init(self._post_init).build()
        self.completion = CompletionProtocol(self.task_manager, self.send_text)

        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("run", self._handle_run_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_group_message))

        return self.app

    async def run(self) -> None:
        """봇 실행."""
        await self.context_db.initialize()
        app = self.build()
        logger.info(f"PM Bot 시작... (워커 {len(self.workers)}개)")
        await app.run_polling()
