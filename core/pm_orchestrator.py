"""PM 오케스트레이터 — 사용자 요청을 부서별 태스크로 분해·배분."""
from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Literal, Any
from pathlib import Path

from loguru import logger

from core.context_db import ContextDB
from core.task_graph import TaskGraph
from core.claim_manager import ClaimManager
from core.memory_manager import MemoryManager
from core.constants import KNOWN_DEPTS, DEPT_INSTRUCTIONS, DEPT_ROLES
from core.orchestration_config import load_orchestration_config
from core.orchestration_runbook import OrchestrationRunbook
from core.result_synthesizer import ResultSynthesizer, SynthesisJudgment
from core.structured_prompt import StructuredPromptGenerator
from core.pm_decision import DecisionClientProtocol
from core.pm_identity import PMIdentity
from core.telegram_user_guardrail import ensure_user_friendly_output, extract_local_artifact_paths

ENABLE_PM_ORCHESTRATOR = os.environ.get("ENABLE_PM_ORCHESTRATOR", "0") == "1"


@dataclass
class SubTask:
    """분해된 서브태스크."""
    description: str
    assigned_dept: str  # org_id (e.g., "aiorg_engineering_bot")
    depends_on: list[str] = field(default_factory=list)  # 다른 subtask의 인덱스 (0-based)
    workdir: str | None = None


@dataclass
class DiscussionNeeded:
    """분해 결과 중 토론이 필요한 항목."""
    topic: str
    proposal: str
    participants: list[str] = field(default_factory=list)


@dataclass
class RequestPlan:
    """유저 요청 처리 전략."""

    lane: Literal[
        "clarify",
        "direct_answer",
        "review_or_audit",
        "attachment_analysis",
        "single_org_execution",
        "multi_org_execution",
    ]
    route: Literal["direct_reply", "local_execution", "delegate"]
    complexity: Literal["low", "medium", "high"]
    rationale: str
    dept_hints: list[str] = field(default_factory=list)
    confidence: float = 0.0


