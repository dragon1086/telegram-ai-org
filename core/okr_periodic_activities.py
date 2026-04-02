"""OKR 주기적 활동 관리 — 일일회고/주간회의/월간리뷰/분기평가.

OKR 계층의 check_interval 설정에 따라 주기적으로 진척 확인,
스냅샷 기록, 보고서 생성을 수행한다.

Activity 유형:
    - daily_retro: 일일 회고 (Task 단위)
    - weekly_review: 주간 점검 (Initiative 단위)
    - monthly_review: 월간 리뷰 (KR 단위)
    - quarterly_eval: 분기 평가 (Objective 단위)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger

from core.context_db import ContextDB
from core.goal_tracker import (
    DeadlineChecker,
    GoalTracker,
    GoalType,
)


@dataclass
class ActivityReport:
    """주기적 활동 결과 보고서."""

    activity_type: str
    date: str
    goals_checked: int
    snapshots_recorded: int
    alerts_generated: int
    summary: str
    details: list[dict]


class OKRPeriodicActivities:
    """OKR 주기적 활동 매니저.

    GoalTracker, DeadlineChecker와 연동하여
    각 주기별 활동을 실행한다.
    """

    def __init__(
        self,
        context_db: ContextDB,
        goal_tracker: GoalTracker,
        deadline_checker: DeadlineChecker | None = None,
    ) -> None:
        self._db = context_db
        self._tracker = goal_tracker
        self._deadline = deadline_checker or DeadlineChecker(context_db)

    async def run_daily_retro(
        self,
        date: str | None = None,
    ) -> ActivityReport:
        """일일 회고: Task 단위 진척 확인 + 스냅샷.

        - 모든 활성 Task의 progress 확인
        - 일일 스냅샷 기록
        - 마감 임박 알림 수집
        """
        if not date:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        tasks = await self._db.get_goals_by_type(
            GoalType.TASK.value, status="active",
        )
        details = []
        snapshots = 0

        for task in tasks:
            # 스냅샷 기록
            await self._tracker.record_snapshot(
                task["id"], "daily", date,
            )
            snapshots += 1

            details.append({
                "id": task["id"],
                "title": task.get("title", ""),
                "progress": task.get("progress", 0),
                "status": task.get("status", ""),
            })

        # 마감 알림
        now = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        alerts = await self._deadline.check_by_type(
            GoalType.TASK.value, now=now,
        )

        summary = (
            f"일일 회고 ({date}): "
            f"Task {len(tasks)}개 점검, "
            f"스냅샷 {snapshots}건, "
            f"마감 알림 {len(alerts)}건"
        )
        logger.info(f"[OKR] {summary}")

        return ActivityReport(
            activity_type="daily_retro",
            date=date,
            goals_checked=len(tasks),
            snapshots_recorded=snapshots,
            alerts_generated=len(alerts),
            summary=summary,
            details=details,
        )

    async def run_weekly_review(
        self,
        date: str | None = None,
    ) -> ActivityReport:
        """주간 점검: Initiative 단위 진척 + 계층 업데이트.

        - Initiative progress 재계산
        - 주간 스냅샷 기록
        - 상위 KR progress 업데이트
        """
        if not date:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        initiatives = await self._db.get_goals_by_type(
            GoalType.INITIATIVE.value, status="active",
        )
        details = []
        snapshots = 0

        for init in initiatives:
            # 계층 진척률 재계산
            progress = await self._tracker.calculate_progress(init["id"])
            await self._db.update_goal(init["id"], progress=progress)

            # 스냅샷 기록
            await self._tracker.record_snapshot(
                init["id"], "weekly", date,
            )
            snapshots += 1

            details.append({
                "id": init["id"],
                "title": init.get("title", ""),
                "progress": progress,
            })

        # KR도 업데이트
        krs = await self._db.get_goals_by_type(
            GoalType.KEY_RESULT.value, status="active",
        )
        for kr in krs:
            await self._tracker.update_hierarchy_progress(kr["id"])

        now = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        alerts = await self._deadline.check_by_type(
            GoalType.INITIATIVE.value, now=now,
        )

        summary = (
            f"주간 점검 ({date}): "
            f"Initiative {len(initiatives)}개, "
            f"KR {len(krs)}개 업데이트, "
            f"마감 알림 {len(alerts)}건"
        )
        logger.info(f"[OKR] {summary}")

        return ActivityReport(
            activity_type="weekly_review",
            date=date,
            goals_checked=len(initiatives) + len(krs),
            snapshots_recorded=snapshots,
            alerts_generated=len(alerts),
            summary=summary,
            details=details,
        )

    async def run_monthly_review(
        self,
        date: str | None = None,
    ) -> ActivityReport:
        """월간 리뷰: KR 단위 KPI 점검 + Objective 업데이트.

        - KR KPI 진척률 확인
        - 월간 스냅샷 기록
        - Objective 가중 평균 업데이트
        """
        if not date:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        krs = await self._db.get_goals_by_type(
            GoalType.KEY_RESULT.value, status="active",
        )
        details = []
        snapshots = 0

        for kr in krs:
            progress = await self._tracker.calculate_progress(kr["id"])
            await self._db.update_goal(kr["id"], progress=progress)

            await self._tracker.record_snapshot(
                kr["id"], "monthly", date,
            )
            snapshots += 1

            details.append({
                "id": kr["id"],
                "title": kr.get("title", ""),
                "progress": progress,
                "kpi_current": kr.get("kpi_current"),
                "kpi_target": kr.get("kpi_target"),
            })

        # Objective 업데이트
        objectives = await self._db.get_goals_by_type(
            GoalType.OBJECTIVE.value, status="active",
        )
        for obj in objectives:
            await self._tracker.update_hierarchy_progress(obj["id"])

        now = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        alerts = await self._deadline.check_by_type(
            GoalType.KEY_RESULT.value, now=now,
        )

        summary = (
            f"월간 리뷰 ({date}): "
            f"KR {len(krs)}개, "
            f"Objective {len(objectives)}개 업데이트, "
            f"마감 알림 {len(alerts)}건"
        )
        logger.info(f"[OKR] {summary}")

        return ActivityReport(
            activity_type="monthly_review",
            date=date,
            goals_checked=len(krs) + len(objectives),
            snapshots_recorded=snapshots,
            alerts_generated=len(alerts),
            summary=summary,
            details=details,
        )

    async def run_quarterly_eval(
        self,
        date: str | None = None,
    ) -> ActivityReport:
        """분기 평가: Objective 단위 종합 평가.

        - 전체 Objective 진척률 재계산
        - 분기 스냅샷 기록
        - 미달 Objective 자동 롤오버 후보 식별
        """
        if not date:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        objectives = await self._db.get_goals_by_type(
            GoalType.OBJECTIVE.value, status="active",
        )
        details = []
        snapshots = 0
        rollover_candidates = []

        for obj in objectives:
            progress = await self._tracker.calculate_progress(obj["id"])
            await self._db.update_goal(obj["id"], progress=progress)

            await self._tracker.record_snapshot(
                obj["id"], "quarterly", date,
            )
            snapshots += 1

            is_underperforming = progress < 0.7
            detail = {
                "id": obj["id"],
                "title": obj.get("title", ""),
                "progress": progress,
                "grade": self._grade(progress),
                "rollover_candidate": is_underperforming,
            }
            details.append(detail)

            if is_underperforming:
                rollover_candidates.append(obj["id"])

        summary = (
            f"분기 평가 ({date}): "
            f"Objective {len(objectives)}개, "
            f"롤오버 후보 {len(rollover_candidates)}개"
        )
        logger.info(f"[OKR] {summary}")

        return ActivityReport(
            activity_type="quarterly_eval",
            date=date,
            goals_checked=len(objectives),
            snapshots_recorded=snapshots,
            alerts_generated=len(rollover_candidates),
            summary=summary,
            details=details,
        )

    def _grade(self, progress: float) -> str:
        """진척률 → 등급 변환."""
        if progress >= 0.9:
            return "S"
        if progress >= 0.8:
            return "A"
        if progress >= 0.7:
            return "B"
        if progress >= 0.5:
            return "C"
        if progress >= 0.3:
            return "D"
        return "F"
