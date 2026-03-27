"""PM 오케스트레이터 — 사용자 요청을 부서별 태스크로 분해·배분."""
from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal

from loguru import logger

from core.claim_manager import ClaimManager
from core.constants import DEPT_INSTRUCTIONS, DEPT_ROLES, KNOWN_DEPTS
from core.context_db import ContextDB
from core.memory_manager import MemoryManager
from core.orchestration_config import load_orchestration_config
from core.orchestration_runbook import OrchestrationRunbook
from core.pm_decision import DecisionClientProtocol
from core.pm_identity import PMIdentity
from core.result_synthesizer import ResultSynthesizer, SynthesisJudgment, SynthesisResult
from core.staleness_checker import SUBTASK_TIMEOUT_SEC, StalenessChecker
from core.structured_prompt import StructuredPromptGenerator
from core.task_graph import TaskGraph
from core.pm_discussion_mixin import PMDiscussionMixin
from core.pm_synthesis_mixin import PMSynthesisMixin
from core.telegram_formatting import markdown_to_html
from core.telegram_user_guardrail import ensure_user_friendly_output, extract_local_artifact_paths

if TYPE_CHECKING:
    from core.discussion import DiscussionManager

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
    # LLM 자율 분류 (Step 0 판단 체인): 조사/분석/기획/설계/검토/수정/구현/운영
    task_type: str | None = None
    # 파일·코드 변경 허용 여부 (실행형=True, 사고형=False)
    allow_file_change: bool | None = None
    # 태스크 메타데이터 (회의 브로드캐스트·오케스트레이션 컨텍스트 전달용)
    expected_output: str = ""    # 예상 출력 형태/내용 힌트
    rationale: str = ""          # 이 태스크를 배분하는 이유
    priority: str = "medium"     # 우선순위: low | medium | high


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
            from datetime import UTC, datetime
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


# ── 2-pass 위임 판단 헬퍼 ────────────────────────────────────────────────────

def _infer_dept_from_text(text: str) -> str | None:
    """태스크 설명 텍스트에서 대상 부서를 키워드 매칭으로 추론한다.

    반환값은 KNOWN_DEPTS에 등록된 org_id 문자열이거나 None.
    """
    text_lower = text.lower()
    _DEPT_KEYWORDS: dict[str, list[str]] = {
        "aiorg_ops_bot": [
            "운영실", "운영", "배포", "deploy", "크론", "cron",
            "infra", "인프라", "모니터링", "watchdog", "ops",
            "restart", "재시작", "서버",
        ],
        "aiorg_engineering_bot": [
            "개발실", "개발", "코드", "code", "구현", "implement",
            "버그", "fix", "engineering", "api", "스크립트",
        ],
        "aiorg_design_bot": [
            "디자인실", "디자인", "design", "ui", "ux", "와이어프레임",
        ],
        "aiorg_product_bot": [
            "기획실", "기획", "product", "prd", "요구사항", "기능 정의",
        ],
        "aiorg_growth_bot": [
            "성장실", "성장", "growth", "마케팅", "marketing", "지표",
        ],
        "aiorg_research_bot": [
            "리서치실", "리서치", "research", "조사", "분석", "시장",
        ],
    }
    for dept, keywords in _DEPT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return dept
    return None


