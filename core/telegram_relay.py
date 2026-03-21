"""텔레그램 ↔ tmux Claude Code 세션 중계 — 얇은 relay 레이어.

Python봇의 역할: 메시지 수신 → session_manager.send_message() → 응답 전송.
무거운 로직은 tmux 세션 안의 Claude Code가 처리.
자율 라우팅: confidence scoring + 파일 기반 claim으로 가장 적합한 PM이 담당.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import time
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger
from telegram import Update
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from core.message_bus import MessageBus, Event, EventType
from core.session_manager import SessionManager
from core.memory_manager import MemoryManager
from core.pm_identity import PMIdentity
from core.claim_manager import ClaimManager
from core.confidence_scorer import ConfidenceScorer
from core.session_store import SessionStore
from core.global_context import GlobalContext
from core.collab_request import (
    is_collab_request, make_collab_request_v2, make_collab_claim,
    make_collab_done, parse_collab_request, is_placeholder_collab,
)
from core.display_limiter import DisplayLimiter
from core.nl_classifier import NLClassifier, Intent
from core.pm_router import PMRouter
from core.pm_orchestrator import ENABLE_PM_ORCHESTRATOR, KNOWN_DEPTS
from core.orchestration_config import load_orchestration_config
from core.orchestration_runbook import OrchestrationRunbook
from core.attachment_manager import AttachmentContext, AttachmentBundle
from core.attachment_analysis import AttachmentAnalyzer
from core.artifact_pipeline import prepare_upload_bundle
from core.builtin_surfaces import recommend_builtin_surfaces
from core.telegram_delivery import resolve_delivery_target
from core.telegram_user_guardrail import (
    ensure_user_friendly_output,
    extract_local_artifact_paths,
)
from core.session_registry import SessionRegistry
from core.message_envelope import MessageEnvelope, EnvelopeManager
from core.p2p_messenger import P2PMessenger
from core.discussion_parser import is_discussion_message, parse_discussion_tags
from core.discussion import ENABLE_DISCUSSION_PROTOCOL
from core.dispatch_engine import ENABLE_AUTO_DISPATCH
from core.verification import ENABLE_CROSS_VERIFICATION
from core.goal_tracker import ENABLE_GOAL_TRACKER
from core.task_poller import TaskPoller
from core.telegram_formatting import split_message
from core.setup_registration import (
    default_identity_for_org,
    parse_setup_identity,
    refresh_legacy_bot_configs,
    refresh_pm_identity_files,
    upsert_org_in_canonical_config,
    upsert_runtime_env_var,
)

TEAM_ID = "pm"  # aiorg_pm tmux 세션
DEFAULT_CONFIDENCE_THRESHOLD = 5  # 이 점수 미만이면 다른 PM에게 양보
USE_NL_CLASSIFIER = True  # 2-tier NLClassifier 활성화 플래그 (False 시 기존 키워드 로직 사용)
ARTIFACT_MARKER_RE = re.compile(r"\[ARTIFACT:([^\]]+)\]")
PM_CHAT_REPLY_TIMEOUT_SEC = int(os.environ.get("PM_CHAT_REPLY_TIMEOUT_SEC", "120"))

# /setup 마법사 ConversationHandler 상태
SETUP_MENU, SETUP_AWAIT_TOKEN, SETUP_AWAIT_ENGINE, SETUP_AWAIT_IDENTITY = range(4)
ATTACHMENT_GROUP_DEBOUNCE_SEC = 1.2


@dataclass
class _AttachmentGroupState:
    items: list[AttachmentContext] = field(default_factory=list)
    caption: str = ""
    message: object | None = None
    task: asyncio.Task | None = None


class TelegramRelay:
    """텔레그램 ↔ tmux Claude Code 세션 중계만 담당."""

    def __init__(
        self,
        token: str,
        allowed_chat_id: int,
        session_manager: SessionManager,
        memory_manager: MemoryManager,
        org_id: str = "global",
        engine: str = "claude-code",
        bus: MessageBus | None = None,
        context_db: "ContextDB | None" = None,
    ) -> None:
        self.token = token
        self.allowed_chat_id = allowed_chat_id
        self.session_manager = session_manager
        self.memory_manager = memory_manager
        self.org_id = org_id
        self.engine = engine
        self.bus = bus
        self.context_db = context_db
        self.app: Application | None = None

        # ContextDB를 MemoryManager에 주입 — BM25가 conversation_messages까지 검색
        if context_db is not None:
            self.memory_manager._context_db = context_db
        self._message_count: int = 0

        # 자율 라우팅 컴포넌트
        self.identity = PMIdentity(org_id)
        self.identity.load()
        from core.dynamic_team_builder import DynamicTeamBuilder
        self._team_builder = DynamicTeamBuilder()
        self.claim_manager = ClaimManager()
        self.confidence_scorer = ConfidenceScorer()
        self._start_time = time.time()  # 봇 시작 시각 — 이전 메시지 무시용

        # Claude Code 세션 영속화 (--resume으로 대화 맥락 유지)
        self.session_store = SessionStore(org_id)

        # PM 집단 기억 — PM 간 맥락 공유
        self.global_context = GlobalContext()
        self._attachment_analyzer = AttachmentAnalyzer()

        self.display = DisplayLimiter(
            debounce_sec=5.0,
            enabled=os.getenv("USE_DISPLAY_LIMITER", "true").lower() == "true",
        )
        self._nl_classifier = NLClassifier()
        self._attachment_groups: dict[tuple[int, str], _AttachmentGroupState] = {}

        # PM 오케스트레이터 모드 — ENABLE_PM_ORCHESTRATOR + context_db 필요
        self._pm_orchestrator = None
        self._synthesizing: set = set()  # 합성 중복 방지 (이벤트 드리븐 + 폴러 공유)
        self._collab_injecting: set[str] = set()
        self._uploaded_artifacts: set[str] = set()  # 중복 파일 업로드 방지
        self._pending_confirmation: dict = {}  # {chat_id: {action, task_ids, expires}}
        self._is_pm_org = ENABLE_PM_ORCHESTRATOR and org_id not in KNOWN_DEPTS
        self._is_dept_org = ENABLE_PM_ORCHESTRATOR and org_id in KNOWN_DEPTS
        self._pm_decision_client = None
        if self._is_pm_org or self._is_dept_org:
            from core.pm_decision import PMDecisionClient
            # Decision client는 메인 실행 세션과 분리된 전용 세션 사용
            # (동일 세션 공유 시 동시 --resume 충돌로 code=1 발생)
            _decision_session_store = SessionStore(f"{org_id}_decision")
            _raw_decision_client = PMDecisionClient(
                org_id=org_id,
                engine=self.engine,
                session_store=_decision_session_store,
            )
            # LLMCostTracker로 래핑 — 비용 추적 + circuit breaker
            from core.llm_cost_tracker import LLMCostTracker as _LLMCostTracker
            self._pm_decision_client = _LLMCostTracker(
                wrapped=_raw_decision_client,
                send_func=self._send_message if hasattr(self, "_send_message") else None,
                chat_id=self.chat_id if hasattr(self, "chat_id") else None,
            )
            self._team_builder.set_decision_client(self._pm_decision_client)
            if self._is_pm_org:
                self.global_context.set_decision_client(self._pm_decision_client)
        self._router = PMRouter(decision_client=self._pm_decision_client)
        # P2P 봇 간 직접 통신
        self._p2p = P2PMessenger(bus=self.bus)
        if self._is_pm_org and context_db is not None:
            from core.task_graph import TaskGraph
            from core.pm_orchestrator import PMOrchestrator
            self._pm_orchestrator = PMOrchestrator(
                context_db=context_db,
                task_graph=TaskGraph(context_db),
                claim_manager=self.claim_manager,
                memory=self.memory_manager,
                org_id=org_id,
                telegram_send_func=self._pm_send_message,
                decision_client=self._pm_decision_client,
            )

        # Discussion Protocol — ENABLE_DISCUSSION_PROTOCOL + context_db 필요
        self._discussion_manager = None
        if ENABLE_DISCUSSION_PROTOCOL and context_db is not None:
            from core.discussion import DiscussionManager
            self._discussion_manager = DiscussionManager(
                context_db=context_db,
                telegram_send_func=self._pm_send_message,
                bus=self.bus,
                org_id=org_id,
            )
            # PM 오케스트레이터에 토론 매니저 연결
            if self._pm_orchestrator is not None:
                self._pm_orchestrator._discussion = self._discussion_manager

        # Auto-Dispatch 엔진 — ENABLE_AUTO_DISPATCH + PM org + context_db 필요
        self._dispatch_engine = None
        if ENABLE_AUTO_DISPATCH and self._is_pm_org and context_db is not None:
            from core.dispatch_engine import DispatchEngine
            from core.task_graph import TaskGraph
            tg = self._pm_orchestrator._graph if self._pm_orchestrator else TaskGraph(context_db)
            self._dispatch_engine = DispatchEngine(
                context_db=context_db,
                task_graph=tg,
                telegram_send_func=self._pm_send_message,
            )

        # Cross-Model Verification — ENABLE_CROSS_VERIFICATION + PM org + context_db 필요
        self._verifier = None
        if ENABLE_CROSS_VERIFICATION and self._is_pm_org and context_db is not None:
            from core.verification import CrossModelVerifier
            self._verifier = CrossModelVerifier(
                context_db=context_db,
                telegram_send_func=self._pm_send_message,
            )

        # GoalTracker — ENABLE_GOAL_TRACKER + PM org + context_db + orchestrator 필요
        self._goal_tracker = None
        if ENABLE_GOAL_TRACKER and self._is_pm_org and context_db is not None and self._pm_orchestrator is not None:
            from core.goal_tracker import GoalTracker
            self._goal_tracker = GoalTracker(
                context_db=context_db,
                orchestrator=self._pm_orchestrator,
                telegram_send_func=self._pm_send_message,
                org_id=org_id,
            )

        # TaskPoller — 부서 봇이 ContextDB를 폴링하여 PM 배정 태스크 수신
        self._task_poller: TaskPoller | None = None
        if self._is_dept_org and context_db is not None:
            self._task_poller = TaskPoller(
                context_db=context_db,
                org_id=org_id,
                on_task=self._execute_polled_task,
            )

        # OrgScheduler — pm_bot 내장 스케줄러 (회의·회고 자율 실행)
        self._org_scheduler = None
        self._schedule_store = None
        self._nl_parser = None
        if self._is_pm_org:
            from core.scheduler import OrgScheduler
            from core.user_schedule_store import UserScheduleStore
            from core.nl_schedule_parser import NLScheduleParser

            async def _sched_send(text: str) -> None:
                await self._pm_send_message(self.allowed_chat_id, text)

            self._org_scheduler = OrgScheduler(send_text=_sched_send)
            self._schedule_store = UserScheduleStore()
            self._nl_parser = NLScheduleParser()
            self._org_scheduler.load_user_schedules(self._schedule_store)

        # WarmSessionPool — 엔진 타입에 맞게 세션/러너 예열
        from core.session_manager import WarmSessionPool
        self._warm_pool = WarmSessionPool(
            session_manager=self.session_manager,
            org_id=org_id,
            engine=self.engine,
        )

    async def _pm_send_message(
        self,
        chat_id: int,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> object | None:
        """PMOrchestrator용 텔레그램 메시지 발송 콜백.

        4000자 초과 메시지는 split_message로 분할 전송.
        """
        if self.app and self.app.bot:
            raw = ARTIFACT_MARKER_RE.sub("", text).strip() or "첨부 파일을 전송합니다."
            env = MessageEnvelope.wrap(content=raw, sender_bot=self.org_id, intent="DIRECT_REPLY")
            visible_text = env.to_display()
            sent = None
            first = True
            for chunk in split_message(visible_text, 4000):
                sent = await self.display.send_to_chat(
                    self.app.bot,
                    chat_id,
                    chunk,
                    reply_to_message_id=reply_to_message_id if first else None,
                )
                first = False
            if sent is not None and self.context_db is not None:
                mgr = EnvelopeManager(self.context_db)
                await mgr.save(sent.message_id, env)
            await self._auto_upload(text, self.token, chat_id)
            return sent
        return None

    def _make_runner(self):
        """engine 설정에 따라 적합한 runner를 반환한다."""
        from tools.base_runner import RunnerFactory, RunContext  # noqa: F401
        return RunnerFactory.create(self.engine)

    @staticmethod
    def _make_claude_runner():
        from tools.base_runner import RunnerFactory
        return RunnerFactory.create("claude-code")

    @staticmethod
    def _make_codex_runner():
        from tools.base_runner import RunnerFactory
        return RunnerFactory.create("codex")

    async def _build_pm_db_context(self) -> str:
        """진행 중인 PM 태스크를 짧은 컨텍스트 문자열로 만든다."""
        if self._pm_orchestrator is None or self.context_db is None:
            return ""
        try:
            import aiosqlite as _sq
            async with _sq.connect(self.context_db.db_path) as _db:
                _db.row_factory = _sq.Row
                cur = await _db.execute(
                    "SELECT id, assigned_dept, status, description FROM pm_tasks "
                    "WHERE status NOT IN ('done','failed') ORDER BY created_at DESC LIMIT 10"
                )
                rows = await cur.fetchall()
            if not rows:
                return ""
            lines = [
                f"- {r['id']} [{r['assigned_dept']}] {r['status']}: {r['description'][:60]}"
                for r in rows
            ]
            return "\n\n현재 진행 중인 태스크:\n" + "\n".join(lines)
        except Exception:
            return ""

    @staticmethod
    def _build_user_expectations(text: str) -> list[str]:
        lower = text.lower()
        expectations = [
            "첫 문단에서 사용자의 질문이나 불만에 직접 답한다.",
            "파일 경로·링크·문서 위치만 나열하지 말고 핵심 내용을 먼저 설명한다.",
            "확인한 내용, 바뀐 점, 다음 조치를 구체적으로 적는다.",
            "응답이 길어지면 결론, 핵심 변경점, 첨부 안내 순으로 정리한다.",
        ]
        if any(token in lower for token in ("불친절", "친절", "불편")):
            expectations.append("톤은 정중하고 협업적으로 유지하되, 모호한 표현은 줄인다.")
        if "요약" in text:
            expectations.append("요약은 결론, 근거, 남은 이슈를 포함하고 위치 안내만으로 끝내지 않는다.")
        if any(token in lower for token in ("반응이 없", "응답이 없", "무응답", "대답이 없")):
            expectations.append("무응답이 있었다면 원인과 복구 상태를 분명히 설명한다.")
        if any(token in lower for token in ("첨부", "파일", "md", "슬라이드", "이미지")):
            expectations.append("필요한 산출물이나 첨부 여부를 답변 본문에서 먼저 안내한다.")
        deduped: list[str] = []
        for item in expectations:
            if item not in deduped:
                deduped.append(item)
        return deduped[:6]

    def _telegram_verbosity(self) -> int:
        try:
            return self.session_store.get_telegram_verbosity()
        except Exception:
            return 1

    def _progress_interval(self, *, delegated: bool = False) -> float:
        level = self._telegram_verbosity()
        if level <= 0:
            return float("inf")
        if delegated:
            return 2.0 if level >= 2 else float("inf")
        return 0.9 if level >= 2 else 1.5

    def _progress_history_limit(self, *, delegated: bool = False) -> int:
        level = self._telegram_verbosity()
        if delegated:
            return 4 if level >= 2 else 0
        return 6 if level >= 2 else 4

    def _show_progress(self, *, delegated: bool = False) -> bool:
        level = self._telegram_verbosity()
        if level <= 0:
            return False
        if delegated and level < 2:
            return False
        return True

    async def _build_conversation_context_packet(
        self,
        text: str,
        replied_context: str = "",
        db_context: str = "",
    ) -> str:
        sections = [f"## 최신 사용자 요청\n{text[:700]}"]
        if replied_context:
            sections.append(f"## 답장 대상 맥락\n{replied_context[:500]}")

        expectations = self._build_user_expectations(text)
        if expectations:
            sections.append(
                "## 이번 응답에서 꼭 만족할 점\n" + "\n".join(f"- {item}" for item in expectations)
            )

        # BM25 통합 검색 (LOG + conversation_messages)
        memory_context = ""
        try:
            memory_results = await self.memory_manager.search_memories(
                query=text, user_id="global", top_k=5
            )
            if memory_results:
                memory_context = "\n".join(memory_results)
            else:
                memory_context = self.memory_manager.build_context(text)
        except Exception:
            memory_context = self.memory_manager.build_context(text)
        if memory_context:
            sections.append(f"## 현재 조직 내부 기억\n{memory_context[:1800]}")

        if db_context:
            sections.append(f"## 진행 중인 관련 태스크\n{db_context[:1200]}")

        # 최근 대화 이력 포함 (부서봇에 맥락 전달)
        recent_conv = ""
        if self.context_db is not None:
            try:
                recent_msgs = await self.context_db.get_conversation_messages(
                    chat_id=str(self.allowed_chat_id), is_bot=False, limit=8
                )
                if recent_msgs:
                    lines = [f"[{m['timestamp'][:16]}] {m['content'][:200]}" for m in recent_msgs[:8]]
                    recent_conv = "\n".join(lines)
            except Exception:
                pass

        if recent_conv:
            sections.append(f"## 최근 대화 이력 (참고용)\n{recent_conv[:1200]}")

        return "\n\n".join(section.strip() for section in sections if section.strip())

    async def _collect_upstream_result_context(
        self,
        parent_id: str | None,
        *,
        exclude_task_id: str | None = None,
    ) -> str:
        if self.context_db is None or not parent_id:
            return ""
        try:
            siblings = await self.context_db.get_subtasks(parent_id)
        except Exception:
            return ""
        completed = [
            task for task in siblings
            if task.get("id") != exclude_task_id and task.get("status") == "done" and task.get("result")
        ]
        if not completed:
            return ""
        lines: list[str] = []
        for task in completed[:3]:
            dept_name = KNOWN_DEPTS.get(task.get("assigned_dept") or "", task.get("assigned_dept") or "?")
            excerpt = (task.get("result") or "").strip().replace("\n", " ")
            lines.append(f"- {dept_name}: {excerpt[:240]}")
        return "## 이미 완료된 관련 조직 결과\n" + "\n".join(lines)

    async def _build_delegated_task_packet(self, task_info: dict) -> str:
        metadata = task_info.get("metadata") or {}
        packet = metadata.get("task_packet") or {}
        description = task_info.get("description", "")
        sections: list[str] = []

        original_request = packet.get("original_request") or metadata.get("original_request")
        if original_request:
            sections.append(f"## 상위 사용자 요청\n{str(original_request)[:900]}")

        conversation_context = packet.get("conversation_context") or metadata.get("conversation_context")
        if conversation_context:
            sections.append(f"## 현재 대화 맥락\n{str(conversation_context)[:1500]}")

        rationale = packet.get("rationale") or metadata.get("rationale")
        if rationale:
            sections.append(f"## 왜 이 태스크를 지금 맡았는가\n{str(rationale)[:500]}")

        expectations = packet.get("user_expectations") or metadata.get("user_expectations") or []
        if isinstance(expectations, list) and expectations:
            sections.append("## 사용자 기대치\n" + "\n".join(f"- {str(item)[:160]}" for item in expectations[:6]))

        # BM25 통합 검색 (LOG + conversation_messages)
        memory_context = ""
        try:
            memory_results = await self.memory_manager.search_memories(
                query=description, user_id="global", top_k=5
            )
            if memory_results:
                memory_context = "\n".join(memory_results)
            else:
                memory_context = self.memory_manager.build_context(description)
        except Exception:
            memory_context = self.memory_manager.build_context(description)
        if memory_context:
            sections.append(f"## 이 조직의 내부 기억\n{memory_context[:1500]}")

        upstream = await self._collect_upstream_result_context(
            task_info.get("parent_id"),
            exclude_task_id=task_info.get("id"),
        )
        if upstream:
            sections.append(upstream)

        sections.append(
            "## 실행 규칙\n"
            "- 주어진 지시문만 기계적으로 수행하지 말고, 이 조직의 전문성 관점에서 숨은 blocker와 개선 기회를 함께 본다.\n"
            "- 범위를 무한정 넓히지는 말고 현재 목표 달성에 직접 도움이 되는 추가 제안만 포함한다.\n"
            "- 산출물 위치만 적지 말고 핵심 결과와 이유를 본문에 설명한다.\n"
            "- 추가 협업이 필요하면 이유가 드러나는 형태로 제안한다."
        )

        return "\n\n".join(section.strip() for section in sections if section.strip())

    @staticmethod
    def _looks_like_failed_reply(reply: str) -> bool:
        stripped = (reply or "").strip()
        if not stripped:
            return True
        return stripped.startswith("❌") or stripped.startswith("Error:") or stripped.startswith("Exception:")

    def _get_org_config(self):
        try:
            return load_orchestration_config().get_org(self.org_id)
        except Exception:
            return None

    def _org_mention(self, org_id: str) -> str:
        try:
            org = load_orchestration_config().get_org(org_id)
            if org and org.username:
                return org.username if org.username.startswith("@") else f"@{org.username}"
        except Exception:
            pass
        return f"@{org_id}"

    def _user_mention(self, user) -> str:
        if user is None:
            return ""
        username = getattr(user, "username", "") or ""
        if username:
            return f"@{username}"
        full_name = getattr(user, "full_name", "") or getattr(user, "first_name", "") or ""
        return full_name.strip()

    def _requester_mention_from_metadata(self, metadata: dict | None) -> str:
        metadata = metadata or {}
        return (
            metadata.get("requester_mention")
            or metadata.get("source_org_mention")
            or metadata.get("requester_org_mention")
            or ""
        )

    def _reply_message_id_from_metadata(self, metadata: dict | None) -> int | None:
        metadata = metadata or {}
        raw = metadata.get("source_message_id") or metadata.get("reply_to_message_id")
        try:
            return int(raw) if raw is not None else None
        except Exception:
            return None

    def _infer_collab_target_mentions(self, task: str, *, exclude_org_id: str | None = None) -> list[str]:
        cfg = load_orchestration_config()
        words = {w for w in re.split(r"\W+", task.lower()) if len(w) >= 2}
        scored: list[tuple[int, str]] = []
        for org in cfg.list_specialist_orgs():
            if exclude_org_id and org.id == exclude_org_id:
                continue
            haystack = " ".join([
                org.dept_name,
                org.role,
                org.direction,
                " ".join(org.specialties),
            ]).lower()
            score = sum(1 for word in words if word and word in haystack)
            if score > 0:
                mention = org.username if org.username.startswith("@") else f"@{org.username}"
                scored.append((score, mention))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [mention for _, mention in scored[:2]]

    async def _infer_collab_target_org(self, task: str) -> str | None:
        """task 텍스트에서 협업 대상 org_id를 추론한다.

        Returns:
            추론된 org_id 문자열 (예: "cokac"), 신뢰도 부족 시 None.
        """
        cfg = load_orchestration_config()
        words = {w for w in re.split(r"\W+", task.lower()) if len(w) >= 2}
        scored: list[tuple[int, str]] = []
        for org in cfg.list_specialist_orgs():
            if org.id == self.org_id:
                continue
            haystack = " ".join([
                org.dept_name,
                org.role,
                org.direction,
                " ".join(org.specialties),
            ]).lower()
            score = sum(1 for word in words if word and word in haystack)
            if score >= 2:  # confidence threshold: at least 2 keyword matches
                scored.append((score, org.id))
        if not scored:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]

    def _runbook(self) -> OrchestrationRunbook:
        return OrchestrationRunbook(Path(__file__).resolve().parent.parent)

    def _session_registry(self) -> SessionRegistry:
        return SessionRegistry(self.session_manager)

    def _phase_policy_name(self) -> str:
        org = self._get_org_config()
        if org is None:
            return "default"
        return org.execution.get("phase_policy", "default")

    def _create_runbook(self, request: str) -> str | None:
        try:
            state = self._runbook().create_run(
                self.org_id,
                request,
                phase_policy_name=self._phase_policy_name(),
            )
            return state["run_id"]
        except Exception as e:
            logger.warning(f"[runbook] 생성 실패: {e}")
            return None

    def _advance_runbook(self, run_id: str | None, note: str) -> None:
        if not run_id:
            return
        try:
            self._runbook().advance_phase(run_id, note=note)
        except Exception as e:
            logger.warning(f"[runbook] phase 진행 실패 ({run_id}): {e}")

    def _complete_runbook(self, run_id: str | None, note: str) -> None:
        if not run_id:
            return
        try:
            while True:
                state = self._runbook().get_state(run_id)
                if state["status"] == "completed":
                    break
                self._runbook().advance_phase(run_id, note=note)
        except Exception as e:
            logger.warning(f"[runbook] 완료 처리 실패 ({run_id}): {e}")

    def _append_runbook(self, run_id: str | None, title: str, content: str, *, phase_name: str | None = None) -> None:
        if not run_id:
            return
        try:
            self._runbook().append_note(run_id, title, content, phase_name=phase_name)
        except Exception as e:
            logger.warning(f"[runbook] note 기록 실패 ({run_id}): {e}")

    def _apply_runner_metrics(self, runner) -> None:
        getter = getattr(runner, "get_last_run_metrics", None)
        if getter is None:
            return
        metrics = getter() or {}
        if not metrics:
            return
        self.session_store.update_runtime(
            input_tokens=metrics.get("input_tokens") if isinstance(metrics.get("input_tokens"), int) else None,
            output_tokens=metrics.get("output_tokens") if isinstance(metrics.get("output_tokens"), int) else None,
            total_tokens=metrics.get("total_tokens") if isinstance(metrics.get("total_tokens"), int) else None,
            context_percent=metrics.get("context_percent") if isinstance(metrics.get("context_percent"), int) else None,
            usage_source=metrics.get("usage_source") if isinstance(metrics.get("usage_source"), str) else None,
            output_chars=metrics.get("output_chars") if isinstance(metrics.get("output_chars"), int) else None,
        )

    async def _compact_org_session(self, org_id: str) -> str:
        store = SessionStore(org_id)
        registry = self._session_registry()
        detail = registry.get_session(org_id)
        if detail is None:
            return f"알 수 없는 조직: {org_id}"

        if detail["tmux_active"]:
            try:
                did = await self.session_manager.maybe_compact(org_id, detail["msg_count"])
                if did:
                    store.mark_compacted(reason="telegram /compact")
                    return f"🧹 {org_id} tmux 세션 compact 트리거 완료"
            except Exception as e:
                logger.warning(f"[session] tmux compact 실패 ({org_id}): {e}")

        store.mark_compacted(reason="telegram /compact reset")
        store.reset(preserve_metrics=True)
        return f"🧹 {org_id} 세션 메타데이터를 리셋하고 compact 처리로 기록했습니다."

    async def _maybe_emit_session_alert(self, org_id: str) -> None:
        if not self.app or not self.app.bot:
            return
        registry = self._session_registry()
        item = registry.get_session(org_id)
        if item is None:
            return
        store = SessionStore(org_id)
        session_policy = load_orchestration_config().get_session_policy(item.get("session_policy", ""))
        cooldown = int(session_policy.get("alert_cooldown_minutes", 30) or 30)
        if not store.should_emit_alert(item["health"], cooldown_minutes=cooldown):
            return
        if item["health"] not in {"warning", "compact_recommended", "stale"}:
            return

        ctx_pct = item.get("context_percent", 0) or 0

        # 70% 이상이면 자동 compact 실행 (알림 대신 조용히 처리)
        if ctx_pct >= 70 and item.get("tmux_active"):
            try:
                did = await self.session_manager.maybe_compact(org_id, item.get("msg_count", 0))
                if did:
                    store.mark_compacted(reason="auto-compact at 70%")
                    store.mark_alerted(item["health"])
                    logger.info(f"[auto-compact] {org_id} 자동 compact 완료 ({ctx_pct}%)")
                    # 텔레그램에는 조용한 로그만
                    await self.display.send_to_chat(
                        self.app.bot, self.allowed_chat_id,
                        f"🧹 {org_id} 자동 compact 완료 (컨텍스트 {ctx_pct}%)"
                    )
                    return
            except Exception as e:
                logger.warning(f"[auto-compact] {org_id} 실패: {e}")

        # compact 실패하거나 tmux 없으면 기존 알림 전송
        usage_hint = f"tok={item['total_tokens']}" if item["total_tokens"] else f"msg={item['msg_count']}"
        text = (
            f"⚠️ 세션 알림: {org_id}\n"
            f"- 상태: {item['health']}\n"
            f"- 컨텍스트: {ctx_pct}%\n"
            f"- 사용량: {usage_hint}\n"
            f"- 권장 조치: {item['next_action']}"
        )
        await self.display.send_to_chat(self.app.bot, self.allowed_chat_id, text)
        store.mark_alerted(item["health"])

    async def _queue_retry_candidates_from_db_context(self, db_context: str) -> None:
        if self._pm_orchestrator is None or self.context_db is None or not db_context:
            return
        try:
            import aiosqlite as _sq
            async with _sq.connect(self.context_db.db_path) as _db:
                _db.row_factory = _sq.Row
                cur = await _db.execute(
                    "SELECT id FROM pm_tasks WHERE status IN ('failed', 'pending', 'assigned') "
                    "ORDER BY created_at DESC LIMIT 10"
                )
                rows = await cur.fetchall()
            retry_ids = [r["id"] for r in rows]
            if retry_ids:
                asyncio.create_task(
                    self._store_pending_confirmation("retry_tasks", retry_ids, db_context)
                )
        except Exception:
            return

    async def _handle_set_bot_tone_nl(self, update: Update, text: str) -> None:
        """NL 말투/성격 설정 요청 처리. 봇 이름과 말투 지시를 파싱해 direction 업데이트."""
        if update.message is None:
            return

        # 알려진 봇 이름(dept_name) → org_id 매핑 구성
        try:
            cfg = load_orchestration_config(force_reload=True)
            name_to_id: dict[str, str] = {
                org.dept_name: org.id for org in cfg.list_specialist_orgs()
            }
        except Exception as _e:
            logger.warning(f"[set_bot_tone] org 목록 로드 실패: {_e}")
            name_to_id = {}

        # 텍스트에서 봇 이름 탐색
        matched_org_id: str | None = None
        matched_dept: str | None = None
        for dept_name, org_id in name_to_id.items():
            if dept_name in text:
                matched_org_id = org_id
                matched_dept = dept_name
                break

        if matched_org_id is None:
            await update.message.reply_text(
                "봇 이름을 찾지 못했어요.\n"
                "예) '성장실 봇 말투를 데이터 지향적으로 바꿔줘'\n"
                "또는 `/org set-tone <봇이름> <말투지시>` 명령어를 사용하세요.",
                parse_mode="Markdown",
            )
            return

        # 말투 지시 추출: 봇 이름 + 말투 키워드 제거 후 나머지
        import re as _re
        tone_kws = [
            "말투를", "말투로", "말투 바꿔줘", "말투 바꿔", "말투 변경해줘", "말투 변경",
            "말투 설정해줘", "말투 설정", "말투", "톤 설정해줘", "톤 설정", "톤을", "톤으로",
            "성격 바꿔줘", "성격 바꿔", "성격 변경해줘", "성격 변경", "성격을", "성격으로",
            "어투를", "어투로", "어투", "봇", "바꿔줘", "변경해줘", "설정해줘",
        ]
        tone_text = text
        for kw in [matched_dept] + tone_kws:
            tone_text = tone_text.replace(kw, " ")
        tone_instruction = _re.sub(r"\s+", " ", tone_text).strip()

        if not tone_instruction:
            await update.message.reply_text(
                f"{matched_dept} 봇의 말투 지시를 입력해주세요.\n"
                "예) '성장실 봇 말투를 데이터 지향적이고 직설적으로 바꿔줘'",
            )
            return

        # direction에 말투 지시 주입 (기존 direction 보존 + 말투 섹션 추가/교체)
        target_identity = PMIdentity(matched_org_id)
        current_direction = target_identity._data.get("direction", "") or ""
        # 기존 말투 섹션이 있으면 교체, 없으면 추가
        tone_marker = "[말투/성격]"
        if tone_marker in current_direction:
            new_direction = _re.sub(
                r"\[말투/성격\].*?(\n|$)", f"{tone_marker} {tone_instruction}\n", current_direction
            ).strip()
        else:
            new_direction = (
                (current_direction + f"\n{tone_marker} {tone_instruction}").strip()
                if current_direction
                else f"{tone_marker} {tone_instruction}"
            )

        target_identity.update({"direction": new_direction})
        try:
            _sync_identity_to_canonical_config(matched_org_id, target_identity._data)
            _refresh_legacy_bot_configs()
        except Exception as _sync_err:
            logger.warning(f"[set_bot_tone] canonical sync 실패: {_sync_err}")

        await update.message.reply_text(
            f"✅ *{matched_dept}* 봇 말투 업데이트!\n\n"
            f"말투 지시: `{tone_instruction}`\n\n"
            f"현재 방향성:\n{new_direction}",
            parse_mode="Markdown",
        )

    async def _reply_with_pm_chat(
        self,
        update: Update,
        text: str,
        replied_context: str = "",
    ) -> None:
        """가벼운 질문/상태 확인은 PM이 직접 대답한다."""
        if update.message is None:
            return
        db_context = await self._build_pm_db_context()
        await self._queue_retry_candidates_from_db_context(db_context)
        context_packet = await self._build_conversation_context_packet(
            text,
            replied_context=replied_context,
            db_context=db_context,
        )
        system_prompt = (
            self.identity.build_system_prompt()
            + "\n\n## 사용자 응답 계약\n"
            "- 당신은 총괄 PM이며, 텔레그램 사용자에게 직접 설명한다.\n"
            "- 첫 문단에서 질문이나 불만에 바로 답한다.\n"
            "- 링크, 경로, 내부 문서 위치만 던지지 말고 핵심 내용을 먼저 설명한다.\n"
            "- 필요한 경우 무엇을 확인했고 무엇을 바꿀지 다음 조치를 분명히 적는다.\n"
            "- 간단한 질문·확인·상태 문의는 직접 답하고 불필요한 위임을 하지 않는다.\n"
            "- 단, 코드·스크립트·예제 작성 요청 및 REST API 설계·엔드포인트 설계 요청은 반드시 @aiorg_engineering_bot에 위임한다. PM이 직접 코드/API 설계 금지.\n\n"
            f"{context_packet}"
        )
        prompt = text + replied_context
        progress_msg = await self.display.send_reply(update.message, "잠깐요, 한번 볼게요 🧠")
        history: list[str] = []
        last_edit = 0.0
        progress_interval = self._progress_interval()
        history_limit = self._progress_history_limit()

        async def on_progress(line: str) -> None:
            nonlocal last_edit
            if not self._show_progress():
                return
            cleaned = self._clean_progress_line(line)
            if not cleaned:
                return
            history.append(cleaned)
            if time.time() - last_edit < progress_interval:
                return
            last_edit = time.time()
            try:
                await self.display.edit_progress(
                    progress_msg,
                    "🧠 확인 중...\n\n" + "\n".join(history[-history_limit:]),
                    agent_id=f"{self.org_id}-chat",
                )
            except Exception:
                pass

        reply = ""
        used_codex = self.engine == "codex"
        try:
            if self.engine == "codex":
                runner = self._make_codex_runner()
                reply = await asyncio.wait_for(
                    runner.run(
                        f"{system_prompt}\n\n{prompt}",
                        progress_callback=on_progress,
                    ),
                    timeout=PM_CHAT_REPLY_TIMEOUT_SEC,
                )
            else:
                runner = self._make_claude_runner()
                reply = await asyncio.wait_for(
                    runner.run_single(
                        prompt,
                        progress_callback=on_progress,
                        system_prompt=system_prompt,
                        org_id=self.org_id,
                        session_store=self.session_store,
                        global_context=self.global_context,
                    ),
                    timeout=PM_CHAT_REPLY_TIMEOUT_SEC,
                )
        except asyncio.TimeoutError:
            reply = ""
            history.append("응답이 길어져 복구 경로로 전환합니다.")
        except Exception as exc:
            logger.warning(f"[{self.org_id}] PM chat primary reply 실패: {exc}")
            reply = ""

        if used_codex and self._looks_like_failed_reply(reply):
            try:
                fallback_runner = self._make_claude_runner()
                reply = await fallback_runner.run_single(
                    prompt,
                    progress_callback=on_progress,
                    system_prompt=system_prompt,
                    org_id=self.org_id,
                    session_store=self.session_store,
                    global_context=self.global_context,
                )
                used_codex = False
            except Exception as exc:
                logger.warning(f"[{self.org_id}] PM chat fallback 실패: {exc}")

        reply = await ensure_user_friendly_output(
            reply or "지금 응답을 복구하는 중입니다. 조금 더 구체적으로 다시 이어서 처리하겠습니다.",
            original_request=text,
            decision_client=self._pm_decision_client,
        )

        if used_codex and reply:
            await self.global_context.extract_and_save(self.org_id, prompt, reply)

        await self.memory_manager.add_log(f"PM 응답: {reply[:200]}")

        chunks = split_message(reply.strip() or "알겠습니다.", 4000)
        first = chunks[0]
        try:
            await progress_msg.edit_text(first)
        except Exception:
            await self.display.send_reply(update.message, first)
        for chunk in chunks[1:]:
            await self.display.send_reply(update.message, chunk)

    async def _build_team_config(self, task: str):
        prefs = self.identity.get_team_preferences()
        return await self._team_builder.build_team(
            task,
            role=prefs.get("role", ""),
            specialties=prefs.get("specialties", []),
            direction=prefs.get("direction", ""),
            preferred_agents=prefs.get("preferred_agents", []),
            avoid_agents=prefs.get("avoid_agents", []),
            max_team_size=prefs.get("max_team_size", 3),
            preferred_engine=self.engine,
            guidance=prefs.get("guidance", ""),
        )

    def _resolve_execution_backend(self, route_kind: str, team_config, task: str) -> str:
        org = self._get_org_config()
        if org is None:
            return "resume_session"

        cfg = load_orchestration_config()
        policy_name = org.execution.get("backend_policy", "")
        policy = cfg.get_backend_policy(policy_name)
        backend = policy.get(route_kind, "resume_session")

        if (
            policy.get("long_running") == "tmux_session"
            and len(task) > 220
        ):
            if team_config.engine == "claude-code" and team_config.execution_mode.value == "sequential":
                backend = "tmux_session"
            else:
                backend = "tmux_batch"

        if backend == "tmux_session" and (
            team_config.engine != "claude-code" or team_config.execution_mode.value != "sequential"
        ):
            backend = "tmux_batch"
        return backend

    def _format_execution_brief(
        self,
        task: str,
        team_config,
        *,
        owner_label: str,
        route_label: str,
        route_kind: str = "local_execution",
    ) -> str:
        checkpoints = {
            "structured_team": "구조 파악 → 역할 분담 → 실행 → 검증",
            "agent_teams": "탐색/분석 → 병렬 처리 → 통합",
            "sequential": "요청 파악 → 실행 → 결과 정리",
        }
        plan = self._team_builder.format_team_announcement(team_config)
        runtime_label = self._describe_runtime_mode(task, team_config, route_kind)
        builtin_surfaces = recommend_builtin_surfaces(task, org_id=self.org_id)
        builtin_text = "\n".join(
            f"- {surface.command}: {surface.purpose}"
            for surface in builtin_surfaces[:3]
        )
        return (
            f"🧭 {owner_label} 실행 계획\n"
            f"- 처리 방식: {route_label}\n"
            f"- 요청 요약: {task[:120]}\n"
            f"- 실행 런타임: {runtime_label}\n"
            f"{plan}\n"
            f"🧰 권장 내장 Surface\n{builtin_text}\n"
            f"🛰️ 체크포인트: {checkpoints.get(team_config.execution_mode.value, '실행 → 검증')}"
        )

    def _describe_runtime_mode(self, task: str, team_config, route_kind: str) -> str:
        backend = self._resolve_execution_backend(route_kind, team_config, task)
        if team_config.engine == "codex":
            strategy = {
                "structured_team": "structured_team_compat",
                "agent_teams": "agent_teams_compat",
                "sequential": "sequential",
            }.get(team_config.execution_mode.value, team_config.execution_mode.value)
            return f"Codex CLI / {strategy} / {backend}"

        strategy = {
            "structured_team": "structured_team",
            "agent_teams": "agent_teams",
            "sequential": "sequential",
        }.get(team_config.execution_mode.value, team_config.execution_mode.value)
        return f"Claude Code / {strategy} / {backend}"

    async def _execute_with_team_config(
        self,
        *,
        task: str,
        system_prompt: str,
        team_config,
        progress_callback=None,
        workdir: str | None = None,
        route_kind: str = "local_execution",
    ) -> str:
        backend = self._resolve_execution_backend(route_kind, team_config, task)
        tmux_available = self.session_manager.status().get("tmux", False)
        agent_names = [persona.name for persona in team_config.agents]
        self.session_store.update_runtime(
            engine=team_config.engine,
            backend=backend,
            execution_mode=team_config.execution_mode.value,
            increment_messages=True,
        )
        if backend == "tmux_batch" and not tmux_available:
            backend = "resume_session" if team_config.engine == "claude-code" else "ephemeral"
            self.session_store.update_runtime(
                engine=team_config.engine,
                backend=backend,
                execution_mode=team_config.execution_mode.value,
            )
        if team_config.engine == "codex":
            runner = self._make_codex_runner()
            prompt = task
            if agent_names:
                prompt = f"[Agents: {', '.join(agent_names)}]\n{task}"
            if self.global_context:
                ctx_prompt = await self.global_context.build_system_prompt(self.org_id, task)
                if ctx_prompt:
                    system_prompt = f"{system_prompt}\n\n{ctx_prompt}".strip()
            if system_prompt:
                prompt = f"{system_prompt}\n\n{prompt}"
            result = await runner.run(
                prompt,
                workdir=workdir,
                workdir_hint=task,
                agents=agent_names,
                progress_callback=progress_callback,
                shell_session_manager=self.session_manager if backend == "tmux_batch" else None,
                shell_team_id=self.org_id if backend == "tmux_batch" else None,
            )
            self._apply_runner_metrics(runner)
            if self.global_context and result and not self._looks_like_failed_reply(result):
                await self.global_context.extract_and_save(self.org_id, task, result)
            if progress_callback:
                backend_label = "tmux_batch" if backend == "tmux_batch" else "direct"
                await progress_callback(
                    f"Codex 실행 완료 [{backend_label}] ({', '.join(agent_names[:3]) or 'solo'})"
                )
            await self._maybe_emit_session_alert(self.org_id)
            return result

        if backend == "tmux_session":
            if not tmux_available:
                backend = "resume_session"
                self.session_store.update_runtime(
                    engine=team_config.engine,
                    backend=backend,
                    execution_mode=team_config.execution_mode.value,
                )
            else:
                if progress_callback:
                    await progress_callback("tmux persistent session 실행")
                full_prompt = f"{system_prompt}\n\n{task}".strip()
                result = await self.session_manager.send_message(self.org_id, full_prompt)
                await self._maybe_emit_session_alert(self.org_id)
                return result

        if backend == "tmux_session":
            if progress_callback:
                await progress_callback("tmux unavailable -> resume_session fallback")

        runner = self._make_claude_runner()
        session_store = self.session_store if backend == "resume_session" else None
        counts: dict[str, int] = {}
        for name in agent_names:
            counts[name] = counts.get(name, 0) + 1
        unique_agents = list(counts.keys())
        unique_counts = [counts[name] for name in unique_agents]

        if team_config.execution_mode.value == "structured_team" and len(unique_agents) >= 2:
            if "team" in runner.capabilities():
                result = await runner.run_structured_team(
                    task,
                    unique_agents,
                    counts=unique_counts,
                    progress_callback=progress_callback,
                    session_store=session_store,
                    org_id=self.org_id,
                    global_context=self.global_context,
                    system_prompt=system_prompt,
                    workdir=workdir,
                    shell_session_manager=self.session_manager if backend == "tmux_batch" else None,
                    shell_team_id=self.org_id if backend == "tmux_batch" else None,
                )
            else:
                from tools.base_runner import RunContext
                result = await runner.run(RunContext(prompt=f"{system_prompt}\n\n{task}".strip() if system_prompt else task, workdir=workdir))
            self._apply_runner_metrics(runner)
            await self._maybe_emit_session_alert(self.org_id)
            return result
        if team_config.execution_mode.value == "agent_teams" and len(unique_agents) >= 2:
            if "team" in runner.capabilities():
                result = await runner.run_agent_teams(
                    task,
                    unique_agents,
                    progress_callback=progress_callback,
                    system_prompt=system_prompt,
                    workdir=workdir,
                    shell_session_manager=self.session_manager if backend == "tmux_batch" else None,
                    shell_team_id=self.org_id if backend == "tmux_batch" else None,
                )
            else:
                from tools.base_runner import RunContext
                result = await runner.run(RunContext(prompt=f"{system_prompt}\n\n{task}".strip() if system_prompt else task, workdir=workdir))
            self._apply_runner_metrics(runner)
            await self._maybe_emit_session_alert(self.org_id)
            return result
        persona = unique_agents[0] if unique_agents else None
        result = await runner.run_single(
            task,
            persona=persona,
            progress_callback=progress_callback,
            session_store=session_store,
            org_id=self.org_id,
            global_context=self.global_context,
            system_prompt=system_prompt,
            workdir=workdir,
            shell_session_manager=self.session_manager if backend == "tmux_batch" else None,
            shell_team_id=self.org_id if backend == "tmux_batch" else None,
        )
        self._apply_runner_metrics(runner)
        await self._maybe_emit_session_alert(self.org_id)
        return result

    async def _handle_collab_tags(
        self,
        response: str,
        *,
        bot,
        chat_id: int,
        requester_mention: str = "",
        reply_to_message_id: int | None = None,
    ) -> str:
        """응답의 [TEAM:], [COLLAB:] 태그를 정리하고 협업 요청을 발송한다."""
        if not response:
            return response
        import re as _re

        cleaned = _re.sub(r"\[TEAM:[^\]]+\]", "", response).strip()
        for match in _re.findall(r"\[COLLAB:([^\]]+)\]", cleaned):
            parts = match.split("|맥락:", 1)
            collab_task = parts[0].strip()
            collab_ctx = parts[1].strip() if len(parts) > 1 else ""
            if is_placeholder_collab(collab_task, collab_ctx):
                continue
            target_org = await self._infer_collab_target_org(collab_task)
            if target_org is not None and self._pm_orchestrator is not None:
                try:
                    parent_id = await self._pm_orchestrator._next_task_id()
                    await self._pm_orchestrator.collab_dispatch(
                        parent_task_id=parent_id,
                        task=collab_task,
                        target_org=target_org,
                        requester_org=self.org_id,
                        context=collab_ctx,
                        chat_id=chat_id,
                    )
                except Exception as _e:
                    logger.warning(f"collab PM dispatch 실패: {_e}")
            else:
                target_mentions = self._infer_collab_target_mentions(
                    collab_task, exclude_org_id=self.org_id
                )
                collab_msg = make_collab_request_v2(
                    collab_task,
                    self.org_id,
                    context=collab_ctx,
                    requester_mention=requester_mention,
                    from_org_mention=self._org_mention(self.org_id),
                    target_mentions=target_mentions,
                )
                try:
                    if bot is not None:
                        await self.display.send_to_chat(
                            bot,
                            chat_id,
                            collab_msg,
                            reply_to_message_id=reply_to_message_id,
                        )
                except Exception as _e:
                    logger.warning(f"협업 요청 발송 실패: {_e}")
        cleaned = _re.sub(r"\[COLLAB:[^\]]+\]", "", cleaned).strip()
        return cleaned

    def _clean_progress_line(self, line: str) -> str:
        stripped = line.strip()
        if not stripped:
            return ""

        lowered = stripped.lower()
        noisy_headers = {
            "thinking",
            "exec",
            "collab",
            "plan update",
        }
        noisy_prefixes = (
            "spawn_agent(",
            "wait(",
            "🌐 searching the web",
            "🌐 searched",
            "__exit_code__:",
            "__done__",
            "[agent:",
            "--- name:",
            "openai codex v",
        )
        noisy_contains = (
            "## 협업 요청",
            "## pm 배정 태스크",
            "→ 응답에 [collab:",
            "→ 위 팀이 더 적합한 업무가 있으면",
            "python jwt 로그인 라이브러리 v1.0, b2b 타겟",
            "현재 작업 요약",
        )
        if lowered in noisy_headers:
            return ""
        if lowered.startswith(noisy_prefixes):
            return ""
        if any(token in lowered for token in noisy_contains):
            return ""
        if stripped.startswith("<") and stripped.endswith(">"):
            return ""
        return stripped

    async def _auto_upload(self, response: str, token: str, chat_id: int) -> None:
        """응답 내 생성 파일 경로를 감지해 현재 조직의 설정된 채팅방으로 업로드."""
        from tools.telegram_uploader import upload_file

        target = resolve_delivery_target(self.org_id)
        if target is None:
            logger.warning(
                f"[auto_upload:{self.org_id}] configured target 없음 — passed token/chat_id 사용"
            )
            safe_token = token
            safe_chat_id = int(chat_id)
        else:
            safe_token = target.token
            safe_chat_id = target.chat_id
            if token != safe_token or int(chat_id) != safe_chat_id:
                logger.warning(
                    f"[auto_upload:{self.org_id}] 전달 대상 불일치 감지, configured target 사용"
                )

        seen: set[str] = set()
        for raw in extract_local_artifact_paths(response or ""):
            path_text = os.path.expanduser(raw.strip())
            if path_text in seen:
                continue
            if path_text in self._uploaded_artifacts:
                logger.debug(f"[auto_upload:{self.org_id}] 중복 업로드 스킵: {path_text}")
                continue
            seen.add(path_text)
            self._uploaded_artifacts.add(path_text)
            path = Path(path_text)
            for artifact in prepare_upload_bundle(path):
                try:
                    await upload_file(
                        safe_token,
                        safe_chat_id,
                        str(artifact),
                        f"📎 {self.org_id} 산출물: {artifact.name}",
                    )
                except Exception as exc:
                    logger.warning(f"[auto_upload:{self.org_id}] 업로드 실패 {artifact}: {exc}")

    async def _upload_artifacts_to(
        self, result: str, token: str, chat_id: int
    ) -> None:
        """Cross-org artifact upload — calls upload_file directly, bypasses resolve_delivery_target."""
        from core.artifact_pipeline import extract_local_artifact_paths, prepare_upload_bundle
        from tools.telegram_uploader import upload_file
        for raw in extract_local_artifact_paths(result):
            for p in prepare_upload_bundle(raw):
                if p not in self._uploaded_artifacts:
                    caption = f"📎 {self.org_id} 산출물: {p.name}"
                    await upload_file(token, int(chat_id), str(p), caption)
                    self._uploaded_artifacts.add(p)

    async def _inject_collab_result(self, task_info: dict) -> None:
        """When a collab PM_TASK completes, inject result back to the requester org."""
        metadata = task_info.get("metadata") or {}
        if not metadata.get("collab"):
            return
        if metadata.get("result_injected"):
            return
        task_id = task_info.get("task_id") or task_info.get("id", "")
        collab_requester = metadata.get("collab_requester")
        if not collab_requester:
            logger.warning(f"[collab_inject:{self.org_id}] {task_id} — collab_requester 없음")
            return
        if task_id in self._collab_injecting:
            return
        self._collab_injecting.add(task_id)
        try:
            from core.orchestration_config import load_orchestration_config
            cfg = load_orchestration_config()
            requester_org = cfg.get_org(collab_requester)
            if requester_org is None:
                logger.warning(
                    f"[collab_inject:{self.org_id}] {task_id} — "
                    f"requester org '{collab_requester}' config 없음"
                )
                return
            requester_token = requester_org.token
            requester_chat_id = requester_org.chat_id
            if not requester_token or not requester_chat_id:
                logger.warning(
                    f"[collab_inject:{self.org_id}] {task_id} — "
                    f"requester org '{collab_requester}' token/chat_id 없음"
                )
                return
            result_text = (task_info.get("result") or "")[:3000]
            task_desc = (task_info.get("description") or "")[:200]
            message = (
                f"🤝 [{self.org_id}] 협업 결과 도착\n"
                f"태스크: {task_desc}\n\n"
                f"{result_text}"
            )
            import telegram
            bot = telegram.Bot(token=requester_token)
            await bot.send_message(chat_id=requester_chat_id, text=message)
            if "[ARTIFACT:" in (task_info.get("result") or ""):
                await self._upload_artifacts_to(
                    task_info.get("result", ""), requester_token, requester_chat_id
                )
            await self.context_db.update_pm_task_metadata(task_id, {"result_injected": True})
            logger.info(
                f"[collab_inject:{self.org_id}] {task_id} → {collab_requester} 완료"
            )
        except Exception as exc:
            logger.warning(
                f"[collab_inject:{self.org_id}] {task_id} 주입 실패: {exc}"
            )
        finally:
            self._collab_injecting.discard(task_id)

    # ── 메시지 처리 ────────────────────────────────────────────────────────

    async def _with_progress_feedback(self, update: Update, coro, delay: float = 3.0):
        """delay초 이상 걸리면 '🤔 분석 중...' 피드백을 전송하고, 완료 시 자동 취소."""
        progress_task = None

        async def _send_progress():
            await asyncio.sleep(delay)
            try:
                await self.display.send_reply(update.message, "어디 보자... 🤔")
            except Exception:
                pass

        try:
            progress_task = asyncio.create_task(_send_progress())
            return await coro
        finally:
            if progress_task and not progress_task.done():
                progress_task.cancel()

    async def _with_immediate_ack(self, update: Update, coro):
        """
        처리 시작 즉시 '🤔 분석 중...' ACK를 전송하고,
        처리 완료 후 해당 메시지를 삭제한다 (최종 결과는 별도 전송).
        """
        ack_msg = None
        try:
            ack_msg = await self.display.send_reply(update.message, "🤔 분석 중...")
        except Exception:
            pass  # ACK 실패해도 처리는 계속

        try:
            return await coro
        finally:
            if ack_msg is not None:
                try:
                    await ack_msg.delete()
                except Exception:
                    pass  # 삭제 실패 무시

    async def on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """메시지 수신 → confidence scoring → claim → 응답."""
        if update.message is None or update.effective_chat is None:
            return

        # 허용된 채팅만 처리
        if update.effective_chat.id != self.allowed_chat_id:
            return

        text = update.message.text or ""
        if not text:
            return

        # 대화 이력 캡처 (non-blocking, 실패해도 처리 계속)
        if self.context_db is not None:
            try:
                import asyncio as _asyncio
                _sender = update.message.from_user
                _asyncio.create_task(
                    self.context_db.insert_conversation_message(
                        msg_id=update.message.message_id,
                        chat_id=str(update.message.chat_id),
                        user_id=str(_sender.id) if _sender else "unknown",
                        bot_id=self.org_id,
                        role="bot" if (_sender and _sender.is_bot) else "user",
                        is_bot=bool(_sender and _sender.is_bot),
                        content=text[:4000],
                        timestamp=update.message.date.isoformat(),
                    )
                )
            except Exception:
                pass  # 캡처 실패해도 처리 계속

        # 명령어는 허용하되, PM 오케스트레이터 모드의 부서 봇은 일반 사용자 메시지를 처리하지 않는다.
        if text.startswith("/"):
            await self._handle_command(text, update, context)
            return

        # 봇 메시지 처리 — 협업 요청, [PM_TASK:...], 토론 태그 수락
        sender = update.message.from_user
        if sender and sender.is_bot:
            if is_collab_request(text):
                await self._handle_collab_request(text, update, context)
            elif self._is_dept_org and "[PM_TASK:" in text:
                await self._handle_pm_task(text, update, context)
            elif self._discussion_manager and is_discussion_message(text):
                await self._handle_discussion_message(text, update, context)
            # pm_bot: 워커봇 완료 메시지 감지 → 즉시 합성 트리거 (이벤트 드리븐)
            elif self._pm_orchestrator is not None and re.search(r"태스크\s+T-[A-Za-z0-9_]+-\d+\s+완료", text):
                await self._handle_pm_done_event(text)
            return

        if self._is_dept_org:
            logger.debug(f"[{self.org_id}] PM 오케스트레이터 활성 — 일반 사용자 메시지 무시")
            return

        message_id = str(update.message.message_id)
        # 봇 시작 이전 메시지 무시 (pending updates 방지)
        # 재시작에 30초+ 소요되므로 grace period를 120초로 설정
        _msg_ts = update.message.date.timestamp() if update.message.date else 0
        if _msg_ts and _msg_ts < self._start_time - 120:
            logger.debug(f"[{self.org_id}] 오래된 메시지 무시 (message_id={message_id}, age={self._start_time - _msg_ts:.0f}s)")
            return
        if _msg_ts and _msg_ts < self._start_time:
            logger.info(f"[{self.org_id}] 재시작 중 수신 메시지 복구 처리 (message_id={message_id}, age={self._start_time - _msg_ts:.0f}s)")
        logger.info(f"텔레그램 수신 [{self.org_id}]: {text[:80]}")

        # LLM 기반 라우팅 (pm_bot 전용)
        _replied_context = ""
        if self._pm_orchestrator is not None:
            _route_ctx = {
                "pending_confirmation": self._pending_confirmation.get(self.allowed_chat_id),
                "replied_to": None,
            }
            # replied_to 컨텍스트 미리 수집
            if (update.message.reply_to_message
                    and update.message.reply_to_message.from_user
                    and update.message.reply_to_message.from_user.is_bot):
                _pre_replied = update.message.reply_to_message.text or ""
                if _pre_replied:
                    _route_ctx["replied_to"] = _pre_replied[:200]
            _route = await self._router.route(text, _route_ctx)

            if _route.action == "confirm_pending":
                _conf = self._pending_confirmation.get(self.allowed_chat_id)
                if _conf and _conf.get("expires", 0) > __import__("time").time():
                    if self.claim_manager.try_claim(message_id, self.org_id):
                        await self._execute_pending_confirmation(_conf, update)
                        del self._pending_confirmation[self.allowed_chat_id]
                        return

            elif _route.action == "retry_task":
                if (update.message.reply_to_message and
                        update.message.reply_to_message.from_user and
                        update.message.reply_to_message.from_user.is_bot):
                    if self.claim_manager.try_claim(message_id, self.org_id):
                        await self._handle_retry_request(text, _route_ctx.get("replied_to") or "", update, task_id_hint=_route.task_id)
                        return

            elif _route.action == "status_query":
                pass  # fall through to normal NL classifier / task handling

        # 봇 메시지에 답장 처리 (pm_bot 전용)
        if (self._pm_orchestrator is not None
                and update.message.reply_to_message
                and update.message.reply_to_message.from_user
                and update.message.reply_to_message.from_user.is_bot):
            replied_text = update.message.reply_to_message.text or ""
            # 재시도 아닌 답장 → 답장한 메시지 내용을 context로 주입
            if replied_text:
                _replied_context = f"\n\n[답장 대상 메시지]\n{replied_text[:300]}"

        # 1. 대화형 vs 작업 분류
        if USE_NL_CLASSIFIER:
            _result = self._nl_classifier.classify(text)
            _intent = _result.intent
            is_greeting = _intent == Intent.GREETING
            # APPROVE/REJECT/CANCEL/STATUS 는 짧은 명령이므로 task로 라우팅
            # CHAT 은 greeting과 동일하게 default PM만 처리
            is_greeting = is_greeting or _intent == Intent.CHAT
            is_task = _intent in (Intent.TASK, Intent.APPROVE, Intent.REJECT, Intent.CANCEL, Intent.STATUS)
        else:
            is_greeting = False
            is_task = len(text) > 5

        # 1-A. 말투/성격 설정 의도 → PM 봇만 처리
        if USE_NL_CLASSIFIER and _intent == Intent.SET_BOT_TONE and self._is_pm_org:
            if not self.claim_manager.try_claim(message_id, self.org_id):
                return
            await self._handle_set_bot_tone_nl(update, text)
            return

        # 2. 인사 → default PM만 claim 후 응답
        if is_greeting:
            is_default = self.identity._data.get("default_handler", False)
            if not is_default:
                return
            if not self.claim_manager.try_claim(message_id, self.org_id):
                return
            await self._reply_with_pm_chat(update, text, _replied_context)
            return

        # PM 오케스트레이터 모드: 부서 봇은 사용자 메시지에 자율 입찰 안함
        if self._is_dept_org:
            logger.debug(f"[{self.org_id}] PM 오케스트레이터 활성 — 사용자 메시지 입찰 건너뜀")
            return

        # 3. 작업 요청 → confidence 계산
        score = await self.confidence_scorer.score(text, self.identity)
        is_default = self.identity._data.get("default_handler", False)
        if score < DEFAULT_CONFIDENCE_THRESHOLD and not is_default:
            return

        # 1단계: 입찰 제출
        text_hash = hashlib.md5(text.encode()).hexdigest()
        # PM 오케스트레이터 모드: PM은 score=999로 항상 승리
        if self._is_pm_org:
            bid_score = 999
        else:
            bid_score = score if score >= DEFAULT_CONFIDENCE_THRESHOLD else 0
        self.claim_manager.submit_bid(text_hash, self.org_id, bid_score)

        # 2단계: BID_WAIT_SEC 대기 (다른 봇들도 입찰 제출하도록)
        BID_WAIT_SEC = 0.8
        await asyncio.sleep(BID_WAIT_SEC)

        # 3단계: 내가 winner인지 확인
        winner = self.claim_manager.get_winner(text_hash)
        if winner != self.org_id:
            logger.debug(f"[bid] {self.org_id} 패배 — winner: {winner}")
            return

        # 4단계: hash lock + message_id claim (race condition 최종 방지)
        if not self.claim_manager.try_claim(message_id, self.org_id, text_hash):
            return

        asyncio.get_event_loop().run_in_executor(None, self.claim_manager.cleanup_old_claims)
        await self.memory_manager.add_log(f"사용자 메시지: {text[:200]}")
        if self._is_pm_org:
            self.global_context.append_entry(
                self.org_id,
                f"**사용자 요청**: {text[:160]}",
                category="대화",
            )

        # PM 오케스트레이터: 사용자 요청을 분해·배분 (Claude Code 직접 실행 대신)
        if self._pm_orchestrator is not None:
            try:
                request_text = text + _replied_context
                plan = await self._with_immediate_ack(
                    update,
                    self._pm_orchestrator.plan_request(request_text),
                )
                if plan.interaction_mode == "discussion" and ENABLE_DISCUSSION_PROTOCOL:
                    disc_ids = await self._pm_orchestrator.discussion_dispatch(
                        request_text, plan.dept_hints, update.effective_chat.id,
                    )
                    if disc_ids:
                        await self.display.send_reply(
                            update.message,
                            f"💬 자유 토론을 시작합니다\n주제: {request_text[:100]}",
                        )
                        return
                    logger.info("[PM] discussion 참여자 부족, delegate fallback")
                elif plan.interaction_mode == "collab":
                    if not ENABLE_DISCUSSION_PROTOCOL:
                        logger.info("[PM] interaction_mode=collab — ENABLE_DISCUSSION_PROTOCOL 미설정, delegate fallback")

                if plan.route == "direct_reply":
                    await self._reply_with_pm_chat(update, text, _replied_context)
                    return

                if plan.route == "local_execution":
                    await self.display.send_reply(update.message, "제가 직접 해볼게요! 팀 꾸리는 중이에요 🧠")
                    run_id = self._create_runbook(request_text)
                    self._advance_runbook(run_id, "요청 접수 후 planning phase로 이동")
                    team_config = await self._build_team_config(request_text)
                    brief = self._format_execution_brief(
                        request_text,
                        team_config,
                        owner_label="PM",
                        route_label="PM 직접 실행",
                        route_kind="local_execution",
                    )
                    self._append_runbook(run_id, "Planning brief", brief, phase_name="planning")
                    self._advance_runbook(run_id, "계획 공유 완료, design phase로 이동")
                    self._append_runbook(
                        run_id,
                        "Design summary",
                        f"engine={team_config.engine}\nmode={team_config.execution_mode.value}\nagents={', '.join(p.name for p in team_config.agents)}",
                        phase_name="design",
                    )
                    self._advance_runbook(run_id, "설계 공유 완료, implementation phase로 이동")
                    progress_msg = await self.display.send_reply(update.message, "알겠어요, 바로 시작할게요! ⚙️")
                    history: list[str] = []
                    last_edit = time.time()
                    progress_interval = self._progress_interval()
                    history_limit = self._progress_history_limit()

                    async def on_progress(line: str) -> None:
                        nonlocal last_edit
                        if not self._show_progress():
                            return
                        stripped = self._clean_progress_line(line)
                        if not stripped:
                            return
                        history.append(stripped)
                        if time.time() - last_edit > progress_interval:
                            display = "\n".join(history[-history_limit:])
                            try:
                                await self.display.edit_progress(
                                    progress_msg,
                                    f"중간 상황 공유할게요!\n\n{display}",
                                    agent_id=self.org_id,
                                )
                                last_edit = time.time()
                            except Exception:
                                pass

                    response = await self._execute_with_team_config(
                        task=request_text,
                        system_prompt=self.identity.build_system_prompt(),
                        team_config=team_config,
                        progress_callback=on_progress,
                        route_kind="local_execution",
                    )
                    upload_candidates = extract_local_artifact_paths(response or "")
                    self._append_runbook(
                        run_id,
                        "Implementation result",
                        (response or "(결과 없음)")[:6000],
                        phase_name="implementation",
                    )
                    self._advance_runbook(run_id, "실행 완료, verification phase로 이동")
                    try:
                        await progress_msg.edit_text("다 됐어요! ✅")
                    except Exception:
                        pass
                    response = await self._handle_collab_tags(
                        response,
                        bot=context.bot,
                        chat_id=update.effective_chat.id,
                        requester_mention=self._user_mention(update.effective_user),
                        reply_to_message_id=update.message.message_id if update.message else None,
                    )
                    if response:
                        response = await ensure_user_friendly_output(
                            response,
                            original_request=request_text,
                            decision_client=self._pm_decision_client,
                        )
                        for chunk in split_message(response, 4000):
                            await self.display.send_reply(update.message, chunk)
                        await self._auto_upload("\n".join(upload_candidates), self.token, update.effective_chat.id)
                    self._append_runbook(
                        run_id,
                        "Verification summary",
                        f"응답 길이: {len(response or '')}\n실행 backend 검토 완료.",
                        phase_name="verification",
                    )
                    self._advance_runbook(run_id, "검증 완료, feedback phase로 이동")
                    self._append_runbook(
                        run_id,
                        "Feedback",
                        "후속 개선점이 있으면 다음 run에서 이어간다.",
                        phase_name="feedback",
                    )
                    self._complete_runbook(run_id, "로컬 실행 완료 및 피드백 반영")
                    if self.bus:
                        asyncio.ensure_future(self._p2p.notify_task_done(self.org_id, run_id or "", response[:200] if response else "완료"))
                    return

                if plan.interaction_mode == "collab" and ENABLE_DISCUSSION_PROTOCOL:
                    collab_target = await self._infer_collab_target_org(request_text)
                    parent_id = await self._pm_orchestrator._next_task_id()
                    await self.context_db.create_pm_task(
                        task_id=parent_id,
                        description=request_text[:500],
                        assigned_dept=self.org_id,
                        created_by=self.org_id,
                        metadata={"interaction_mode": "collab", "collab_topic": request_text},
                    )
                    if collab_target is not None:
                        collab_participants = [collab_target]
                    else:
                        collab_participants = self._pm_orchestrator._select_debate_participants(
                            plan.dept_hints, request_text
                        )
                    if collab_participants:
                        participants_display = ", ".join(collab_participants)
                        await self.display.send_reply(
                            update.message,
                            f"🤝 협업을 시작합니다\n주제: {request_text[:100]}\n참여: {participants_display}",
                        )
                        for p in collab_participants:
                            await self._pm_orchestrator.collab_dispatch(
                                parent_task_id=parent_id,
                                task=request_text,
                                target_org=p,
                                requester_org=self.org_id,
                                context="",
                                chat_id=update.effective_chat.id,
                            )
                        return

                if plan.interaction_mode == "debate" and ENABLE_DISCUSSION_PROTOCOL:
                    participants = self._pm_orchestrator._select_debate_participants(
                        plan.dept_hints, request_text
                    )
                    if len(participants) >= 2:
                        bot_names = ", ".join(participants)
                        await self.display.send_reply(
                            update.message,
                            f"🥊 토론을 시작합니다\n"
                            f"주제: {request_text[:100]}\n"
                            f"참여 봇: {bot_names}",
                        )
                        parent_id = await self._pm_orchestrator._next_task_id()
                        await self.context_db.create_pm_task(
                            task_id=parent_id,
                            description=text[:500],
                            assigned_dept=self.org_id,
                            created_by=self.org_id,
                            metadata={
                                "route": plan.route,
                                "lane": plan.lane,
                                "complexity": plan.complexity,
                                "rationale": plan.rationale,
                                "original_request": text[:2000],
                            },
                        )
                        await self._pm_orchestrator.debate_dispatch(
                            parent_task_id=parent_id,
                            topic=request_text,
                            participants=participants,
                            chat_id=update.effective_chat.id,
                        )
                        return

                await self.display.send_reply(update.message, "여러 팀이 같이 해야 할 것 같아서 오케스트레이터한테 넘길게요 📋")
                run_id = self._create_runbook(request_text)
                conversation_context = await self._build_conversation_context_packet(
                    text,
                    replied_context=_replied_context,
                )
                user_expectations = self._build_user_expectations(text)
                self._advance_runbook(run_id, "오케스트레이션 계획 수립 시작")
                self._append_runbook(
                    run_id,
                    "Planning rationale",
                    f"lane={plan.lane}\nroute={plan.route}\ncomplexity={plan.complexity}\nrationale={plan.rationale}\ndept_hints={', '.join(plan.dept_hints)}",
                    phase_name="planning",
                )
                parent_id = await self._pm_orchestrator._next_task_id()
                await self.context_db.create_pm_task(
                    task_id=parent_id,
                    description=text[:500],
                    assigned_dept=self.org_id,
                    created_by=self.org_id,
                    metadata={
                        "route": plan.route,
                        "lane": plan.lane,
                        "complexity": plan.complexity,
                        "rationale": plan.rationale,
                        "run_id": run_id,
                        "original_request": text[:2000],
                        "conversation_context": conversation_context,
                        "user_expectations": user_expectations,
                        "source_message_id": update.message.message_id if update.message else None,
                        "requester_mention": self._user_mention(update.effective_user),
                        "source_org_mention": self._org_mention(self.org_id),
                    },
                )
                subtasks = await self._pm_orchestrator.decompose(request_text)
                await self._pm_orchestrator.dispatch(
                    parent_id,
                    subtasks,
                    self.allowed_chat_id,
                    rationale=plan.rationale,
                )
                dept_list = ", ".join(
                    KNOWN_DEPTS.get(st.assigned_dept, st.assigned_dept) for st in subtasks
                )
                self._advance_runbook(run_id, "부서 분해 완료, design phase로 이동")
                self._append_runbook(
                    run_id,
                    "Design summary",
                    "\n".join(
                        f"- {KNOWN_DEPTS.get(st.assigned_dept, st.assigned_dept)}: {st.description[:140]}"
                        for st in subtasks
                    ),
                    phase_name="design",
                )
                self._advance_runbook(run_id, "조직 배분 완료, implementation phase로 이동")
                self._append_runbook(
                    run_id,
                    "Implementation dispatch",
                    f"delegated departments: {dept_list}",
                    phase_name="implementation",
                )
                await self.display.send_reply(
                    update.message,
                    f"{dept_list}에 부탁드렸어요 🙌 각 팀에서 처리해줄 거예요!",
                )
            except Exception as e:
                logger.error(f"[PM] 오케스트레이터 분해 실패: {e}")
                await self.display.send_reply(update.message, f"❌ 태스크 분해 실패: {e}")
            return

        # 4. 담당 선언 + 실행 (모델 기반 팀 구성)
        await self.display.send_reply(update.message, "저희가 맡을게요! 팀 꾸리는 중이에요 ✋")
        run_id = self._create_runbook(text)
        self._advance_runbook(run_id, "요청 접수 후 planning phase로 이동")
        team_config = await self._build_team_config(text)
        brief = self._format_execution_brief(
            text,
            team_config,
            owner_label=self.org_id,
            route_label="조직 직접 실행",
            route_kind="local_execution",
        )
        self._append_runbook(run_id, "Planning brief", brief, phase_name="planning")
        self._advance_runbook(run_id, "계획 공유 완료, design phase로 이동")
        self._append_runbook(
            run_id,
            "Design summary",
            f"engine={team_config.engine}\nmode={team_config.execution_mode.value}\nagents={', '.join(p.name for p in team_config.agents)}",
            phase_name="design",
        )
        self._advance_runbook(run_id, "설계 공유 완료, implementation phase로 이동")

        progress_msg = await self.display.send_reply(update.message, "알겠어요, 바로 시작할게요! ⚙️")
        history: list[str] = []
        last_edit = time.time()
        progress_interval = self._progress_interval()
        history_limit = self._progress_history_limit()

        async def on_progress(line: str) -> None:
            nonlocal last_edit
            if not self._show_progress():
                return
            stripped = self._clean_progress_line(line)
            if not stripped:
                return
            history.append(stripped)
            if time.time() - last_edit > progress_interval:
                display = "\n".join(history[-history_limit:])
                try:
                    await self.display.edit_progress(
                        progress_msg,
                        f"중간 상황 공유할게요!\n\n{display}",
                        agent_id=self.org_id,
                    )
                    last_edit = time.time()
                except Exception:
                    pass

        response = await self._execute_with_team_config(
            task=text,
            system_prompt=self.identity.build_system_prompt(),
            team_config=team_config,
            progress_callback=on_progress,
            route_kind="local_execution",
        )
        upload_candidates = extract_local_artifact_paths(response or "")
        self._append_runbook(
            run_id,
            "Implementation result",
            (response or "(결과 없음)")[:6000],
            phase_name="implementation",
        )
        self._advance_runbook(run_id, "실행 완료, verification phase로 이동")

        try:
            await progress_msg.edit_text("다 됐어요! ✅")
        except Exception:
            pass

        response = await self._handle_collab_tags(
            response,
            bot=context.bot,
            chat_id=update.effective_chat.id,
            requester_mention=self._user_mention(update.effective_user),
            reply_to_message_id=update.message.message_id if update.message else None,
        )

        if response:
            response = await ensure_user_friendly_output(
                response,
                original_request=text,
                decision_client=self._pm_decision_client if self._is_pm_org else None,
            )
            for chunk in split_message(response, 4000):
                await self.display.send_reply(update.message, chunk)
            await self._auto_upload("\n".join(upload_candidates), self.token, update.effective_chat.id)
            await self.memory_manager.add_log(f"claude 응답: {response[:200]}")
            if self.bus:
                await self.bus.publish(Event(
                    type=EventType.TASK_RESULT,
                    source=self.org_id,
                    data={"response": response[:500], "message_id": message_id},
                ))
        self._append_runbook(
            run_id,
            "Verification summary",
            f"응답 길이: {len(response or '')}\n조직 직접 실행 검증 단계 완료.",
            phase_name="verification",
        )
        self._advance_runbook(run_id, "검증 완료, feedback phase로 이동")
        self._append_runbook(
            run_id,
            "Feedback",
            "후속 요청 시 현재 결과를 기반으로 refinement 한다.",
            phase_name="feedback",
        )
        self._complete_runbook(run_id, "조직 직접 실행 완료")
        if self.bus:
            asyncio.ensure_future(self._p2p.notify_task_done(self.org_id, run_id or "", response[:200] if response else "완료"))

    # ── 첨부파일 처리 ──────────────────────────────────────────────────────

    async def on_attachment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """문서/이미지 수신 → 로컬 저장 → claude에 전달."""
        msg = update.message
        if msg is None:
            return
        if update.effective_chat is None or update.effective_chat.id != self.allowed_chat_id:
            return
        if self._is_dept_org:
            logger.debug(f"[{self.org_id}] PM 오케스트레이터 활성 — 일반 사용자 첨부 무시")
            return

        save_dir = Path.home() / ".ai-org" / "uploads"
        save_dir.mkdir(parents=True, exist_ok=True)

        attachment = await self._download_attachment_context(msg, context, save_dir)
        if attachment is None:
            return

        attachment.analysis_text = await self._attachment_analyzer.analyze(attachment)

        media_group_id = getattr(msg, "media_group_id", None)
        if media_group_id:
            await self._queue_attachment_group(update.effective_chat.id, media_group_id, attachment, msg)
            return

        await self._process_attachment_bundle(AttachmentBundle(items=[attachment], caption=attachment.caption), msg)

    async def _download_attachment_context(self, msg, context, save_dir: Path) -> AttachmentContext | None:
        if msg.document:
            tg_file = await context.bot.get_file(msg.document.file_id)
            filename = msg.document.file_name or f"doc_{msg.message_id}"
            save_path = save_dir / filename
            await tg_file.download_to_drive(save_path)
            caption = msg.caption or f"{filename} 파일을 분석해줘"
            return AttachmentContext.from_local_file(
                kind="document",
                local_path=save_path,
                caption=caption,
                original_filename=filename,
                mime_type=msg.document.mime_type or "",
            )
        if msg.photo:
            photo = msg.photo[-1]
            tg_file = await context.bot.get_file(photo.file_id)
            save_path = save_dir / f"photo_{msg.message_id}.jpg"
            await tg_file.download_to_drive(save_path)
            caption = msg.caption or "이 이미지를 분석해줘"
            return AttachmentContext.from_local_file(
                kind="photo",
                local_path=save_path,
                caption=caption,
                original_filename=save_path.name,
                mime_type="image/jpeg",
            )
        if msg.video:
            tg_file = await context.bot.get_file(msg.video.file_id)
            filename = msg.video.file_name or f"video_{msg.message_id}.mp4"
            save_path = save_dir / filename
            await tg_file.download_to_drive(save_path)
            caption = msg.caption or f"{filename} 비디오를 분석해줘"
            return AttachmentContext.from_local_file(
                kind="video",
                local_path=save_path,
                caption=caption,
                original_filename=filename,
                mime_type=msg.video.mime_type or "video/mp4",
            )
        if msg.audio:
            tg_file = await context.bot.get_file(msg.audio.file_id)
            filename = msg.audio.file_name or f"audio_{msg.message_id}.mp3"
            save_path = save_dir / filename
            await tg_file.download_to_drive(save_path)
            caption = msg.caption or f"{filename} 오디오를 분석해줘"
            return AttachmentContext.from_local_file(
                kind="audio",
                local_path=save_path,
                caption=caption,
                original_filename=filename,
                mime_type=msg.audio.mime_type or "audio/mpeg",
            )
        if msg.voice:
            tg_file = await context.bot.get_file(msg.voice.file_id)
            save_path = save_dir / f"voice_{msg.message_id}.ogg"
            await tg_file.download_to_drive(save_path)
            caption = msg.caption or "이 음성 메시지를 분석해줘"
            return AttachmentContext.from_local_file(
                kind="voice",
                local_path=save_path,
                caption=caption,
                original_filename=save_path.name,
                mime_type="audio/ogg",
            )
        return None

    async def _queue_attachment_group(self, chat_id: int, media_group_id: str, attachment: AttachmentContext, msg) -> None:
        key = (chat_id, media_group_id)
        state = self._attachment_groups.setdefault(key, _AttachmentGroupState())
        state.items.append(attachment)
        if attachment.caption and not state.caption:
            state.caption = attachment.caption
        if state.message is None:
            state.message = msg
        if state.task and not state.task.done():
            state.task.cancel()
        state.task = asyncio.create_task(self._flush_attachment_group_after_delay(key))

    async def _flush_attachment_group_after_delay(self, key: tuple[int, str]) -> None:
        try:
            await asyncio.sleep(ATTACHMENT_GROUP_DEBOUNCE_SEC)
        except asyncio.CancelledError:
            return
        state = self._attachment_groups.pop(key, None)
        if state is None or not state.items or state.message is None:
            return
        bundle = AttachmentBundle(items=state.items, caption=state.caption)
        await self._process_attachment_bundle(bundle, state.message)

    async def _process_attachment_bundle(self, bundle: AttachmentBundle, msg) -> None:
        attachment_names = ", ".join(item.local_path.name for item in bundle.items)

        await msg.reply_text(f"📎 파일 수신: {attachment_names}\n처리 중...")
        logger.info(f"[on_attachment] 저장: {attachment_names}")

        task = bundle.build_task_prompt()
        score = await self.confidence_scorer.score(task, self.identity)
        is_default = self.identity._data.get("default_handler", False)
        if score < DEFAULT_CONFIDENCE_THRESHOLD and not is_default:
            return

        message_id = str(msg.message_id) + "_att"
        if not self.claim_manager.try_claim(message_id, self.org_id):
            return

        await self._execute_task(task, msg)

    async def _execute_task(self, task: str, msg: object) -> None:
        """태스크 실행 공통 로직 (progress 스트리밍 + 결과 전송)."""
        system_prompt = self.identity.build_system_prompt()
        requester_mention = self._user_mention(getattr(msg, "from_user", None))
        reply_to_message_id = getattr(msg, "message_id", None)
        run_id = self._create_runbook(task)
        self._advance_runbook(run_id, "첨부파일 실행 planning phase 시작")
        team_config = await self._build_team_config(task)
        brief = self._format_execution_brief(
            task,
            team_config,
            owner_label=self.org_id,
            route_label="첨부파일 포함 직접 실행",
            route_kind="local_execution",
        )
        self._append_runbook(run_id, "Planning brief", brief, phase_name="planning")
        await msg.reply_text(
            brief
        )
        self._advance_runbook(run_id, "첨부파일 실행 plan 공유 완료")
        self._append_runbook(
            run_id,
            "Design summary",
            f"engine={team_config.engine}\nmode={team_config.execution_mode.value}\nagents={', '.join(p.name for p in team_config.agents)}",
            phase_name="design",
        )
        self._advance_runbook(run_id, "첨부파일 실행 implementation phase 이동")

        progress_msg = await msg.reply_text("⚙️ 처리 중...")
        history: list[str] = []
        last_edit = time.time()
        progress_interval = self._progress_interval()
        history_limit = self._progress_history_limit()

        async def on_progress(line: str) -> None:
            nonlocal last_edit
            if not self._show_progress():
                return
            stripped = self._clean_progress_line(line)
            if not stripped:
                return
            history.append(stripped)
            if time.time() - last_edit > progress_interval:
                display = "\n".join(history[-history_limit:])
                try:
                    await progress_msg.edit_text(f"중간 상황 공유할게요!\n\n{display}")
                    last_edit = time.time()
                except Exception:
                    pass

        response = await self._execute_with_team_config(
            task=task,
            system_prompt=system_prompt,
            team_config=team_config,
            progress_callback=on_progress,
            route_kind="local_execution",
        )
        upload_candidates = extract_local_artifact_paths(response or "")
        self._append_runbook(
            run_id,
            "Implementation result",
            (response or "(결과 없음)")[:6000],
            phase_name="implementation",
        )
        self._advance_runbook(run_id, "첨부파일 실행 완료, verification phase 이동")

        try:
            await progress_msg.edit_text("다 됐어요! ✅")
        except Exception:
            pass

        if response:
            response = await self._handle_collab_tags(
                response,
                bot=self.app.bot if self.app else None,
                chat_id=self.allowed_chat_id,
                requester_mention=requester_mention,
                reply_to_message_id=reply_to_message_id,
            )
            response = await ensure_user_friendly_output(
                response,
                original_request=task,
                decision_client=self._pm_decision_client if self._is_pm_org else None,
            )
            for chunk in split_message(response, 4000):
                await msg.reply_text(chunk)
            await self._auto_upload("\n".join(upload_candidates), self.token, self.allowed_chat_id)
            await self.memory_manager.add_log(f"claude 응답: {response[:200]}")
        self._append_runbook(
            run_id,
            "Verification summary",
            "첨부파일 포함 실행 결과를 검토했다.",
            phase_name="verification",
        )
        self._advance_runbook(run_id, "첨부파일 실행 feedback phase 이동")
        self._append_runbook(
            run_id,
            "Feedback",
            "첨부파일 기반 실행 완료.",
            phase_name="feedback",
        )
        self._complete_runbook(run_id, "첨부파일 실행 완료")
        if self.bus:
            asyncio.ensure_future(self._p2p.notify_task_done(self.org_id, run_id or "", locals().get("response", "첨부파일 처리 완료")[:200] if locals().get("response") else "첨부파일 처리 완료"))

    # ── 명령 처리 ──────────────────────────────────────────────────────────

    async def on_command_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """PM 세션 없으면 생성 + 메모리 주입 후 /start."""
        if update.message is None:
            return

        initialized = self._ensure_runtime_bootstrap()

        if initialized:
            await update.message.reply_text(
                "🤖 **PM Bot 온라인**\n\n"
                "tmux 세션에서 Claude Code가 실행 중입니다.\n"
                "무엇이든 말씀하세요 — 메시지를 Claude에게 전달합니다.\n\n"
                "/status — 세션 상태 확인",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text("✅ 이미 실행 중인 세션에 연결됩니다.")

    def _ensure_runtime_bootstrap(self) -> bool:
        existed = self.session_manager.session_exists(TEAM_ID)
        self.session_manager.ensure_session(TEAM_ID)
        if existed:
            return False
        ctx = self.memory_manager.build_context()
        if ctx:
            self.session_manager.inject_context(TEAM_ID, ctx)
        # CLAUDE.md에 BM25 메모리 동적 기록 (Claude Code 자동 읽기)
        try:
            memory_ctx = self.memory_manager.build_context()
            if memory_ctx:
                self.session_manager.write_memory_to_claude_md(TEAM_ID, memory_ctx)
        except Exception as _e:
            logger.debug(f"[{self.org_id}] CLAUDE.md 갱신 실패(무시): {_e}")
        return True

    async def on_self_added_to_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """봇이 그룹에 추가되면 /start 없이 자동 초기화한다."""
        if update.message is None or update.effective_chat is None:
            return
        if update.effective_chat.id != self.allowed_chat_id:
            return
        new_members = getattr(update.message, "new_chat_members", None) or []
        if not new_members:
            return
        me = await context.bot.get_me()
        if not any(member.id == me.id for member in new_members):
            return

        initialized = self._ensure_runtime_bootstrap()
        specialties = self.identity.get_specialty_text() or "미설정"
        if initialized:
            text = (
                "✅ 봇 초기화 완료\n\n"
                f"조직: {self.org_id}\n"
                f"전문분야: {specialties}\n\n"
                "이제 바로 메시지를 보내면 됩니다. 별도 `/start` 나 `/org` 초기 설정은 필요하지 않습니다."
            )
        else:
            text = "✅ 이미 준비된 세션에 연결되어 있습니다. 바로 사용하시면 됩니다."
        await update.message.reply_text(text)

    async def on_command_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """세션 상태, 메모리 크기, PM 정체성 출력."""
        if update.message is None:
            return

        try:
            sess_status = self.session_manager.status()
            mem_stats = self.memory_manager.stats()
            specialties = self.identity.get_specialty_text() or "없음"
            text = (
                f"📊 세션 상태\n"
                f"• tmux 사용 가능: {sess_status.get('tmux', False)}\n"
                f"• 활성 세션: {', '.join(sess_status.get('sessions', [])) or '없음'}\n\n"
                f"🏷️ PM 정체성 [{self.org_id}]\n"
                f"• 전문분야: {specialties}\n\n"
                f"🧠 메모리 ({mem_stats['scope']})\n"
                f"• CORE: {mem_stats['core']}개\n"
                f"• SUMMARY: {mem_stats['summary']}개\n"
                f"• LOG: {mem_stats['log']}개\n\n"
                f"메시지 카운터: {self._message_count}"
            )
            await update.message.reply_text(text)
        except Exception as e:
            logger.error(f"/status 처리 실패: {e}")
            await update.message.reply_text(f"⚠️ 상태 조회 실패: {e}")

    async def on_command_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """세션 writeback + 리셋."""
        if update.message is None:
            return

        await update.message.reply_text("🔄 세션 writeback 후 리셋 중...")
        try:
            await self.session_manager.writeback_and_reset(TEAM_ID, self.memory_manager)
            self._message_count = 0
            self.session_store.reset()
            await update.message.reply_text("✅ 새 세션으로 시작합니다. 대화 기록도 초기화했습니다.")
        except Exception as e:
            logger.error(f"리셋 실패: {e}")
            await update.message.reply_text(f"❌ 리셋 실패: {e}")

    # ── 사용자 스케줄 커맨드 (pm_org 전용) ───────────────────────────────

    async def on_command_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/schedule [자연어 텍스트] — 새 스케줄 등록."""
        if update.message is None:
            return
        if not self._is_pm_org or self._schedule_store is None or self._nl_parser is None:
            await update.message.reply_text("❌ 이 봇에서는 스케줄 기능을 사용할 수 없습니다.")
            return
        text = " ".join(context.args) if context.args else ""
        if not text:
            await update.message.reply_text(
                "사용법: /schedule [자연어 스케줄]\n"
                "예시:\n"
                "  /schedule 매일 오전 9시에 AI 뉴스 요약\n"
                "  /schedule 매주 월요일 오전 10시에 팀 리포트 확인\n"
                "  /schedule 매달 1일 오전 9시에 월간 보고서 생성"
            )
            return
        try:
            from apscheduler.triggers.cron import CronTrigger as _CronTrigger
            parsed = self._nl_parser.parse(text)
            # cron 표현식 유효성 검증 (APScheduler로 실제 파싱 시도)
            _CronTrigger.from_crontab(parsed["cron_expr"], timezone="Asia/Seoul")
            loop = asyncio.get_event_loop()
            sched = await loop.run_in_executor(
                None, self._schedule_store.add, text, parsed["cron_expr"], parsed["task_description"]
            )
            if self._org_scheduler is not None:
                self._org_scheduler.add_user_job(sched)
            await update.message.reply_text(
                f"✅ 스케줄 등록!\n"
                f"📋 ID: {sched.id}\n"
                f"⏰ {parsed['human_readable']}\n"
                f"📝 {parsed['task_description']}"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ 등록 실패: {e}")

    async def on_command_schedules(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/schedules — 등록된 스케줄 목록."""
        if update.message is None:
            return
        if not self._is_pm_org or self._schedule_store is None:
            return
        loop = asyncio.get_event_loop()
        schedules = await loop.run_in_executor(None, self._schedule_store.list_all)
        if not schedules:
            await update.message.reply_text("등록된 스케줄이 없습니다.")
            return
        lines = ["📋 *등록된 스케줄 목록*\n"]
        for s in schedules:
            status = "✅" if s.enabled else "⏸️"
            lines.append(f"{status} ID:{s.id} | `{s.cron_expr}` | {s.task_description}")
        lines.append(
            "\n취소: /cancel\\_schedule [id]  일시중지: /pause\\_schedule [id]  재개: /resume\\_schedule [id]"
        )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def on_command_cancel_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/cancel_schedule [id] — 스케줄 영구 삭제."""
        if update.message is None:
            return
        if not self._is_pm_org or self._schedule_store is None:
            return
        if not context.args:
            await update.message.reply_text("사용법: /cancel_schedule [스케줄 ID]")
            return
        try:
            schedule_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ 유효하지 않은 ID입니다.")
            return
        loop = asyncio.get_event_loop()
        deleted = await loop.run_in_executor(None, self._schedule_store.delete, schedule_id)
        if deleted:
            if self._org_scheduler is not None:
                self._org_scheduler.remove_user_job(schedule_id)
            await update.message.reply_text(f"🗑️ 스케줄 ID {schedule_id} 삭제 완료.")
        else:
            await update.message.reply_text(f"❌ ID {schedule_id}를 찾을 수 없습니다.")

    async def on_command_pause_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/pause_schedule [id] — 스케줄 일시중지."""
        if update.message is None:
            return
        if not self._is_pm_org or self._schedule_store is None:
            return
        if not context.args:
            await update.message.reply_text("사용법: /pause_schedule [스케줄 ID]")
            return
        try:
            schedule_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ 유효하지 않은 ID입니다.")
            return
        loop = asyncio.get_event_loop()
        disabled = await loop.run_in_executor(None, self._schedule_store.disable, schedule_id)
        if disabled:
            if self._org_scheduler is not None:
                self._org_scheduler.remove_user_job(schedule_id)
            await update.message.reply_text(f"⏸️ 스케줄 ID {schedule_id} 일시중지.")
        else:
            await update.message.reply_text(f"❌ ID {schedule_id}를 찾을 수 없습니다.")

    async def on_command_resume_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/resume_schedule [id] — 스케줄 재개."""
        if update.message is None:
            return
        if not self._is_pm_org or self._schedule_store is None:
            return
        if not context.args:
            await update.message.reply_text("사용법: /resume_schedule [스케줄 ID]")
            return
        try:
            schedule_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ 유효하지 않은 ID입니다.")
            return
        loop = asyncio.get_event_loop()
        sched = await loop.run_in_executor(None, self._schedule_store.get_by_id, schedule_id)
        if sched is None:
            await update.message.reply_text(f"❌ ID {schedule_id}를 찾을 수 없습니다.")
            return
        enabled = await loop.run_in_executor(None, self._schedule_store.enable, schedule_id)
        if enabled:
            sched.enabled = True
            if self._org_scheduler is not None:
                self._org_scheduler.add_user_job(sched)
            await update.message.reply_text(f"▶️ 스케줄 ID {schedule_id} 재개.")
        else:
            await update.message.reply_text(f"❌ 재개 실패: ID {schedule_id}")

    async def on_command_stop_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """현재 진행 중인 tmux 세션 전체 종료. PM봇 전용."""
        if update.message is None:
            return
        if not self._is_pm_org:
            return

        sessions = self.session_manager.list_sessions()
        if not sessions:
            await update.message.reply_text("ℹ️ 현재 실행 중인 세션이 없습니다.")
            return

        prefix = "aiorg_"
        stopped = []
        for session_name in sessions:
            team_id = session_name[len(prefix):] if session_name.startswith(prefix) else session_name
            try:
                self.session_manager.kill_session(team_id)
                stopped.append(session_name)
            except Exception as exc:
                logger.warning(f"[stop_tasks] 세션 종료 실패 {session_name}: {exc}")

        if stopped:
            await update.message.reply_text(
                f"🛑 작업 종료 완료\n종료된 세션: {', '.join(stopped)}"
            )
        else:
            await update.message.reply_text("⚠️ 세션 종료 중 오류가 발생했습니다.")

    async def on_command_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """봇 전체 재시작 (scripts/restart_bots.sh 실행). PM봇 전용."""
        if update.message is None:
            return
        if not self._is_pm_org:
            return

        await update.message.reply_text("🔄 봇 재시작 중... (약 5초 후 다시 온라인 됩니다)")
        import asyncio as _asyncio
        project_dir = Path(__file__).parent.parent
        restart_script = project_dir / "scripts" / "restart_bots.sh"
        try:
            proc = await _asyncio.create_subprocess_exec(
                "bash", str(restart_script),
                stdout=_asyncio.subprocess.DEVNULL,
                stderr=_asyncio.subprocess.DEVNULL,
                cwd=str(project_dir),
            )
            _asyncio.create_task(proc.wait())
        except Exception as exc:
            logger.error(f"/restart 실패: {exc}")
            await update.message.reply_text(f"❌ 재시작 실패: {exc}")

    async def on_command_set_engine(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/set_engine <engine> — bots/*.yaml 엔진 변경 후 재시작. PM봇 전용."""
        if update.message is None:
            return
        if not self._is_pm_org:
            return

        args = (update.message.text or "").split()
        if len(args) < 2:
            await update.message.reply_text(
                "사용법: /set_engine <engine>\n예: /set_engine claude-code"
            )
            return

        engine = args[1].strip()
        _VALID_ENGINES = {"claude-code", "codex"}
        if engine not in _VALID_ENGINES:
            await update.message.reply_text(
                f"❌ 유효하지 않은 엔진: {engine}\n사용 가능: {', '.join(sorted(_VALID_ENGINES))}"
            )
            return

        import yaml as _yaml
        project_dir = Path(__file__).parent.parent
        bots_dir = project_dir / "bots"
        updated = []
        errors = []

        # 1) bots/*.yaml 업데이트
        for yaml_path in sorted(bots_dir.glob("*.yaml")):
            try:
                data = _yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                if data.get("engine") != engine:
                    data["engine"] = engine
                    yaml_path.write_text(
                        _yaml.dump(data, allow_unicode=True, sort_keys=False),
                        encoding="utf-8",
                    )
                    updated.append(yaml_path.stem)
            except Exception as exc:
                logger.warning(f"[set_engine] {yaml_path.name} 수정 실패: {exc}")
                errors.append(yaml_path.stem)

        # 2) organizations.yaml preferred_engine / fallback_engine 업데이트
        org_yaml_path = project_dir / "organizations.yaml"
        try:
            org_data = _yaml.safe_load(org_yaml_path.read_text(encoding="utf-8")) or {}
            org_changed = False
            for org in org_data.get("organizations", []):
                exec_block = org.setdefault("execution", {})
                if exec_block.get("preferred_engine") != engine:
                    exec_block["preferred_engine"] = engine
                    org_changed = True
                if exec_block.get("fallback_engine") != engine:
                    exec_block["fallback_engine"] = engine
                    org_changed = True
            if org_changed:
                org_yaml_path.write_text(
                    _yaml.dump(org_data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8",
                )
                updated.append("organizations")
        except Exception as exc:
            logger.warning(f"[set_engine] organizations.yaml 수정 실패: {exc}")
            errors.append("organizations")

        if not updated and not errors:
            await update.message.reply_text(f"ℹ️ 모든 봇이 이미 {engine} 엔진을 사용 중입니다.")
            return

        msg = f"⚙️ 엔진 변경: {engine}\n"
        if updated:
            msg += f"• 업데이트: {', '.join(updated)}\n"
        if errors:
            msg += f"• 실패: {', '.join(errors)}\n"
        msg += "\n🔄 재시작 중..."
        await update.message.reply_text(msg)

        import asyncio as _asyncio
        restart_script = project_dir / "scripts" / "restart_bots.sh"
        try:
            proc = await _asyncio.create_subprocess_exec(
                "bash", str(restart_script),
                stdout=_asyncio.subprocess.PIPE,
                stderr=_asyncio.subprocess.PIPE,
                cwd=str(project_dir),
            )
            _, stderr = await _asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode != 0:
                logger.error(f"[set_engine] 재시작 실패 (rc={proc.returncode}): {stderr.decode()[:200]}")
                await update.message.reply_text(f"❌ 재시작 실패 (rc={proc.returncode})")
        except _asyncio.TimeoutError:
            logger.warning("[set_engine] 재시작 타임아웃 — 백그라운드에서 계속 실행 중일 수 있음")
        except Exception as exc:
            logger.error(f"[set_engine] 재시작 실패: {exc}")
            await update.message.reply_text(f"❌ 재시작 실패: {exc}")

    async def on_command_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """설정 마법사 진입 — 메뉴 표시."""
        if update.message is None:
            return ConversationHandler.END
        keyboard = [
            [InlineKeyboardButton("📋 현재 봇 설정 보기", callback_data="setup_view")],
            [InlineKeyboardButton("🤖 새 조직 봇 추가 (토큰 입력)", callback_data="setup_add")],
            [InlineKeyboardButton("❌ 취소", callback_data="setup_cancel")],
        ]
        await update.message.reply_text(
            "🔧 *봇 설정 마법사*\n\n원하는 작업을 선택하세요:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return SETUP_MENU

    async def _setup_callback_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """메뉴 버튼 선택 처리."""
        query = update.callback_query
        await query.answer()

        if query.data == "setup_view":
            me = await query.bot.get_me()
            bot_name = me.username or "봇이름"
            d = self.identity._data
            msg = (
                f"🔧 *{self.org_id} 봇 현재 설정*\n\n"
                f"역할: {d.get('role', '미설정')}\n"
                f"전문분야: {', '.join(d.get('specialties', [])) or '미설정'}\n"
                f"방향성: {d.get('direction', '미설정')}\n\n"
                f"*설정 변경 명령어*\n"
                f"`/org@{bot_name} 역할|전문분야1,분야2|방향성`\n"
                f"`/org add@{bot_name} <이름> [engine]`\n\n"
                f"💡 그룹방에서는 `/명령어@{bot_name}` 형식으로 사용하세요."
            )
            await query.edit_message_text(msg, parse_mode="Markdown")
            return ConversationHandler.END

        elif query.data == "setup_add":
            await query.edit_message_text(
                "🤖 *새 조직 봇 추가*\n\n"
                "BotFather에서 발급받은 토큰을 입력하세요:\n\n"
                "⚠️ 보안: 토큰 메시지는 즉시 삭제됩니다.\n"
                "취소하려면 /cancel 을 입력하세요.",
                parse_mode="Markdown",
            )
            return SETUP_AWAIT_TOKEN

        else:  # setup_cancel
            await query.edit_message_text("❌ 설정 취소됨.")
            return ConversationHandler.END

    async def _setup_receive_token(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """토큰 수신 → 검증 → 등록 → 봇 실행."""
        if update.message is None:
            return SETUP_AWAIT_TOKEN

        token = (update.message.text or "").strip()

        # 보안: 토큰 메시지 즉시 삭제
        try:
            await update.message.delete()
        except Exception:
            pass

        processing_msg = await update.effective_chat.send_message("🔍 토큰 검증 중...")

        bot_info = await _validate_bot_token(token)
        if not bot_info:
            await processing_msg.edit_text(
                "❌ 유효하지 않은 토큰입니다.\n\n"
                "토큰을 다시 입력하거나 /cancel 로 취소하세요."
            )
            return SETUP_AWAIT_TOKEN

        username = bot_info["username"]
        bot_display = bot_info["first_name"]
        chat_id = update.effective_chat.id

        # 토큰 임시 저장 후 엔진 선택 단계로 진행
        context.user_data["setup_token"] = token
        context.user_data["setup_username"] = username
        context.user_data["setup_bot_display"] = bot_display
        context.user_data["setup_chat_id"] = chat_id

        keyboard = [
            [InlineKeyboardButton("1️⃣ Claude Code (기본, 권장)", callback_data="engine_claude-code")],
            [InlineKeyboardButton("2️⃣ Codex", callback_data="engine_codex")],
            [InlineKeyboardButton("3️⃣ Auto (자동 결정)", callback_data="engine_auto")],
        ]
        await processing_msg.edit_text(
            f"✅ 봇 확인: *@{username}*\n\n"
            f"⚙️ *실행 엔진을 선택하세요:*\n\n"
            f"1️⃣ `claude-code` — 복잡한 작업, 고품질 *(기본)*\n"
            f"2️⃣ `codex` — 단순한 작업, 저렴\n"
            f"3️⃣ `auto` — LLM이 자동 결정",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return SETUP_AWAIT_ENGINE

    async def _setup_receive_engine(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """엔진 선택 콜백 → 조직 정체성 입력 단계."""
        query = update.callback_query
        await query.answer()

        engine = (query.data or "").replace("engine_", "") or "claude-code"
        username = context.user_data.get("setup_username", "")
        context.user_data["setup_engine"] = engine

        _engine_labels = {
            "claude-code": "Claude Code",
            "codex": "Codex",
            "auto": "자동 결정",
        }
        identity = default_identity_for_org(username)
        specialty_text = ",".join(identity.specialties) if identity.specialties else ""
        await query.edit_message_text(
            f"✅ 엔진 선택: `{engine}` — {_engine_labels.get(engine, engine)}\n\n"
            "🏷️ *조직 정체성을 입력하세요.*\n"
            "형식: `역할|전문분야1,전문분야2|방향성`\n\n"
            f"기본값:\n`{identity.role}|{specialty_text}|{identity.direction}`\n\n"
            "기본값을 그대로 쓰려면 `기본` 이라고 입력하세요.",
            parse_mode="Markdown",
        )
        return SETUP_AWAIT_IDENTITY

    async def _setup_receive_identity(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """조직 정체성 수신 → 등록 완료."""
        if update.message is None:
            return SETUP_AWAIT_IDENTITY

        token = context.user_data.get("setup_token", "")
        username = context.user_data.get("setup_username", "")
        bot_display = context.user_data.get("setup_bot_display", "")
        chat_id = context.user_data.get("setup_chat_id", 0)
        engine = context.user_data.get("setup_engine", "claude-code")
        raw_identity = (update.message.text or "").strip()

        _engine_labels = {
            "claude-code": "Claude Code",
            "codex": "Codex",
            "auto": "자동 결정",
        }
        processing_msg = await update.effective_chat.send_message("⚙️ 조직 등록 중...")

        try:
            identity = parse_setup_identity(username, raw_identity)
            env_key = f"BOT_TOKEN_{username.upper().replace('-', '_')}"
            upsert_runtime_env_var(Path(__file__).parent.parent, env_key, token)
            upsert_org_in_canonical_config(
                Path(__file__).parent.parent,
                username=username,
                token_env=env_key,
                chat_id=chat_id,
                engine=engine,
                identity=identity,
            )
            refresh_legacy_bot_configs(Path(__file__).parent.parent)
            refresh_pm_identity_files(Path(__file__).parent.parent)
            pid = _launch_bot_subprocess(token, username, chat_id)
            org_kind = _profile_bundle_for_org(username)["kind"]
            await _set_org_bot_commands(token, kind=org_kind)

            await processing_msg.edit_text(
                f"✅ *@{username} 등록 완료!*\n\n"
                f"봇 이름: {bot_display}\n"
                f"역할: {identity.role}\n"
                f"전문분야: {', '.join(identity.specialties) or '미설정'}\n"
                f"엔진: `{engine}` ({_engine_labels.get(engine, engine)})\n"
                f"PID: {pid}\n\n"
                "canonical config / PM identity / bot commands 동기화 완료\n"
                "봇이 시작되었습니다. 그룹방에 초대하면 자동으로 초기화됩니다.\n"
                "별도 `/org` 나 `/start` 초기 설정은 필요하지 않습니다.",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"봇 등록 실패: {e}")
            await processing_msg.edit_text(f"❌ 등록 실패: {e}")

        return ConversationHandler.END

    async def _setup_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """설정 마법사 취소."""
        if update.message:
            await update.message.reply_text("❌ 설정 취소됨.")
        return ConversationHandler.END

    # ── 앱 빌드 ───────────────────────────────────────────────────────────

    async def _post_init(self, application: Application) -> None:
        """Application 초기화 후 백그라운드 작업 시작."""
        # 재시작 시 stale 'running' 태스크 → 'assigned' 리셋
        if self.context_db is not None:
            try:
                import aiosqlite as _aiosqlite
                cutoff = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
                async with _aiosqlite.connect(self.context_db.db_path) as _db:
                    result = await _db.execute(
                        "UPDATE pm_tasks SET status='assigned' "
                        "WHERE status='running' AND assigned_dept=? AND updated_at < ?",
                        (self.org_id, cutoff),
                    )
                    await _db.commit()
                    if result.rowcount:
                        logger.info(f"[{self.org_id}] stale running 태스크 {result.rowcount}개 → assigned 리셋")
            except Exception as _e:
                logger.warning(f"[{self.org_id}] stale 리셋 실패: {_e}")

        if self._task_poller is not None:
            self._task_poller.start()
            logger.info(f"[{self.org_id}] TaskPoller 시작됨")

        # pm_bot(global)에서만 완료 감지 폴러 시작 — 최종 합성 보장
        if self._pm_orchestrator is not None and self.context_db is not None:
            import asyncio as _asyncio
            _asyncio.create_task(self._synthesis_poll_loop())
            logger.info(f"[{self.org_id}] SynthesisPoller 시작됨")

        if self._is_pm_org:
            import asyncio as _asyncio
            _asyncio.create_task(register_all_bot_commands())
            logger.info(f"[{self.org_id}] 봇 명령어 등록 태스크 시작됨")

        if self._org_scheduler is not None:
            self._org_scheduler.start()
            logger.info(f"[{self.org_id}] OrgScheduler 시작됨")

        # WarmSessionPool 예열 시작 (엔진별 분기)
        if self._warm_pool is not None:
            import asyncio as _asyncio
            _asyncio.create_task(self._warm_pool.start())
            logger.info(f"[{self.org_id}] WarmSessionPool 예열 시작 (engine={self.engine})")

    async def _store_pending_confirmation(self, action: str, task_ids: list, description: str = "") -> None:
        """pm_bot 제안 상태 저장 (5분 유효). 사용자 긍정 응답 시 _execute_pending_confirmation 실행."""
        import time as _time
        self._pending_confirmation[self.allowed_chat_id] = {
            "action": action,
            "task_ids": task_ids,
            "description": description,
            "expires": _time.time() + 300,  # 5분
        }
        logger.info(f"[pending] 확인 대기 저장: {action} {task_ids}")

    async def _execute_pending_confirmation(self, conf: dict, update) -> None:
        """pending_confirmation 실행."""
        action = conf.get("action")
        task_ids = conf.get("task_ids", [])
        description = conf.get("description", "")

        if action == "retry_tasks" and task_ids:
            reset_count = 0
            for tid in task_ids:
                task_info = await self.context_db.get_pm_task(tid)
                if task_info and task_info.get("status") not in ("running",):
                    await self.context_db.update_pm_task_status(tid, "assigned")
                    reset_count += 1
            dept_names = []
            for tid in task_ids:
                t = await self.context_db.get_pm_task(tid)
                if t:
                    dept_names.append(KNOWN_DEPTS.get(t.get("assigned_dept",""), t.get("assigned_dept","")))
            await self.display.send_reply(
                update.message,
                f"✅ {', '.join(dept_names)} 태스크 {reset_count}개 재시도 예약됨!"
            )
            logger.info(f"[pending] retry 실행: {task_ids}")
        else:
            await self.display.send_reply(update.message, "✅ 알겠어요, 진행할게요!")

    async def _handle_retry_request(self, user_text: str, replied_text: str, update, task_id_hint: str | None = None) -> None:
        """봇 메시지에 답장 + 재시도 → 해당 태스크만 재실행 (pm_bot 전용)."""
        import re as _re
        # replied_text에서 task_id 추출, 없으면 task_id_hint 사용
        m = _re.search(r"태스크\s+(T-[A-Za-z0-9_]+-\d+)", replied_text)
        if m:
            task_id = m.group(1)
        elif task_id_hint:
            task_id = task_id_hint
        else:
            await self.display.send_reply(
                update.message,
                "⚠️ 답장한 메시지에서 태스크 ID를 찾지 못했어요.\n"
                "봇이 완료/실패 메시지에 직접 답장해 주세요."
            )
            return
        logger.info(f"[재시도 요청] {task_id} — 사용자: {user_text[:50]}")

        task_info = await self.context_db.get_pm_task(task_id)
        if not task_info:
            await self.display.send_reply(update.message, f"⚠️ {task_id} 태스크 정보를 찾을 수 없어요.")
            return

        dept = task_info.get("assigned_dept", "")
        dept_name = KNOWN_DEPTS.get(dept, dept)  # Fix 3: 직접 참조
        current_status = task_info.get("status", "")

        # Fix 2: running 상태 체크 — 이미 실행 중이면 중복 방지
        if current_status == "running":
            await self.display.send_reply(
                update.message,
                f"⏳ {dept_name} 태스크 {task_id}는 현재 실행 중이에요.\n"
                "완료될 때까지 기다려 주세요."
            )
            return

        # Fix 6: done 태스크는 확인 후 재시도
        if current_status == "done":
            logger.info(f"[재시도] {task_id} 이미 완료된 태스크 — 사용자 명시적 요청으로 재시도")

        # 상태 초기화 → assigned 재배정
        await self.context_db.update_pm_task_status(task_id, "assigned")
        await self.display.send_reply(
            update.message,
            f"🔄 {dept_name} 태스크 {task_id} 재시도 예약됨\n"
            f"(이전 상태: {current_status} → assigned)"
        )
        logger.info(f"[재시도] {task_id} → assigned 재설정, {dept} 폴러가 픽업 예정")

    async def _handle_pm_done_event(self, text: str) -> None:
        """[PM_DONE:task_id|dept:xxx] 이벤트 수신 시 즉시 합성 트리거 (pm_bot 전용)."""
        import re as _re
        # "✅ [X] 태스크 T-xxx-NNN 완료" 패턴에서 task_id 추출
        m = _re.search(r"태스크\s+(T-[A-Za-z0-9_]+-\d+)\s+완료", text)
        if not m:
            return
        task_id = m.group(1).strip()
        logger.info(f"[PM_DONE 이벤트] {task_id} 완료 수신 → 합성 체크")
        try:
            task_info = await self.context_db.get_pm_task(task_id)
            asyncio.create_task(self._inject_collab_result(task_info))
            if not task_info or not task_info.get("parent_id"):
                return
            parent_id = task_info["parent_id"]
            # 이중 합성 방지 — SynthesisPoller와 공유 가드
            if parent_id in self._synthesizing:
                logger.debug(f"[PM_DONE 이벤트] {parent_id} 이미 합성 중 — 스킵")
                return
            siblings = await self.context_db.get_subtasks(parent_id)
            if siblings and all(s["status"] == "done" for s in siblings):
                self._synthesizing.add(parent_id)
                logger.info(f"[PM_DONE 이벤트] {parent_id} 전체 완료 → 즉시 합성")
                try:
                    await self._pm_orchestrator._synthesize_and_act(
                        parent_id, siblings, self.allowed_chat_id
                    )
                finally:
                    self._synthesizing.discard(parent_id)
            else:
                pending = [s["id"] for s in siblings if s["status"] != "done"]
                logger.info(f"[PM_DONE 이벤트] {parent_id} 아직 미완료: {pending}")
        except Exception as e:
            logger.error(f"[PM_DONE 이벤트] 처리 오류: {e}")

    async def _synthesis_poll_loop(self) -> None:
        """완료된 parent 태스크의 합성을 보장하는 백그라운드 폴러 (pm_bot 전용).

        모든 서브태스크가 done이지만 parent가 아직 pending/assigned 상태인 경우
        자동으로 _synthesize_and_act()를 트리거한다.
        """
        import asyncio as _asyncio
        while True:
            try:
                await _asyncio.sleep(30)  # fallback only; primary via PM_DONE event
                if self.context_db is None or self._pm_orchestrator is None:
                    continue

                import aiosqlite as _aiosqlite
                async with _aiosqlite.connect(self.context_db.db_path) as _db:
                    _db.row_factory = _aiosqlite.Row
                    # 서브태스크가 있고, 아직 완료 처리 안 된 parent 조회
                    cursor = await _db.execute("""
                        SELECT DISTINCT t.parent_id FROM pm_tasks t
                        WHERE t.parent_id IS NOT NULL
                          AND t.status = 'done'
                        AND EXISTS (
                            SELECT 1 FROM pm_tasks p
                            WHERE p.id = t.parent_id
                              AND p.status NOT IN ('done','failed')
                        )
                    """)
                    candidates = [r[0] async for r in cursor]

                for parent_id in candidates:
                    if parent_id in self._synthesizing:
                        continue
                    siblings = await self.context_db.get_subtasks(parent_id)
                    for sibling in siblings:
                        if (
                            sibling.get("status") == "done"
                            and (sibling.get("metadata") or {}).get("collab")
                        ):
                            asyncio.create_task(self._inject_collab_result(sibling))
                    if siblings and all(s["status"] == "done" for s in siblings):
                        self._synthesizing.add(parent_id)
                        logger.info(f"[SynthesisPoller] {parent_id} 전체 완료 감지 → 합성 시작")
                        try:
                            await self._pm_orchestrator._synthesize_and_act(
                                parent_id, siblings, self.allowed_chat_id
                            )
                        except Exception as _e:
                            logger.error(f"[SynthesisPoller] 합성 실패 {parent_id}: {_e}")
                        finally:
                            self._synthesizing.discard(parent_id)
            except Exception as _e:
                logger.warning(f"[SynthesisPoller] 폴링 오류: {_e}")

    def build(self) -> Application:
        """텔레그램 Application 빌드."""
        from telegram.request import HTTPXRequest
        req = HTTPXRequest(
            connection_pool_size=8,
            connect_timeout=10.0,
            read_timeout=30.0,
            write_timeout=30.0,
            pool_timeout=5.0,
        )
        builder = Application.builder().token(self.token).request(req)
        if self._task_poller is not None or self._pm_orchestrator is not None or self._org_scheduler is not None:
            builder = builder.post_init(self._post_init)
        self.app = builder.build()

        # /setup 마법사 — ConversationHandler로 다단계 대화 처리
        setup_conv = ConversationHandler(
            entry_points=[CommandHandler("setup", self.on_command_setup)],
            states={
                SETUP_MENU: [
                    CallbackQueryHandler(self._setup_callback_menu, pattern="^setup_"),
                ],
                SETUP_AWAIT_TOKEN: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._setup_receive_token),
                    CommandHandler("cancel", self._setup_cancel),
                ],
                SETUP_AWAIT_ENGINE: [
                    CallbackQueryHandler(self._setup_receive_engine, pattern="^engine_"),
                    CommandHandler("cancel", self._setup_cancel),
                ],
                SETUP_AWAIT_IDENTITY: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._setup_receive_identity),
                    CommandHandler("cancel", self._setup_cancel),
                ],
            },
            fallbacks=[CommandHandler("cancel", self._setup_cancel)],
            per_chat=True,
            per_user=True,
            allow_reentry=True,
        )
        self.app.add_handler(setup_conv)

        self.app.add_handler(CommandHandler("start", self.on_command_start))
        self.app.add_handler(CommandHandler("status", self.on_command_status))
        self.app.add_handler(CommandHandler("reset", self.on_command_reset))
        self.app.add_handler(CommandHandler("stop_tasks", self.on_command_stop_tasks))
        self.app.add_handler(CommandHandler("restart", self.on_command_restart))
        self.app.add_handler(CommandHandler("set_engine", self.on_command_set_engine))
        # 사용자 정의 스케줄 커맨드 (pm_org 전용)
        if self._is_pm_org:
            self.app.add_handler(CommandHandler("schedule", self.on_command_schedule))
            self.app.add_handler(CommandHandler("schedules", self.on_command_schedules))
            self.app.add_handler(CommandHandler("cancel_schedule", self.on_command_cancel_schedule))
            self.app.add_handler(CommandHandler("pause_schedule", self.on_command_pause_schedule))
            self.app.add_handler(CommandHandler("resume_schedule", self.on_command_resume_schedule))
        self.app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, self.on_self_added_to_chat))
        self.app.add_handler(
            MessageHandler(filters.TEXT, self.on_message)  # 명령어 포함
        )
        self.app.add_handler(MessageHandler(filters.Document.ALL, self.on_attachment))
        self.app.add_handler(MessageHandler(filters.PHOTO, self.on_attachment))
        self.app.add_handler(MessageHandler(filters.VIDEO, self.on_attachment))
        self.app.add_handler(MessageHandler(filters.AUDIO, self.on_attachment))
        self.app.add_handler(MessageHandler(filters.VOICE, self.on_attachment))

        return self.app


# ── 유틸 ──────────────────────────────────────────────────────────────────

    async def _handle_discussion_message(
        self, text: str, update, context
    ) -> None:
        """토론 태그 메시지 처리 — DiscussionManager에 위임."""
        if not self._discussion_manager:
            return
        tags = parse_discussion_tags(text)
        for tag in tags:
            # 토론 ID 추출: 메시지에 discussion_id가 포함되어야 함
            import re as _re
            disc_match = _re.search(r'ID:\s*(D-[\w-]+)', text)
            if disc_match:
                disc_id = disc_match.group(1)
                # 발신자 org_id 추출
                from_match = _re.search(r'\[(\w+)\]', text)
                from_dept = from_match.group(1) if from_match else self.org_id
                await self._discussion_manager.add_message(
                    discussion_id=disc_id,
                    msg_type=tag.msg_type,
                    content=tag.content,
                    from_dept=from_dept,
                    chat_id=self.allowed_chat_id,
                )

    async def _handle_pm_task(
        self, text: str, update, context
    ) -> None:
        """PM 오케스트레이터가 배정한 [PM_TASK:task_id|dept:org_id] 처리.

        Telegram bot-to-bot 메시지용 핸들러 (fallback).
        주요 경로는 TaskPoller를 통한 _execute_polled_task.
        """
        import re as _re
        match = _re.search(r'\[PM_TASK:([^|]+)\|dept:([^\]]+)\]', text)
        if not match:
            return

        task_id = match.group(1).strip()
        target_dept = match.group(2).strip()

        # 내 부서에 배정된 태스크만 처리
        if target_dept != self.org_id:
            return

        if self.context_db is None:
            logger.warning(f"[{self.org_id}] context_db 없음 — PM_TASK 처리 불가")
            return

        # ContextDB에서 태스크 상세 읽기
        task_info = await self.context_db.get_pm_task(task_id)
        if not task_info:
            logger.warning(f"[{self.org_id}] PM_TASK {task_id} ContextDB에 없음")
            return

        await self._execute_pm_task(task_info)

    async def _execute_polled_task(self, task_info: dict) -> None:
        """TaskPoller 콜백 — ContextDB에서 감지된 태스크 실행."""
        await self._execute_pm_task(task_info)

    async def _execute_pm_task(self, task_info: dict) -> None:
        """PM 배정 태스크 실행 (공통 로직).

        Telegram 핸들러와 TaskPoller 양쪽에서 호출.
        """
        task_id = task_info["id"]
        description = task_info.get("description", "")
        metadata = task_info.get("metadata", {})
        # 요약 표시용: PM이 저장한 원본 description 우선 사용 (structured.render() 결과 회피)
        summary_text = metadata.get("original_description") or description
        dept_name = KNOWN_DEPTS.get(self.org_id, self.org_id)
        run_id = metadata.get("run_id") or self._create_runbook(description)
        requester_mention = self._requester_mention_from_metadata(metadata)
        reply_to_message_id = self._reply_message_id_from_metadata(metadata)

        logger.info(f"[{self.org_id}] PM_TASK 실행 시작: {task_id} — {summary_text[:80]}")

        if self.context_db is None:
            return

        await self.context_db.update_pm_task_status(task_id, "running")

        # 진행 상태 알림 전송
        if self.app and self.app.bot:
            team_config = await self._build_team_config(description)
            brief = self._format_execution_brief(
                summary_text,
                team_config,
                owner_label=dept_name,
                route_label="조직 위임 실행",
                route_kind="delegated_execution",
            )
            self._advance_runbook(run_id, "조직 위임 planning phase 시작")
            self._append_runbook(run_id, "Planning brief", brief, phase_name="planning")
            await self.display.send_to_chat(
                self.app.bot,
                self.allowed_chat_id,
                brief,
                reply_to_message_id=reply_to_message_id,
            )
            self._advance_runbook(run_id, "조직 위임 실행 design phase 이동")
            self._append_runbook(
                run_id,
                "Design summary",
                f"engine={team_config.engine}\nmode={team_config.execution_mode.value}\nagents={', '.join(p.name for p in team_config.agents)}",
                phase_name="design",
            )
            self._advance_runbook(run_id, "조직 위임 implementation phase 이동")
        else:
            team_config = await self._build_team_config(description)

        # 진행 콜백: Claude Code 스트리밍 출력을 텔레그램으로 중계
        last_progress_time = [0.0]  # mutable for closure
        progress_interval = self._progress_interval(delegated=True)

        async def on_progress(line: str) -> None:
            if not self._show_progress(delegated=True):
                return
            now = time.time()
            # 2초 간격으로 진행 상태 전송 (도배 방지)
            if now - last_progress_time[0] < progress_interval:
                return
            last_progress_time[0] = now
            short = self._clean_progress_line(line)[:150]
            if short and self.app and self.app.bot:
                await self.display.send_to_chat(
                    self.app.bot, self.allowed_chat_id,
                    f"🛰️ {dept_name} 작업 중: {short}",
                )

        # Claude Code / Codex로 태스크 실행
        try:
            # Pre-task briefing: 관련 과거 교훈 주입
            briefing_text = ""
            try:
                from core.lesson_memory import LessonMemory
                _lm = LessonMemory()
                briefing_text = await _lm.aget_briefing(description, worker=self.org_id)
            except Exception as _be:
                logger.debug(f"[{self.org_id}] briefing 조회 실패 (무시): {_be}")

            system_prompt = self.identity.build_system_prompt()
            task_packet = await self._build_delegated_task_packet(task_info)
            system_prompt += (
                f"\n\n## PM 배정 태스크\n"
                f"Task ID: {task_id}\n"
                f"담당 조직: {dept_name}\n"
                f"실행 지시: {description}\n\n"
                f"{task_packet}\n\n"
                f"## 자율 실행 규칙\n"
                f"- 사용자 확인 없이 자율적으로 판단하여 완료하라.\n"
                f"- 완료 후 \"커밋할까요?\", \"계속할까요?\" 같은 확인 질문을 하지 마라.\n"
                f"- 작업이 끝나면 결과를 요약 보고하고 즉시 종료하라.\n"
                f"- 위험한 작업(프로덕션 변경, 데이터 삭제)만 피하고, 나머지는 스스로 결정하라.\n"
            )
            if briefing_text:
                system_prompt += f"\n{briefing_text}\n"

            # 봇에 매핑된 스킬 컨텍스트 주입
            try:
                from core.skill_loader import build_skill_context
                skill_ctx = build_skill_context(self.org_id, description)
                if skill_ctx:
                    system_prompt += f"\n{skill_ctx}\n"
            except Exception as _se:
                logger.debug(f"[{self.org_id}] 스킬 로딩 실패 (무시): {_se}")

            response = await self._execute_with_team_config(
                task=description,
                system_prompt=system_prompt,
                team_config=team_config,
                progress_callback=on_progress,
                workdir=task_info.get("metadata", {}).get("workdir"),
                route_kind="delegated_execution",
            )
            upload_candidates = extract_local_artifact_paths(response or "")
            self._append_runbook(
                run_id,
                "Implementation result",
                (response or "(완료)")[:6000],
                phase_name="implementation",
            )
            if self.app and self.app.bot:
                response = await self._handle_collab_tags(
                    response,
                    bot=self.app.bot if self.app else None,
                    chat_id=self.allowed_chat_id,
                    requester_mention=requester_mention,
                    reply_to_message_id=reply_to_message_id,
                )
            self._advance_runbook(run_id, "조직 위임 실행 완료, verification phase 이동")

            full_result = (response or "(완료)")
            await self.context_db.update_pm_task_status(task_id, "done", result=full_result)
            logger.info(f"[{self.org_id}] PM_TASK {task_id} 완료")

            # Post-task debrief: 성공 교훈 자동 기록
            try:
                from core.lesson_memory import LessonMemory
                _lm_post = LessonMemory()
                await _lm_post.arecord_success(
                    task_description=description[:200],
                    category="approach",
                    what_went_well=f"태스크 {task_id} 정상 완료",
                    reuse_tip=full_result[:300],
                    worker=self.org_id,
                )
            except Exception as _de:
                logger.debug(f"[{self.org_id}] 성공 교훈 기록 실패 (무시): {_de}")

            # 결과를 채팅방에 공유
            # pm_bot은 "✅ [X] 태스크 T-xxx 완료" 패턴을 파싱해서 on_task_complete 트리거
            public_result = await ensure_user_friendly_output(
                full_result,
                original_request=(task_info.get("metadata") or {}).get("original_request", description),
            )
            summary_prefix = f"{requester_mention} " if requester_mention else ""
            summary = f"{summary_prefix}✅ [{dept_name}] 태스크 {task_id} 완료\n{public_result[:500]}"
            if self.app and self.app.bot:
                await self.display.send_to_chat(
                    self.app.bot,
                    self.allowed_chat_id,
                    summary,
                    reply_to_message_id=reply_to_message_id,
                )
                await self._auto_upload("\n".join(upload_candidates), self.token, self.allowed_chat_id)
            self._append_runbook(
                run_id,
                "Verification summary",
                summary,
                phase_name="verification",
            )
            self._advance_runbook(run_id, "조직 위임 feedback phase 이동")
            self._append_runbook(
                run_id,
                "Feedback",
                "조직 위임 실행 결과를 PM에 보고했다.",
                phase_name="feedback",
            )
            self._complete_runbook(run_id, "조직 위임 실행 완료")
            if self.bus:
                asyncio.ensure_future(self._p2p.notify_task_done(self.org_id, run_id or "", response[:200] if response else "완료"))

        except Exception as e:
            logger.error(f"[{self.org_id}] PM_TASK {task_id} 실행 실패: {e}")
            await self.context_db.update_pm_task_status(task_id, "failed", result=str(e))
            # Performance DB 업데이트 (실패)
            import asyncio as _asyncio
            from core.pm_orchestrator import _record_bot_perf as _rbp
            _asyncio.create_task(_rbp(self.context_db, task_id, success=False))
            # Post-task debrief: 실패 교훈 자동 기록
            try:
                from core.lesson_memory import LessonMemory
                _lm_fail = LessonMemory()
                await _lm_fail.arecord(
                    task_description=description[:200],
                    category="other",
                    what_went_wrong=str(e)[:300],
                    how_to_prevent=f"태스크 {task_id} 실패 패턴 확인 필요",
                    worker=self.org_id,
                    outcome="failure",
                )
            except Exception:
                pass
            # 실패 알림
            if self.app and self.app.bot:
                fail_prefix = f"{requester_mention} " if requester_mention else ""
                await self.display.send_to_chat(
                    self.app.bot, self.allowed_chat_id,
                    f"{fail_prefix}❌ [{dept_name}] 태스크 {task_id} 실패: {e}",
                    reply_to_message_id=reply_to_message_id,
                )

    async def _handle_collab_request(
        self, text: str, update, context
    ) -> None:
        """다른 PM의 협업 요청 — confidence → claim → 실행 → 결과 채팅방 발송."""
        parsed = parse_collab_request(text)
        task = parsed["task"]
        ctx = parsed["context"]
        from_org = parsed["from_org"]
        requester_mention = parsed.get("requester_mention") or parsed.get("from_org_mention") or self._org_mention(from_org)
        target_mentions = parsed.get("target_mentions") or []
        my_mention = self._org_mention(self.org_id)

        if from_org == self.org_id or not task:
            return
        if target_mentions and my_mention not in target_mentions:
            return

        # confidence 계산
        score = await self.confidence_scorer.score(task, self.identity)
        if score < 6:
            return

        import asyncio as _asyncio
        await _asyncio.sleep(max(0.0, (10 - score) * 0.3))

        message_id = f"collab_{update.message.message_id}"
        if not self.claim_manager.try_claim(message_id, self.org_id):
            return

        claim_text = f"{requester_mention} {make_collab_claim(self.org_id)}".strip()
        await update.message.reply_text(claim_text)

        # 요청 조직의 맥락 + 글로벌 맥락 모두 주입
        system_prompt = self.identity.build_system_prompt()
        if ctx:
            system_prompt += f"\n\n## 협업 요청 조직({from_org})의 작업 맥락\n{ctx}"

        run_id = self._create_runbook(task)
        self._advance_runbook(run_id, f"{from_org} 협업 요청 planning phase 시작")
        team_config = await self._build_team_config(task)
        brief = self._format_execution_brief(
            task,
            team_config,
            owner_label=self.org_id,
            route_label=f"{from_org} 협업 요청 수행",
            route_kind="delegated_execution",
        )
        self._append_runbook(run_id, "Planning brief", brief, phase_name="planning")
        await update.message.reply_text(
            brief
        )
        self._advance_runbook(run_id, "협업 실행 plan 공유 완료")
        self._append_runbook(
            run_id,
            "Design summary",
            f"from_org={from_org}\nengine={team_config.engine}\nmode={team_config.execution_mode.value}\nagents={', '.join(p.name for p in team_config.agents)}",
            phase_name="design",
        )
        self._advance_runbook(run_id, "협업 execution phase 이동")
        progress_msg = await update.message.reply_text("⚙️ 협업 작업 중...")
        history: list[str] = []
        last_edit = 0.0
        progress_interval = self._progress_interval()
        history_limit = self._progress_history_limit()

        async def on_progress(line: str) -> None:
            nonlocal last_edit
            if not self._show_progress():
                return
            import time
            cleaned_line = self._clean_progress_line(line)
            if not cleaned_line:
                return
            history.append(cleaned_line)
            if time.time() - last_edit > progress_interval:
                try:
                    await progress_msg.edit_text(
                        "협업 진행 상황 공유할게요!\n\n" + "\n".join(history[-history_limit:])
                    )
                    last_edit = time.time()
                except Exception:
                    pass

        response = await self._execute_with_team_config(
            task=task,
            system_prompt=system_prompt,
            team_config=team_config,
            progress_callback=on_progress,
            route_kind="delegated_execution",
        )
        self._append_runbook(
            run_id,
            "Implementation result",
            (response or "(결과 없음)")[:6000],
            phase_name="implementation",
        )
        self._advance_runbook(run_id, "협업 실행 완료, verification phase 이동")

        try:
            await progress_msg.edit_text("✅ 협업 완료!")
        except Exception:
            pass

        response = await ensure_user_friendly_output(
            response or "(결과 없음)",
            original_request=task,
            decision_client=self._pm_decision_client if self._is_pm_org else None,
        )
        summary = response[:300]
        done_text = f"{requester_mention} {make_collab_done(self.org_id, summary)}".strip()
        await update.message.reply_text(done_text)
        if response and len(response) > 300:
            for chunk in split_message(response[300:], 4000):
                await update.message.reply_text(chunk)
        self._append_runbook(
            run_id,
            "Verification summary",
            summary,
            phase_name="verification",
        )
        self._advance_runbook(run_id, "협업 feedback phase 이동")
        self._append_runbook(
            run_id,
            "Feedback",
            "협업 요청 처리 결과를 원 요청 조직에 반환했다.",
            phase_name="feedback",
        )
        self._complete_runbook(run_id, "협업 요청 처리 완료")
        if self.bus:
            asyncio.ensure_future(self._p2p.notify_task_done(self.org_id, run_id or "", response[:200] if response else "완료"))

    async def _handle_command(
        self, text: str, update, context
    ) -> None:
        """/ 명령어 처리 — 특정 봇 태그(/org@aiorg_pm_bot)도 지원."""
        import re as _re
        import os as _os
        cmd_full = text.strip().split()[0].lower()
        cmd = _re.sub(r'@\S+', '', cmd_full)  # /org@bot → /org
        cmd = cmd.replace("_", "-")
        arg = text[len(text.split()[0]):].strip()

        # 이 PM 대상이 아닌 태그된 명령어면 응답
        bot_tag = _re.search(r'@(\S+)', text.split()[0])
        if bot_tag:
            my_username = (await context.bot.get_me()).username or ""
            if bot_tag.group(1).lower() != my_username.lower():
                return  # 다른 봇 대상 명령어는 조용히 무시

        # /org — 조직 정체성 조회/설정
        if cmd == "/org":
            # @태그 없을 때 다중 PM 보호: default_handler만 처리
            pm_count = int(_os.environ.get("PM_COUNT", "1"))
            if not bot_tag and pm_count > 1:
                is_default = self.identity._data.get("default_handler", False)
                if not is_default:
                    return  # 다른 PM은 조용히 무시
                # default_handler가 경고 메시지 (설정 변경 없이)
                if arg and arg.lower() != "status":
                    await update.message.reply_text(
                        f"⚠️ PM이 {pm_count}개 있습니다. 특정 PM을 지정해주세요:\n"
                        f"`/org@봇이름 역할|전문분야|방향성`",
                        parse_mode="Markdown"
                    )
                    return

            if not arg or arg.lower() == "status":
                d = self.identity._data
                me = await context.bot.get_me()
                bot_name = me.username or "봇이름"
                msg = (
                    f"🏢 *{self.org_id} 조직 정체성*\n\n"
                    f"현재 설정:\n"
                    f"• 역할: {d.get('role','미설정')}\n"
                    f"• 전문분야: {', '.join(d.get('specialties', [])) or '미설정'}\n"
                    f"• 방향성: {d.get('direction','미설정')}\n\n"
                    f"⚙️ 설정 방법:\n"
                    f"`/org@{bot_name} 프로덕트PM|기획,UX|사용자중심`\n\n"
                    f"형식: `역할|전문분야1,분야2|방향성`\n"
                    f"예시:\n"
                    f"  • 개발PM|백엔드,API|빠른출시\n"
                    f"  • 디자인PM|UI,UX|사용자경험\n"
                    f"  • 마케팅PM|콘텐츠,SNS|성장"
                )
                await update.message.reply_text(msg, parse_mode="Markdown")
            else:
                # 자유 텍스트 → 정체성 업데이트 (빈 필드 skip)
                parts = [p.strip() for p in arg.split("|")]
                new_data: dict = {}
                if len(parts) >= 1 and parts[0]:
                    new_data["role"] = parts[0]
                if len(parts) >= 2 and parts[1]:
                    new_data["specialties"] = [s.strip() for s in parts[1].split(",") if s.strip()]
                if len(parts) >= 3 and parts[2]:
                    new_data["direction"] = parts[2]
                elif not new_data:
                    new_data["direction"] = arg  # 파이프 없으면 전체를 direction으로
                self.identity.update(new_data)
                try:
                    _sync_identity_to_canonical_config(self.org_id, self.identity._data)
                    _refresh_legacy_bot_configs()
                except Exception as _sync_err:
                    logger.warning(f"/org canonical sync 실패: {_sync_err}")
                d = self.identity._data
                msg = (
                    f"✅ *{self.org_id} 정체성 업데이트!*\n\n"
                    f"역할: {d.get('role','')}\n"
                    f"전문분야: {', '.join(d.get('specialties', []))}\n"
                    f"방향성: {d.get('direction','')}\n\n"
                    f"이제 이 방향성으로 팀을 구성할게요 🤖"
                )
                await update.message.reply_text(msg, parse_mode="Markdown")
            return

        # /org set-tone <봇이름> <말투지시> — 봇 말투/성격 설정
        if arg.lower().startswith("set-tone") or arg.lower().startswith("set_tone"):
            tone_parts = arg.split(None, 2)  # ["set-tone", <봇이름>, <말투지시>]
            if len(tone_parts) < 3:
                await update.message.reply_text(
                    "사용법: `/org set-tone <봇이름> <말투지시>`\n"
                    "예) `/org set-tone 성장실 데이터 지향적이고 직설적으로`",
                    parse_mode="Markdown",
                )
                return
            target_name = tone_parts[1].strip()
            tone_instruction = tone_parts[2].strip()

            # 봇 이름 → org_id 매핑
            try:
                _cfg = load_orchestration_config(force_reload=True)
                _name_to_id: dict[str, str] = {
                    org.dept_name: org.id for org in _cfg.list_specialist_orgs()
                }
                # org_id 직접 입력도 허용
                _id_set = {org.id for org in _cfg.list_specialist_orgs()}
            except Exception as _e:
                logger.warning(f"[/org set-tone] org 목록 로드 실패: {_e}")
                _name_to_id = {}
                _id_set = set()

            target_org_id = _name_to_id.get(target_name) or (target_name if target_name in _id_set else None)
            if target_org_id is None:
                known = ", ".join(_name_to_id.keys()) or "알 수 없음"
                await update.message.reply_text(
                    f"봇 이름 '{target_name}'을 찾지 못했어요.\n"
                    f"알려진 봇: {known}",
                )
                return

            import re as _re
            _tone_identity = PMIdentity(target_org_id)
            _cur_dir = _tone_identity._data.get("direction", "") or ""
            _marker = "[말투/성격]"
            if _marker in _cur_dir:
                _new_dir = _re.sub(
                    r"\[말투/성격\].*?(\n|$)", f"{_marker} {tone_instruction}\n", _cur_dir
                ).strip()
            else:
                _new_dir = (
                    (_cur_dir + f"\n{_marker} {tone_instruction}").strip()
                    if _cur_dir else f"{_marker} {tone_instruction}"
                )
            _tone_identity.update({"direction": _new_dir})
            try:
                _sync_identity_to_canonical_config(target_org_id, _tone_identity._data)
                _refresh_legacy_bot_configs()
            except Exception as _sync_err:
                logger.warning(f"[/org set-tone] canonical sync 실패: {_sync_err}")
            dept_display = target_name
            await update.message.reply_text(
                f"✅ *{dept_display}* 봇 말투 업데이트!\n\n"
                f"말투 지시: `{tone_instruction}`\n\n"
                f"현재 방향성:\n{_new_dir}",
                parse_mode="Markdown",
            )
            return

        # /org add <이름> [engine] — 새 조직 등록
        if arg.lower().startswith("add ") or arg.lower() == "add":
            add_parts = arg.split(None, 2)  # ["add", <name>, <engine?>]
            if len(add_parts) < 2:
                await update.message.reply_text(
                    "사용법: `/org add <이름> [engine]`\n"
                    "engine: `claude-code` (기본) | `codex` | `auto`",
                    parse_mode="Markdown"
                )
                return
            new_org_id = add_parts[1].strip()
            raw_engine = add_parts[2].strip() if len(add_parts) >= 3 else "claude-code"
            _valid_engines = {"claude-code", "codex", "auto"}
            if raw_engine not in _valid_engines:
                await update.message.reply_text(
                    f"⚠️ 알 수 없는 engine: `{raw_engine}`\n"
                    f"사용 가능: `claude-code` | `codex` | `auto`",
                    parse_mode="Markdown"
                )
                return
            try:
                from core.org_registry import OrgRegistry
                registry = OrgRegistry()
                registry.load()
                registry.register_org(
                    org_id=new_org_id,
                    bot_token=self.token,
                    chat_id=self.allowed_chat_id,
                    specialties=["일반"],
                    engine=raw_engine,
                )
                _engine_labels = {"claude-code": "Claude Code", "codex": "Codex", "auto": "자동 결정"}
                await update.message.reply_text(
                    f"✅ **{new_org_id}** 조직 등록 완료!\n"
                    f"engine: `{raw_engine}` ({_engine_labels.get(raw_engine, raw_engine)})",
                    parse_mode="Markdown"
                )
            except Exception as _e:
                logger.error(f"조직 등록 실패: {_e}")
                await update.message.reply_text(f"❌ 조직 등록 실패: {_e}")
            return

        # /agents — 에이전트 목록
        if cmd == "/agents":
            from pathlib import Path as _Path
            agents_dir = _Path.home() / ".claude" / "agents"
            agents = sorted(agents_dir.glob("*.md"))
            by_cat: dict = {}
            for a in agents:
                cat = a.stem.split("-")[0]
                by_cat.setdefault(cat, []).append(a.stem.split("-", 1)[-1])
            msg = f"🤖 **에이전트 {len(agents)}개**\n\n"
            for cat, names in sorted(by_cat.items()):
                preview = ", ".join(names[:4])
                suffix = f" +{len(names)-4}" if len(names) > 4 else ""
                msg += f"**{cat}** ({len(names)}): {preview}{suffix}\n"
            await update.message.reply_text(msg[:4000], parse_mode="Markdown")
            return

        # /team — 현재 전략
        if cmd == "/team":
            from tools.team_strategy import detect_strategy
            s = detect_strategy()
            desc = {
                "omc": "omc /team (plan→exec→verify)",
                "native": "native --agents",
                "solo": "단독 실행",
            }
            await update.message.reply_text(
                f"⚙️ 현재 팀 전략: **{desc.get(s, s)}**",
                parse_mode="Markdown",
            )
            return

        # /sessions [org_id] — 세션 현황
        if cmd == "/sessions":
            registry = self._session_registry()
            target = arg.strip()
            text_out = registry.format_detail(target) if target else registry.format_summary()
            await update.message.reply_text(text_out)
            return

        # /verbose [0|1|2]
        if cmd == "/verbose":
            level_map = {
                "quiet": 0,
                "normal": 1,
                "verbose": 2,
            }
            if not arg:
                level = self._telegram_verbosity()
                await update.message.reply_text(
                    "🔈 현재 텔레그램 진행 노출 레벨: "
                    f"{level}\n0=최종만, 1=요약 진행, 2=자세한 진행"
                )
                return
            raw = arg.strip().lower()
            if raw in level_map:
                level = level_map[raw]
            elif raw.isdigit():
                level = int(raw)
            else:
                await update.message.reply_text("사용법: /verbose 0|1|2")
                return
            level = self.session_store.set_telegram_verbosity(level)
            labels = {
                0: "최종 응답만 보여줍니다.",
                1: "중간 진행은 요약해서 보여줍니다.",
                2: "중간 진행을 더 자세히 보여줍니다.",
            }
            await update.message.reply_text(
                f"🔈 진행 노출 레벨을 {level}로 설정했습니다. {labels[level]}"
            )
            return

        # /context-budget — 조직별 세션 컨텍스트 예산 요약
        if cmd == "/context-budget":
            registry = self._session_registry()
            lines = ["📏 context budget"]
            for item in registry.list_sessions():
                usage_hint = f"tok={item['total_tokens']}" if item["total_tokens"] else f"msgs={item['msg_count']}"
                lines.append(
                    f"- {item['org_id']}: {item['context_percent']}% | {item['health']} | {usage_hint} | src={item['usage_source']}"
                )
            await update.message.reply_text("\n".join(lines))
            return

        # /session-policy [org_id]
        if cmd == "/session-policy":
            target_org = arg.strip() or self.org_id
            org_cfg = load_orchestration_config().get_org(target_org)
            if org_cfg is None:
                await update.message.reply_text(f"알 수 없는 조직: {target_org}")
                return
            policy_name = org_cfg.execution.get("session_policy", "")
            policy = load_orchestration_config().get_session_policy(policy_name)
            lines = [f"🧠 {target_org} session policy"]
            lines.append(f"- policy: {policy_name or '-'}")
            for key, value in policy.items():
                lines.append(f"- {key}: {value}")
            await update.message.reply_text("\n".join(lines))
            return

        # /compact [org_id]
        if cmd == "/compact":
            target_org = arg.strip() or self.org_id
            result = await self._compact_org_session(target_org)
            await update.message.reply_text(result)
            return

        # /reset-session [org_id]
        if cmd == "/reset-session":
            target_org = arg.strip() or self.org_id
            SessionStore(target_org).reset()
            await update.message.reply_text(f"🔄 {target_org} 세션 메타데이터 초기화됨")
            return

        # /reset — 세션 초기화
        if cmd == "/reset":
            self.session_store.reset()
            await update.message.reply_text("🔄 PM 세션 초기화됨")
            return

        # /pm — /org 로 통합 (하위 호환 리다이렉트)
        if cmd == "/pm":
            parts = arg.split(None, 1)
            sub = parts[0].lower() if parts else ""
            sub_arg = parts[1] if len(parts) > 1 else ""

            if sub == "delete":
                await update.message.reply_text(
                    f"⚠️ PM 삭제는 봇을 그룹에서 내보내고\n"
                    f"`~/.ai-org/memory/pm_{self.org_id}.md` 삭제 후\n"
                    f"봇을 재시작하면 됩니다."
                )
                return

            # /pm set 역할|... → /org 로 위임하여 처리
            if sub == "set" and sub_arg:
                identity_arg = sub_arg
            else:
                identity_arg = ""

            if identity_arg:
                # 정체성 업데이트 (빈 필드 skip)
                id_parts = [p.strip() for p in identity_arg.split("|")]
                new_data: dict = {}
                if len(id_parts) >= 1 and id_parts[0]:
                    new_data["role"] = id_parts[0]
                if len(id_parts) >= 2 and id_parts[1]:
                    new_data["specialties"] = [s.strip() for s in id_parts[1].split(",") if s.strip()]
                if len(id_parts) >= 3 and id_parts[2]:
                    new_data["direction"] = id_parts[2]
                if new_data:
                    self.identity.update(new_data)
                    d = self.identity._data
                    await update.message.reply_text(
                        f"✅ *{self.org_id} 정체성 업데이트!*\n\n"
                        f"역할: {d.get('role','')}\n"
                        f"전문분야: {', '.join(d.get('specialties',[]))}\n"
                        f"방향성: {d.get('direction','')}\n\n"
                        f"💡 앞으로는 `/org` 명령어를 사용해주세요.",
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text(
                        "사용법: `/org@봇이름 역할|전문분야1,분야2|방향성`",
                        parse_mode="Markdown"
                    )
            else:
                # 현재 상태 + 리다이렉트 안내
                me = await context.bot.get_me()
                bot_name = me.username or "봇이름"
                d = self.identity._data
                await update.message.reply_text(
                    f"ℹ️ `/pm` 명령어는 `/org`로 통합되었습니다.\n\n"
                    f"현재 설정:\n"
                    f"• 역할: {d.get('role','미설정')}\n"
                    f"• 전문분야: {', '.join(d.get('specialties', [])) or '미설정'}\n"
                    f"• 방향성: {d.get('direction','미설정')}\n\n"
                    f"⚙️ 설정: `/org@{bot_name} 역할|전문분야|방향성`",
                    parse_mode="Markdown"
                )
            return

        # /prompt — 시스템 프롬프트 조회/수정
        if cmd == "/prompt":
            parts = arg.split(None, 1)
            sub = parts[0].lower() if parts else "show"
            sub_arg = parts[1] if len(parts) > 1 else ""

            if sub == "show" or not arg:
                prompt_text = self.identity.build_system_prompt()
                await update.message.reply_text(
                    f"📋 **현재 시스템 프롬프트 ({self.org_id})**\n\n{prompt_text[:3000]}",
                    parse_mode="Markdown",
                )
            elif sub == "add" and sub_arg:
                current = self.identity._data.get("direction", "") or ""
                new_direction = (current + "\n" + sub_arg).strip() if current else sub_arg
                self.identity.update({"direction": new_direction})
                await update.message.reply_text(
                    f"✅ direction에 추가됨:\n`{sub_arg}`\n\n현재 방향성:\n{new_direction}",
                    parse_mode="Markdown",
                )
            elif sub == "set" and sub_arg:
                self.identity.update({"direction": sub_arg})
                await update.message.reply_text(
                    f"✅ direction 교체됨:\n`{sub_arg}`",
                    parse_mode="Markdown",
                )
            elif sub == "reset":
                self.identity.update({"direction": ""})
                await update.message.reply_text("✅ direction 초기화됨.")
            else:
                await update.message.reply_text(
                    "사용법:\n"
                    "`/prompt show` — 현재 시스템 프롬프트 표시\n"
                    "`/prompt add <텍스트>` — direction에 추가\n"
                    "`/prompt set <텍스트>` — direction 전체 교체\n"
                    "`/prompt reset` — direction 초기화",
                    parse_mode="Markdown",
                )
            return

        # /help
        if cmd == "/help":
            import os as _os
            me = await context.bot.get_me()
            bot_name = me.username or "봇이름"
            pm_count = int(_os.environ.get("PM_COUNT", "1"))
            multibot_hint = (
                f"\n🤖 **그룹방 멀티봇 사용법**\n"
                f"`/명령어@{bot_name}` — 이 봇에게만 명령\n"
                f"`@{bot_name} 메시지` — 이 봇에게 메시지\n"
                f"봇 목록: PM_COUNT={pm_count}개 활성 중"
            ) if pm_count > 1 else (
                f"\n💡 그룹방에선 `/명령어@{bot_name}` 형식 사용 권장"
            )
            msg = (
                f"📋 **명령어 안내**\n\n"
                f"🔧 **설정**\n"
                f"`/org` — 조직 정체성 조회·설정\n"
                f"  예) `/org@{bot_name} 프로덕트PM|기획,UX|사용자중심`\n"
                f"`/org set-tone <봇이름> <말투지시>` — 봇 말투/성격 설정\n"
                f"  예) `/org set-tone 성장실 데이터 지향적이고 직설적으로`\n"
                f"`/pm` — `/org`와 동일 (하위 호환)\n\n"
                f"📊 **조회**\n"
                f"`/status` — 봇 상태 확인\n"
                f"`/team` — 전체 팀 현황\n"
                f"`/agents` — 에이전트 목록\n"
                f"`/history [N]` — 최근 태스크 이력 (기본 10개)\n"
                f"`/stats` — 봇별 성과 대시보드\n\n"
                f"⚙️ **관리 (총괄PM만)**\n"
                f"`/setup` — 새 조직 봇 등록 마법사\n"
                f"`/sessions [org]` — 세션 현황\n"
                f"`/verbose 0|1|2` — 진행 노출 레벨\n"
                f"`/context_budget` — 세션 예산 요약\n"
                f"`/session_policy [org]` — 세션 정책 확인\n"
                f"`/compact [org]` — 세션 압축/정리\n"
                f"`/reset_session [org]` — 세션 메타데이터 초기화\n"
                f"`/reset` — 세션 초기화\n"
                + multibot_hint
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
            return

        # /history [N] — 최근 태스크 이력 조회
        if cmd == "/history":
            if self.context_db is None:
                await update.message.reply_text("❌ DB가 초기화되지 않았습니다.")
                return
            try:
                limit = int(arg) if arg.strip().isdigit() else 10
                limit = max(1, min(limit, 50))
            except ValueError:
                limit = 10
            tasks = await self.context_db.get_recent_pm_tasks(limit)
            if not tasks:
                await update.message.reply_text("📋 태스크 이력이 없습니다.")
                return
            status_icons = {
                "done": "✅", "running": "🔄", "assigned": "📨",
                "pending": "⏳", "failed": "❌", "needs_review": "⚠️",
            }
            from core.constants import KNOWN_DEPTS
            lines = [f"📋 **최근 태스크 이력** (최대 {limit}개)\n"]
            for t in tasks:
                icon = status_icons.get(t["status"], "•")
                dept = KNOWN_DEPTS.get(t.get("assigned_dept") or "", t.get("assigned_dept") or "?")
                desc = (t["description"] or "")[:60].replace("\n", " ")
                ts = (t.get("updated_at") or "")[:16].replace("T", " ")
                lines.append(f"{icon} `{t['id']}` [{ts}] **{dept}**\n   {desc}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
            return

        # /stats — 봇별 성과 대시보드
        if cmd == "/stats":
            if self.context_db is None:
                await update.message.reply_text("❌ DB가 초기화되지 않았습니다.")
                return
            perf_list = await self.context_db.get_all_bot_performance()
            if not perf_list:
                await update.message.reply_text("📊 아직 기록된 성과 데이터가 없습니다.")
                return
            from core.constants import KNOWN_DEPTS
            lines = ["📊 **봇별 성과 대시보드**\n"]
            for p in perf_list:
                bot_id = p.get("bot_id", "?")
                bot_name = KNOWN_DEPTS.get(bot_id, bot_id)
                total = p.get("task_count", 0)
                success = p.get("success_count", 0)
                pct = round(success / total * 100) if total > 0 else 0
                avg_lat = p.get("avg_latency_sec", 0.0) or 0.0
                lat_str = f" | 평균 {avg_lat:.1f}s" if avg_lat > 0 else ""
                lines.append(f"• **{bot_name}**: 태스크 {total}건 | 성공 {success}건 ({pct}%){lat_str}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
            return

        # /setup fallback — ConversationHandler entry가 안 잡히는 경우 대비
        if cmd == "/setup":
            await self.on_command_setup(update, context)
            return

# ── /setup 마법사 헬퍼 함수 ────────────────────────────────────────────────

async def _set_org_bot_commands(token: str, *, kind: str = "specialist") -> None:
    """새로 등록된 조직봇에 전용 명령어 세트를 자동으로 등록한다."""
    from telegram import Bot as _TGBot
    from core.bot_commands import get_bot_commands
    try:
        bot = _TGBot(token=token)
        org_commands = get_bot_commands(kind)
        await bot.set_my_commands(org_commands)
        logger.info(f"조직봇 명령어 자동 등록 완료: {[c.command for c in org_commands]}")
    except Exception as e:
        logger.warning(f"조직봇 명령어 등록 실패 (무시): {e}")


async def register_all_bot_commands() -> None:
    """bots/*.yaml 의 모든 봇에 setMyCommands 를 호출해 명령어 목록을 최신화한다."""
    import yaml as _yaml
    from telegram import Bot as _TGBot
    from core.bot_commands import get_bot_commands

    bots_dir = Path(__file__).parent.parent / "bots"
    for yaml_path in sorted(bots_dir.glob("*.yaml")):
        try:
            data = _yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            token_env = data.get("token_env", "")
            token = os.environ.get(token_env, "") if token_env else ""
            if not token:
                logger.debug(f"[register_commands] 토큰 없음: {yaml_path.name} ({token_env})")
                continue
            kind = "orchestrator" if data.get("is_pm") else "specialist"
            commands = get_bot_commands(kind)
            bot = _TGBot(token=token)
            await bot.set_my_commands(commands)
            logger.info(f"[register_commands] {yaml_path.stem} ({kind}) 명령어 등록 완료")
        except Exception as exc:
            logger.warning(f"[register_commands] {yaml_path.name} 실패 (무시): {exc}")


async def _validate_bot_token(token: str) -> dict | None:
    """토큰으로 봇 정보를 조회한다. 유효하지 않으면 None 반환."""
    from telegram import Bot as _TGBot
    try:
        bot = _TGBot(token=token)
        me = await bot.get_me()
        return {"username": me.username, "first_name": me.first_name, "id": me.id}
    except Exception:
        return None


def _append_env_var(key: str, value: str) -> None:
    """.env 파일에 환경변수를 추가한다. 이미 존재하면 덮어쓴다."""
    env_path = Path(__file__).parent.parent / ".env"
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    new_lines = [line for line in lines if not line.startswith(f"{key}=")]
    new_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(new_lines) + "\n")


def _create_bot_config(
    username: str, token_env: str, org_id: str, chat_id: int,
    engine: str = "claude-code",
    dept_name: str = "", role: str = "", instruction: str = "",
) -> None:
    """bots/ 디렉토리에 봇 설정 YAML 파일을 생성한다."""
    import datetime
    bots_dir = Path(__file__).parent.parent / "bots"
    bots_dir.mkdir(exist_ok=True)
    config_path = bots_dir / f"{username}.yaml"
    lines = [
        f"# 자동 생성 봇 설정 — {datetime.datetime.now().isoformat()}",
        f'username: "{username}"',
        f'org_id: "{org_id}"',
        f'token_env: "{token_env}"',
        f"chat_id: {chat_id}",
        f'engine: "{engine}"',
    ]
    if dept_name:
        lines.append(f'dept_name: "{dept_name}"')
    if role:
        lines.append(f'role: "{role}"')
    if instruction:
        lines.append(f'instruction: "{instruction}"')
    config_path.write_text("\n".join(lines) + "\n")


def _profile_bundle_for_org(org_id: str) -> dict:
    lowered = org_id.lower()
    if lowered in {"global", "aiorg_pm_bot"} or lowered.endswith("_pm_bot"):
        return {
            "kind": "orchestrator",
            "team_profile": "global_orchestrator",
            "verification_profile": "orchestrator_default",
            "backend_policy": "orchestrator_default",
            "session_policy": "orchestrator_default",
            "can_direct_reply": True,
        }
    if "research" in lowered or "insight" in lowered or "reference" in lowered:
        return {
            "kind": "specialist",
            "team_profile": "research_strategy",
            "verification_profile": "specialist_default",
            "backend_policy": "specialist_default",
            "session_policy": "specialist_default",
            "can_direct_reply": False,
        }
    if "engineering" in lowered or "dev" in lowered or "code" in lowered:
        return {
            "kind": "specialist",
            "team_profile": "engineering_delivery",
            "verification_profile": "specialist_default",
            "backend_policy": "specialist_default",
            "session_policy": "specialist_default",
            "can_direct_reply": False,
        }
    if "design" in lowered or "ux" in lowered or "ui" in lowered:
        return {
            "kind": "specialist",
            "team_profile": "design_strategy",
            "verification_profile": "specialist_default",
            "backend_policy": "specialist_default",
            "session_policy": "specialist_default",
            "can_direct_reply": False,
        }
    if "product" in lowered or "plan" in lowered or "prd" in lowered:
        return {
            "kind": "specialist",
            "team_profile": "product_strategy",
            "verification_profile": "specialist_default",
            "backend_policy": "specialist_default",
            "session_policy": "specialist_default",
            "can_direct_reply": False,
        }
    if "growth" in lowered or "marketing" in lowered:
        return {
            "kind": "specialist",
            "team_profile": "growth_strategy",
            "verification_profile": "specialist_default",
            "backend_policy": "specialist_default",
            "session_policy": "specialist_default",
            "can_direct_reply": False,
        }
    if "ops" in lowered or "infra" in lowered:
        return {
            "kind": "specialist",
            "team_profile": "ops_delivery",
            "verification_profile": "specialist_default",
            "backend_policy": "specialist_default",
            "session_policy": "specialist_default",
            "can_direct_reply": False,
        }
    return {
        "kind": "specialist",
        "team_profile": "research_strategy",
        "verification_profile": "specialist_default",
        "backend_policy": "specialist_default",
        "session_policy": "specialist_default",
        "can_direct_reply": False,
    }


def _default_identity_for_org(org_id: str) -> dict:
    lowered = org_id.lower()
    if "research" in lowered or "insight" in lowered or "reference" in lowered:
        return {
            "dept_name": "리서치실",
            "display_name": "Research",
            "role": "시장조사/레퍼런스 조사/문서 요약/경쟁사 분석",
            "specialties": ["시장조사", "레퍼런스조사", "문서요약", "경쟁사분석"],
            "instruction": "시장·레퍼런스·경쟁사 조사 결과를 출처 기반으로 구조화해 정리하세요.",
            "guidance": "조사 범위, 출처, 비교표, 핵심 인사이트를 반드시 남긴다.",
        }
    return {
        "dept_name": org_id,
        "display_name": org_id,
        "role": f"{org_id} 역할",
        "specialties": [],
        "instruction": "요청을 분석하고 처리하세요.",
        "guidance": "추후 /org 명령으로 조직 정체성을 보완하세요.",
    }


def _upsert_org_in_canonical_config(
    *,
    username: str,
    token_env: str,
    chat_id: int,
    engine: str,
) -> None:
    import yaml as _yaml

    orgs_path = Path(__file__).parent.parent / "organizations.yaml"
    if orgs_path.exists():
        data = _yaml.safe_load(orgs_path.read_text(encoding="utf-8")) or {}
    else:
        data = {
            "schema_version": 2,
            "source_of_truth": {
                "docs_root": "docs/orchestration-v2",
                "orchestration_config": "orchestration.yaml",
            },
            "organizations": [],
        }

    bundle = _profile_bundle_for_org(username)
    identity_defaults = _default_identity_for_org(username)
    org_entry = {
        "id": username,
        "enabled": True,
        "kind": bundle["kind"],
        "description": f"{username} org",
        "telegram": {
            "username": username,
            "token_env": token_env,
            "chat_id": chat_id,
        },
        "identity": {
            "dept_name": identity_defaults["dept_name"],
            "display_name": identity_defaults["display_name"],
            "role": identity_defaults["role"],
            "specialties": identity_defaults["specialties"],
            "direction": "추후 /org 명령으로 업데이트",
            "instruction": identity_defaults["instruction"],
        },
        "routing": {
            "default_handler": False,
            "can_direct_reply": bundle["can_direct_reply"],
            "confidence_threshold": 5,
            "orchestration_mode": "skill_cli",
        },
        "execution": {
            "preferred_engine": engine,
            "fallback_engine": "claude-code" if engine != "claude-code" else "codex",
            "team_profile": bundle["team_profile"],
            "verification_profile": bundle["verification_profile"],
            "phase_policy": "default",
            "backend_policy": bundle["backend_policy"],
            "session_policy": bundle["session_policy"],
        },
        "team": {
            "preferred_agents": [],
            "avoid_agents": [],
            "max_team_size": 3,
            "preferred_skills": [],
            "guidance": identity_defaults["guidance"],
        },
        "collaboration": {
            "peers": [],
            "announce_plan": True,
            "announce_progress": True,
            "brainstorming_mode": "structured",
        },
    }

    orgs = data.setdefault("organizations", [])
    replaced = False
    for idx, existing in enumerate(orgs):
        if existing.get("id") == username:
            orgs[idx] = org_entry
            replaced = True
            break
    if not replaced:
        orgs.append(org_entry)

    orgs_path.write_text(
        _yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _sync_identity_to_canonical_config(org_id: str, identity_data: dict) -> None:
    import yaml as _yaml

    orgs_path = Path(__file__).parent.parent / "organizations.yaml"
    if not orgs_path.exists():
        return

    data = _yaml.safe_load(orgs_path.read_text(encoding="utf-8")) or {}
    for org in data.get("organizations", []):
        if org.get("id") != org_id:
            continue
        identity = org.setdefault("identity", {})
        if identity_data.get("role"):
            identity["role"] = identity_data["role"]
        specialties = identity_data.get("specialties")
        if specialties:
            identity["specialties"] = list(specialties)
        if identity_data.get("direction"):
            identity["direction"] = identity_data["direction"]
        break

    orgs_path.write_text(
        _yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _refresh_legacy_bot_configs() -> None:
    import subprocess as _subprocess
    import sys as _sys
    project_dir = Path(__file__).parent.parent
    _subprocess.run(
        [_sys.executable, str(project_dir / "tools" / "orchestration_cli.py"), "export-legacy-bots", "--target-dir", "bots"],
        cwd=str(project_dir),
        check=False,
        stdout=_subprocess.DEVNULL,
        stderr=_subprocess.DEVNULL,
    )


def _launch_bot_subprocess(token: str, org_id: str, chat_id: int) -> int:
    """새 봇 프로세스를 시작하고 PID를 반환한다."""
    import subprocess as _subprocess
    import sys as _sys
    project_dir = Path(__file__).parent.parent
    env = {
        **os.environ,
        "PM_BOT_TOKEN": token,
        "TELEGRAM_GROUP_CHAT_ID": str(chat_id),
        "PM_ORG_NAME": org_id,
    }
    proc = _subprocess.Popen(
        [_sys.executable, str(project_dir / "main.py")],
        env=env,
        stdin=_subprocess.DEVNULL,
        stdout=_subprocess.DEVNULL,
        stderr=_subprocess.DEVNULL,
        cwd=str(project_dir),
        start_new_session=True,
    )
    pid_dir = Path.home() / ".ai-org" / "bots"
    pid_dir.mkdir(parents=True, exist_ok=True)
    (pid_dir / f"{org_id}.pid").write_text(str(proc.pid))
    return proc.pid