class PMOrchestrator:
    """사용자 요청을 부서별 태스크로 분해하고 배분하는 오케스트레이터."""

    def __init__(
        self,
        context_db: ContextDB,
        task_graph: TaskGraph,
        claim_manager: ClaimManager,
        memory: MemoryManager,
        org_id: str,
        telegram_send_func: Callable[..., Awaitable[Any]],
        discussion_manager: "DiscussionManager | None" = None,
        decision_client: DecisionClientProtocol | None = None,
    ):
        self._db = context_db
        self._graph = task_graph
        self._claim = claim_manager
        self._memory = memory
        self._org_id = org_id
        self._send = telegram_send_func
        self._discussion = discussion_manager
        self._decision_client = decision_client
        self._task_counter: int | None = None  # DB에서 지연 초기화
        self._synthesizer = ResultSynthesizer(decision_client=decision_client)
        self._prompt_gen = StructuredPromptGenerator(decision_client=decision_client)

    @property
    def decision_client(self) -> DecisionClientProtocol | None:
        return self._decision_client

    async def plan_request(self, user_message: str) -> RequestPlan:
        """유저 요청을 직접 답변/PM 직접 실행/조직 위임 중 어디로 보낼지 결정한다."""
        dept_hints = self._detect_relevant_depts(user_message)
        workdir = self._extract_workdir(user_message)
        lane = await self._classify_lane(user_message, dept_hints, workdir=workdir)
        llm_plan = await self._llm_plan_request(user_message, dept_hints, workdir=workdir)
        if llm_plan is not None:
            llm_plan.lane = lane
            return self._normalize_request_plan(llm_plan)
        return self._normalize_request_plan(self._heuristic_plan_request(user_message, dept_hints, lane=lane))

    _BASE_DEPT_KEYWORDS: dict[str, list[str]] = {
        "aiorg_product_bot": ["기획", "스펙", "요구사항", "prd", "plan"],
        "aiorg_research_bot": ["리서치", "research", "시장조사", "레퍼런스", "reference", "경쟁사", "벤치마크", "문서요약", "자료조사"],
        "aiorg_engineering_bot": ["개발", "구현", "코딩", "코드", "api", "build", "fix", "버그"],
        "aiorg_design_bot": ["디자인", "ui", "ux", "화면", "레이아웃", "design"],
        "aiorg_growth_bot": ["성장", "마케팅", "분석", "지표", "growth", "marketing"],
        "aiorg_ops_bot": ["운영", "배포", "인프라", "모니터링", "deploy", "ops"],
    }

    _BASE_DEPT_ORDER = [
        "aiorg_product_bot",
        "aiorg_research_bot",
        "aiorg_design_bot",
        "aiorg_engineering_bot",
        "aiorg_growth_bot",
        "aiorg_ops_bot",
    ]

    def _dept_profiles(self) -> dict[str, dict[str, Any]]:
        try:
            cfg = load_orchestration_config(force_reload=True)
            profiles: dict[str, dict[str, Any]] = {}
            for org in cfg.list_specialist_orgs():
                identity = PMIdentity(org.id)
                data = identity.load()
                instruction = org.instruction or ""
                if not instruction or instruction == "요청을 분석하고 처리하세요.":
                    role_hint = data.get("role") or org.role or org.dept_name
                    instruction = f"{role_hint} 관점에서 조사·분석·정리하세요."
                profiles[org.id] = {
                    "dept_name": org.dept_name,
                    "role": data.get("role") or org.role or org.dept_name,
                    "specialties": list(data.get("specialties") or org.specialties or []),
                    "direction": data.get("direction") or org.direction or "",
                    "instruction": instruction,
                }
            return profiles
        except Exception as e:
            logger.warning(f"[PM] live dept profile 로드 실패, 상수 fallback 사용: {e}")

        return {
            org_id: {
                "dept_name": dept_name,
                "role": DEPT_ROLES.get(org_id, dept_name),
                "specialties": [],
                "direction": "",
                "instruction": DEPT_INSTRUCTIONS.get(org_id, f"{dept_name} 업무를 수행하세요"),
            }
            for org_id, dept_name in KNOWN_DEPTS.items()
        }

    def _dept_map(self) -> dict[str, str]:
        return {
            org_id: profile["dept_name"]
            for org_id, profile in self._dept_profiles().items()
        }

    def _dept_order(self) -> list[str]:
        dept_map = self._dept_map()
        ordered = [dept for dept in self._BASE_DEPT_ORDER if dept in dept_map]
        remaining = sorted(dept for dept in dept_map if dept not in ordered)
        return ordered + remaining

    def _dept_keywords(self, dept_id: str, profile: dict[str, Any]) -> list[str]:
        keywords: list[str] = list(self._BASE_DEPT_KEYWORDS.get(dept_id, []))
        for raw in [profile.get("dept_name", ""), profile.get("role", ""), *profile.get("specialties", [])]:
            text = str(raw).strip().lower()
            if text:
                keywords.append(text)
                keywords.extend(tok for tok in re.split(r"[\s,()/|]+", text) if len(tok) >= 2)
        deduped: list[str] = []
        for keyword in keywords:
            keyword = keyword.strip().lower()
            if len(keyword) < 2 or keyword in deduped:
                continue
            deduped.append(keyword)
        return deduped

    def _normalize_request_plan(self, plan: RequestPlan) -> RequestPlan:
        """현재 조직 구성이 허용하는 범위로 실행 전략을 보정한다."""
        if plan.route == "delegate" and not self._dept_map():
            return RequestPlan(
                lane="single_org_execution",
                route="local_execution",
                complexity=plan.complexity,
                rationale="현재는 총괄PM만 활성화되어 있어 조직 위임 대신 PM이 직접 처리합니다.",
                dept_hints=[],
                confidence=plan.confidence,
            )
        return plan

    def _build_request_plan_prompt(self, message: str, dept_hints: list[str]) -> str:
        dept_profiles = self._dept_profiles()
        dept_lines = "\n".join(
            f"- {dept} ({dept_profiles.get(dept, {}).get('dept_name', dept)}): {dept_profiles.get(dept, {}).get('role', '')}"
            for dept in dept_hints
        ) or "- currently no obvious specialist hints"
        return (
            "You are the chief PM for a Telegram-based AI organization.\n"
            "Decide the lightest correct handling strategy for the user request.\n\n"
            "Available routes:\n"
            '- "direct_reply": answer or clarify directly. No execution or delegation.\n'
            '- "local_execution": the PM should handle it like a single coding agent.\n'
            '- "delegate": coordinate one or more specialist organizations.\n\n'
            "Choose direct_reply for simple questions, confirmations, status checks, and lightweight explanations.\n"
            "Choose local_execution for focused tasks that do not need cross-team coordination.\n"
            "Choose delegate only when multi-discipline collaboration, explicit planning/brainstorming, or longer multi-step execution is needed.\n\n"
            "Department hints:\n"
            f"{dept_lines}\n\n"
            "Return JSON only in this exact shape:\n"
            '{"route":"direct_reply|local_execution|delegate","complexity":"low|medium|high","rationale":"short reason","confidence":0.0}\n\n'
            f"User request: {message[:700]}"
        )

    async def _classify_lane(
        self,
        user_message: str,
        dept_hints: list[str],
        *,
        workdir: str | None = None,
    ) -> Literal[
        "clarify",
        "direct_answer",
        "review_or_audit",
        "attachment_analysis",
        "single_org_execution",
        "multi_org_execution",
    ]:
        if self._decision_client is None:
            return self._heuristic_lane(user_message, dept_hints)
        prompt = (
            "Classify the user's request into exactly one lane.\n"
            "Return only one token from:\n"
            "clarify, direct_answer, review_or_audit, attachment_analysis, single_org_execution, multi_org_execution\n\n"
            f"User request: {user_message[:800]}"
        )
        try:
            response = await asyncio.wait_for(
                self._decision_client.complete(prompt, workdir=workdir),
                timeout=25.0,
            )
            lane = response.strip().split()[0].strip().lower()
            if lane in {
                "clarify",
                "direct_answer",
                "review_or_audit",
                "attachment_analysis",
                "single_org_execution",
                "multi_org_execution",
            }:
                return lane  # type: ignore[return-value]
        except Exception as e:
            logger.warning(f"[PM] lane 분류 실패, heuristic fallback: {e}")
        return self._heuristic_lane(user_message, dept_hints)

    def _heuristic_lane(
        self,
        user_message: str,
        dept_hints: list[str],
    ) -> Literal[
        "clarify",
        "direct_answer",
        "review_or_audit",
        "attachment_analysis",
        "single_org_execution",
        "multi_org_execution",
    ]:
        text = user_message.lower().strip()
        if any(token in text for token in ("첨부", "파일", "이미지", "pdf", "문서", "voice", "audio", "video")):
            return "attachment_analysis"
        if any(token in text for token in ("리뷰", "audit", "검토", "평가", "문제점", "코드리뷰")):
            return "review_or_audit"
        if any(token in text for token in ("뭐가 빠졌", "무응답", "왜 답이 없", "무슨 뜻", "명확히")):
            return "clarify"
        if len(dept_hints) >= 2 or any(token in text for token in ("여러 조직", "협업", "기획하고", "디자인하고", "개발하고", "조율")):
            return "multi_org_execution"
        if any(token in text for token in ("왜", "무엇", "어떻게", "설명", "상태", "현황", "가능해", "?")):
            return "direct_answer"
        return "single_org_execution"

    async def _llm_plan_request(
        self, user_message: str, dept_hints: list[str], workdir: str | None = None,
    ) -> RequestPlan | None:
        if self._decision_client is None:
            return None
        prompt = self._build_request_plan_prompt(user_message, dept_hints)
        try:
            response = await asyncio.wait_for(
                self._decision_client.complete(prompt, workdir=workdir),
                timeout=35.0,
            )
            return self._parse_request_plan(response, dept_hints)
        except Exception as e:
            logger.warning(f"[PM] 요청 전략 LLM 판단 실패, 휴리스틱 fallback: {e}")
            return None

    def _parse_request_plan(self, response: str, dept_hints: list[str]) -> RequestPlan:
        text = response.strip()
        if "```" in text:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if match:
                text = match.group(1).strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]
        data = json.loads(text)
        route = data.get("route", "delegate")
        if route not in {"direct_reply", "local_execution", "delegate"}:
            route = "delegate"
        complexity = data.get("complexity", "medium")
        if complexity not in {"low", "medium", "high"}:
            complexity = "medium"
        return RequestPlan(
            lane="single_org_execution",
            route=route,
            complexity=complexity,
            rationale=str(data.get("rationale", "")).strip() or "LLM 전략 판단",
            dept_hints=dept_hints,
            confidence=float(data.get("confidence", 0.7)),
        )

    def _heuristic_plan_request(self, user_message: str, dept_hints: list[str], *, lane: str) -> RequestPlan:
        text = user_message.strip()
        lower = text.lower()

        question_markers = (
            "?", "왜", "뭐", "무엇", "어떻게", "맞아", "맞나요", "가능해", "가능한가",
            "확인", "상태", "진행", "현황", "설명", "알려줘", "인가요",
        )
        action_markers = (
            "만들", "작성", "구현", "개발", "설계", "수정", "고쳐", "분석", "정리",
            "실행", "자동화", "배포", "기획", "브레인스토밍", "논의",
        )
        collaboration_markers = (
            "협업", "조율", "각 조직", "여러 조직", "팀", "브레인스토밍", "토론",
            "논의", "기획하고", "디자인하고", "개발하고", "마케팅", "영업", "재무",
        )

        is_question = any(marker in text for marker in question_markers)
        action_hits = sum(1 for marker in action_markers if marker in lower)
        needs_collaboration = len(dept_hints) >= 2 or any(
            marker in lower for marker in collaboration_markers
        )

        if lane == "clarify":
            return RequestPlan(
                lane="clarify",
                route="direct_reply",
                complexity="low",
                rationale="요청 의도나 불만의 정확한 지점을 먼저 짚어 답하는 편이 맞습니다.",
                dept_hints=dept_hints,
                confidence=0.8,
            )
        if lane == "direct_answer":
            return RequestPlan(
                lane="direct_answer",
                route="direct_reply",
                complexity="low",
                rationale="설명·현황·확인 성격이 강해 PM이 직접 답하는 것이 자연스럽습니다.",
                dept_hints=dept_hints,
                confidence=0.8,
            )
        if lane == "review_or_audit":
            route = "delegate" if len(dept_hints) >= 2 else "local_execution"
            return RequestPlan(
                lane="review_or_audit",
                route=route,
                complexity="medium" if route == "local_execution" else "high",
                rationale="리뷰/감사 성격이라 검토 중심 실행 lane으로 처리합니다.",
                dept_hints=dept_hints,
                confidence=0.78,
            )
        if lane == "attachment_analysis":
            route = "delegate" if len(dept_hints) >= 2 else "local_execution"
            return RequestPlan(
                lane="attachment_analysis",
                route=route,
                complexity="medium",
                rationale="첨부 기반 분석 요청이라 attachment lane으로 처리합니다.",
                dept_hints=dept_hints,
                confidence=0.76,
            )
        if lane == "multi_org_execution":
            return RequestPlan(
                lane="multi_org_execution",
                route="delegate",
                complexity="high",
                rationale="복수 조직 협업이 필요한 execution lane입니다.",
                dept_hints=dept_hints,
                confidence=0.8,
            )

        if is_question and action_hits == 0:
            return RequestPlan(
                lane="direct_answer",
                route="direct_reply",
                complexity="low",
                rationale="질문·확인 성격이 강해서 PM이 바로 답하는 편이 자연스럽습니다.",
                dept_hints=dept_hints,
                confidence=0.8,
            )

        if needs_collaboration or action_hits >= 3 or len(text) > 220:
            complexity = "high" if needs_collaboration or len(dept_hints) >= 3 else "medium"
            return RequestPlan(
                lane="multi_org_execution",
                route="delegate",
                complexity=complexity,
                rationale="복수 조직 협업 또는 다단계 실행이 필요해 보여 조직 오케스트레이션으로 보냅니다.",
                dept_hints=dept_hints,
                confidence=0.75,
            )

        return RequestPlan(
            lane="single_org_execution",
            route="local_execution",
            complexity="medium" if action_hits >= 2 or len(text) > 100 else "low",
            rationale="집중된 단일 작업이라 PM이 직접 처리하는 편이 더 빠릅니다.",
            dept_hints=dept_hints,
            confidence=0.7,
        )

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

    def _build_decompose_prompt(self, message: str, dept_hints: list[str]) -> str:
        """현재 specialist 조직 프로필 기반 LLM 분해 프롬프트 생성."""
        dept_profiles = self._dept_profiles()
        dept_lines = "\n".join(
            f"- {org_id} ({profile['dept_name']}): {profile['role']} | specialties={', '.join(profile['specialties']) or '-'}"
            for org_id, profile in dept_profiles.items()
        )
        hint_lines = "\n".join(
            f"- {dept} ({dept_profiles.get(dept, {}).get('dept_name', dept)})"
            for dept in dept_hints
        ) or "- none"
        return (
            f"You are the PM of an AI organization with these departments:\n"
            f"{dept_lines}\n\n"
            f"Priority department hints (must be respected unless clearly irrelevant):\n"
            f"{hint_lines}\n\n"
            f"Break the user's request into specific subtasks for each relevant department.\n"
            f"Each subtask should be a CONCRETE, ACTIONABLE instruction (not the user's raw message).\n\n"
            f"Reply in this exact format (one line per subtask):\n"
            f"DEPT:<org_id>|TASK:specific task description|DEPENDS:comma-separated indices or none\n\n"
            f"Rules:\n"
            f"- Only include departments that are actually needed\n"
            f"- If the user explicitly asked for a department in the hints above, include it unless clearly unrelated\n"
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
        if not self._dept_map():
            logger.info("[PM] 활성 specialist 조직이 없어 분해를 건너뜁니다.")
            return []
        workdir = self._extract_workdir(user_message)
        dept_hints = self._detect_relevant_depts(user_message)
        subtasks = await self._llm_decompose(user_message, dept_hints, workdir=workdir)
        if subtasks:
            for subtask in subtasks:
                subtask.workdir = workdir
            logger.info(f"[PM] LLM 분해 결과: {len(subtasks)}개 서브태스크")
            return subtasks

        subtasks = self._keyword_decompose(user_message)
        for subtask in subtasks:
            subtask.workdir = workdir
        logger.info(f"[PM] 키워드 분해 결과: {len(subtasks)}개 서브태스크")
        return subtasks

    @staticmethod
    def _extract_workdir(user_message: str) -> str | None:
        for raw in re.findall(r"(?:(?<=\s)|^)(~?/[^ \t\r\n'\"`]+)", user_message):
            candidate = Path(raw).expanduser()
            if not candidate.exists():
                continue
            target = candidate if candidate.is_dir() else candidate.parent
            repo_root = PMOrchestrator._find_repo_root(target)
            return str(repo_root or target)
        return None

    @staticmethod
    def _find_repo_root(path: Path) -> Path | None:
        current = path.resolve()
        for candidate in [current, *current.parents]:
            if (candidate / ".git").exists():
                return candidate
        return None

    async def _llm_decompose(
        self,
        user_message: str,
        dept_hints: list[str],
        workdir: str | None = None,
    ) -> list[SubTask]:
        """LLM으로 태스크 분해. 실패 시 빈 리스트 반환."""
        if self._decision_client is None:
            return []

        prompt = self._build_decompose_prompt(user_message, dept_hints)
        try:
            response = await asyncio.wait_for(
                self._decision_client.complete(prompt, workdir=workdir),
                timeout=45.0,
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
        try:
            cfg = load_orchestration_config(force_reload=True)
            known_depts = {
                org.id: org.dept_name
                for org in cfg.list_specialist_orgs()
            }
        except Exception:
            known_depts = dict(KNOWN_DEPTS)
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

            if not dept or dept not in known_depts or not task_desc:
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

    def _detect_relevant_depts(self, user_message: str) -> list[str]:
        """요청에 바로 연관된 부서 후보만 추린다.

        키워드가 하나도 없으면 기본 부서를 강제하지 않는다.
        """
        msg_lower = user_message.lower()
        dept_profiles = self._dept_profiles()
        matched: list[str] = []
        for dept in self._dept_order():
            keywords = self._dept_keywords(dept, dept_profiles.get(dept, {}))
            if any(kw in msg_lower for kw in keywords):
                matched.append(dept)
        return matched

    def _keyword_decompose(self, user_message: str) -> list[SubTask]:
        """키워드 기반 태스크 분해 (fallback).

        현재 specialist 조직 프로필에서 동적으로 부서를 매칭.
        """
        dept_profiles = self._dept_profiles()
        dept_map = {org_id: profile["dept_name"] for org_id, profile in dept_profiles.items()}
        if not dept_map:
            return []
        subtasks: list[SubTask] = []
        msg_lower = user_message.lower()
        short_msg = user_message[:200]

        # 키워드 매칭으로 필요한 부서 탐지
        matched_depts: list[str] = []
        dept_order = self._dept_order()
        for dept in dept_order:
            keywords = self._dept_keywords(dept, dept_profiles.get(dept, {}))
            if any(kw in msg_lower for kw in keywords):
                matched_depts.append(dept)

        # 매칭된 부서별 서브태스크 생성 (순서에 따른 의존성)
        for dept in matched_depts:
            instruction = dept_profiles.get(dept, {}).get("instruction") or f"{dept_map[dept]} 업무를 수행하세요"
            deps: list[str] = []
            # 앞 순서 부서에 의존
            for i, prev in enumerate(subtasks):
                prev_order = dept_order.index(prev.assigned_dept) if prev.assigned_dept in dept_order else 99
                curr_order = dept_order.index(dept) if dept in dept_order else 99
                if prev_order < curr_order:
                    deps.append(str(i))
            subtasks.append(SubTask(
                description=f"{instruction}: {short_msg}",
                assigned_dept=dept,
                depends_on=deps,
            ))

        # 매칭 없으면 첫 번째 부서(기획)로 fallback
        if not subtasks:
            first_dept = next(
                (dept for dept in dept_order if dept in dept_map),
                next(iter(dept_map)),
            )
            instruction = dept_profiles.get(first_dept, {}).get("instruction") or "요청을 분석하세요"
            subtasks.append(SubTask(
                description=f"{instruction}: {user_message[:500]}",
                assigned_dept=first_dept,
            ))

        return subtasks

    def _org_mention(self, org_id: str) -> str:
        try:
            org = load_orchestration_config().get_org(org_id)
            if org and org.username:
                return org.username if org.username.startswith("@") else f"@{org.username}"
        except Exception:
            pass
        return f"@{org_id}"

    def _requester_mention(self, metadata: dict[str, Any] | None) -> str:
        metadata = metadata or {}
        return (
            metadata.get("requester_mention")
            or metadata.get("source_org_mention")
            or metadata.get("requester_org_mention")
            or ""
        )

    def _reply_message_id(self, metadata: dict[str, Any] | None) -> int | None:
        metadata = metadata or {}
        raw = metadata.get("source_message_id") or metadata.get("reply_to_message_id")
        try:
            return int(raw) if raw is not None else None
        except Exception:
            return None

    async def _send_plan_preview(
        self,
        subtasks: list[SubTask],
        chat_id: int,
        rationale: str | None = None,
        parent_metadata: dict[str, Any] | None = None,
    ) -> None:
        """태스크 분배 전 계획을 먼저 텔레그램에 보여준다."""
        lines = ["📋 **PM 실행 계획**\n"]
        requester = self._requester_mention(parent_metadata)
        if requester:
            lines.append(f"요청자: {requester}")
        if rationale:
            lines.append(f"왜 이렇게 처리하나: {rationale}")
            lines.append("")
        for i, st in enumerate(subtasks):
            dept_name = KNOWN_DEPTS.get(st.assigned_dept, st.assigned_dept)
            dept_mention = self._org_mention(st.assigned_dept)
            desc_short = st.description[:100].replace("\n", " ")
            deps = f" (의존: {','.join(st.depends_on)})" if st.depends_on else ""
            lines.append(f"{i+1}. {dept_mention} **{dept_name}**: {desc_short}{deps}")
        lines.append(f"\n총 {len(subtasks)}개 서브태스크 → 실행 시작합니다.")
        try:
            await self._send(
                chat_id,
                "\n".join(lines),
                reply_to_message_id=self._reply_message_id(parent_metadata),
            )
        except Exception as e:
            logger.warning(f"[PM] 계획 미리보기 전송 실패: {e}")

    def _build_subtask_packet(
        self,
        parent_description: str,
        subtask: SubTask,
        *,
        rationale: str | None,
        parent_metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        meta = parent_metadata or {}
        packet = {
            "original_request": meta.get("original_request") or parent_description[:2000],
            "conversation_context": meta.get("conversation_context", ""),
            "rationale": rationale or meta.get("rationale", ""),
            "requester_mention": meta.get("requester_mention") or meta.get("source_org_mention") or "",
            "user_expectations": list(meta.get("user_expectations") or []),
            "goal": subtask.description[:1000],
        }
        return {key: value for key, value in packet.items() if value}

    def _write_unified_report_artifact(
        self,
        parent_task_id: str,
        original_request: str,
        report: str,
        subtasks: list[dict],
    ) -> Path:
        reports_root = os.environ.get("AIORG_REPORT_DIR")
        reports_dir = Path(reports_root).expanduser() if reports_root else Path(__file__).resolve().parent.parent / ".omx" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        path = reports_dir / f"{parent_task_id}-telegram-report.md"
        lines = [
            f"# {parent_task_id} 통합 보고서",
            "",
            "## 원 요청",
            original_request.strip() or "(요청 없음)",
            "",
            "## 최종 전달본",
            report.strip() or "(보고서 없음)",
            "",
            "## 조직별 핵심 결과",
        ]
        for task in subtasks:
            dept = task.get("assigned_dept") or "unknown"
            dept_name = KNOWN_DEPTS.get(dept, dept)
            result = (task.get("result") or "(결과 없음)").strip().lstrip("-").strip()
            lines.extend([
                f"### {dept_name}",
                result[:4000],
                "",
            ])
        path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        return path

    async def dispatch(
        self,
        parent_task_id: str,
        subtasks: list[SubTask],
        chat_id: int,
        rationale: str | None = None,
    ) -> list[str]:
        """서브태스크를 ContextDB에 생성하고 TaskGraph 구성 후 첫 번째 웨이브 발송."""
        if not subtasks:
            await self._send(
                chat_id,
                "ℹ️ 현재 활성 specialist 조직이 없어 총괄PM 직접 실행 경로로 처리해야 합니다.",
                reply_to_message_id=self._reply_message_id(
                    (await self._db.get_pm_task(parent_task_id) or {}).get("metadata")
                ),
            )
            return []
        parent_task = await self._db.get_pm_task(parent_task_id)
        parent_metadata = parent_task.get("metadata", {}) if parent_task else {}
        parent_description = parent_task.get("description", "") if parent_task else ""
        # 0. 계획 미리보기 전송
        await self._send_plan_preview(
            subtasks,
            chat_id,
            rationale=rationale,
            parent_metadata=parent_metadata,
        )

        task_ids: list[str] = []

        # 1. 서브태스크 생성 (구조화 프롬프트 적용)
        for st in subtasks:
            tid = await self._next_task_id()
            task_packet = self._build_subtask_packet(
                parent_description,
                st,
                rationale=rationale,
                parent_metadata=parent_metadata,
            )
            # 구조화 프롬프트 생성
            structured = await self._prompt_gen.generate(
                description=st.description,
                dept=st.assigned_dept,
                context=(
                    f"상위 목표: {task_packet.get('original_request', '')[:400]}\n"
                    f"현재 배정 목표: {task_packet.get('goal', '')[:300]}\n"
                    f"사용자 기대: {'; '.join(task_packet.get('user_expectations', [])[:4])}"
                ).strip(),
            )
            full_description = structured.render()

            await self._db.create_pm_task(
                task_id=tid,
                description=full_description,
                assigned_dept=st.assigned_dept,
                created_by=self._org_id,
                parent_id=parent_task_id,
                metadata={
                    **parent_metadata,
                    "task_packet": task_packet,
                    "original_description": st.description,
                    **({"workdir": st.workdir} if st.workdir else {}),
                },
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
                dept_mention = self._org_mention(dept)
                requester = self._requester_mention(task.get("metadata"))
                prefix = f"{dept_mention} "
                if requester:
                    prefix += f"(요청자: {requester}) "
                msg = f"{prefix}[PM_TASK:{tid}|dept:{dept}] {dept_name}에 배정: {task['description'][:300]}"
                # DB 먼저 업데이트 — send 실패해도 task_poller가 감지 가능
                await self._db.update_pm_task_status(tid, "assigned")
                try:
                    await self._send(
                        chat_id,
                        msg,
                        reply_to_message_id=self._reply_message_id(task.get("metadata")),
                    )
                except Exception as _e:
                    logger.warning(f"[PM] 태스크 {tid} 알림 전송 실패 (태스크는 assigned 상태): {_e}")
                logger.info(f"[PM] 태스크 발송: {tid} → {dept}")

        return task_ids

    async def build_status_snapshot(self, parent_task_id: str) -> str:
        """부모 태스크 진행 상태를 사람이 읽기 쉽게 요약한다."""
        subtasks = await self._db.get_subtasks(parent_task_id)
        if not subtasks:
            return "진행 중인 세부 태스크가 없습니다."

        icons = {
            "done": "✅",
            "running": "🔄",
            "assigned": "📨",
            "pending": "⏳",
            "failed": "❌",
            "needs_review": "⚠️",
        }
        total = len(subtasks)
        done = sum(1 for task in subtasks if task["status"] == "done")
        running = sum(1 for task in subtasks if task["status"] in {"running", "assigned"})
        lines = [f"📊 진행 상황: {done}/{total} 완료, {running}개 진행 중"]
        for task in subtasks[:8]:
            dept_name = KNOWN_DEPTS.get(task.get("assigned_dept") or "", task.get("assigned_dept") or "?")
            icon = icons.get(task["status"], "•")
            desc = task["description"][:60].replace("\n", " ")
            lines.append(f"{icon} {dept_name}: {desc}")
        if total > 8:
            lines.append(f"… 외 {total - 8}개 태스크")
        return "\n".join(lines)

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
                dept_mention = self._org_mention(dept)
                requester = self._requester_mention(task.get("metadata"))
                prefix = f"{dept_mention} "
                if requester:
                    prefix += f"(요청자: {requester}) "
                msg = f"{prefix}[PM_TASK:{tid}|dept:{dept}] {dept_name}에 배정: {task['description'][:300]}"
                await self._db.update_pm_task_status(tid, "assigned")
                try:
                    await self._send(
                        chat_id,
                        msg,
                        reply_to_message_id=self._reply_message_id(task.get("metadata")),
                    )
                except Exception as _e:
                    logger.warning(f"[PM] 태스크 {tid} 알림 전송 실패 (태스크는 assigned 상태): {_e}")

        # 모든 서브태스크 완료 확인
        task_info = await self._db.get_pm_task(task_id)
        if task_info and task_info.get("parent_id"):
            parent_id = task_info["parent_id"]
            siblings = await self._db.get_subtasks(parent_id)
            if all(s["status"] == "done" for s in siblings):
                await self._synthesize_and_act(parent_id, siblings, chat_id)
            else:
                await self._send(chat_id, await self.build_status_snapshot(parent_id))

    async def consolidate_results(self, parent_task_id: str) -> str:
        """부모 태스크의 완료된 서브태스크 결과를 단순 요약 문자열로 합친다."""
        subtasks = await self._db.get_subtasks(parent_task_id)
        lines: list[str] = []
        for task in subtasks:
            dept = task.get("assigned_dept") or "unknown"
            dept_name = KNOWN_DEPTS.get(dept, dept)
            result = (task.get("result") or "").strip() or "(결과 없음)"
            lines.append(f"[{dept_name}] {result}")
        return "\n".join(lines)

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
        parent_meta = parent.get("metadata", {}) if parent else {}
        parent_workdir = parent_meta.get("workdir")
        run_id = parent_meta.get("run_id")
        runbook = OrchestrationRunbook(Path(__file__).resolve().parent.parent)
        # LLM 합성 성공 시 unified_report 사용, 실패(keyword fallback) 시 subtask 원본 결과 직접 전달
        full_results = "\n\n".join(
            f"## {KNOWN_DEPTS.get(st.get('assigned_dept', ''), st.get('assigned_dept', '?'))}\n"
            f"{(st.get('result') or '').lstrip('-').strip()}"
            for st in subtasks
            if st.get("result")
        )
        report_text = synthesis.unified_report or full_results or synthesis.summary
        user_friendly_report = await ensure_user_friendly_output(
            report_text,
            original_request=original_request,
            full_context=full_results,
            decision_client=self._decision_client,
        )
        artifact_path = self._write_unified_report_artifact(
            parent_task_id,
            original_request,
            user_friendly_report,
            subtasks,
        )

        # 하위 조직이 생성한 파일 경로 수집 (PNG, MD 등)
        subtask_artifact_markers = ""
        seen_paths: set[str] = set()
        for st in subtasks:
            for path in extract_local_artifact_paths(st.get("result") or ""):
                if path not in seen_paths:
                    seen_paths.add(path)
                    subtask_artifact_markers += f"\n[ARTIFACT:{path}]"

        if synthesis.judgment == SynthesisJudgment.SUFFICIENT:
            report = user_friendly_report
            await self._send(
                chat_id,
                f"✅ 모든 부서 작업 완료!\n\n{report}\n\n통합 보고서를 첨부합니다.\n[ARTIFACT:{artifact_path}]{subtask_artifact_markers}",
            )
            if run_id:
                try:
                    runbook.advance_phase(run_id, note="조직 협업 결과 통합 완료, verification phase 이동")
                    runbook.advance_phase(run_id, note="피드백 phase 이동")
                    runbook.advance_phase(run_id, note="delegated run 완료")
                except Exception as e:
                    logger.warning(f"[PM] runbook 완료 처리 실패 ({run_id}): {e}")
            # 향후 계획/추가 작업이 있으면 자동 실행 (LLM이 FOLLOW_UP으로 추출한 것)
            if synthesis.follow_up_tasks:
                follow_ups = [
                    SubTask(
                        description=ft["description"],
                        assigned_dept=ft["dept"],
                        workdir=parent_workdir,
                    )
                    for ft in synthesis.follow_up_tasks
                ]
                await self._send(
                    chat_id,
                    f"📋 향후 계획 {len(follow_ups)}건 자동 실행 중..."
                )
                await self.dispatch(parent_task_id, follow_ups, chat_id)
            else:
                await self._db.update_pm_task_status(
                    parent_task_id, "done", result=report,
                )
        elif synthesis.judgment == SynthesisJudgment.INSUFFICIENT:
            await self._send(
                chat_id,
                f"⚠️ 결과 부족 — 추가 작업 배분 중...\n"
                f"사유: {synthesis.reasoning}\n\n{user_friendly_report}\n\n현재까지의 통합 보고서를 첨부합니다.\n[ARTIFACT:{artifact_path}]{subtask_artifact_markers}",
            )
            if run_id:
                try:
                    runbook.advance_phase(run_id, note="결과 부족으로 verification phase에서 추가 작업 필요")
                except Exception as e:
                    logger.warning(f"[PM] runbook 진행 실패 ({run_id}): {e}")
            if synthesis.follow_up_tasks:
                follow_ups = [
                    SubTask(
                        description=ft["description"],
                        assigned_dept=ft["dept"],
                        workdir=parent_workdir,
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
                f"사유: {synthesis.reasoning}\n\n{user_friendly_report}\n\n"
                f"조율이 필요합니다.\n현재 통합 보고서를 첨부합니다.\n[ARTIFACT:{artifact_path}]{subtask_artifact_markers}",
            )
            if run_id:
                try:
                    runbook.advance_phase(run_id, note="결과 충돌로 verification phase에서 정지")
                except Exception as e:
                    logger.warning(f"[PM] runbook 진행 실패 ({run_id}): {e}")
            await self._db.update_pm_task_status(
                parent_task_id, "needs_review", result=synthesis.summary,
            )
        else:  # NEEDS_INTEGRATION
            report = user_friendly_report
            await self._send(
                chat_id,
                f"📋 결과 통합 보고서:\n\n{report}\n\n통합 보고서를 첨부합니다.\n[ARTIFACT:{artifact_path}]{subtask_artifact_markers}",
            )
            if run_id:
                try:
                    runbook.advance_phase(run_id, note="통합 보고서 작성 완료, verification phase 이동")
                    runbook.advance_phase(run_id, note="피드백 phase 이동")
                    runbook.advance_phase(run_id, note="delegated run 완료")
                except Exception as e:
                    logger.warning(f"[PM] runbook 완료 처리 실패 ({run_id}): {e}")
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

        needs_discussion = await self._llm_detect_discussion(
            user_message,
            participants,
            workdir=self._extract_workdir(user_message),
        )

        if not needs_discussion:
            return []

        return [DiscussionNeeded(
            topic=user_message[:100],
            proposal=user_message[:300],
            participants=participants,
        )]

    async def _llm_detect_discussion(
        self,
        user_message: str,
        participants: list[str],
        workdir: str | None = None,
    ) -> bool:
        """LLM으로 토론 필요 여부 판단. 실패 시 키워드 fallback."""
        if self._decision_client is None:
            logger.debug("[PM] LLM provider 없음 — 키워드 fallback")
            return self._keyword_detect_discussion(user_message)

        dept_names = [KNOWN_DEPTS.get(p, p) for p in participants]
        prompt = self._LLM_DISCUSSION_PROMPT.format(
            message=user_message[:500],
            departments=", ".join(dept_names),
        )

        try:
            response = await asyncio.wait_for(
                self._decision_client.complete(prompt, workdir=workdir),
                timeout=30.0,
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