def should_delegate_further(
    synthesis: "SynthesisResult",
    report_text: str = "",
) -> list[dict]:
    """PM 합성 후 추가 위임이 필요한 태스크 목록을 반환한다 (2-pass 판단).

    기존 synthesis.follow_up_tasks (LLM FOLLOW_UP: 줄 파싱 결과)와
    보고서 본문 내 [COLLAB:...] 태그를 모두 수집하여 중복 없이 합산한다.

    COLLAB 태그 예시: "[COLLAB:크론 중복 삭제 후 단일 운영|맥락: daily_ai_news 중복]"
    → 태그 내 텍스트에서 대상 부서를 키워드로 추론.

    Args:
        synthesis: ResultSynthesizer.synthesize() 반환값
        report_text: PM 합성 보고서 텍스트 (COLLAB 태그 소스)

    Returns:
        [{"dept": org_id, "description": task_description}, ...] 리스트.
        빈 리스트 반환 시 추가 위임 불필요.
    """
    from core.collab_dispatcher import parse_collab_tags

    results: list[dict] = list(synthesis.follow_up_tasks)  # 기존 FOLLOW_UP 태스크
    seen_keys: set[tuple[str, str]] = {
        (ft["dept"], ft["description"][:80]) for ft in results
    }

    # 보고서 내 [COLLAB:...] 태그 파싱
    if report_text:
        collab_tags = parse_collab_tags(report_text)
        for tag in collab_tags:
            task_desc = tag["task"].strip()
            context_text = tag.get("context", "")
            # 대상 부서 추론: task + context 텍스트 합산
            combined = task_desc + " " + context_text
            target_dept = _infer_dept_from_text(combined)
            if not target_dept:
                logger.debug(
                    f"[PM 2-pass] COLLAB 태그 부서 추론 실패, skip: {task_desc[:60]}"
                )
                continue
            key = (target_dept, task_desc[:80])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            results.append({"dept": target_dept, "description": task_desc})
            logger.info(
                f"[PM 2-pass] COLLAB 태그 → 추가 위임 감지: "
                f"{target_dept} ← {task_desc[:60]}"
            )

    return results


def aggregate_results(
    first_pass_subtasks: list[dict],
    second_pass_subtasks: list[dict],
    original_request: str = "",
) -> str:
    """1차 + 2차 위임 결과를 합산 요약 문자열로 반환한다.

    ResultSynthesizer가 이미 모든 서브태스크를 통합 합성하므로
    이 함수는 주로 로깅·테스트·디버깅 목적으로 사용한다.

    Args:
        first_pass_subtasks:  1차 위임 완료 서브태스크 딕셔너리 목록
        second_pass_subtasks: 2차 추가 위임 완료 서브태스크 딕셔너리 목록
        original_request:    원본 사용자 요청 텍스트

    Returns:
        "[2-pass 결과 합산: 1차 N개 + 2차 M개]\\n..." 형식 요약 문자열
    """
    from core.constants import KNOWN_DEPTS

    lines: list[str] = [
        f"[2-pass 결과 합산: 1차 {len(first_pass_subtasks)}개 + 2차 {len(second_pass_subtasks)}개]"
    ]
    if original_request:
        lines.append(f"원본 요청: {original_request[:200]}")
    lines.append("")

    first_set: set[str] = {t.get("id", "") for t in first_pass_subtasks}
    all_tasks = first_pass_subtasks + second_pass_subtasks
    for task in all_tasks:
        dept = task.get("assigned_dept", "unknown")
        dept_name = KNOWN_DEPTS.get(dept, dept)
        result = (task.get("result") or "(결과 없음)").strip()[:300]
        pass_label = "1차" if task.get("id", "") in first_set else "2차"
        lines.append(f"[{pass_label} | {dept_name}]\n{result}")

    return "\n\n".join(lines)


