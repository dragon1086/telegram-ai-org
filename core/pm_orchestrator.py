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
from core.constants import KNOWN_DEPTS, DEPT_INSTRUCTIONS, DEPT_ROLES
from core.result_synthesizer import ResultSynthesizer, SynthesisJudgment
from core.structured_prompt import StructuredPromptGenerator

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
        self._task_counter: int | None = None  # DB에서 지연 초기화
        self._synthesizer = ResultSynthesizer()
        self._prompt_gen = StructuredPromptGenerator()

    async def _next_task_id(self) -> str:
        """DB 최대값 기반 고유 태스크 ID 생성 (재시작 후 중복 방지)."""
        if self._task_counter is None:
            # DB에서 현재 org의 최대 counter 값 로드
            try:
                import aiosqlite, re
                async with aiosqlite.connect(self._db.db_path) as db:
                    prefix = f"T-{self._org_id}-"
                    cursor = await db.execute(
                        "SELECT id FROM pm_tasks WHERE id LIKE ? ORDER BY id DESC LIMIT 1",
                        (prefix + "%",),
                    )
                    row = await cursor.fetchone()
                if row:
                    m = re.search(r"-(\d+)$", row[0])
                    self._task_counter = int(m.group(1)) if m else 0
                else:
                    self._task_counter = 0
                logger.debug(f"[PM] task_counter 초기화: {self._task_counter}")
            except Exception:
                self._task_counter = 0
        self._task_counter += 1
        return f"T-{self._org_id}-{self._task_counter:03d}"

    @staticmethod
    def _build_decompose_prompt(message: str) -> str:
        """KNOWN_DEPTS + DEPT_ROLES에서 동적으로 LLM 분해 프롬프트 생성."""
        dept_lines = "\n".join(
            f"- {org_id} ({dept_name}): {DEPT_ROLES.get(org_id, dept_name)}"
            for org_id, dept_name in KNOWN_DEPTS.items()
        )
        return (
            f"You are the PM of an AI organization with these departments:\n"
            f"{dept_lines}\n\n"
            f"Break the user's request into specific subtasks for each relevant department.\n"
            f"Each subtask should be a CONCRETE, ACTIONABLE instruction (not the user's raw message).\n\n"
            f"Reply in this exact format (one line per subtask):\n"
            f"DEPT:<org_id>|TASK:specific task description|DEPENDS:comma-separated indices or none\n\n"
            f"Rules:\n"
            f"- Only include departments that are actually needed\n"
            f"- Write task descriptions in Korean, specific to each department's role\n"
            f"- DEPENDS uses 0-based index of prior subtasks (e.g., '0' or '0,1')\n"
            f"- Planning usually comes first, design before engineering, engineering before ops\n"
            f"- If only one department is needed, output just one line\n\n"
            f"User request: {message[:500]}"
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

        prompt = self._build_decompose_prompt(user_message)
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

    # 부서별 키워드 매핑 — 키워드 기반 fallback 분해용
    _DEPT_KEYWORDS: dict[str, list[str]] = {
        "aiorg_product_bot": ["기획", "스펙", "요구사항", "prd", "plan"],
        "aiorg_engineering_bot": ["개발", "구현", "코딩", "코드", "api", "build", "fix", "버그"],
        "aiorg_design_bot": ["디자인", "ui", "ux", "화면", "레이아웃", "design"],
        "aiorg_growth_bot": ["성장", "마케팅", "분석", "지표", "growth", "marketing"],
        "aiorg_ops_bot": ["운영", "배포", "인프라", "모니터링", "deploy", "ops"],
    }

    # 부서 간 의존 순서 (index가 낮을수록 먼저)
    _DEPT_ORDER = [
        "aiorg_product_bot",
        "aiorg_design_bot",
        "aiorg_engineering_bot",
        "aiorg_growth_bot",
        "aiorg_ops_bot",
    ]

    def _keyword_decompose(self, user_message: str) -> list[SubTask]:
        """키워드 기반 태스크 분해 (fallback).

        KNOWN_DEPTS + DEPT_INSTRUCTIONS에서 동적으로 부서를 매칭.
        """
        subtasks: list[SubTask] = []
        msg_lower = user_message.lower()
        short_msg = user_message[:200]

        # 키워드 매칭으로 필요한 부서 탐지
        matched_depts: list[str] = []
        for dept in self._DEPT_ORDER:
            if dept not in KNOWN_DEPTS:
                continue
            keywords = self._DEPT_KEYWORDS.get(dept, [])
            if any(kw in msg_lower for kw in keywords):
                matched_depts.append(dept)

        # 매칭된 부서별 서브태스크 생성 (순서에 따른 의존성)
        for dept in matched_depts:
            instruction = DEPT_INSTRUCTIONS.get(dept, f"{KNOWN_DEPTS[dept]} 업무를 수행하세요")
            deps: list[str] = []
            # 앞 순서 부서에 의존
            for i, prev in enumerate(subtasks):
                prev_order = self._DEPT_ORDER.index(prev.assigned_dept) if prev.assigned_dept in self._DEPT_ORDER else 99
                curr_order = self._DEPT_ORDER.index(dept) if dept in self._DEPT_ORDER else 99
                if prev_order < curr_order:
                    deps.append(str(i))
            subtasks.append(SubTask(
                description=f"{instruction}: {short_msg}",
                assigned_dept=dept,
                depends_on=deps,
            ))

        # 매칭 없으면 첫 번째 부서(기획)로 fallback
        if not subtasks:
            first_dept = next(iter(KNOWN_DEPTS))
            instruction = DEPT_INSTRUCTIONS.get(first_dept, "요청을 분석하세요")
            subtasks.append(SubTask(
                description=f"{instruction}: {user_message[:500]}",
                assigned_dept=first_dept,
            ))

        return subtasks

    async def dispatch(self, parent_task_id: str, subtasks: list[SubTask],
                       chat_id: int) -> list[str]:
        """서브태스크를 ContextDB에 생성하고 TaskGraph 구성 후 첫 번째 웨이브 발송."""
        task_ids: list[str] = []

        # 1. 서브태스크 생성 (구조화 프롬프트 적용)
        for st in subtasks:
            tid = await self._next_task_id()
            # 구조화 프롬프트 생성
            structured = await self._prompt_gen.generate(
                description=st.description,
                dept=st.assigned_dept,
            )
            full_description = structured.render()

            await self._db.create_pm_task(
                task_id=tid,
                description=full_description,
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
                # DB 먼저 업데이트 — send 실패해도 task_poller가 감지 가능
                await self._db.update_pm_task_status(tid, "assigned")
                try:
                    await self._send(chat_id, msg)
                except Exception as _e:
                    logger.warning(f"[PM] 태스크 {tid} 알림 전송 실패 (태스크는 assigned 상태): {_e}")
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
                await self._db.update_pm_task_status(tid, "assigned")
                try:
                    await self._send(chat_id, msg)
                except Exception as _e:
                    logger.warning(f"[PM] 태스크 {tid} 알림 전송 실패 (태스크는 assigned 상태): {_e}")

        # 모든 서브태스크 완료 확인
        task_info = await self._db.get_pm_task(task_id)
        if task_info and task_info.get("parent_id"):
            parent_id = task_info["parent_id"]
            siblings = await self._db.get_subtasks(parent_id)
            if all(s["status"] == "done" for s in siblings):
                await self._synthesize_and_act(parent_id, siblings, chat_id)

    async def _synthesize_and_act(
        self, parent_task_id: str, subtasks: list[dict], chat_id: int,
    ) -> None:
        """부서 결과를 합성하고 판단에 따라 후속 조치."""
        # 원래 요청 복원
        parent = await self._db.get_pm_task(parent_task_id)
        original_request = parent["description"][:500] if parent else ""

        synthesis = await self._synthesizer.synthesize(original_request, subtasks)
        logger.info(
            f"[PM] 결과 합성: {parent_task_id} → {synthesis.judgment.value}"
        )

        if synthesis.judgment == SynthesisJudgment.SUFFICIENT:
            report = synthesis.unified_report or synthesis.summary
            await self._send(chat_id, f"✅ 모든 부서 작업 완료!\n\n{report}")
            await self._db.update_pm_task_status(
                parent_task_id, "done", result=report,
            )
        elif synthesis.judgment == SynthesisJudgment.INSUFFICIENT:
            await self._send(
                chat_id,
                f"⚠️ 결과 부족 — 추가 작업 배분 중...\n"
                f"사유: {synthesis.reasoning}\n\n{synthesis.summary}",
            )
            if synthesis.follow_up_tasks:
                follow_ups = [
                    SubTask(
                        description=ft["description"],
                        assigned_dept=ft["dept"],
                    )
                    for ft in synthesis.follow_up_tasks
                ]
                await self.dispatch(parent_task_id, follow_ups, chat_id)
            else:
                # LLM이 follow-up을 안 줬으면 보고만
                await self._db.update_pm_task_status(
                    parent_task_id, "done", result=synthesis.summary,
                )
        elif synthesis.judgment == SynthesisJudgment.CONFLICTING:
            await self._send(
                chat_id,
                f"⚠️ 부서 간 결과 충돌 감지\n"
                f"사유: {synthesis.reasoning}\n\n{synthesis.summary}\n\n"
                f"조율이 필요합니다.",
            )
            await self._db.update_pm_task_status(
                parent_task_id, "needs_review", result=synthesis.summary,
            )
        else:  # NEEDS_INTEGRATION
            report = synthesis.unified_report or synthesis.summary
            await self._send(chat_id, f"📋 결과 통합 보고서:\n\n{report}")
            await self._db.update_pm_task_status(
                parent_task_id, "done", result=report,
            )

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
