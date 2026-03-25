"""AutonomousLoop — GoalTracker 기반 idle→evaluate→replan→dispatch 자율 루프.

GoalTracker가 개별 목표 루프를 담당한다면,
AutonomousLoop는 여러 목표를 관장하는 외부 오케스트레이터 루프다.

상태 머신:
    idle     → (목표 존재 확인) → evaluate
    evaluate → (진행 평가) → replan  (또는 idle if no goals)
    replan   → (서브태스크 생성) → dispatch
    dispatch → (조직별 배분) → idle

Feature flag: ENABLE_GOAL_TRACKER=1 (GoalTracker와 동일 플래그 사용)
루프 간격: orchestration.yaml autonomous_loop.idle_sleep_sec (기본 300초)
"""
from __future__ import annotations

import asyncio
import os
from enum import Enum
from typing import Callable, Awaitable

from loguru import logger

# GoalTracker와 동일 feature flag
ENABLE_GOAL_TRACKER = os.environ.get("ENABLE_GOAL_TRACKER", "0") == "1"

# 기본 idle sleep (orchestration.yaml에서 오버라이드 가능)
DEFAULT_IDLE_SLEEP_SEC = 300   # 5분
DEFAULT_MAX_DISPATCH_PER_CYCLE = 3  # 한 사이클에 최대 배분 목표 수

# 조직별 태스크 타입 매핑 (replan 단계에서 서브태스크 배분 기준)
ORG_TASK_TYPE_MAP: dict[str, list[str]] = {
    "aiorg_engineering_bot": ["구현", "코드", "API", "버그", "개발", "테스트"],
    "aiorg_product_bot":     ["기획", "PRD", "요구사항", "스펙", "정책"],
    "aiorg_design_bot":      ["디자인", "UI", "UX", "와이어프레임", "프로토타입"],
    "aiorg_growth_bot":      ["성장", "마케팅", "지표", "분석", "전략"],
    "aiorg_ops_bot":         ["배포", "인프라", "모니터링", "운영", "DevOps"],
    "aiorg_research_bot":    ["조사", "리서치", "레퍼런스", "경쟁사", "분석"],
}


class LoopState(str, Enum):
    IDLE = "idle"
    EVALUATE = "evaluate"
    REPLAN = "replan"
    DISPATCH = "dispatch"


