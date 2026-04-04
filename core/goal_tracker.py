"""GoalTracker — PM Goal Loop (ralph at organization level).

사용자 목표를 설정하고, 부서 태스크 결과를 수집·평가하며,
목표 달성까지 반복적으로 재계획·재배분하는 외부 루프.

oh-my-openagent의 ralph loop 패턴 차용:
  idle → evaluate → (not done) → replan → dispatch → idle ...

Feature flag: ENABLE_GOAL_TRACKER (환경변수, 기본 off)
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone  # noqa: F401
from enum import Enum  # noqa: F401 — GoalType에서 사용
from typing import Awaitable, Callable

from loguru import logger

from core.constants import KNOWN_DEPTS
from core.context_db import ContextDB
from core.pm_orchestrator import PMOrchestrator

ENABLE_GOAL_TRACKER = os.environ.get("ENABLE_GOAL_TRACKER", "1") == "1"


class GoalType(str, Enum):
    """OKR 계층 유형."""

    OBJECTIVE = "objective"
    KEY_RESULT = "key_result"
    INITIATIVE = "initiative"
    TASK = "task"


# 계층별 평가 전략 설정
EVALUATION_CONFIG: dict[GoalType, dict] = {
    GoalType.OBJECTIVE: {
        "method": "rollup",
        "check_interval": "quarterly",
        "rollover_on_miss": True,
    },
    GoalType.KEY_RESULT: {
        "method": "kpi_tracking",
        "check_interval": "monthly",
        "rollover_on_miss": False,
    },
    GoalType.INITIATIVE: {
        "method": "milestone",
        "check_interval": "weekly",
        "rollover_on_miss": False,
    },
    GoalType.TASK: {
        "method": "iteration",
        "check_interval": "daily",
        "rollover_on_miss": False,
    },
}


# ── DeadlineChecker (Phase 1.4) ───────────────────────────────────


class DeadlineSeverity(str, Enum):
    """마감 임박 심각도."""

    NONE = "none"          # 마감 여유 충분 (>14일)
    INFO = "info"          # 마감 접근 중 (7~14일)
    WARNING = "warning"    # 마감 임박 (3~7일)
    CRITICAL = "critical"  # 마감 직전 (1~3일)
    EMERGENCY = "emergency"  # 마감 초과


@dataclass
class DeadlineAlert:
    """마감 알림 결과."""

    goal_id: str
    title: str
    goal_type: str
    deadline: str
    days_remaining: int
    severity: DeadlineSeverity
    progress: float
    message: str


class DeadlineChecker:
    """시간 기반 마감 알림 체커.

    각 목표의 deadline을 확인하여 심각도별 알림을 생성한다.
    """

    # 심각도 임계값 (일 기준)
    THRESHOLDS = {
        DeadlineSeverity.EMERGENCY: 0,    # 마감 초과
        DeadlineSeverity.CRITICAL: 3,     # 3일 이내
        DeadlineSeverity.WARNING: 7,      # 7일 이내
        DeadlineSeverity.INFO: 14,        # 14일 이내
    }

    def __init__(self, context_db: ContextDB) -> None:
        self._db = context_db

    def check_deadline(
        self,
        goal: dict,
        now: datetime | None = None,
    ) -> DeadlineAlert | None:
        """단일 목표의 마감 상태를 확인.

        Args:
            goal: 목표 dict (deadline 필드 필수).
            now: 현재 시각 (테스트용). None이면 UTC now.

        Returns:
            DeadlineAlert 또는 None (deadline 미설정 시).
        """
        deadline_str = goal.get("deadline")
        if not deadline_str:
            return None

        if now is None:
            now = datetime.now(timezone.utc)

        try:
            deadline_dt = datetime.strptime(
                deadline_str, "%Y-%m-%d",
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            return None

        days_remaining = (deadline_dt - now).days
        severity = self._classify_severity(days_remaining)

        if severity == DeadlineSeverity.NONE:
            return None

        progress = goal.get("progress", 0.0) or 0.0
        message = self._build_message(
            goal.get("title", goal.get("id", "")),
            days_remaining,
            severity,
            progress,
        )

        return DeadlineAlert(
            goal_id=goal.get("id", ""),
            title=goal.get("title", ""),
            goal_type=goal.get("goal_type", "task"),
            deadline=deadline_str,
            days_remaining=days_remaining,
            severity=severity,
            progress=progress,
            message=message,
        )

    def _classify_severity(self, days_remaining: int) -> DeadlineSeverity:
        """남은 일수로 심각도 분류."""
        if days_remaining < 0:
            return DeadlineSeverity.EMERGENCY
        if days_remaining <= self.THRESHOLDS[DeadlineSeverity.CRITICAL]:
            return DeadlineSeverity.CRITICAL
        if days_remaining <= self.THRESHOLDS[DeadlineSeverity.WARNING]:
            return DeadlineSeverity.WARNING
        if days_remaining <= self.THRESHOLDS[DeadlineSeverity.INFO]:
            return DeadlineSeverity.INFO
        return DeadlineSeverity.NONE

    def _build_message(
        self,
        title: str,
        days_remaining: int,
        severity: DeadlineSeverity,
        progress: float,
    ) -> str:
        """알림 메시지 생성."""
        pct = int(progress * 100)
        if severity == DeadlineSeverity.EMERGENCY:
            return (
                f"🚨 [{title}] 마감 {abs(days_remaining)}일 초과! "
                f"(진척률 {pct}%) — 즉시 조치 필요"
            )
        if severity == DeadlineSeverity.CRITICAL:
            return (
                f"⚠️ [{title}] 마감 {days_remaining}일 남음 "
                f"(진척률 {pct}%) — 긴급 점검 필요"
            )
        if severity == DeadlineSeverity.WARNING:
            return (
                f"⏰ [{title}] 마감 {days_remaining}일 남음 "
                f"(진척률 {pct}%) — 점검 권장"
            )
        return (
            f"📋 [{title}] 마감 {days_remaining}일 남음 "
            f"(진척률 {pct}%)"
        )

    async def check_all_active(
        self,
        now: datetime | None = None,
    ) -> list[DeadlineAlert]:
        """모든 활성 목표의 마감 상태를 확인."""
        goals = await self._db.get_active_goals()
        alerts = []
        for goal in (goals or []):
            alert = self.check_deadline(goal, now=now)
            if alert:
                alerts.append(alert)
        # 심각도순 정렬 (emergency → critical → warning → info)
        severity_order = {
            DeadlineSeverity.EMERGENCY: 0,
            DeadlineSeverity.CRITICAL: 1,
            DeadlineSeverity.WARNING: 2,
            DeadlineSeverity.INFO: 3,
        }
        alerts.sort(key=lambda a: severity_order.get(a.severity, 99))
        return alerts

    async def check_by_type(
        self,
        goal_type: str,
        now: datetime | None = None,
    ) -> list[DeadlineAlert]:
        """특정 goal_type의 활성 목표 마감 상태를 확인."""
        goals = await self._db.get_goals_by_type(goal_type, status="active")
        alerts = []
        for goal in (goals or []):
            alert = self.check_deadline(goal, now=now)
            if alert:
                alerts.append(alert)
        return alerts


# 정체 판정: 연속 N회 진전 없으면 escalate
DEFAULT_MAX_STAGNATION = 3
# 기본 최대 반복 횟수
DEFAULT_MAX_ITERATIONS = 10
# 폴링 간격 (초) — 부서 작업 완료 대기 시 DB 확인 주기
DEFAULT_POLL_INTERVAL_SEC = 30
# 대기 시간 배수 — poll_interval * 이 값 = 최대 대기 시간
WAIT_TIMEOUT_MULTIPLIER = 60


@dataclass
class GoalStatus:
    """목표 평가 결과."""
    achieved: bool
    progress_summary: str
    remaining_work: str
    done_count: int = 0   # 정체 감지용 안정 지표
    total_count: int = 0
    confidence: float = 0.0  # 0.0~1.0


class GoalTracker:
    """PM Goal Loop — 목표 달성까지 반복하는 외부 루프.

    Flow:
        set_goal() → run_loop():
            1. orchestrator.decompose() + dispatch()
            2. wait for dept results
            3. evaluate_progress() via LLM
            4. achieved? → done / stagnated? → escalate / else → replan + re-dispatch

    Cancellation:
        cancel_goal(goal_id) 또는 cancel_all()로 루프 중단 가능.
    """

    def __init__(
        self,
        context_db: ContextDB,
        orchestrator: PMOrchestrator,
        telegram_send_func: Callable[[int, str], Awaitable[None]],
        org_id: str = "pm",
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        max_stagnation: int = DEFAULT_MAX_STAGNATION,
        poll_interval_sec: float = DEFAULT_POLL_INTERVAL_SEC,
    ):
        self._db = context_db
        self._orch = orchestrator
        self._send = telegram_send_func
        self._org_id = org_id
        self._max_iterations = max_iterations
        self._max_stagnation = max_stagnation
        self._poll_interval = poll_interval_sec
        self._goal_counter = 0
        self._counter_initialized = False
        # 취소 이벤트: goal_id → Event
        self._cancel_events: dict[str, asyncio.Event] = {}

    async def _init_counter(self) -> None:
        """DB에서 기존 goal ID 최대값을 조회하여 카운터를 restart-safe하게 초기화."""
        if self._counter_initialized:
            return
        self._goal_counter = await self._db._query_max_goal_counter(self._org_id)
        self._counter_initialized = True

    def _next_goal_id(self) -> str:
        self._goal_counter += 1
        return f"G-{self._org_id}-{self._goal_counter:03d}"

    async def set_goal(
        self,
        description: str,
        chat_id: int,
        org_id: str | None = None,
        title: str = "",
    ) -> dict:
        """새 목표 설정 및 DB 저장."""
        await self._init_counter()
        goal_id = self._next_goal_id()
        goal = await self._db.create_goal(
            goal_id=goal_id,
            description=description,
            created_by=org_id or self._org_id,
            chat_id=chat_id,
            max_iterations=self._max_iterations,
            title=title or description[:80],
        )
        logger.info(f"[GoalTracker] 목표 설정: {goal_id} — {description[:80]}")
        return goal

    async def start_goal(
        self,
        title: str,
        description: str,
        meta: dict | None = None,
        chat_id: int = 0,
        org_id: str | None = None,
        goal_type: GoalType | str = GoalType.TASK,
        parent_goal_id: str | None = None,
        deadline: str | None = None,
        kpi_metric: str | None = None,
        kpi_target: float | None = None,
        kpi_unit: str | None = None,
        weight: float | None = None,
    ) -> str:
        """목표를 DB에 저장하고 자율 루프를 백그라운드 태스크로 시작.

        Phase 1 신규 메서드 — idle→evaluate→replan→dispatch 루프를
        asyncio.create_task()로 백그라운드에서 실행한다.
        OKR 계층 지원: goal_type이 TASK일 때만 자율 루프 시작.

        Args:
            title: 목표 제목 (짧은 레이블).
            description: 목표 상세 설명.
            meta: 메타데이터 dict (sprint, due_date, tags 등). None이면 빈 dict.
            chat_id: Telegram 채팅방 ID (0이면 _org_id 채널 전송 생략).
            goal_type: OKR 계층 유형 (objective/key_result/initiative/task).
            parent_goal_id: 상위 목표 ID.
            deadline: 마감일 (YYYY-MM-DD).
            kpi_metric: KPI 측정 지표명.
            kpi_target: KPI 목표값.
            kpi_unit: KPI 단위.
            weight: 가중치 (0.0~1.0).

        Returns:
            goal_id: 생성된 목표 ID (예: "G-pm-001").
        """
        import json as _json

        # 동일/유사 제목의 active/achieved 목표가 이미 있으면 재생성 방지
        # 1) 정확한 제목 일치
        existing = await self.get_goals_by_title(title)
        for g in existing:
            if g["status"] in ("active", "achieved"):
                logger.info(
                    f"[GoalTracker] start_goal 건너뜀 — 동일 제목 목표 이미 존재: "
                    f"{g['id']} (status={g['status']})"
                )
                return g["id"]

        # 2) 제목 키워드 유사도 체크 — 제목 첫 10자(정규화) 기준으로 active/achieved 목표와 비교
        #    "오픈소스화 스프린트" vs "오픈소스화 — 원클릭" 같은 변형 제목 중복 방지
        import re as _re

        def _normalize(s: str) -> str:
            return _re.sub(r"[\s\-—_·:·]+", "", s).lower()[:10]

        title_key = _normalize(title)
        all_goals = await self._db.get_active_goals()
        # achieved 목표도 포함하여 조회
        achieved_goals = await self._db.get_goals_by_status("achieved")
        for g in (all_goals or []) + (achieved_goals or []):
            if _normalize(g.get("title", "")) == title_key and title_key:
                logger.info(
                    f"[GoalTracker] start_goal 건너뜀 — 유사 제목 목표 이미 존재: "
                    f"{g['id']} title='{g.get('title', '')}' (status={g.get('status')})"
                )
                return g["id"]

        await self._init_counter()
        goal_id = self._next_goal_id()
        meta_json = _json.dumps(meta or {}, ensure_ascii=False)
        full_desc = f"{title}\n\n{description}" if description else title

        # goal_type을 문자열로 정규화
        gt = GoalType(goal_type) if isinstance(goal_type, str) else goal_type
        config = EVALUATION_CONFIG.get(gt, EVALUATION_CONFIG[GoalType.TASK])
        check_interval = config.get("check_interval", "daily")

        await self._db.create_goal(
            goal_id=goal_id,
            title=title,
            description=full_desc,
            created_by=self._org_id,
            chat_id=chat_id,
            max_iterations=self._max_iterations,
            meta_json=meta_json,
            goal_type=gt.value,
            parent_goal_id=parent_goal_id,
            deadline=deadline,
            check_interval=check_interval,
            kpi_metric=kpi_metric,
            kpi_target=kpi_target,
            kpi_unit=kpi_unit,
            weight=weight,
        )
        logger.info(f"[GoalTracker] start_goal: {goal_id} ({gt.value}) — {title[:80]}")

        # TASK만 자율 루프 시작 (Objective/KR/Initiative는 시간 기반 평가)
        if gt == GoalType.TASK:
            asyncio.create_task(
                self.run_loop(goal_id),
                name=f"goal-loop-{goal_id}",
            )
        return goal_id

    async def get_goals_by_title(self, title: str) -> list[dict]:
        """제목이 일치하는 목표를 상태와 무관하게 조회.

        중복 시딩 방지 — 달성(achieved)·정체(stagnated) 상태 포함.

        Returns:
            [{id, status, title}] 리스트.
        """
        return await self._db.get_goals_by_title(title)

    async def get_active_goals(self, org_id: str | None = None) -> list[dict]:
        """활성 목표 목록 조회.

        Args:
            org_id: 필터링할 조직 ID. None이면 전체 반환.

        Returns:
            활성(status='active') 목표 dict 리스트.
        """
        return await self._db.get_active_goals(org_id=org_id)

    async def update_goal_status(self, goal_id: str, status: str) -> dict | None:
        """목표 상태 업데이트.

        Args:
            goal_id: 목표 ID.
            status: 새 상태 (active/achieved/cancelled/stagnated/max_iterations_reached).

        Returns:
            업데이트된 목표 dict.
        """
        result = await self._db.update_goal(goal_id, status=status)
        logger.info(f"[GoalTracker] update_goal_status: {goal_id} → {status}")
        return result

    async def tick_iteration(self, goal_id: str) -> tuple[int, int]:
        """iteration 카운터를 1 증가시키고 (new_iteration, max_iterations) 반환.

        AutonomousLoop에서 매 사이클마다 호출하여 반복 횟수를 추적한다.
        new_iteration > max_iterations 이면 호출 측에서 max_iterations_reached 처리.

        Args:
            goal_id: 목표 ID.

        Returns:
            (new_iteration, max_iterations) 튜플.
        """
        goal = await self._db.get_goal(goal_id)
        if not goal:
            return 0, self._max_iterations
        new_iter = goal.get("iteration", 0) + 1
        max_iter = goal.get("max_iterations", self._max_iterations)
        await self._db.update_goal(goal_id, iteration=new_iter)
        logger.debug(f"[GoalTracker] tick_iteration: {goal_id} → {new_iter}/{max_iter}")
        return new_iter, max_iter

    async def resume_active_goals(self) -> int:
        """재시작 시 DB의 활성 목표를 루프 재개.

        봇 재기동 후 호출하면 이전 세션에서 active였던 목표들의
        run_loop()를 백그라운드 태스크로 재시작한다.

        Returns:
            재개된 목표 수.
        """
        goals = await self._db.get_active_goals(org_id=self._org_id)
        resumed = 0
        for goal in goals:
            goal_id = goal["id"]
            if goal_id in self._cancel_events:
                continue  # 이미 실행 중
            logger.info(f"[GoalTracker] 활성 목표 재개: {goal_id}")
            self._cancel_events[goal_id] = asyncio.Event()
            asyncio.create_task(
                self._run_loop_inner(goal_id, goal.get("chat_id", 0)),
                name=f"goal-loop-resume-{goal_id}",
            )
            resumed += 1
        return resumed

    async def recover_interrupted_goals(self, **_kwargs: object) -> int:
        """봇 재시작으로 중단된 목표를 자동 복구.

        status="active"인 목표만 복구 대상. completed 목표는 절대 되살리지 않는다.
        (이전 로직은 completed + updated_at 기반이었으나, recovery 자체가
         updated_at을 갱신하여 무한 부활 루프를 일으킴.)

        Returns:
            복구된 목표 수.
        """
        active_goals = await self._db.get_goals_by_status("active")
        recovered = 0

        for goal in active_goals:
            goal_id = goal["id"]

            # 이미 실행 중이면 스킵
            if goal_id in self._cancel_events:
                continue

            logger.info(
                f"[GoalTracker] active 목표 루프 재시작: {goal_id} "
                f"({goal.get('title', '')[:40]})"
            )

            # 루프 재시작
            self._cancel_events[goal_id] = asyncio.Event()
            asyncio.create_task(
                self._run_loop_inner(goal_id, goal.get("chat_id", 0)),
                name=f"goal-loop-recover-{goal_id}",
            )
            recovered += 1

        return recovered

    def cancel_goal(self, goal_id: str) -> None:
        """특정 목표의 루프를 취소."""
        event = self._cancel_events.get(goal_id)
        if event:
            event.set()
            logger.info(f"[GoalTracker] 목표 취소 요청: {goal_id}")

    def cancel_all(self) -> None:
        """모든 활성 목표 루프를 취소."""
        for goal_id, event in self._cancel_events.items():
            event.set()
            logger.info(f"[GoalTracker] 목표 취소 요청: {goal_id}")

    def _is_cancelled(self, goal_id: str) -> bool:
        event = self._cancel_events.get(goal_id)
        return event is not None and event.is_set()

    def has_active_loop(self, goal_id: str) -> bool:
        """해당 목표의 _run_loop_inner 백그라운드 루프가 실행 중인지 확인.

        AutonomousLoop._tick()에서 중복 replan 방지용.
        _cancel_events에 존재하고 아직 취소되지 않았으면 실행 중으로 판단.
        """
        event = self._cancel_events.get(goal_id)
        return event is not None and not event.is_set()

    async def evaluate_progress(self, goal_id: str) -> GoalStatus:
        """현재까지의 부서 결과를 수집하고 LLM으로 목표 달성도 평가.

        LLM 없으면 규칙 기반 fallback (모든 서브태스크 done → achieved).
        """
        goal = await self._db.get_goal(goal_id)
        if not goal:
            return GoalStatus(achieved=False, progress_summary="목표를 찾을 수 없음",
                              remaining_work="", confidence=0.0)

        # 이 목표에 연결된 태스크 결과 수집
        subtasks = await self._db.get_subtasks(goal_id)
        if not subtasks:
            return GoalStatus(achieved=False, progress_summary="아직 태스크가 없음",
                              remaining_work="태스크 분해 필요", confidence=0.0)

        # cancelled 서브태스크 제외 — 이전 iteration 이력이 평가에 섞이지 않도록
        active_subtasks = [s for s in subtasks if s["status"] != "cancelled"]
        if not active_subtasks:
            return GoalStatus(achieved=False, progress_summary="활성 태스크 없음 (재계획 필요)",
                              remaining_work="태스크 재분해 필요", confidence=0.0)

        total = len(active_subtasks)
        done = [s for s in active_subtasks if s["status"] == "done"]
        failed = [s for s in active_subtasks if s["status"] == "failed"]
        in_progress = [s for s in active_subtasks if s["status"] in ("assigned", "in_progress")]

        # LLM 평가 시도 (active_subtasks 기준으로 전달)
        llm_status = await self._llm_evaluate(goal, active_subtasks, done)
        if llm_status is not None:
            # LLM 결과에도 안정 지표(done_count, total_count) 추가
            llm_status.done_count = len(done)
            llm_status.total_count = total
            return llm_status

        # Fallback: 규칙 기반 (active_subtasks 기준)
        if len(done) == total:
            return GoalStatus(
                achieved=True,
                progress_summary=f"모든 {total}개 태스크 완료",
                remaining_work="",
                done_count=len(done), total_count=total,
                confidence=0.9,
            )

        progress = f"{len(done)}/{total} 완료"
        if failed:
            progress += f", {len(failed)}개 실패"
        if in_progress:
            progress += f", {len(in_progress)}개 진행중"

        remaining_descs = [s["description"][:50] for s in active_subtasks if s["status"] != "done"]
        remaining = "; ".join(remaining_descs)

        return GoalStatus(
            achieved=False,
            progress_summary=progress,
            remaining_work=remaining,
            done_count=len(done), total_count=total,
            confidence=len(done) / total if total > 0 else 0.0,
        )

    _LLM_EVALUATE_PROMPT = (
        "You are a project manager evaluating if a goal has been achieved.\n\n"
        "GOAL: {goal}\n\n"
        "SUCCESS CRITERIA: {success_criteria}\n\n"
        "COMPLETED TASKS AND RESULTS:\n{results}\n\n"
        "PENDING/FAILED TASKS:\n{pending}\n\n"
        "Judge achievement strictly against the SUCCESS CRITERIA above.\n"
        "If no criteria specified, use reasonable judgment based on the goal description.\n"
        "Reply in this exact format (3 lines):\n"
        "ACHIEVED: YES or NO\n"
        "PROGRESS: one-line summary of what's been done\n"
        "REMAINING: what still needs to be done (or 'nothing' if achieved)\n"
    )

    async def _llm_evaluate(self, goal: dict, subtasks: list[dict],
                            done: list[dict]) -> GoalStatus | None:
        """LLM으로 목표 달성 평가. 실패 시 None (fallback으로)."""
        decision_client = self._orch.decision_client
        if decision_client is None:
            return None

        results_text = "\n".join(
            f"- [{KNOWN_DEPTS.get(s.get('assigned_dept', ''), '?')}] {s.get('result', '(결과 없음)')[:200]}"
            for s in done
        ) or "(없음)"

        pending_text = "\n".join(
            f"- [{KNOWN_DEPTS.get(s.get('assigned_dept', ''), '?')}] {s['status']}: {s['description'][:100]}"
            for s in subtasks if s["status"] != "done"
        ) or "(없음)"

        meta = goal.get("meta_json") or {}
        if isinstance(meta, str):
            import json as _json
            try:
                meta = _json.loads(meta)
            except Exception:
                meta = {}
        success_criteria = meta.get("success_criteria", "(없음 — 목표 설명 기준으로 판단)")

        prompt = self._LLM_EVALUATE_PROMPT.format(
            goal=goal["description"][:500],
            success_criteria=success_criteria,
            results=results_text,
            pending=pending_text,
        )

        try:
            response = await asyncio.wait_for(
                decision_client.complete(prompt),
                timeout=35.0,
            )
            return self._parse_evaluation(response)
        except Exception as e:
            logger.warning(f"[GoalTracker] LLM 평가 실패, fallback 사용: {e}")
            return None

    @staticmethod
    def _parse_evaluation(response: str) -> GoalStatus:
        """LLM 응답 파싱."""
        lines = response.strip().split("\n")
        achieved = False
        progress = ""
        remaining = ""

        for line in lines:
            upper = line.strip().upper()
            if upper.startswith("ACHIEVED:"):
                achieved = "YES" in upper
            elif upper.startswith("PROGRESS:"):
                progress = line.split(":", 1)[1].strip()
            elif upper.startswith("REMAINING:"):
                remaining = line.split(":", 1)[1].strip()

        confidence = 1.0 if achieved else 0.5
        return GoalStatus(
            achieved=achieved,
            progress_summary=progress or "(평가 결과 없음)",
            remaining_work=remaining or "",
            confidence=confidence,
        )

    async def _cancel_old_subtasks(self, goal_id: str) -> None:
        """이전 iteration의 서브태스크를 모두 cancelled로 마킹.

        replan() 호출 시 새 iteration을 위한 슬레이트 초기화.
        done 태스크 포함 cancelled 이외 모든 태스크를 취소한다 —
        evaluate_progress가 현재 iteration 태스크만을 기준으로 평가할 수 있도록
        이전 누적 결과를 격리한다.
        """
        subtasks = await self._db.get_subtasks(goal_id)
        cancelled_count = 0
        for st in subtasks:
            if st["status"] != "cancelled":
                await self._db.update_pm_task_status(st["id"], "cancelled")
                cancelled_count += 1
        if cancelled_count:
            logger.debug(
                f"[GoalTracker] _cancel_old_subtasks: {goal_id} → {cancelled_count}개 취소"
            )

    async def replan(self, goal_id: str, remaining_work: str,
                     chat_id: int) -> list[str]:
        """미완료 작업을 기반으로 재계획·재배분.

        기존 미완료 태스크를 cancelled로 마킹 후 새로 분해.
        """
        goal = await self._db.get_goal(goal_id)
        if not goal:
            return []

        # 이전 미완료 태스크 정리
        await self._cancel_old_subtasks(goal_id)

        # 새 iteration의 요청 메시지: 원래 목표 + 남은 작업
        replan_msg = f"{goal['description']}\n\n남은 작업: {remaining_work}"

        subtasks = await self._orch.decompose(replan_msg)
        if not subtasks:
            logger.warning(f"[GoalTracker] 재계획 실패: decompose 결과 없음 ({goal_id})")
            return []

        task_ids = await self._orch.dispatch(goal_id, subtasks, chat_id)
        if not task_ids:
            logger.warning(f"[GoalTracker] 재계획 실패: dispatch 결과 없음 ({goal_id})")
            return []

        logger.info(f"[GoalTracker] 재계획: {goal_id} → {len(task_ids)}개 태스크 재배분")
        return task_ids

    async def run_loop(self, goal_id: str) -> GoalStatus:
        """목표 달성까지 반복하는 메인 루프.

        Returns:
            최종 GoalStatus (achieved=True or 최대 반복/정체/취소 도달).
        """
        goal = await self._db.get_goal(goal_id)
        if not goal:
            return GoalStatus(achieved=False, progress_summary="목표 없음",
                              remaining_work="", confidence=0.0)

        chat_id = goal["chat_id"]

        # 취소 이벤트 등록
        self._cancel_events[goal_id] = asyncio.Event()

        try:
            return await self._run_loop_inner(goal_id, chat_id)
        finally:
            # 취소 이벤트 정리
            self._cancel_events.pop(goal_id, None)

    async def _run_loop_inner(self, goal_id: str, chat_id: int) -> GoalStatus:
        goal = await self._db.get_goal(goal_id)
        if not goal:
            return GoalStatus(achieved=False, progress_summary="목표 없음",
                              remaining_work="", confidence=0.0)

        # 재시작 복구: DB에 저장된 iteration부터 재개 (0이면 신규 → 1부터)
        start_iter = goal.get("iteration", 0) + 1

        if start_iter == 1:
            # 신규 목표: 환영 메시지 및 첫 분해·배분
            await self._send(chat_id,
                f"🎯 목표 설정 완료: {goal['description'][:200]}\n"
                f"최대 {self._max_iterations}회 반복으로 목표 달성을 추진합니다.")
            subtasks = await self._orch.decompose(goal["description"])
            task_ids = await self._orch.dispatch(goal_id, subtasks, chat_id)
            if not task_ids:
                logger.warning(f"[GoalTracker] 첫 dispatch 결과 없음 ({goal_id})")
        else:
            # 재시작 복구: 이전 iteration에서 이어서 실행
            logger.info(
                f"[GoalTracker] {goal_id} 재시작 복구 — "
                f"iteration {start_iter - 1}/{self._max_iterations}에서 재개"
            )
            await self._send(chat_id,
                f"♻️ 목표 재개: {goal['description'][:200]}\n"
                f"iteration {start_iter - 1}/{self._max_iterations}에서 재시작합니다.")

        last_done_count = 0
        stagnation = 0
        for iteration in range(start_iter, self._max_iterations + 1):
            # 취소 확인
            if self._is_cancelled(goal_id):
                await self._db.update_goal(goal_id, status="cancelled")
                await self._send(chat_id, f"🛑 목표 취소됨 (iteration {iteration})")
                return GoalStatus(achieved=False, progress_summary="사용자 취소",
                                  remaining_work="", confidence=0.0)

            await self._db.update_goal(goal_id, iteration=iteration)
            logger.info(f"[GoalTracker] {goal_id} iteration {iteration}/{self._max_iterations}")

            # 부서 작업 완료 대기
            await self._wait_for_completion(goal_id)

            # 취소 재확인 (대기 중 취소됐을 수 있음)
            if self._is_cancelled(goal_id):
                await self._db.update_goal(goal_id, status="cancelled")
                await self._send(chat_id, f"🛑 목표 취소됨 (iteration {iteration})")
                return GoalStatus(achieved=False, progress_summary="사용자 취소",
                                  remaining_work="", confidence=0.0)

            # 평가
            status = await self.evaluate_progress(goal_id)

            if status.achieved:
                await self._db.update_goal(goal_id, status="achieved",
                                           last_progress=status.progress_summary)
                await self._send(chat_id,
                    f"✅ 목표 달성! (iteration {iteration})\n"
                    f"📊 {status.progress_summary}")
                return status

            # 정체 감지: done_count가 이전과 동일하면 stagnation (LLM 응답 문자열 불안정 대비)
            if status.done_count == last_done_count:
                stagnation += 1
                await self._db.update_goal(goal_id, stagnation_count=stagnation)
                if stagnation >= self._max_stagnation:
                    await self._db.update_goal(goal_id, status="stagnated",
                                               last_progress=status.progress_summary)
                    await self._send(chat_id,
                        f"⚠️ 목표 정체 감지 ({stagnation}회 연속 진전 없음)\n"
                        f"📊 {status.progress_summary}\n"
                        f"사용자 개입이 필요합니다.")
                    return status
            else:
                stagnation = 0
                await self._db.update_goal(goal_id, stagnation_count=0)

            last_done_count = status.done_count
            await self._db.update_goal(goal_id, last_progress=status.progress_summary)

            # 재계획·재배분
            await self._send(chat_id,
                f"🔄 iteration {iteration}: 목표 미달성\n"
                f"📊 {status.progress_summary}\n"
                f"📋 남은 작업: {status.remaining_work[:200]}\n"
                f"재계획 후 재배분합니다...")

            await self.replan(goal_id, status.remaining_work, chat_id)

        # 최대 반복 도달
        final_status = await self.evaluate_progress(goal_id)
        await self._db.update_goal(goal_id, status="max_iterations_reached",
                                   last_progress=final_status.progress_summary)
        await self._send(chat_id,
            f"⏰ 최대 반복 횟수({self._max_iterations}) 도달\n"
            f"📊 {final_status.progress_summary}\n"
            f"남은 작업: {final_status.remaining_work[:200]}")
        return final_status

    async def _wait_for_completion(self, goal_id: str) -> None:
        """모든 서브태스크가 terminal 상태(done/failed/cancelled)가 될 때까지 대기.

        최대 대기: poll_interval_sec * WAIT_TIMEOUT_MULTIPLIER (기본 30*60=1800초=30분).
        취소 이벤트 발생 시 즉시 반환.
        """
        max_wait = self._poll_interval * WAIT_TIMEOUT_MULTIPLIER
        waited = 0.0
        poll_interval = min(self._poll_interval, 10.0)
        cancel_event = self._cancel_events.get(goal_id)
        terminal = {"done", "failed", "cancelled"}

        while waited < max_wait:
            if cancel_event and cancel_event.is_set():
                return

            subtasks = await self._db.get_subtasks(goal_id)
            if not subtasks:
                break
            active = [s for s in subtasks if s["status"] not in terminal]
            if not active:
                # 루트 PM 태스크가 아직 실행 중이면 계속 대기 (dispatch collision 방지)
                root_active = await self._db.get_active_parent_tasks()
                if not root_active:
                    break

            # cancel_event와 sleep을 동시에 대기
            if cancel_event:
                try:
                    await asyncio.wait_for(cancel_event.wait(), timeout=poll_interval)
                    return  # 취소됨
                except asyncio.TimeoutError:
                    pass  # 타임아웃 → 다음 폴링
            else:
                await asyncio.sleep(poll_interval)
            waited += poll_interval

        if waited >= max_wait:
            logger.warning(f"[GoalTracker] {goal_id} 대기 시간 초과 ({max_wait}s)")

    # ── OKR 계층 CRUD (Phase 1.2) ──────────────────────────────────

    async def create_objective(
        self,
        title: str,
        description: str,
        deadline: str,
        chat_id: int = 0,
    ) -> str:
        """Objective(연간/분기 목표) 생성."""
        return await self.start_goal(
            title=title,
            description=description,
            goal_type=GoalType.OBJECTIVE,
            deadline=deadline,
            chat_id=chat_id,
        )

    async def create_key_result(
        self,
        title: str,
        description: str,
        parent_objective_id: str,
        deadline: str,
        kpi_metric: str | None = None,
        kpi_target: float | None = None,
        kpi_unit: str | None = None,
        weight: float | None = None,
    ) -> str:
        """Key Result 생성 (Objective 하위)."""
        return await self.start_goal(
            title=title,
            description=description,
            goal_type=GoalType.KEY_RESULT,
            parent_goal_id=parent_objective_id,
            deadline=deadline,
            kpi_metric=kpi_metric,
            kpi_target=kpi_target,
            kpi_unit=kpi_unit,
            weight=weight,
        )

    async def create_initiative(
        self,
        title: str,
        description: str,
        parent_kr_id: str,
        deadline: str | None = None,
    ) -> str:
        """Initiative 생성 (KR 하위)."""
        return await self.start_goal(
            title=title,
            description=description,
            goal_type=GoalType.INITIATIVE,
            parent_goal_id=parent_kr_id,
            deadline=deadline,
        )

    async def get_children(
        self,
        parent_id: str,
        goal_type: GoalType | None = None,
    ) -> list[dict]:
        """특정 목표의 하위 목표 조회."""
        gt_str = goal_type.value if goal_type else None
        return await self._db.get_children_goals(parent_id, goal_type=gt_str)

    async def get_objectives(self, status: str = "active") -> list[dict]:
        """Objective 목록 조회."""
        return await self._db.get_goals_by_type("objective", status=status)

    async def get_key_results(
        self,
        parent_id: str | None = None,
        status: str = "active",
    ) -> list[dict]:
        """Key Result 목록 조회."""
        krs = await self._db.get_goals_by_type("key_result", status=status)
        if parent_id:
            krs = [kr for kr in krs if kr.get("parent_goal_id") == parent_id]
        return krs

    async def update_kpi(
        self,
        goal_id: str,
        kpi_current: float,
    ) -> dict:
        """KPI 현재값 업데이트 + 진척률 자동 계산."""
        goal = await self._db.get_goal(goal_id)
        if not goal:
            raise ValueError(f"Goal not found: {goal_id}")
        kpi_target = goal.get("kpi_target")
        progress = 0.0
        if kpi_target and kpi_target > 0:
            progress = min(kpi_current / kpi_target, 1.0)
        updated = await self._db.update_goal(
            goal_id, kpi_current=kpi_current, progress=progress,
        )
        return updated

    async def trace_to_kr(self, goal_id: str) -> dict | None:
        """Task/Initiative에서 상위 KR까지 추적 (최대 3단계)."""
        current_id = goal_id
        for _ in range(3):
            goal = await self._db.get_goal(current_id)
            if not goal:
                return None
            if goal.get("goal_type") == GoalType.KEY_RESULT.value:
                return goal
            parent_id = goal.get("parent_goal_id")
            if not parent_id:
                return None
            current_id = parent_id
        return None

    async def record_snapshot(
        self,
        goal_id: str,
        snapshot_type: str,
        snapshot_date: str,
    ) -> None:
        """진척 스냅샷 기록."""
        goal = await self._db.get_goal(goal_id)
        if not goal:
            return
        await self._db.record_progress_snapshot(
            goal_id=goal_id,
            progress=goal.get("progress", 0.0),
            snapshot_type=snapshot_type,
            snapshot_date=snapshot_date,
            kpi_current=goal.get("kpi_current"),
        )

    # ── 계층 진척률 집계 (Phase 1.3) ──────────────────────────────

    async def calculate_progress(self, goal_id: str) -> float:
        """계층 진척률 집계: 하위 목표 → 상위 목표 롤업.

        - Task: 자체 progress 반환 (iteration 기반)
        - Initiative: 하위 Task들의 평균 progress
        - KR: kpi_current/kpi_target 또는 하위 Initiative 평균
        - Objective: 하위 KR들의 가중 평균 (weight 기반)

        Returns:
            0.0~1.0 사이 진척률.
        """
        goal = await self._db.get_goal(goal_id)
        if not goal:
            return 0.0

        goal_type = goal.get("goal_type", "task")
        children = await self._db.get_children_goals(goal_id)

        # Task: 하위 없음 — 자체 progress 반환
        if goal_type == GoalType.TASK.value or not children:
            return goal.get("progress", 0.0)

        # KR: KPI가 설정되어 있으면 KPI 기반 진척률 우선
        if goal_type == GoalType.KEY_RESULT.value:
            kpi_target = goal.get("kpi_target")
            kpi_current = goal.get("kpi_current")
            if kpi_target and kpi_target > 0 and kpi_current is not None:
                return min(kpi_current / kpi_target, 1.0)

        # Objective: 가중 평균 (weight 기반)
        if goal_type == GoalType.OBJECTIVE.value:
            return await self._weighted_average_progress(children)

        # Initiative / KR(KPI 없음): 하위 목표 단순 평균
        return await self._simple_average_progress(children)

    async def _weighted_average_progress(
        self, children: list[dict],
    ) -> float:
        """가중 평균 진척률 계산 (Objective → KR 롤업)."""
        total_weight = 0.0
        weighted_sum = 0.0
        for child in children:
            child_progress = await self.calculate_progress(child["id"])
            w = child.get("weight") or 1.0
            weighted_sum += child_progress * w
            total_weight += w
        if total_weight == 0:
            return 0.0
        return weighted_sum / total_weight

    async def _simple_average_progress(
        self, children: list[dict],
    ) -> float:
        """단순 평균 진척률 계산 (Initiative → Task 롤업)."""
        if not children:
            return 0.0
        total = 0.0
        for child in children:
            total += await self.calculate_progress(child["id"])
        return total / len(children)

    async def update_hierarchy_progress(self, goal_id: str) -> float:
        """계층 진척률을 재계산하고 DB에 저장.

        하위 → 상위 방향으로 진척률을 롤업하고,
        부모 목표의 progress 필드도 함께 업데이트한다.

        Returns:
            업데이트된 진척률.
        """
        progress = await self.calculate_progress(goal_id)
        await self._db.update_goal(goal_id, progress=progress)

        # 부모 목표도 재귀적으로 업데이트
        goal = await self._db.get_goal(goal_id)
        if goal and goal.get("parent_goal_id"):
            await self.update_hierarchy_progress(goal["parent_goal_id"])

        return progress
