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
from typing import Callable, Awaitable

from loguru import logger

from core.context_db import ContextDB
from core.pm_orchestrator import PMOrchestrator, KNOWN_DEPTS
from core.llm_provider import get_provider

ENABLE_GOAL_TRACKER = os.environ.get("ENABLE_GOAL_TRACKER", "0") == "1"

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

    async def set_goal(self, description: str, chat_id: int) -> dict:
        """새 목표 설정 및 DB 저장."""
        await self._init_counter()
        goal_id = self._next_goal_id()
        goal = await self._db.create_goal(
            goal_id=goal_id,
            description=description,
            created_by=self._org_id,
            chat_id=chat_id,
            max_iterations=self._max_iterations,
        )
        logger.info(f"[GoalTracker] 목표 설정: {goal_id} — {description[:80]}")
        return goal

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

        total = len(subtasks)
        done = [s for s in subtasks if s["status"] == "done"]
        failed = [s for s in subtasks if s["status"] == "failed"]
        in_progress = [s for s in subtasks if s["status"] in ("assigned", "in_progress")]

        # LLM 평가 시도
        llm_status = await self._llm_evaluate(goal, subtasks, done)
        if llm_status is not None:
            # LLM 결과에도 안정 지표(done_count, total_count) 추가
            llm_status.done_count = len(done)
            llm_status.total_count = total
            return llm_status

        # Fallback: 규칙 기반
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

        remaining_descs = [s["description"][:50] for s in subtasks if s["status"] != "done"]
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
        "COMPLETED TASKS AND RESULTS:\n{results}\n\n"
        "PENDING/FAILED TASKS:\n{pending}\n\n"
        "Based on the completed results, has the GOAL been sufficiently achieved?\n"
        "Reply in this exact format (3 lines):\n"
        "ACHIEVED: YES or NO\n"
        "PROGRESS: one-line summary of what's been done\n"
        "REMAINING: what still needs to be done (or 'nothing' if achieved)\n"
    )

    async def _llm_evaluate(self, goal: dict, subtasks: list[dict],
                            done: list[dict]) -> GoalStatus | None:
        """LLM으로 목표 달성 평가. 실패 시 None (fallback으로)."""
        provider = get_provider()
        if provider is None:
            return None

        results_text = "\n".join(
            f"- [{KNOWN_DEPTS.get(s.get('assigned_dept', ''), '?')}] {s.get('result', '(결과 없음)')[:200]}"
            for s in done
        ) or "(없음)"

        pending_text = "\n".join(
            f"- [{KNOWN_DEPTS.get(s.get('assigned_dept', ''), '?')}] {s['status']}: {s['description'][:100]}"
            for s in subtasks if s["status"] != "done"
        ) or "(없음)"

        prompt = self._LLM_EVALUATE_PROMPT.format(
            goal=goal["description"][:500],
            results=results_text,
            pending=pending_text,
        )

        try:
            response = await asyncio.wait_for(
                provider.complete(prompt, timeout=15.0),
                timeout=18.0,
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
        """이전 iteration의 미완료 서브태스크를 cancelled로 마킹."""
        subtasks = await self._db.get_subtasks(goal_id)
        for st in subtasks:
            if st["status"] in ("pending", "assigned", "in_progress"):
                await self._db.update_pm_task_status(st["id"], "cancelled")

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

        await self._send(chat_id,
            f"🎯 목표 설정 완료: {goal['description'][:200]}\n"
            f"최대 {self._max_iterations}회 반복으로 목표 달성을 추진합니다.")

        # 첫 분해·배분
        subtasks = await self._orch.decompose(goal["description"])
        task_ids = await self._orch.dispatch(goal_id, subtasks, chat_id)
        if not task_ids:
            logger.warning(f"[GoalTracker] 첫 dispatch 결과 없음 ({goal_id})")

        last_done_count = 0
        stagnation = 0
        for iteration in range(1, self._max_iterations + 1):
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
