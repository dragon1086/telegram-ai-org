"""PM 오케스트레이터 — 사용자 요청을 부서별 태스크로 분해·배분."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Awaitable

from loguru import logger

from core.context_db import ContextDB
from core.task_graph import TaskGraph
from core.claim_manager import ClaimManager
from core.memory_manager import MemoryManager


# 알려진 부서 봇 목록
KNOWN_DEPTS: dict[str, str] = {
    "aiorg_product_bot": "기획실",
    "aiorg_engineering_bot": "개발실",
    "aiorg_design_bot": "디자인실",
    "aiorg_growth_bot": "성장실",
    "aiorg_ops_bot": "운영실",
}

ENABLE_PM_ORCHESTRATOR = os.environ.get("ENABLE_PM_ORCHESTRATOR", "0") == "1"


@dataclass
class SubTask:
    """분해된 서브태스크."""
    description: str
    assigned_dept: str  # org_id (e.g., "aiorg_engineering_bot")
    depends_on: list[str] = field(default_factory=list)  # 다른 subtask의 인덱스 (0-based)


@dataclass
class DiscussionNeeded:
    """분해 결과 중 토론이 필요한 항목."""
    topic: str
    proposal: str
    participants: list[str] = field(default_factory=list)


class PMOrchestrator:
    """사용자 요청을 부서별 태스크로 분해하고 배분하는 오케스트레이터."""

    def __init__(
        self,
        context_db: ContextDB,
        task_graph: TaskGraph,
        claim_manager: ClaimManager,
        memory: MemoryManager,
        org_id: str,
        telegram_send_func: Callable[[int, str], Awaitable[None]],
        discussion_manager: "DiscussionManager | None" = None,
    ):
        self._db = context_db
        self._graph = task_graph
        self._claim = claim_manager
        self._memory = memory
        self._org_id = org_id
        self._send = telegram_send_func
        self._discussion = discussion_manager
        self._task_counter = 0

    def _next_task_id(self) -> str:
        """프로세스 내 고유 태스크 ID 생성."""
        self._task_counter += 1
        return f"T-{self._org_id}-{self._task_counter:03d}"

    async def decompose(self, user_message: str) -> list[SubTask]:
        """사용자 메시지를 부서별 서브태스크로 분해.

        현재는 규칙 기반. 향후 LLM 기반으로 확장 가능.
        """
        subtasks: list[SubTask] = []
        msg_lower = user_message.lower()

        # 규칙 기반 분해 — 키워드로 관련 부서 판단
        needs_product = any(kw in msg_lower for kw in ["기획", "스펙", "요구사항", "prd", "plan"])
        needs_engineering = any(kw in msg_lower for kw in ["개발", "구현", "코딩", "코드", "api", "build", "fix", "버그"])
        needs_design = any(kw in msg_lower for kw in ["디자인", "ui", "ux", "화면", "레이아웃", "design"])
        needs_growth = any(kw in msg_lower for kw in ["성장", "마케팅", "분석", "지표", "growth", "marketing"])
        needs_ops = any(kw in msg_lower for kw in ["운영", "배포", "인프라", "모니터링", "deploy", "ops"])

        # 기획은 보통 선행
        if needs_product:
            subtasks.append(SubTask(
                description=f"기획/스펙 작성: {user_message[:200]}",
                assigned_dept="aiorg_product_bot",
            ))

        if needs_design:
            deps = ["0"] if needs_product else []
            subtasks.append(SubTask(
                description=f"디자인/UX: {user_message[:200]}",
                assigned_dept="aiorg_design_bot",
                depends_on=deps,
            ))

        if needs_engineering:
            deps = []
            if needs_product:
                deps.append("0")
            if needs_design:
                deps.append(str(len(subtasks) - 1) if needs_design else "")
            deps = [d for d in deps if d]
            subtasks.append(SubTask(
                description=f"개발/구현: {user_message[:200]}",
                assigned_dept="aiorg_engineering_bot",
                depends_on=deps,
            ))

        if needs_growth:
            subtasks.append(SubTask(
                description=f"성장/마케팅 전략: {user_message[:200]}",
                assigned_dept="aiorg_growth_bot",
            ))

        if needs_ops:
            # 운영은 개발 후
            eng_idx = None
            for i, st in enumerate(subtasks):
                if st.assigned_dept == "aiorg_engineering_bot":
                    eng_idx = str(i)
            deps = [eng_idx] if eng_idx else []
            subtasks.append(SubTask(
                description=f"운영/배포: {user_message[:200]}",
                assigned_dept="aiorg_ops_bot",
                depends_on=deps,
            ))

        # 키워드 매칭이 없으면 기본으로 기획실에 전체 위임
        if not subtasks:
            subtasks.append(SubTask(
                description=user_message[:500],
                assigned_dept="aiorg_product_bot",
            ))

        logger.info(f"[PM] 분해 결과: {len(subtasks)}개 서브태스크")
        return subtasks

    async def dispatch(self, parent_task_id: str, subtasks: list[SubTask],
                       chat_id: int) -> list[str]:
        """서브태스크를 ContextDB에 생성하고 TaskGraph 구성 후 첫 번째 웨이브 발송."""
        task_ids: list[str] = []

        # 1. 서브태스크 생성
        for st in subtasks:
            tid = self._next_task_id()
            await self._db.create_pm_task(
                task_id=tid,
                description=st.description,
                assigned_dept=st.assigned_dept,
                created_by=self._org_id,
                parent_id=parent_task_id,
            )
            task_ids.append(tid)

        # 2. 의존성 등록
        for i, st in enumerate(subtasks):
            deps = [task_ids[int(d)] for d in st.depends_on if d.isdigit() and int(d) < len(task_ids)]
            await self._graph.add_task(task_ids[i], depends_on=deps)

        # 3. 첫 번째 웨이브 (의존성 없는 태스크) 발송
        ready = await self._graph.get_ready_tasks(parent_task_id)
        for tid in ready:
            task = await self._db.get_pm_task(tid)
            if task:
                dept = task["assigned_dept"]
                dept_name = KNOWN_DEPTS.get(dept, dept)
                msg = f"[PM_TASK:{tid}|dept:{dept}] {dept_name}에 배정: {task['description'][:300]}"
                await self._send(chat_id, msg)
                await self._db.update_pm_task_status(tid, "assigned")
                logger.info(f"[PM] 태스크 발송: {tid} → {dept}")

        return task_ids

    async def on_task_complete(self, task_id: str, result: str, chat_id: int) -> None:
        """부서 태스크 완료 처리. 새로 unblock된 태스크 발송."""
        # mark_complete이 before/after diff를 계산하므로 먼저 호출 후 result 저장
        newly_ready = await self._graph.mark_complete(task_id)
        await self._db.update_pm_task_status(task_id, "done", result=result)

        # 새로 unblock된 태스크 발송
        for tid in newly_ready:
            task = await self._db.get_pm_task(tid)
            if task:
                dept = task["assigned_dept"]
                dept_name = KNOWN_DEPTS.get(dept, dept)
                msg = f"[PM_TASK:{tid}|dept:{dept}] {dept_name}에 배정: {task['description'][:300]}"
                await self._send(chat_id, msg)
                await self._db.update_pm_task_status(tid, "assigned")

        # 모든 서브태스크 완료 확인
        task_info = await self._db.get_pm_task(task_id)
        if task_info and task_info.get("parent_id"):
            parent_id = task_info["parent_id"]
            siblings = await self._db.get_subtasks(parent_id)
            if all(s["status"] == "done" for s in siblings):
                summary = await self.consolidate_results(parent_id)
                await self._send(chat_id, f"✅ 모든 부서 작업 완료!\n\n{summary}")
                await self._db.update_pm_task_status(parent_id, "done", result=summary)

    async def consolidate_results(self, parent_task_id: str) -> str:
        """서브태스크 결과를 하나의 요약으로 통합."""
        subtasks = await self._db.get_subtasks(parent_task_id)
        lines: list[str] = []
        for st in subtasks:
            dept_name = KNOWN_DEPTS.get(st.get("assigned_dept", ""), st.get("assigned_dept", "?"))
            result = st.get("result", "(결과 없음)")
            lines.append(f"**{dept_name}**: {result[:200]}")
        return "\n".join(lines)

    # ── Discussion Integration ────────────────────────────────────────────

    # 토론이 필요한 키워드 패턴 — 여러 부서가 동시에 관여하고 방향 결정이 필요할 때
    _DISCUSSION_KEYWORDS = ["어떤 방식", "어떻게 할까", "선택", "비교", "vs", "논의", "토론", "결정"]

    def detect_discussion_needs(self, user_message: str, subtasks: list[SubTask]) -> list[DiscussionNeeded]:
        """분해 결과에서 토론이 필요한 항목을 감지.

        조건: 2개 이상 부서가 관여하고, 메시지에 결정 키워드가 포함될 때.
        """
        if len(subtasks) < 2:
            return []

        msg_lower = user_message.lower()
        has_decision_keyword = any(kw in msg_lower for kw in self._DISCUSSION_KEYWORDS)
        if not has_decision_keyword:
            return []

        # 관여 부서 목록
        participants = list({st.assigned_dept for st in subtasks})
        if len(participants) < 2:
            return []

        return [DiscussionNeeded(
            topic=user_message[:100],
            proposal=user_message[:300],
            participants=participants,
        )]

    async def start_discussions(
        self, discussions: list[DiscussionNeeded],
        parent_task_id: str, chat_id: int,
    ) -> list[str]:
        """토론이 필요한 항목들에 대해 DiscussionManager로 토론 시작.

        Returns:
            생성된 discussion_id 목록.
        """
        if not self._discussion or not discussions:
            return []

        disc_ids: list[str] = []
        for dn in discussions:
            disc = await self._discussion.start_discussion(
                topic=dn.topic,
                initial_proposal=dn.proposal,
                from_dept=self._org_id,
                participants=dn.participants,
                parent_task_id=parent_task_id,
                chat_id=chat_id,
            )
            disc_ids.append(disc["id"])
            logger.info(f"[PM] 토론 시작: {disc['id']} — {dn.topic[:50]}")

        return disc_ids
