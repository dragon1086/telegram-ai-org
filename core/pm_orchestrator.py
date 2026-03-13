"""PM 오케스트레이터 — 사용자 요청을 부서별 태스크로 분해·배분."""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Callable, Awaitable

from loguru import logger

from core.context_db import ContextDB
from core.task_graph import TaskGraph
from core.claim_manager import ClaimManager
from core.memory_manager import MemoryManager
from core.llm_provider import get_provider


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

    _LLM_DECOMPOSE_PROMPT = (
        "You are the PM of an AI organization with these departments:\n"
        "- aiorg_product_bot (기획실): planning, specs, PRD, requirements\n"
        "- aiorg_engineering_bot (개발실): development, coding, API, bug fixes\n"
        "- aiorg_design_bot (디자인실): UI/UX design, layouts, visual design\n"
        "- aiorg_growth_bot (성장실): growth, marketing, analytics, metrics\n"
        "- aiorg_ops_bot (운영실): operations, deployment, infra, monitoring\n\n"
        "Break the user's request into specific subtasks for each relevant department.\n"
        "Each subtask should be a CONCRETE, ACTIONABLE instruction (not the user's raw message).\n\n"
        "Reply in this exact format (one line per subtask):\n"
        "DEPT:aiorg_xxx_bot|TASK:specific task description|DEPENDS:comma-separated indices or none\n\n"
        "Rules:\n"
        "- Only include departments that are actually needed\n"
        "- Write task descriptions in Korean, specific to each department's role\n"
        "- DEPENDS uses 0-based index of prior subtasks (e.g., '0' or '0,1')\n"
        "- Planning usually comes first, design before engineering, engineering before ops\n"
        "- If only one department is needed, output just one line\n\n"
        "User request: {message}"
    )

    async def decompose(self, user_message: str) -> list[SubTask]:
        """사용자 메시지를 부서별 서브태스크로 분해.

        LLM 기반 분해를 시도하고, 실패 시 키워드 기반 fallback.
        """
        subtasks = await self._llm_decompose(user_message)
        if subtasks:
            logger.info(f"[PM] LLM 분해 결과: {len(subtasks)}개 서브태스크")
            return subtasks

        subtasks = self._keyword_decompose(user_message)
        logger.info(f"[PM] 키워드 분해 결과: {len(subtasks)}개 서브태스크")
        return subtasks

    async def _llm_decompose(self, user_message: str) -> list[SubTask]:
        """LLM으로 태스크 분해. 실패 시 빈 리스트 반환."""
        provider = get_provider()
        if provider is None:
            return []

        prompt = self._LLM_DECOMPOSE_PROMPT.format(message=user_message[:500])
        try:
            response = await asyncio.wait_for(
                provider.complete(prompt, timeout=15.0),
                timeout=18.0,
            )
            return self._parse_decompose(response)
        except Exception as e:
            logger.warning(f"[PM] LLM 분해 실패, 키워드 fallback: {e}")
            return []

    @staticmethod
    def _parse_decompose(response: str) -> list[SubTask]:
        """LLM 분해 응답 파싱.

        형식: DEPT:aiorg_xxx_bot|TASK:description|DEPENDS:0,1
        """
        subtasks: list[SubTask] = []
        for line in response.strip().split("\n"):
            line = line.strip()
            if not line or "DEPT:" not in line or "TASK:" not in line:
                continue
            parts = {}
            for segment in line.split("|"):
                if ":" in segment:
                    key, val = segment.split(":", 1)
                    parts[key.strip().upper()] = val.strip()

            dept = parts.get("DEPT", "")
            task_desc = parts.get("TASK", "")
            depends_str = parts.get("DEPENDS", "none").lower()

            if not dept or dept not in KNOWN_DEPTS or not task_desc:
                continue

            deps: list[str] = []
            if depends_str and depends_str != "none":
                deps = [d.strip() for d in depends_str.split(",") if d.strip().isdigit()]

            subtasks.append(SubTask(
                description=task_desc,
                assigned_dept=dept,
                depends_on=deps,
            ))
        return subtasks

    # 부서별 역할 특화 지시 템플릿 (키워드 fallback용)
    _DEPT_INSTRUCTIONS: dict[str, str] = {
        "aiorg_product_bot": "다음 요청에 대해 기획/요구사항 관점에서 분석하고 PRD 또는 스펙 문서를 작성하세요",
        "aiorg_engineering_bot": "다음 요청에 대해 기술적 관점에서 분석하고 코드 구현 계획 또는 구현을 수행하세요",
        "aiorg_design_bot": "다음 요청에 대해 UI/UX 관점에서 분석하고 디자인 방안을 제시하세요",
        "aiorg_growth_bot": "다음 요청에 대해 성장/마케팅 관점에서 분석하고 전략을 수립하세요",
        "aiorg_ops_bot": "다음 요청에 대해 운영/인프라 관점에서 분석하고 배포 및 모니터링 계획을 수립하세요",
    }

    def _keyword_decompose(self, user_message: str) -> list[SubTask]:
        """키워드 기반 태스크 분해 (fallback).

        각 부서에 역할 특화 지시문 + 사용자 원문을 전달.
        """
        subtasks: list[SubTask] = []
        msg_lower = user_message.lower()
        short_msg = user_message[:200]

        needs_product = any(kw in msg_lower for kw in ["기획", "스펙", "요구사항", "prd", "plan"])
        needs_engineering = any(kw in msg_lower for kw in ["개발", "구현", "코딩", "코드", "api", "build", "fix", "버그"])
        needs_design = any(kw in msg_lower for kw in ["디자인", "ui", "ux", "화면", "레이아웃", "design"])
        needs_growth = any(kw in msg_lower for kw in ["성장", "마케팅", "분석", "지표", "growth", "marketing"])
        needs_ops = any(kw in msg_lower for kw in ["운영", "배포", "인프라", "모니터링", "deploy", "ops"])

        if needs_product:
            subtasks.append(SubTask(
                description=f"{self._DEPT_INSTRUCTIONS['aiorg_product_bot']}: {short_msg}",
                assigned_dept="aiorg_product_bot",
            ))
        if needs_design:
            deps = ["0"] if needs_product else []
            subtasks.append(SubTask(
                description=f"{self._DEPT_INSTRUCTIONS['aiorg_design_bot']}: {short_msg}",
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
                description=f"{self._DEPT_INSTRUCTIONS['aiorg_engineering_bot']}: {short_msg}",
                assigned_dept="aiorg_engineering_bot",
                depends_on=deps,
            ))
        if needs_growth:
            subtasks.append(SubTask(
                description=f"{self._DEPT_INSTRUCTIONS['aiorg_growth_bot']}: {short_msg}",
                assigned_dept="aiorg_growth_bot",
            ))
        if needs_ops:
            eng_idx = None
            for i, st in enumerate(subtasks):
                if st.assigned_dept == "aiorg_engineering_bot":
                    eng_idx = str(i)
            deps = [eng_idx] if eng_idx else []
            subtasks.append(SubTask(
                description=f"{self._DEPT_INSTRUCTIONS['aiorg_ops_bot']}: {short_msg}",
                assigned_dept="aiorg_ops_bot",
                depends_on=deps,
            ))

        if not subtasks:
            subtasks.append(SubTask(
                description=f"{self._DEPT_INSTRUCTIONS['aiorg_product_bot']}: {user_message[:500]}",
                assigned_dept="aiorg_product_bot",
            ))

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

    # 키워드 fallback용 (LLM 실패 시)
    _DISCUSSION_KEYWORDS = [
        "어떤 방식", "어떻게 할까", "선택", "비교", "vs", "논의", "토론", "결정",
        "정해", "골라", "택해", "뭐가 나을", "뭐가 좋을", "어떤 걸", "추천",
        "장단점", "트레이드오프", "tradeoff", "trade-off", "compare", "choose", "decide",
    ]

    _LLM_DISCUSSION_PROMPT = (
        "You are a project manager. Given a user request and a list of departments involved, "
        "determine if this request requires a DISCUSSION between departments before execution.\n\n"
        "A discussion is needed when:\n"
        "- Multiple departments need to AGREE on an approach before starting work\n"
        "- There are trade-offs or alternatives that departments should debate\n"
        "- A technology/design/strategy choice affects multiple departments\n"
        "- The request implies comparison, selection, or decision-making\n\n"
        "A discussion is NOT needed when:\n"
        "- Each department can work independently on their part\n"
        "- The request is straightforward with no ambiguity\n"
        "- Tasks are sequential but don't require agreement\n\n"
        "Reply with ONLY 'YES' or 'NO'. Nothing else.\n\n"
        "User request: {message}\n"
        "Departments involved: {departments}"
    )

    async def detect_discussion_needs(self, user_message: str, subtasks: list[SubTask]) -> list[DiscussionNeeded]:
        """분해 결과에서 토론이 필요한 항목을 LLM으로 감지.

        LLM 판단 실패 시 키워드 fallback.
        조건: 2개 이상 부서가 관여해야 함.
        """
        if len(subtasks) < 2:
            return []

        participants = list({st.assigned_dept for st in subtasks})
        if len(participants) < 2:
            return []

        needs_discussion = await self._llm_detect_discussion(user_message, participants)

        if not needs_discussion:
            return []

        return [DiscussionNeeded(
            topic=user_message[:100],
            proposal=user_message[:300],
            participants=participants,
        )]

    async def _llm_detect_discussion(self, user_message: str, participants: list[str]) -> bool:
        """LLM으로 토론 필요 여부 판단. 실패 시 키워드 fallback."""
        provider = get_provider()
        if provider is None:
            logger.debug("[PM] LLM provider 없음 — 키워드 fallback")
            return self._keyword_detect_discussion(user_message)

        dept_names = [KNOWN_DEPTS.get(p, p) for p in participants]
        prompt = self._LLM_DISCUSSION_PROMPT.format(
            message=user_message[:500],
            departments=", ".join(dept_names),
        )

        try:
            response = await asyncio.wait_for(
                provider.complete(prompt, timeout=10.0),
                timeout=12.0,
            )
            answer = response.strip().upper()
            result = answer.startswith("YES")
            logger.info(f"[PM] LLM 토론 감지: {answer} → {result}")
            return result
        except Exception as e:
            logger.warning(f"[PM] LLM 토론 감지 실패, 키워드 fallback: {e}")
            return self._keyword_detect_discussion(user_message)

    def _keyword_detect_discussion(self, user_message: str) -> bool:
        """키워드 기반 토론 필요 여부 판단 (fallback)."""
        msg_lower = user_message.lower()
        return any(kw in msg_lower for kw in self._DISCUSSION_KEYWORDS)

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
