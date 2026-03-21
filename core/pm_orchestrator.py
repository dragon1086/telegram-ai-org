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
from core.staleness_checker import StalenessChecker

ENABLE_PM_ORCHESTRATOR = os.environ.get("ENABLE_PM_ORCHESTRATOR", "0") == "1"
MAX_REWORK_RETRIES = int(os.environ.get("MAX_REWORK_RETRIES", "2"))
MAX_CONCURRENT_PARENT_TASKS = int(os.environ.get("MAX_CONCURRENT_PARENT_TASKS", "10"))


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
        "debate",
    ]
    route: Literal["direct_reply", "local_execution", "delegate"]
    complexity: Literal["low", "medium", "high"]
    rationale: str
    dept_hints: list[str] = field(default_factory=list)
    confidence: float = 0.0
    interaction_mode: Literal["direct", "delegate", "debate", "discussion", "collab"] = "direct"


async def _record_bot_perf(
    db: "ContextDB",
    task_id: str,
    success: bool,
) -> None:
    """봇 성과 기록 헬퍼. 예외 발생 시 무시 (non-critical)."""
    try:
        task = await db.get_pm_task(task_id)
        if not task:
            return
        bot_id = task.get("assigned_dept", "")
        if not bot_id:
            return
        latency = 0.0
        created = task.get("created_at", "")
        if created:
            from datetime import datetime, UTC
            try:
                start = datetime.fromisoformat(created)
                latency = (datetime.now(UTC) - start).total_seconds()
            except (ValueError, TypeError):
                pass
        await db.record_bot_task_completion(
            bot_id=bot_id, success=success, latency_sec=latency,
        )
    except Exception as _perf_err:
        logger.warning(f"[PM] bot_performance 기록 실패 (무시): {_perf_err}")


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
        # AgentPersonaMemory singleton — instantiated once to avoid per-call DDL overhead
        self._apm = None
        try:
            from core.agent_persona_memory import AgentPersonaMemory as _APM
            self._apm = _APM()
        except Exception as _apm_err:
            logger.debug(f"[PM] AgentPersonaMemory 초기화 실패 (무시): {_apm_err}")
        # StalenessChecker — 백그라운드 루프로 stale 서브태스크 자동 감지
        self._staleness_checker = StalenessChecker(context_db)
        try:
            self._staleness_checker.start()
        except Exception as _sc_err:
            logger.warning(f"[PM] StalenessChecker 시작 실패 (무시): {_sc_err}")

    @property
    def decision_client(self) -> DecisionClientProtocol | None:
        return self._decision_client

    async def plan_request(self, user_message: str) -> RequestPlan:
        """유저 요청을 직접 답변/PM 직접 실행/조직 위임 중 어디로 보낼지 결정한다."""
        dept_hints = self._detect_relevant_depts(user_message)
        # recommend_team feedback loop: 성과 데이터 기반 부서 힌트 보강
        # Only runs when dept_hints is non-empty AND apm is available
        if dept_hints and self._apm is not None:
            try:
                task_type = self._infer_task_type(user_message)
                if task_type != "general":
                    loop = asyncio.get_running_loop()
                    recommended = await loop.run_in_executor(
                        None, self._apm.recommend_team, task_type, 3,
                    )
                    for bot_id in recommended:
                        if bot_id not in dept_hints:
                            dept_hints.append(bot_id)
            except Exception as _e:
                logger.debug(f"[PM] recommend_team 조회 실패 (무시): {_e}")
        workdir = self._extract_workdir(user_message)
        result = await self._llm_unified_classify(user_message, dept_hints, workdir=workdir)
        return self._normalize_request_plan(result)

    # autoresearch 타겟: core/routing_keywords.py 에서 관리
    from core.routing_keywords import BASE_DEPT_KEYWORDS as _BASE_DEPT_KEYWORDS  # noqa: E402
    from core.routing_keywords import BASE_DEPT_ORDER as _BASE_DEPT_ORDER  # noqa: E402

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
            if profiles:
                return profiles
            logger.warning("[PM] orchestration.yaml에 specialist org 없음, 상수 fallback 사용")
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

    async def _llm_unified_classify(
        self,
        user_message: str,
        dept_hints: list[str],
        *,
        workdir: str | None = None,
    ) -> "RequestPlan":
        """lane + route + complexity를 단일 LLM 호출로 처리. 실패 시 heuristic fallback."""
        if self._decision_client is None:
            return self._heuristic_unified_classify(user_message, dept_hints)

        dept_list = ", ".join(dept_hints) if dept_hints else "없음"
        prompt = (
            "Classify the following user request and return JSON only.\n"
            "Fields:\n"
            '  lane: one of [clarify, direct_answer, review_or_audit, attachment_analysis, single_org_execution, multi_org_execution, debate]\n'
            '    - debate: 여러 부서의 상충하는 관점을 수집하고 토론. 비교/찬반/토론/A vs B 요청에 사용.\n'
            '  route: one of [direct_reply, local_execution, delegate]\n'
            '  complexity: one of [low, medium, high]\n'
            '  rationale: brief Korean explanation (max 30 chars)\n\n'
            f"dept_hints: {dept_list}\n"
            f"User request: {user_message[:800]}\n\n"
            "Return only valid JSON, no markdown."
        )
        try:
            response = await asyncio.wait_for(
                self._decision_client.complete(prompt, workdir=workdir),
                timeout=35.0,
            )
            text = response.strip()
            if "```" in text:
                m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
                if m:
                    text = m.group(1).strip()
            start, end = text.find("{"), text.rfind("}") + 1
            if start >= 0 and end > start:
                text = text[start:end]
            data = json.loads(text)

            lane = data.get("lane", "single_org_execution")
            valid_lanes = {"clarify", "direct_answer", "review_or_audit", "attachment_analysis", "single_org_execution", "multi_org_execution", "debate"}
            if lane not in valid_lanes:
                lane = "single_org_execution"

            # 코딩/예제/API 설계 요청은 LLM이 direct_answer로 분류해도 강제 위임
            if lane == "direct_answer" and self._has_coding_request(user_message):
                lane = "single_org_execution"
                if "aiorg_engineering_bot" not in dept_hints:
                    dept_hints = ["aiorg_engineering_bot"] + dept_hints

            route = data.get("route", "delegate")
            if route not in {"direct_reply", "local_execution", "delegate"}:
                route = "delegate"
            if lane == "single_org_execution" and route == "direct_reply":
                route = "delegate"

            complexity = data.get("complexity", "medium")
            if complexity not in {"low", "medium", "high"}:
                complexity = "medium"

            return RequestPlan(
                lane=lane,
                route=route,
                complexity=complexity,
                rationale=str(data.get("rationale", "")).strip() or "통합 LLM 판단",
                dept_hints=dept_hints,
                confidence=0.8,
                interaction_mode=PMOrchestrator._classify_interaction_mode(lane, route, user_message),
            )
        except Exception as e:
            logger.warning(f"[PM] 통합 분류 LLM 실패, heuristic fallback: {e}")
            return self._heuristic_unified_classify(user_message, dept_hints)

    def _heuristic_unified_classify(
        self, user_message: str, dept_hints: list[str]
    ) -> "RequestPlan":
        """통합 heuristic fallback — lane + route + complexity 동시 결정."""
        lane = self._heuristic_lane(user_message, dept_hints)
        plan = self._heuristic_plan_request(user_message, dept_hints, lane=lane)
        plan.lane = lane
        plan.interaction_mode = PMOrchestrator._classify_interaction_mode(
            plan.lane, plan.route, user_message
        )
        return plan

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
        "debate",
    ]:
        if self._decision_client is None:
            return self._heuristic_lane(user_message, dept_hints)
        prompt = (
            "Classify the user's request into exactly one lane.\n"
            "Return only one token from:\n"
            "clarify, direct_answer, review_or_audit, attachment_analysis, single_org_execution, multi_org_execution, debate\n\n"
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
                "debate",
            }:
                return lane  # type: ignore[return-value]
        except Exception as e:
            logger.warning(f"[PM] lane 분류 실패, heuristic fallback: {e}")
        return self._heuristic_lane(user_message, dept_hints)

    _DEBATE_KEYWORDS = [
        "토론", "찬반", "debate", "비교해봐", "vs", "의견 충돌", "두 팀의", "관점을", "비교하면",
    ]

    # 코딩·예제·API 설계 요청 → 항상 engineering bot으로 강제 위임
    _CODING_OVERRIDE_KEYWORDS: list[str] = [
        "예제", "샘플", "코드", "스크립트", "구현해", "작성해줘", "만들어줘", "짜줘",
        "rest api", "endpoint", "엔드포인트", "api 설계", "api 명세",
        "함수", "메서드", "클래스", "알고리즘", "컴프리헨션",
        "파이썬", "python", "javascript", "js ", "sql", "쿼리",
    ]

    def _has_coding_request(self, text: str) -> bool:
        t = text.lower()
        return any(kw in t for kw in self._CODING_OVERRIDE_KEYWORDS)

    _DISCUSSION_RELAY_KEYWORDS = [
        "봇들끼리", "얘기해봐", "자율 토론", "토의해봐", "봇끼리", "서로 논의",
    ]

    _COLLAB_KEYWORDS: list[str] = [
        "협업해줘", "협업해서", "협업하여", "같이 해줘", "같이해줘", "함께 만들어",
        "봇들이 협력", "협력해서", "협력하여", "합작",
    ]

    @staticmethod
    def _classify_interaction_mode(
        lane: str, route: str, user_message: str = ""
    ) -> "Literal['direct', 'delegate', 'debate', 'discussion', 'collab']":
        """lane + route + 메시지 분석으로 interaction_mode 결정.

        discussion/collab 명시 키워드는 lane 기반 debate보다 우선한다.
        (예: 'B2B vs B2C 봇들끼리 얘기해봐' — vs가 debate lane을 트리거해도
         '봇들끼리 얘기해봐'가 사용자의 명시적 의도이므로 discussion으로 처리)
        """
        text = user_message.lower()
        # 사용자 명시 키워드 우선 — lane보다 앞에 체크
        if any(kw in text for kw in PMOrchestrator._DISCUSSION_RELAY_KEYWORDS):
            return "discussion"
        if any(kw in text for kw in PMOrchestrator._COLLAB_KEYWORDS):
            return "collab"
        if lane == "debate":
            return "debate"
        if lane == "multi_org_execution":
            return "delegate"
        return "direct"

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
        "debate",
    ]:
        text = user_message.lower().strip()
        if any(token in text for token in ("첨부", "파일", "이미지", "pdf", "문서", "voice", "audio", "video")):
            return "attachment_analysis"
        if any(token in text for token in ("리뷰", "audit", "검토", "평가", "문제점", "코드리뷰")):
            return "review_or_audit"
        if any(token in text for token in ("뭐가 빠졌", "무응답", "왜 답이 없", "무슨 뜻", "명확히")):
            return "clarify"
        if any(token in text for token in self._DEBATE_KEYWORDS):
            return "debate"
        if len(dept_hints) >= 2 or any(token in text for token in ("여러 조직", "협업", "기획하고", "디자인하고", "개발하고", "조율")):
            return "multi_org_execution"
        if any(token in text for token in ("왜", "무엇", "어떻게", "설명", "상태", "현황", "가능해", "?")):
            if self._has_coding_request(text):
                return "single_org_execution"
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
        if lane == "debate":
            return RequestPlan(
                lane="debate",
                route="delegate",
                complexity="high",
                rationale="여러 부서의 상충하는 관점 수집·토론이 필요한 debate lane입니다.",
                dept_hints=dept_hints,
                confidence=0.8,
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

        if is_question and action_hits == 0 and not self._has_coding_request(text):
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
                import aiosqlite
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
            f"- CRITICAL: Use DEPENDS to enforce sequential ordering. Only use 'none' when tasks are truly parallelizable.\n"
            f"- MANDATORY ordering rules (must be reflected in DEPENDS):\n"
            f"  * research/analysis tasks MUST complete before engineering/coding tasks (engineering DEPENDS on research index)\n"
            f"  * engineering/coding tasks MUST complete before ops/deploy tasks (ops DEPENDS on engineering index)\n"
            f"  * planning/product tasks MUST complete before design or engineering tasks\n"
            f"  * design tasks MUST complete before engineering tasks when design output is needed\n"
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

    def _infer_task_type(self, user_message: str) -> str:
        """메시지에서 TASK_TYPE_VOCAB 키워드 추론. recommend_team() 조회용."""
        from core.agent_persona_memory import TASK_TYPE_VOCAB
        lower = user_message.lower()
        type_keywords: dict[str, list[str]] = {
            "coding": ["코딩", "코드", "개발", "구현", "fix", "버그", "build", "테스트", "파이썬", "python", "예제", "스크립트", "함수", "메서드", "알고리즘", "컴프리헨션", "프로그래밍"],
            "design": ["디자인", "ui", "ux", "화면", "design", "레이아웃"],
            "research": ["리서치", "research", "조사", "분석", "벤치마크", "비교"],
            "planning": ["기획", "스펙", "prd", "plan", "요구사항", "로드맵"],
            "ops": ["배포", "인프라", "deploy", "운영", "ops", "서버", "도커"],
            "marketing": ["마케팅", "성장", "growth", "marketing", "광고", "캠페인"],
        }
        for task_type, keywords in type_keywords.items():
            if task_type in TASK_TYPE_VOCAB and any(kw in lower for kw in keywords):
                return task_type
        return "general"

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
        lines = ["📋 **이렇게 나눠서 진행할게요!**\n"]
        requester = self._requester_mention(parent_metadata)
        if requester:
            lines.append(f"요청자: {requester}")
        if rationale:
            lines.append(f"({rationale})")
            lines.append("")
        for i, st in enumerate(subtasks):
            dept_name = KNOWN_DEPTS.get(st.assigned_dept, st.assigned_dept)
            dept_mention = self._org_mention(st.assigned_dept)
            desc_short = st.description[:100].replace("\n", " ")
            deps = f" (→ {','.join(st.depends_on)} 완료 후)" if st.depends_on else ""
            lines.append(f"{i+1}. {dept_mention} **{dept_name}**: {desc_short}{deps}")
        lines.append(f"\n{len(subtasks)}개 팀에 나눠서 바로 시작할게요 🙌")
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
        # Backpressure: 새 루트 태스크가 MAX_CONCURRENT_PARENT_TASKS 초과 시 거부
        try:
            _active = await self._db.get_active_parent_tasks()
            _others = [p for p in _active if p["id"] != parent_task_id]
            if len(_others) >= MAX_CONCURRENT_PARENT_TASKS:
                await self._send(
                    chat_id,
                    "지금 일이 좀 몰려있어요 😅 잠깐만 기다려주시면 바로 봐드릴게요!",
                )
                return []
        except Exception as _bp_e:
            logger.debug(f"[PM] backpressure check 실패 (무시): {_bp_e}")
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

        # 0. 태스크 ID 사전 생성 + 의존성 먼저 등록 (레이스 컨디션 방지)
        # LLM 프롬프트 생성(~15–20s/태스크) 중 TaskPoller가 의존성 미등록 태스크를
        # 조기 수신하는 경쟁 조건을 차단한다. deps 등록 → 태스크 생성 순서를 보장.
        task_ids: list[str] = []
        for _ in subtasks:
            task_ids.append(await self._next_task_id())
        for i, st in enumerate(subtasks):
            deps = [task_ids[int(d)] for d in st.depends_on if d.isdigit() and int(d) < len(task_ids)]
            await self._graph.add_task(task_ids[i], depends_on=deps)
        logger.debug(f"[PM] 의존성 사전 등록 완료: {len(task_ids)}개 태스크")

        # 1. 서브태스크 생성 (구조화 프롬프트 적용) — task_ids는 이미 확정
        for i, st in enumerate(subtasks):
            tid = task_ids[i]
            task_packet = self._build_subtask_packet(
                parent_description,
                st,
                rationale=rationale,
                parent_metadata=parent_metadata,
            )
            # 구조화 프롬프트 생성 — AgentPersonaMemory 강점/약점 주입
            _persona_ctx = ""
            if self._apm is not None:
                try:
                    _loop = asyncio.get_running_loop()
                    _stats = await _loop.run_in_executor(
                        None, self._apm.get_stats, st.assigned_dept,
                    )
                    if _stats and (_stats.strengths or _stats.weaknesses):
                        _dname = KNOWN_DEPTS.get(st.assigned_dept, st.assigned_dept)
                        if _stats.strengths:
                            _persona_ctx += f"\n[{_dname} 강점]: {', '.join(_stats.strengths)}"
                        if _stats.weaknesses:
                            _persona_ctx += f"\n[{_dname} 약점]: {', '.join(_stats.weaknesses)}"
                except Exception as _apm_e:
                    logger.debug(f"[PM] persona context 조회 실패 (무시): {_apm_e}")
            structured = await self._prompt_gen.generate(
                description=st.description,
                dept=st.assigned_dept,
                context=(
                    f"상위 목표: {task_packet.get('original_request', '')[:400]}\n"
                    f"현재 배정 목표: {task_packet.get('goal', '')[:300]}\n"
                    f"사용자 기대: {'; '.join(task_packet.get('user_expectations', [])[:4])}"
                    f"{_persona_ctx}"
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

        # 2. 의존성 등록 — Step 0에서 이미 완료 (skip)

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
        # Performance DB 업데이트 (성공)
        asyncio.create_task(_record_bot_perf(self._db, task_id, success=True))

        # Effectiveness tracking: 적용된 교훈의 효과 점수 업데이트
        try:
            task_info = await self._db.get_pm_task(task_id)
            if task_info:
                from core.lesson_memory import LessonMemory
                _lm_eff = LessonMemory()
                await _lm_eff.aupdate_effectiveness(
                    worker=task_info.get("assigned_dept", ""),
                    task_description=task_info.get("description", ""),
                    success=True,
                )
        except Exception as _eff_e:
            logger.debug(f"[PM] effectiveness tracking 실패 (무시): {_eff_e}")

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
            task_meta = task_info.get("metadata") or {}
            # discussion 모드: 현재 라운드 서브태스크만 완료 체크 (이전 라운드 done 간섭 방지)
            if task_meta.get("interaction_mode") == "discussion":
                current_round = task_meta.get("discussion_round")
                if current_round is not None:
                    round_siblings = [
                        s for s in siblings
                        if s.get("metadata", {}).get("discussion_round") == current_round
                    ]
                    all_done = bool(round_siblings) and all(
                        s["status"] == "done" for s in round_siblings
                    )
                else:
                    all_done = all(s["status"] == "done" for s in siblings)
            else:
                all_done = all(s["status"] == "done" for s in siblings)
            if all_done:
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

    async def _debate_synthesize(
        self,
        parent_task_id: str,
        parent_meta: dict,
        subtasks: list[dict],
        chat_id: int,
    ) -> None:
        """debate 모드 전용 합성 — 관점 비교 후 PM 종합 판단 전송."""
        topic = parent_meta.get("debate_topic", "토론 주제")
        opinions = [
            {
                "bot_id": task.get("assigned_to", "unknown"),
                "dept_name": task.get("metadata", {}).get(
                    "dept_name", task.get("assigned_to", "")
                ),
                "content": task.get("result", "(응답 없음)"),
            }
            for task in subtasks
        ]

        conclusion = await self._synthesizer.synthesize_debate(topic, opinions)

        header = f"[토론 결론] {topic[:50]}\n\n"
        opinion_lines = "".join(
            f"• {op['dept_name']}: {op['content'][:80]}...\n" for op in opinions
        )
        msg = f"{header}{opinion_lines}\n🎯 PM 종합 판단:\n{conclusion}"

        await self._send(chat_id, msg)
        await self._db.update_pm_task_status(parent_task_id, "done", result=conclusion)

    async def _discussion_summarize(
        self, parent_id: str, results: list[dict], chat_id: int,
    ) -> None:
        """discussion 모드 라운드 관리. 라운드가 남으면 핑퐁 재발행, 아니면 최종 요약."""
        # parent 먼저 조회 — current_round 기준으로 perspectives 필터링 필요
        parent = await self._db.get_pm_task(parent_id)
        parent_meta = parent.get("metadata", {}) if parent else {}
        max_rounds: int = int(parent_meta.get("discussion_rounds", 1))
        current_round: int = int(parent_meta.get("discussion_current_round", 1))
        topic: str = parent_meta.get("discussion_topic", "")
        # 현재 라운드 서브태스크 결과만 추출 (이전 라운드 중복 제외)
        # discussion_round가 없는 결과는 backward compat으로 포함
        perspectives = [
            r.get("result", "") for r in results
            if r.get("result")
            and (
                r.get("metadata", {}).get("discussion_round") is None
                or r.get("metadata", {}).get("discussion_round") == current_round
            )
        ]
        if not perspectives:
            await self._db.update_pm_task_status(parent_id, "done", result="")
            return

        if current_round < max_rounds:
            round_summary = await self._synthesizer.summarize_discussion(perspectives)
            next_round = current_round + 1
            # 충돌/합의 독립 감지 (순차 게이팅 아님)
            has_conflict, conflict_points = await self._detect_discussion_conflict(perspectives)
            has_consensus = await self._detect_discussion_consensus(perspectives)

            if has_conflict:
                logger.info(f"[PM] discussion {parent_id} 라운드 {current_round}: 의견 충돌 감지")
                if chat_id:
                    await self._send(chat_id, "🔥 *의견 충돌 감지* — 다음 라운드에서 구체적 반박 요청")

            # 합의 도달 AND 충돌 없음 → 조기 종료 (충돌+합의 동시 = 모순 신호, 계속 진행)
            if has_consensus and not has_conflict:
                logger.info(f"[PM] discussion {parent_id} 라운드 {current_round}: 합의 도달 — 조기 종료")
                if chat_id:
                    await self._send(
                        chat_id,
                        f"✅ *합의 도달* — 토론 조기 종료 (라운드 {current_round}/{max_rounds})\n\n"
                        f"💬 *최종 요약*\n{round_summary or '의견 수렴 완료'}",
                    )
                await self._db.update_pm_task_status(parent_id, "done", result=round_summary or "")
                return

            follow_up = await self._generate_discussion_followup(
                topic, round_summary, next_round,
                has_conflict=has_conflict, conflict_points=conflict_points,
            )
            await self._db.update_pm_task_metadata(
                parent_id, {"discussion_current_round": next_round}
            )
            if chat_id:
                await self._send(
                    chat_id,
                    f"💬 *라운드 {current_round} 요약*\n{round_summary or '의견 수렴 중...'}"
                    f"\n\n➡️ 라운드 {next_round} 시작",
                )
            participants: list[str] = parent_meta.get("discussion_participants", [])
            if participants:
                await self._redispatch_discussion_round(
                    parent_id, follow_up, participants, chat_id, next_round, max_rounds,
                )
            return

        summary = await self._synthesizer.summarize_discussion(perspectives)
        if summary and chat_id:
            await self._send(chat_id, f"💬 *토론 요약*\n{summary}")
        await self._db.update_pm_task_status(parent_id, "done", result=summary or "")
        # 최종 라운드 완료 → 전체 subtask 결과로 PM 통합 보고서 생성
        # (_skip_discussion_gate=True 로 재귀 방지)
        await self._synthesize_and_act(parent_id, results, chat_id, _skip_discussion_gate=True)

    async def _generate_discussion_followup(
        self, topic: str, round_summary: str, next_round: int,
        has_conflict: bool = False, conflict_points: str = "",
    ) -> str:
        """다음 라운드 follow-up 질문 생성. LLM 실패 시 기본 문자열 반환."""
        if self._decision_client is None:
            if has_conflict and conflict_points:
                return f"[라운드 {next_round}] {topic} (충돌 포인트: {conflict_points})"
            return f"[라운드 {next_round}] {topic}"
        conflict_instruction = ""
        if has_conflict and conflict_points:
            conflict_instruction = (
                f"\n\n다음 의견 차이를 중심으로 반박하도록 유도하세요: {conflict_points[:200]}"
            )
        prompt = (
            f"토론 주제: {topic}\n"
            f"라운드 요약: {round_summary[:300]}\n\n"
            f"다음 라운드({next_round})를 위한 간결한 follow-up 질문을 한 문장으로 작성하세요. "
            f"판단이나 결론 없이 탐색적 질문만 사용하세요."
            f"{conflict_instruction}"
        )
        try:
            return await asyncio.wait_for(
                self._decision_client.complete(prompt), timeout=20.0,
            )
        except Exception as _e:
            logger.debug(f"[PM] follow-up 질문 생성 실패 (무시): {_e}")
            if has_conflict and conflict_points:
                return f"[라운드 {next_round}] {topic} (충돌 포인트: {conflict_points})"
            return f"[라운드 {next_round}] {topic}"

    async def _detect_discussion_conflict(self, perspectives: list[str]) -> tuple[bool, str]:
        """perspectives에서 의견 충돌 감지. LLM 우선, 실패 시 키워드 fallback.

        Returns:
            (has_conflict, conflict_points) — conflict_points는 충돌 요약 문자열 (없으면 "").
        """
        if not perspectives or len(perspectives) < 2:
            return False, ""

        _CONFLICT_KEYWORDS = [
            "반대", "다르다", "아니다", "하지만", "그러나", "반면",
            "disagree", "however", "but", "contrast", "oppose",
        ]

        # LLM 판단 시도
        if self._decision_client is not None:
            prompt = (
                "다음 의견들에서 명확한 의견 충돌(서로 상반된 주장)이 있는지 판단하세요.\n"
                + "\n".join(f"[{i+1}] {p[:200]}" for i, p in enumerate(perspectives))
                + "\n\n충돌이 있으면 'YES: [충돌 포인트 한 줄 요약]', 없으면 'NO'로만 답하세요."
            )
            try:
                answer = await asyncio.wait_for(
                    self._decision_client.complete(prompt), timeout=15.0,
                )
                lower = answer.lower()
                if lower.startswith("yes"):
                    conflict_points = ""
                    if ":" in answer:
                        conflict_points = answer.split(":", 1)[1].strip()
                    return True, conflict_points
                return False, ""
            except Exception as _e:
                logger.debug(f"[PM] conflict 감지 LLM 실패 (키워드 fallback): {_e}")

        # 키워드 fallback — 매칭된 키워드 주변 문맥 반환
        combined = " ".join(perspectives).lower()
        for kw in _CONFLICT_KEYWORDS:
            idx = combined.find(kw)
            if idx != -1:
                start = max(0, idx - 30)
                end = min(len(combined), idx + len(kw) + 60)
                snippet = combined[start:end].strip()
                return True, snippet
        return False, ""

    async def _detect_discussion_consensus(self, perspectives: list[str]) -> bool:
        """perspectives에서 합의/수렴 감지. LLM 우선, 실패 시 키워드 fallback.

        키워드 fallback: 명시적 합의 키워드가 있을 때만 True 반환.
        """
        if not perspectives or len(perspectives) < 2:
            return False

        _CONSENSUS_KEYWORDS = [
            "동의", "합의", "agreed", "맞아요", "동의합니다",
            "agree", "consensus", "맞습니다", "그렇습니다",
        ]

        # LLM 판단 시도
        if self._decision_client is not None:
            prompt = (
                "다음 의견들이 충분히 수렴(합의)되었는지 판단하세요.\n"
                + "\n".join(f"[{i+1}] {p[:200]}" for i, p in enumerate(perspectives))
                + "\n\n합의가 이루어졌으면 'YES', 아직 의견 차이가 있으면 'NO'로만 답하세요."
            )
            try:
                answer = await asyncio.wait_for(
                    self._decision_client.complete(prompt), timeout=15.0,
                )
                return "yes" in answer.lower()
            except Exception as _e:
                logger.debug(f"[PM] consensus 감지 LLM 실패 (키워드 fallback): {_e}")

        # 키워드 fallback — 명시적 합의 키워드가 있을 때만 True
        combined = " ".join(perspectives).lower()
        return any(kw in combined for kw in _CONSENSUS_KEYWORDS)

    async def _redispatch_discussion_round(
        self,
        parent_id: str,
        topic: str,
        participants: list[str],
        chat_id: int,
        current_round: int,
        max_rounds: int,
    ) -> None:
        """discussion 다음 라운드 서브태스크 재발행."""
        try:
            cfg = load_orchestration_config(force_reload=True)
            org_map = {org.id: org for org in cfg.list_orgs()}
        except Exception as _e:
            logger.warning(f"[PM] discussion round {current_round} org_map 로드 실패: {_e}")
            org_map = {}

        # 이전 라운드 발언 컨텍스트 수집 (라운드 2부터)
        prev_round_context = ""
        if current_round > 1:
            try:
                all_subtasks = await self._db.get_subtasks(parent_id)
                prev_utterances = [
                    f"- {KNOWN_DEPTS.get(st.get('assigned_dept', ''), st.get('assigned_dept', '?'))}: "
                    f"{(st.get('result') or '')[:300]}"
                    for st in all_subtasks
                    if st.get("metadata", {}).get("discussion_round") == current_round - 1
                    and st.get("status") == "done"
                    and st.get("result")
                ]
                if prev_utterances:
                    context_text = "\n".join(prev_utterances)
                    if len(context_text) > 2000:
                        context_text = context_text[:2000] + "..."
                    prev_round_context = f"[이전 라운드 발언]\n{context_text}\n\n"
            except Exception as _ctx_e:
                logger.debug(f"[PM] 이전 라운드 컨텍스트 조회 실패 (무시): {_ctx_e}")

        for bot_id in participants:
            org = org_map.get(bot_id)
            dept_name = org.dept_name if org else bot_id
            if prev_round_context:
                prompt = (
                    f"{prev_round_context}"
                    f"{topic}\n\n"
                    f"[자유 토론 라운드 {current_round}/{max_rounds}] 당신은 {dept_name}입니다. "
                    f"위 발언들을 참고하여, 동의/반박/보완할 점을 중심으로 의견을 나눠주세요."
                )
            else:
                prompt = (
                    f"{topic}\n\n"
                    f"[자유 토론 라운드 {current_round}/{max_rounds}] 당신은 {dept_name}입니다. "
                    f"이 주제에 대해 자유롭게 의견을 나눠주세요."
                )
            tid = await self._next_task_id()
            await self._db.create_pm_task(
                task_id=tid,
                description=prompt,
                assigned_dept=bot_id,
                created_by=self._org_id,
                parent_id=parent_id,
                metadata={
                    "interaction_mode": "discussion",
                    "discussion_topic": topic,
                    "discussion_round": current_round,
                },
            )
            await self._db.update_pm_task_status(tid, "assigned")
            dept_mention = self._org_mention(bot_id)
            try:
                await self._send(
                    chat_id,
                    f"{dept_mention} [PM_TASK:{tid}|dept:{bot_id}] "
                    f"토론 라운드 {current_round} 참여 요청: {prompt[:200]}",
                )
            except Exception as _e:
                logger.warning(f"[PM] discussion round {current_round} 태스크 {tid} 알림 실패: {_e}")
            logger.info(f"[PM] discussion 라운드 {current_round} 태스크 발송: {tid} → {bot_id}")

    async def _check_stale_subtasks(
        self, parent_id: str, stale_threshold_sec: float = 300.0,
    ) -> list[str]:
        """assigned 상태인 채로 threshold 이상 지난 서브태스크 ID 반환 + 경고 로그."""
        from datetime import datetime, UTC, timedelta
        try:
            subtasks = await self._db.get_subtasks(parent_id)
        except Exception as _e:
            logger.debug(f"[PM] stale check 실패 (무시): {_e}")
            return []

        stale_ids: list[str] = []
        cutoff = datetime.now(UTC) - timedelta(seconds=stale_threshold_sec)

        for st in subtasks:
            if st.get("status") != "assigned":
                continue
            updated_raw = st.get("updated_at") or st.get("created_at", "")
            if not updated_raw:
                continue
            try:
                updated = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=UTC)
                if updated < cutoff:
                    stale_ids.append(st["id"])
                    logger.warning(
                        f"[PM] stale 서브태스크 감지: {st['id']} "
                        f"(assigned {int((datetime.now(UTC) - updated).total_seconds())}초 전)"
                    )
            except (ValueError, TypeError):
                pass

        return stale_ids

    async def _synthesize_and_act(
        self,
        parent_task_id: str,
        subtasks: list[dict],
        chat_id: int,
        _skip_discussion_gate: bool = False,
    ) -> None:
        """부서 결과를 합성하고 판단에 따라 후속 조치.

        _skip_discussion_gate=True 는 _discussion_summarize 최종 라운드에서
        재귀 호출 없이 전체 synthesis를 수행할 때만 사용한다.
        """
        # 원래 요청 복원
        parent = await self._db.get_pm_task(parent_task_id)
        original_request = parent["description"][:500] if parent else ""

        parent_meta = parent.get("metadata", {}) if parent else {}
        # 스탈니스 체크 — assigned 상태로 오래된 서브태스크 경고
        stale = await self._check_stale_subtasks(parent_task_id)
        if stale:
            logger.warning(f"[PM] _synthesize_and_act {parent_task_id}: stale 서브태스크 {stale}")
        if parent_meta.get("debate"):
            await self._debate_synthesize(parent_task_id, parent_meta, subtasks, chat_id)
            return

        if parent_meta.get("interaction_mode") == "discussion" and not _skip_discussion_gate:
            await self._discussion_summarize(parent_task_id, subtasks, chat_id)
            return

        synthesis = await self._synthesizer.synthesize(original_request, subtasks)
        logger.info(
            f"[PM] 결과 합성: {parent_task_id} → {synthesis.judgment.value}"
        )
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

        # 첨부 파일 경로 수집: LLM 선별 우선, 없으면 정규식 fallback
        seen_paths: set[str] = set()
        subtask_artifact_markers = ""
        if synthesis.artifact_paths:
            # LLM이 사용자에게 보낼 파일을 직접 선별한 경우
            for path in synthesis.artifact_paths:
                if path not in seen_paths:
                    seen_paths.add(path)
                    subtask_artifact_markers += f"\n[ARTIFACT:{path}]"
        else:
            # fallback: subtask result에서 경로 자동 추출
            for st in subtasks:
                for path in extract_local_artifact_paths(st.get("result") or ""):
                    if path not in seen_paths:
                        seen_paths.add(path)
                        subtask_artifact_markers += f"\n[ARTIFACT:{path}]"

        # 사용자가 볼 수 있는 산출물 목록 (ARTIFACT 마커와 별도로 채팅에 표시)
        _extra_paths = [
            m.split("[ARTIFACT:")[1].rstrip("]")
            for m in subtask_artifact_markers.split("\n")
            if "[ARTIFACT:" in m
        ]
        _all_artifact_paths = [artifact_path] + _extra_paths
        _artifact_names = [Path(p).name for p in _all_artifact_paths if p]
        _artifact_list_note = (
            f"\n\n📎 첨부 산출물 ({len(_artifact_names)}개): "
            + ", ".join(f"`{n}`" for n in _artifact_names)
        ) if _artifact_names else ""

        if synthesis.judgment == SynthesisJudgment.SUFFICIENT:
            report = user_friendly_report
            await self._send(
                chat_id,
                f"✅ 모든 부서 작업 완료!\n\n{report}{_artifact_list_note}\n\n"
                f"통합 보고서를 첨부합니다.\n[ARTIFACT:{artifact_path}]{subtask_artifact_markers}",
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
                await self._db.update_pm_task_status(
                    parent_task_id, "done", result=report,
                )
                await self.dispatch(parent_task_id, follow_ups, chat_id)
            else:
                await self._db.update_pm_task_status(
                    parent_task_id, "done", result=report,
                )
        elif synthesis.judgment == SynthesisJudgment.INSUFFICIENT:
            rework_count = int(parent_meta.get("rework_count", 0))
            if run_id:
                try:
                    runbook.advance_phase(run_id, note="결과 부족으로 verification phase에서 추가 작업 필요")
                except Exception as e:
                    logger.warning(f"[PM] runbook 진행 실패 ({run_id}): {e}")
            if rework_count < MAX_REWORK_RETRIES:
                # 재작업 루프: parent는 "running" 유지 (done으로 마킹하지 않음)
                new_rework_count = rework_count + 1
                await self._db.update_pm_task_metadata(
                    parent_task_id, {"rework_count": new_rework_count}
                )
                await self._send(
                    chat_id,
                    f"⚠️ 결과 부족 — 추가 작업 배분 중... (재작업 {new_rework_count}/{MAX_REWORK_RETRIES})\n"
                    f"사유: {synthesis.reasoning}\n\n{user_friendly_report}\n\n"
                    f"현재까지의 통합 보고서를 첨부합니다.\n[ARTIFACT:{artifact_path}]{subtask_artifact_markers}",
                )
                if synthesis.follow_up_tasks:
                    follow_ups = [
                        SubTask(
                            description=ft["description"],
                            assigned_dept=ft["dept"],
                            workdir=parent_workdir,
                        )
                        for ft in synthesis.follow_up_tasks
                    ]
                else:
                    # LLM이 follow-up을 안 줬으면 완료된 서브태스크를 "보완 필요" 프롬프트로 재발행
                    follow_ups = [
                        SubTask(
                            description=(
                                f"[보완 필요] {st.get('metadata', {}).get('original_description', st.get('description', ''))}\n\n"
                                f"이전 결과가 충분하지 않습니다. 더 구체적이고 완성도 높은 결과를 제출해주세요.\n"
                                f"이전 결과 요약: {(st.get('result') or '')[:200]}"
                            ),
                            assigned_dept=st["assigned_dept"],
                            workdir=parent_workdir,
                        )
                        for st in subtasks
                        if st.get("assigned_dept") and st.get("status") == "done"
                    ]
                if follow_ups:
                    # parent를 "running" 상태로 유지한 채 follow-up 서브태스크 발행
                    await self.dispatch(parent_task_id, follow_ups, chat_id)
                else:
                    logger.warning(f"[PM] INSUFFICIENT retry {parent_task_id}: follow-up 없음, done 처리")
                    await self._db.update_pm_task_status(
                        parent_task_id, "done", result=synthesis.summary,
                    )
            else:
                # 최대 재시도 횟수 도달 — 최선의 결과로 done 처리
                await self._send(
                    chat_id,
                    f"⚠️ 자동 보완 한계 ({MAX_REWORK_RETRIES}회) 도달. 현재 최선의 결과를 전달합니다.\n\n"
                    f"{user_friendly_report}\n\n통합 보고서를 첨부합니다.\n[ARTIFACT:{artifact_path}]{subtask_artifact_markers}",
                )
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

    # ── Debate Dispatch ───────────────────────────────────────────────────

    def _select_debate_participants(self, dept_hints: list[str], topic: str) -> list[str]:
        """debate 참여 봇 목록 선정.

        dept_hints가 주어지면 최대 4개까지 그대로 사용.
        비어있으면 orchestration config에서 specialist + enabled 봇을 최대 4개 선택.
        최소 2개 미만이면 빈 리스트 반환 (debate 불가).
        """
        if dept_hints:
            selected = dept_hints[:4]
        else:
            try:
                cfg = load_orchestration_config(force_reload=True)
                selected = [org.id for org in cfg.list_specialist_orgs()][:4]
            except Exception as e:
                logger.warning(f"[PM] debate 참여자 조회 실패: {e}")
                selected = []

        if len(selected) < 2:
            logger.info(f"[PM] debate 참여자 부족 ({len(selected)}개) — debate 불가")
            return []
        return selected

    async def debate_dispatch(
        self,
        parent_task_id: str,
        topic: str,
        participants: list[str],
        chat_id: int,
    ) -> list[str]:
        """각 participant에게 독자적 관점의 debate 서브태스크를 생성·배정한다.

        Args:
            parent_task_id: 상위 태스크 ID.
            topic: debate 주제 (사용자 요청 원문).
            participants: 참여할 봇 ID 목록 (_select_debate_participants 결과).
            chat_id: 알림을 보낼 Telegram chat ID.

        Returns:
            생성된 subtask ID 목록. 참여자가 없으면 빈 리스트.
        """
        if not participants:
            logger.info("[PM] debate 참여자 없음 — debate_dispatch 건너뜀")
            return []

        # 봇 프로필 캐시 (dept_name, direction 조회용)
        try:
            cfg = load_orchestration_config(force_reload=True)
            org_map = {org.id: org for org in cfg.list_orgs()}
        except Exception as e:
            logger.warning(f"[PM] debate org_map 로드 실패: {e}")
            org_map = {}

        task_ids: list[str] = []
        for bot_id in participants:
            org = org_map.get(bot_id)
            dept_name = org.dept_name if org else bot_id
            direction = org.direction if org else ""

            prompt = (
                f"{topic}\n\n"
                f"[당신의 관점] 당신은 {dept_name}입니다. {direction}\n"
                f"다른 부서와 차별화된 {dept_name} 관점에서 의견을 제시하세요. "
                f"반드시 자신의 전문 영역과 가치관을 바탕으로 독자적인 입장을 표명하세요."
            )

            tid = await self._next_task_id()
            await self._db.create_pm_task(
                task_id=tid,
                description=prompt,
                assigned_dept=bot_id,
                created_by=self._org_id,
                parent_id=parent_task_id,
                metadata={
                    "debate": True,
                    "debate_topic": topic,
                    "debate_parent": parent_task_id,
                },
            )
            await self._db.update_pm_task_status(tid, "assigned")
            task_ids.append(tid)

            dept_mention = self._org_mention(bot_id)
            try:
                await self._send(
                    chat_id,
                    f"{dept_mention} [PM_TASK:{tid}|dept:{bot_id}] {dept_name} debate 배정: "
                    f"{prompt[:200]}",
                )
            except Exception as _e:
                logger.warning(f"[PM] debate 태스크 {tid} 알림 전송 실패: {_e}")
            logger.info(f"[PM] debate 태스크 발송: {tid} → {bot_id}")

        # 부모 태스크 metadata 업데이트
        await self._db.update_pm_task_metadata(
            parent_task_id,
            {"debate": True, "debate_topic": topic},
        )

        return task_ids

    async def collab_dispatch(
        self,
        parent_task_id: str,
        task: str,
        target_org: str,
        requester_org: str,
        context: str = "",
        chat_id: int = 0,
    ) -> str:
        """요청 봇이 지정한 target_org에 collab 서브태스크를 생성·배정한다.

        Args:
            parent_task_id: 상위 태스크 ID.
            task: 협업 요청 태스크 내용.
            target_org: 태스크를 수행할 조직 ID.
            requester_org: 협업을 요청한 조직 ID.
            context: 추가 컨텍스트 (선택).
            chat_id: 알림 Telegram chat ID (미사용, 향후 확장용).

        Returns:
            생성된 task_id 문자열.
        """
        try:
            cfg = load_orchestration_config(force_reload=True)
            org_map = {org.id: org for org in cfg.list_orgs()}
        except Exception as e:
            logger.warning(f"[PM] collab_dispatch org_map 로드 실패: {e}")
            org_map = {}

        org = org_map.get(target_org)
        dept_name = org.dept_name if org else target_org
        direction = org.direction if org else ""

        description_parts = [task]
        if context:
            description_parts.append(f"\n[요청 컨텍스트] {context}")
        if direction:
            description_parts.append(
                f"\n[{dept_name} 전문 영역] {direction}"
            )
        description = "".join(description_parts)

        task_id = await self._next_task_id()
        await self._db.create_pm_task(
            task_id=task_id,
            description=description,
            assigned_dept=target_org,
            created_by=requester_org,
            parent_id=parent_task_id,
            metadata={
                "collab": True,
                "collab_requester": requester_org,
                "parent_task_id": parent_task_id,
            },
        )
        logger.info(
            f"[PM] collab_dispatch: {requester_org} -> {target_org} | task_id={task_id}"
        )
        return task_id

    async def discussion_dispatch(
        self,
        topic: str,
        dept_hints: list[str],
        chat_id: int,
        rounds: int = 3,
    ) -> list[str]:
        """자유 토론 모드 — PM 약한 진행, 강제 결론 없음.

        debate_dispatch와 달리 관점 대립 유도 없이 자유 발언.
        부모 태스크를 내부에서 생성한다 (relay가 _db에 직접 접근 불필요).

        # TODO(cycle-6): 서브태스크 타임아웃/스탈니스 체커 추가.
        """
        participants = list(dict.fromkeys(dept_hints))[:4]
        if len(participants) < 2:
            try:
                cfg = load_orchestration_config(force_reload=True)
                participants = [o.id for o in cfg.list_specialist_orgs()][:4]
            except Exception as _e:
                logger.warning(f"[PM] discussion specialist org 로드 실패: {_e}")

        if len(participants) < 2:
            logger.info("[PM] discussion 참여자 부족 — discussion_dispatch 건너뜀")
            return []

        # 부모 태스크 내부 생성 (relay가 _db에 직접 접근 금지)
        parent_id = await self._next_task_id()
        await self._db.create_pm_task(
            task_id=parent_id,
            description=topic,
            assigned_dept=self._org_id,
            created_by=self._org_id,
            metadata={
                "interaction_mode": "discussion",
                "discussion_topic": topic,
                "discussion_rounds": rounds,
                "discussion_current_round": 1,
                "discussion_participants": participants,
            },
        )

        try:
            cfg = load_orchestration_config(force_reload=True)
            org_map = {org.id: org for org in cfg.list_orgs()}
        except Exception as e:
            logger.warning(f"[PM] discussion org_map 로드 실패: {e}")
            org_map = {}

        task_ids: list[str] = []
        for bot_id in participants:
            org = org_map.get(bot_id)
            dept_name = org.dept_name if org else bot_id

            prompt = (
                f"{topic}\n\n"
                f"[자유 토론] 당신은 {dept_name}입니다. "
                f"이 주제에 대해 자유롭게 의견을 나눠주세요."
            )

            tid = await self._next_task_id()
            await self._db.create_pm_task(
                task_id=tid,
                description=prompt,
                assigned_dept=bot_id,
                created_by=self._org_id,
                parent_id=parent_id,
                metadata={"interaction_mode": "discussion", "discussion_topic": topic, "discussion_round": 1},
            )
            await self._db.update_pm_task_status(tid, "assigned")
            task_ids.append(tid)

            dept_mention = self._org_mention(bot_id)
            try:
                await self._send(
                    chat_id,
                    f"{dept_mention} [PM_TASK:{tid}|dept:{bot_id}] "
                    f"토론 참여 요청: {prompt[:200]}",
                )
            except Exception as _e:
                logger.warning(f"[PM] discussion 태스크 {tid} 알림 실패: {_e}")
            logger.info(f"[PM] discussion 태스크 발송: {tid} → {bot_id}")

        return task_ids

    async def _handle_improve_status(self, chat_id: int) -> str:
        """자가개선 상태를 수집·평가하고 요약 메시지를 반환한다.

        ImprovementBus로 신호를 수집하고, EvalRunner로 스킬 평가 결과를 더해
        하나의 상태 요약 문자열을 만든다. 결과는 chat_id로 전송된다.

        Args:
            chat_id: 결과를 보낼 Telegram chat ID.

        Returns:
            전송된 상태 요약 문자열.
        """
        from core.improvement_bus import ImprovementBus
        from core.eval_runner import EvalRunner

        try:
            bus = ImprovementBus(dry_run=True)
            signals = bus.collect_signals()
            report = bus.run(signals)
            bus_text = bus.format_report(report)
        except Exception as e:
            logger.warning(f"[PM] ImprovementBus 오류: {e}")
            bus_text = f"[ImprovementBus 오류] {e}"

        try:
            runner = EvalRunner()
            eval_results = runner.score_all_skills()
            eval_text = runner.format_results(eval_results) if eval_results else "평가할 스킬 없음"
        except Exception as e:
            logger.warning(f"[PM] EvalRunner 오류: {e}")
            eval_text = f"[EvalRunner 오류] {e}"

        summary = f"{bus_text}\n\n{eval_text}"

        try:
            await self._send(chat_id, summary)
        except Exception as e:
            logger.warning(f"[PM] improve_status 전송 실패: {e}")

        return summary

    async def _handle_routing_approve(self, update, context) -> None:
        """대기 중인 라우팅 제안을 nl_classifier에 적용."""
        from core.routing_approval_store import RoutingApprovalStore
        from core.nl_keyword_applier import NLKeywordApplier
        store = RoutingApprovalStore()
        proposal = store.load_pending()
        if not proposal:
            await update.message.reply_text("대기 중인 라우팅 제안 없음.")
            return
        applier = NLKeywordApplier()
        result = applier.apply(proposal.get("keyword_additions", {}))
        store.clear()
        await update.message.reply_text(f"✅ 라우팅 키워드 적용 완료:\n{result}")

    async def _handle_routing_reject(self, update, context) -> None:
        """대기 중인 라우팅 제안을 거절하고 삭제."""
        from core.routing_approval_store import RoutingApprovalStore
        store = RoutingApprovalStore()
        store.clear()
        await update.message.reply_text("❌ 라우팅 제안 거절됨. 다음 분석 시까지 대기.")
