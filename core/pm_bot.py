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
        self.task_manager = TaskManager()
        self.context_db = ContextDB()
        self.app: Application | None = None
        self.completion: CompletionProtocol | None = None

        # 동적 워커 레지스트리
        self.registry = WorkerRegistry()
        self.workers = self.registry.load()
        self.router = LLMRouter()
        self.planner = TaskPlanner()
        self.health = WorkerHealthMonitor()
        # 워커 상태 모니터에 등록
        for w in self.workers:
            self.health.register(w.name)
        self.memory = ProjectMemory()
        # 태스크별 실행 계획 및 Phase 상태 추적
        self._plans: dict[str, ExecutionPlan] = {}
        self._phase_idx: dict[str, int] = {}
        self._phase_pending: dict[str, set[str]] = {}

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

        workers = self.registry.list_workers()
        if not workers:
            await self.send_text("❌ 현재 사용 가능한 워커 봇이 없습니다. `workers.yaml`을 확인하세요.")
            return

        # TaskPlanner로 실행 계획 수립
        plan = await self.planner.plan(user_text, workers)
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
        """Worker 봇의 보고 처리 + Phase 완료 시 다음 Phase 발행."""
        sub_id = org_msg.task_id
        # sub_id 형식: {task_id}_p{phase}_t{i} 또는 일반 task_id
        root_task_id = _extract_root_task_id(sub_id)

        if org_msg.msg_type == "report":
            # Phase 추적 업데이트
            if root_task_id in self._phase_pending:
                self._phase_pending[root_task_id].discard(sub_id)
                if not self._phase_pending[root_task_id]:
                    # 현재 Phase 완료 → 다음 Phase 발행
                    next_idx = self._phase_idx.get(root_task_id, 0) + 1
                    plan = self._plans.get(root_task_id)
                    if plan and next_idx < len(plan.phases):
                        self._phase_idx[root_task_id] = next_idx
                        logger.info(f"Phase {next_idx - 1} 완료 → Phase {next_idx} 시작")
                        await self._dispatch_phase(root_task_id, next_idx)
                    else:
                        # 모든 Phase 완료
                        task = self.task_manager.get_task(root_task_id)
                        if task:
                            await self.task_manager.update_status(root_task_id, TaskStatus.DONE, result=org_msg.content)
                            if self.completion:
                                await self.completion.initiate_completion(task)
                        self._plans.pop(root_task_id, None)
                        self._phase_idx.pop(root_task_id, None)
                        self._phase_pending.pop(root_task_id, None)
            else:
                # 일반 태스크 (phase 추적 없음)
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
            workers = self.registry.list_workers()
            worker_lines = "\n".join(
                f"  • {w['handle']} ({w['engine']}) — {w['description']}"
                for w in workers
            ) or "  (워커 없음 — workers.yaml 확인)"
            await update.message.reply_text(
                f"🤖 PM Bot 온라인. AI 조직 준비 완료.\n\n"
                f"현재 워커 팀:\n{worker_lines}\n\n"
                f"요청사항을 입력하면 적합한 팀원에게 태스크를 할당합니다."
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

    def build(self) -> Application:
        """애플리케이션 빌드."""
        self.app = Application.builder().token(self.token).build()
        self.completion = CompletionProtocol(self.task_manager, self.send_text)

        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_group_message))

        return self.app

    async def run(self) -> None:
        """봇 실행."""
        await self.context_db.initialize()
        app = self.build()
        logger.info(f"PM Bot 시작... (워커 {len(self.workers)}개)")
        await app.run_polling()