class PMOrchestrator(PMDiscussionMixin, PMSynthesisMixin):
    """사용자 요청을 부서별 태스크로 분해하고 배분하는 오케스트레이터."""

    def __init__(
        self,
        context_db: ContextDB,
        task_graph: TaskGraph,
        claim_manager: ClaimManager,
        memory: MemoryManager,
        org_id: str,
        telegram_send_func: Callable[..., Awaitable[Any]],
        discussion_manager: DiscussionManager | None = None,
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
        # NOTE: start()는 _post_init에서 호출 — __init__ 시점에는 이벤트 루프가 없음
        # COLLAB 자동 트리거 dedup 캐시
        # key: (source_task_id, target_dept) → 마지막 트리거 발동 시각 (monotonic seconds)
        self._collab_dedup: dict[tuple[str, str], float] = {}

    @property
    def decision_client(self) -> DecisionClientProtocol | None:
        return self._decision_client

    async def plan_request(
        self,
        user_message: str,
        *,
        prior_context: str = "",
    ) -> RequestPlan:
        """유저 요청을 직접 답변/PM 직접 실행/조직 위임 중 어디로 보낼지 결정한다.

        Args:
            user_message: 현재 사용자 메시지.
            prior_context: format_history_for_prompt() 가 반환한 [CONTEXT]...[/CONTEXT] 문자열.
                           비어 있으면 기존 동작(단일 메시지)으로 graceful fallback.
        """
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
        result = await self._llm_unified_classify(
            user_message, dept_hints, workdir=workdir, prior_context=prior_context
        )
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

    def _build_request_plan_prompt(
        self,
        message: str,
        dept_hints: list[str],
        prior_context: str = "",
    ) -> str:
        dept_profiles = self._dept_profiles()
        dept_lines = "\n".join(
            f"- {dept} ({dept_profiles.get(dept, {}).get('dept_name', dept)}): {dept_profiles.get(dept, {}).get('role', '')}"
            for dept in dept_hints
        ) or "- currently no obvious specialist hints"
        context_block = f"{prior_context}\n\n" if prior_context else ""
        return (
            "You are the chief PM for a Telegram-based AI organization.\n"
            "Decide the lightest correct handling strategy for the user request.\n\n"
            "Available routes:\n"
            '- "direct_reply": answer or clarify directly. No execution or delegation.\n'
            '- "local_execution": the PM should handle it like a single coding agent.\n'
            '- "delegate": coordinate one or more specialist organizations.\n\n'
            "Choose direct_reply for simple questions, confirmations, status checks, and lightweight explanations.\n"
            "Choose local_execution ONLY for simple single-step tasks that a PM can do alone (e.g. rename a file, quick config change). If the task involves code changes, system improvements, analysis, or multiple steps, choose delegate.\n"
            "Choose delegate only when multi-discipline collaboration, explicit planning/brainstorming, or longer multi-step execution is needed.\n\n"
            "Department hints:\n"
            f"{dept_lines}\n\n"
            "Return JSON only in this exact shape:\n"
            '{"route":"direct_reply|local_execution|delegate","complexity":"low|medium|high","rationale":"short reason","confidence":0.0}\n\n'
            f"{context_block}"
            f"User request: {message[:700]}"
        )

    async def _llm_unified_classify(
        self,
        user_message: str,
        dept_hints: list[str],
        *,
        workdir: str | None = None,
        prior_context: str = "",
    ) -> "RequestPlan":
        """lane + route + complexity를 단일 LLM 호출로 처리. 실패 시 heuristic fallback."""
        if self._decision_client is None:
            return self._heuristic_unified_classify(user_message, dept_hints)

        dept_list = ", ".join(dept_hints) if dept_hints else "없음"
        context_block = f"{prior_context}\n\n" if prior_context else ""
        prompt = (
            "Classify the following user request and return JSON only.\n"
            "Fields:\n"
            '  lane: one of [clarify, direct_answer, review_or_audit, attachment_analysis, single_org_execution, multi_org_execution, debate]\n'
            '    - debate: 여러 부서의 상충하는 관점을 수집하고 토론. 비교/찬반/토론/A vs B 요청에 사용.\n'
            '  route: one of [direct_reply, local_execution, delegate]\n'
            '  complexity: one of [low, medium, high]\n'
            '  rationale: brief Korean explanation (max 30 chars)\n\n'
            f"dept_hints: {dept_list}\n"
            f"{context_block}"
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

            # local_execution이지만 실제로는 여러 부서 협업이 필요한 경우 delegate로 강제 전환
            if route == "local_execution" and (
                lane == "multi_org_execution"
                or len(dept_hints) >= 2
                or data.get("complexity") == "high"
            ):
                route = "delegate"
                logger.info(
                    f"[PM] local_execution → delegate 강제 전환 "
                    f"(lane={lane}, depts={len(dept_hints)}, complexity={data.get('complexity')})"
                )

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

        # 코딩 요청이면 PM 직접 처리 대신 engineering에 위임
        if self._has_coding_request(text):
            if "aiorg_engineering_bot" not in dept_hints:
                dept_hints = ["aiorg_engineering_bot"] + dept_hints
            return RequestPlan(
                lane="single_org_execution",
                route="delegate",
                complexity="medium",
                rationale="코딩 요청이라 전문 조직에 위임합니다.",
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
            f"DEPT:<org_id>|TASK:specific task description|DEPENDS:comma-separated indices or none"
            f"|TASK_TYPE:<type>|FILE_CHANGE:<yes|no>\n\n"
            f"TASK_TYPE classification (decide autonomously per subtask using this chain):\n"
            f"  Q1. What is the final output?\n"
            f"    - code/file/config/DB change → execution group (구현/수정/운영)\n"
            f"    - document/report/analysis/plan → thinking group (조사/분석/기획/설계/검토)\n"
            f"  Q2. Core verb of the instruction?\n"
            f"    만들어/구현/개발  → 구현  (FILE_CHANGE=yes)\n"
            f"    수정/바꿔/개선   → 수정  (FILE_CHANGE=yes)\n"
            f"    배포/인프라/재시작 → 운영  (FILE_CHANGE=yes)\n"
            f"    조사/알아봐/찾아봐 → 조사  (FILE_CHANGE=no)\n"
            f"    분석/비교/평가    → 분석  (FILE_CHANGE=no)\n"
            f"    기획/PRD/요구사항 → 기획  (FILE_CHANGE=no)\n"
            f"    설계/아키텍처    → 설계  (FILE_CHANGE=no)\n"
            f"    봐줘/검토/리뷰   → 검토  (FILE_CHANGE=no)\n"
            f"  Q3. Confidence < 60%? → default to 분석 (FILE_CHANGE=no)\n"
            f"FILE_CHANGE: yes only for 구현/수정/운영. All thinking-group types = no.\n\n"
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
            f"⏱ TIMEOUT CONSTRAINT (CRITICAL):\n"
            f"- Each subtask has a {int(SUBTASK_TIMEOUT_SEC)}s timeout. Tasks exceeding this are auto-failed.\n"
            f"- For complex work (multi-phase implementation, large refactoring), split into MULTIPLE sequential subtasks for the SAME department.\n"
            f"  Example: instead of one big '3-phase implementation' task, create:\n"
            f"    DEPT:engineering|TASK:Phase 1 — 설계 및 인터페이스 정의|DEPENDS:none\n"
            f"    DEPT:engineering|TASK:Phase 2 — 핵심 로직 구현|DEPENDS:0\n"
            f"    DEPT:engineering|TASK:Phase 3 — 테스트 및 검증|DEPENDS:1\n"
            f"- Each subtask's TASK description should contain only 1-2 phases (≤{int(SUBTASK_TIMEOUT_SEC // 60)} minutes of work).\n"
            f"- A single subtask with 3+ '=== Phase ===' sections is likely to timeout. Split it.\n\n"
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

    # workdir로 사용하면 안 되는 경로 (에이전트 프롬프트 등에서 오염)
    _WORKDIR_BLOCKLIST = {
        str(Path.home() / ".claude"),
        str(Path.home() / ".claude" / "agents"),
        str(Path.home() / ".ai-org" / "agents"),
        str(Path.home() / ".ai-org"),
    }

    @staticmethod
    def _extract_workdir(user_message: str) -> str | None:
        for raw in re.findall(r"(?:(?<=\s)|^)(~?/[^ \t\r\n'\"`]+)", user_message):
            candidate = Path(raw).expanduser()
            if not candidate.exists():
                continue
            target = candidate if candidate.is_dir() else candidate.parent
            target_str = str(target.resolve())
            if any(target_str.startswith(blocked) for blocked in PMOrchestrator._WORKDIR_BLOCKLIST):
                continue
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

    # 유효한 태스크 유형 8종 (Step 0 판단 체인 기준)
    _VALID_TASK_TYPES = frozenset(["조사", "분석", "기획", "설계", "검토", "수정", "구현", "운영"])
    # 파일 변경이 허용되는 실행형 유형
    _EXECUTION_TYPES = frozenset(["구현", "수정", "운영"])

    @staticmethod
    def _parse_decompose(response: str) -> list[SubTask]:
        """LLM 분해 응답 파싱.

        형식: DEPT:aiorg_xxx_bot|TASK:description|DEPENDS:0,1|TASK_TYPE:분석|FILE_CHANGE:no
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
            task_type_raw = parts.get("TASK_TYPE", "").strip()
            file_change_raw = parts.get("FILE_CHANGE", "").strip().lower()

            if not dept or dept not in known_depts or not task_desc:
                continue

            deps: list[str] = []
            if depends_str and depends_str != "none":
                deps = [d.strip() for d in depends_str.split(",") if d.strip().isdigit()]

            # TASK_TYPE 검증 — 유효하지 않으면 None (렌더링 시 표시 생략)
            task_type: str | None = task_type_raw if task_type_raw in PMOrchestrator._VALID_TASK_TYPES else None

            # FILE_CHANGE 결정: LLM 응답 우선, 없으면 task_type에서 자동 결정
            if file_change_raw in ("yes", "no"):
                allow_file_change: bool | None = file_change_raw == "yes"
            elif task_type is not None:
                allow_file_change = task_type in PMOrchestrator._EXECUTION_TYPES
            else:
                allow_file_change = None

            subtasks.append(SubTask(
                description=task_desc,
                assigned_dept=dept,
                depends_on=deps,
                task_type=task_type,
                allow_file_change=allow_file_change,
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
            type_badge = f" [{st.task_type}]" if st.task_type else ""
            file_badge = ""
            if st.allow_file_change is True:
                file_badge = " 📝파일변경O"
            elif st.allow_file_change is False:
                file_badge = " 🔍파일변경X"
            lines.append(f"{i+1}. {dept_mention} **{dept_name}**{type_badge}{file_badge}: {desc_short}{deps}")
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
            "---",
            "",
            "## 부록: 조직 원문 (참고용 — 최종 전달본과 중복될 수 있음)",
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
            # 부모 태스크가 deps에 포함되면 제거 — 부모 완료는 _synthesize_and_act가 관리
            deps = [d for d in deps if d != parent_task_id]
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
                task_type=st.task_type,
                allow_file_change=st.allow_file_change,
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
                    **({"task_type": st.task_type} if st.task_type else {}),
                    **({"allow_file_change": st.allow_file_change} if st.allow_file_change is not None else {}),
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
                task_meta = task.get("metadata") or {}
                _task_type = task_meta.get("task_type", "")
                _allow_fc = task_meta.get("allow_file_change")
                _type_line = f"\n태스크 유형: {_task_type}" if _task_type else ""
                _fc_line = f"\n파일·코드 변경 허용: {'예' if _allow_fc else '아니오'}" if _allow_fc is not None else ""
                msg = (
                    f"{prefix}[PM_TASK:{tid}|dept:{dept}] {dept_name}에 배정"
                    f"{_type_line}{_fc_line}\n{task['description'][:300]}"
                )
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

        # 4. 부모 태스크 상태를 running으로 전환
        # PM이 하위 태스크 결과를 수집·합성 대기 중임을 의미.
        # 완료는 _synthesize_and_act가 all_done 시점에 처리한다.
        if parent_task and parent_task.get("status") != "running":
            await self._db.update_pm_task_status(parent_task_id, "running")
            logger.info(f"[PM] 부모 태스크 {parent_task_id} → running (하위 {len(task_ids)}개 디스패치 완료)")

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
                task_meta = task.get("metadata") or {}
                _task_type = task_meta.get("task_type", "")
                _allow_fc = task_meta.get("allow_file_change")
                _type_line = f"\n태스크 유형: {_task_type}" if _task_type else ""
                _fc_line = f"\n파일·코드 변경 허용: {'예' if _allow_fc else '아니오'}" if _allow_fc is not None else ""
                msg = (
                    f"{prefix}[PM_TASK:{tid}|dept:{dept}] {dept_name}에 배정"
                    f"{_type_line}{_fc_line}\n{task['description'][:300]}"
                )
                await self._db.update_pm_task_status(tid, "assigned")
                try:
                    await self._send(
                        chat_id,
                        msg,
                        reply_to_message_id=self._reply_message_id(task.get("metadata")),
                    )
                except Exception as _e:
                    logger.warning(f"[PM] 태스크 {tid} 알림 전송 실패 (태스크는 assigned 상태): {_e}")

        # ── COLLAB 자동 트리거 ────────────────────────────────────────────────────
        # orchestration.yaml collab_triggers 기반으로 완료된 태스크의 부서+task_type을
        # 확인해 매칭 트리거를 발동, 크로스팀 후속 태스크를 자동 생성한다.
        await self._fire_collab_triggers(task_id, result, chat_id)

        # 모든 서브태스크가 terminal 상태(done/failed/cancelled)인지 확인 후 합성
        # 기존: all done 체크 → 실패 서브태스크가 있으면 합성 미트리거 (부모 stuck 버그) → 수정
        _TERMINAL = {"done", "failed", "cancelled"}
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
                        s["status"] in _TERMINAL for s in round_siblings
                    )
                else:
                    all_done = bool(siblings) and all(s["status"] in _TERMINAL for s in siblings)
            else:
                all_done = bool(siblings) and all(s["status"] in _TERMINAL for s in siblings)
            if all_done:
                await self._synthesize_and_act(parent_id, siblings, chat_id)
            else:
                await self._send(chat_id, await self.build_status_snapshot(parent_id))


    async def _handle_improve_status(self, chat_id: int) -> str:
        """자가개선 상태를 수집·평가하고 요약 메시지를 반환한다.

        ImprovementBus로 신호를 수집하고, EvalRunner로 스킬 평가 결과를 더해
        하나의 상태 요약 문자열을 만든다. 결과는 chat_id로 전송된다.

        Args:
            chat_id: 결과를 보낼 Telegram chat ID.

        Returns:
            전송된 상태 요약 문자열.
        """
        from core.eval_runner import EvalRunner
        from core.improvement_bus import ImprovementBus

        try:
            bus = ImprovementBus(dry_run=False)
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
        from core.nl_keyword_applier import NLKeywordApplier
        from core.routing_approval_store import RoutingApprovalStore
        store = RoutingApprovalStore()
        proposal = store.load_pending()
        if not proposal:
            await update.message.reply_text("대기 중인 라우팅 제안 없음.", parse_mode="HTML")
            return
        applier = NLKeywordApplier()
        result = applier.apply(proposal.get("keyword_additions", {}))
        store.clear()
        await update.message.reply_text(
            markdown_to_html(f"✅ 라우팅 키워드 적용 완료:\n{result}"),
            parse_mode="HTML",
        )

    async def _handle_routing_reject(self, update, context) -> None:
        """대기 중인 라우팅 제안을 거절하고 삭제."""
        from core.routing_approval_store import RoutingApprovalStore
        store = RoutingApprovalStore()
        store.clear()
        await update.message.reply_text("❌ 라우팅 제안 거절됨. 다음 분석 시까지 대기.", parse_mode="HTML")