class AutonomousLoop:
    """idle→evaluate→replan→dispatch→idle 자율 루프.

    GoalTracker 인스턴스를 받아 활성 목표를 주기적으로 평가·재계획·배분한다.
    GoalTracker.run_loop()가 개별 목표를 다룬다면, AutonomousLoop는 여러 목표를
    주기적으로 관리하는 상위 루프다.

    사용법:
        loop = AutonomousLoop(
            goal_tracker=tracker,
            idle_sleep_sec=300,
            send_func=my_send,
        )
        asyncio.create_task(loop.run())
    """

    def __init__(
        self,
        goal_tracker,           # GoalTracker 인스턴스
        idle_sleep_sec: float = DEFAULT_IDLE_SLEEP_SEC,
        max_dispatch: int = DEFAULT_MAX_DISPATCH_PER_CYCLE,
        send_func: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._tracker = goal_tracker
        self._idle_sleep = idle_sleep_sec
        self._max_dispatch = max_dispatch
        self._send = send_func or _noop_send
        self._state = LoopState.IDLE
        self._running = False
        self._stop_event = asyncio.Event()

    @property
    def state(self) -> LoopState:
        return self._state

    def stop(self) -> None:
        """루프 종료 요청."""
        self._stop_event.set()
        logger.info("[AutonomousLoop] 종료 요청됨")

    async def run(self) -> None:
        """자율 루프 메인 진입점. 백그라운드 태스크로 실행한다."""
        if self._running:
            logger.warning("[AutonomousLoop] 이미 실행 중 — 중복 시작 방지")
            return
        self._running = True
        logger.info("[AutonomousLoop] 자율 루프 시작 (idle_sleep={}s)", self._idle_sleep)
        try:
            while not self._stop_event.is_set():
                await self._tick()
        except asyncio.CancelledError:
            logger.info("[AutonomousLoop] 취소됨")
        finally:
            self._running = False
            logger.info("[AutonomousLoop] 자율 루프 종료")

    async def _tick(self) -> None:
        """한 사이클: idle → evaluate → replan → dispatch → idle."""
        # ── IDLE: 다음 사이클까지 대기 ─────────────────────────────────────
        self._state = LoopState.IDLE
        logger.debug("[AutonomousLoop] IDLE — {}s 대기", self._idle_sleep)
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=self._idle_sleep)
            return  # stop_event 발생 → 루프 종료
        except asyncio.TimeoutError:
            pass  # 정상 타임아웃 → 다음 단계로

        if self._stop_event.is_set():
            return

        # ── EVALUATE: 활성 목표 로드 및 진행 상태 평가 ───────────────────────
        self._state = LoopState.EVALUATE
        logger.info("[AutonomousLoop] EVALUATE — 활성 목표 로드")
        try:
            active_goals = await self._tracker.get_active_goals()
        except Exception as e:
            logger.error(f"[AutonomousLoop] EVALUATE 오류: {e}")
            return

        if not active_goals:
            logger.debug("[AutonomousLoop] 활성 목표 없음 → IDLE 복귀")
            self._state = LoopState.IDLE
            return

        logger.info(f"[AutonomousLoop] 활성 목표 {len(active_goals)}개 평가 중")

        # ── REPLAN: 평가 결과 기반 서브태스크 재계획 ─────────────────────────
        self._state = LoopState.REPLAN
        goals_needing_dispatch: list[dict] = []

        for goal in active_goals[:self._max_dispatch]:
            goal_id = goal["id"]
            try:
                status = await self._tracker.evaluate_progress(goal_id)
                if status.achieved:
                    await self._tracker.update_goal_status(goal_id, "achieved")
                    await self._send(
                        f"✅ [AutonomousLoop] 목표 달성: {goal.get('title') or goal['description'][:60]}"
                    )
                    logger.info(f"[AutonomousLoop] 목표 달성 처리: {goal_id}")
                else:
                    goals_needing_dispatch.append({"goal": goal, "status": status})
            except Exception as e:
                logger.error(f"[AutonomousLoop] REPLAN 평가 오류 ({goal_id}): {e}")

        if not goals_needing_dispatch:
            return

        # ── DISPATCH: 조직별 서브태스크 배분 ──────────────────────────────────
        self._state = LoopState.DISPATCH
        logger.info(f"[AutonomousLoop] DISPATCH — {len(goals_needing_dispatch)}개 목표 재배분")
        for item in goals_needing_dispatch:
            goal = item["goal"]
            status = item["status"]
            goal_id = goal["id"]
            try:
                chat_id = goal.get("chat_id", 0) or 0

                # iteration 카운터 증가 및 최대 반복 횟수 체크
                new_iter, max_iter = await self._tracker.tick_iteration(goal_id)
                if new_iter > max_iter:
                    await self._tracker.update_goal_status(goal_id, "max_iterations_reached")
                    await self._send(
                        f"⏰ [AutonomousLoop] 목표 최대 반복({max_iter}회) 도달: "
                        f"{goal.get('title') or goal_id}"
                    )
                    logger.info(
                        f"[AutonomousLoop] max_iterations 도달, 목표 종료: {goal_id} "
                        f"({new_iter}/{max_iter})"
                    )
                    continue

                await self._tracker.replan(
                    goal_id=goal_id,
                    remaining_work=status.remaining_work,
                    chat_id=chat_id,
                )
                logger.info(
                    f"[AutonomousLoop] {goal_id} 재배분 완료 "
                    f"(iteration {new_iter}/{max_iter})"
                )
            except Exception as e:
                logger.error(f"[AutonomousLoop] DISPATCH 오류 ({goal_id}): {e}")

    @staticmethod
    def infer_org_for_task(task_description: str) -> str | None:
        """태스크 설명에서 담당 조직을 추론 (키워드 매칭).

        Returns:
            org_id 또는 None (매칭 없음 → PM이 결정).
        """
        lower = task_description.lower()
        for org_id, keywords in ORG_TASK_TYPE_MAP.items():
            if any(kw in lower for kw in keywords):
                return org_id
        return None


async def _noop_send(text: str) -> None:  # pragma: no cover
    pass


def load_loop_config(orchestration_yaml_path: str | None = None) -> dict:
    """orchestration.yaml에서 autonomous_loop 설정 로드.

    Returns:
        {idle_sleep_sec: int, max_dispatch: int}
    """
    import yaml
    from pathlib import Path

    default = {"idle_sleep_sec": DEFAULT_IDLE_SLEEP_SEC, "max_dispatch": DEFAULT_MAX_DISPATCH_PER_CYCLE}
    yaml_path = orchestration_yaml_path or str(
        Path(__file__).parent.parent / "orchestration.yaml"
    )
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        loop_cfg = cfg.get("autonomous_loop", {})
        if "idle_sleep_sec" in loop_cfg:
            default["idle_sleep_sec"] = int(loop_cfg["idle_sleep_sec"])
        if "max_dispatch" in loop_cfg:
            default["max_dispatch"] = int(loop_cfg["max_dispatch"])
    except Exception as e:
        logger.warning(f"[AutonomousLoop] orchestration.yaml 로드 실패, 기본값 사용: {e}")
    return default
