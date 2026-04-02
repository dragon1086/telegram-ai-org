"""OKR 성과평가 + 봇 성격 진화 연동.

분기 평가 결과를 기반으로:
1. 부서별 성과 점수 산출 (5가지 기준)
2. 등급 부여 (S/A/B/C/D/F)
3. 성격 진화 프롬프트 프래그먼트 생성
4. DB에 저장 + BotCharacterEvolution 연동

평가 기준:
    - completion_rate: 목표 완료율
    - quality: 산출물 품질 (LLM 평가 또는 규칙 기반)
    - speed: 마감 대비 완료 속도
    - kr_contribution: KR 기여도
    - collaboration: 협업 빈도 (COLLAB 태그 사용)
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from loguru import logger

from core.context_db import ContextDB
from core.goal_tracker import GoalTracker, GoalType


@dataclass
class EvaluationResult:
    """부서 성과 평가 결과."""

    dept_id: str
    period_start: str
    period_end: str
    period_type: str
    overall_score: float
    grade: str
    criteria_scores: dict[str, float]
    strengths: list[str]
    weaknesses: list[str]
    prompt_fragment: str


class PerformanceEvaluator:
    """부서별 성과 평가기.

    GoalTracker 데이터와 DB 이력을 기반으로
    각 부서의 성과를 평가한다.
    """

    # 평가 기준 가중치
    CRITERIA_WEIGHTS = {
        "completion_rate": 0.30,
        "quality": 0.25,
        "speed": 0.20,
        "kr_contribution": 0.15,
        "collaboration": 0.10,
    }

    def __init__(
        self,
        context_db: ContextDB,
        goal_tracker: GoalTracker,
    ) -> None:
        self._db = context_db
        self._tracker = goal_tracker

    async def evaluate_department(
        self,
        dept_id: str,
        period_start: str,
        period_end: str,
        period_type: str = "quarterly",
    ) -> EvaluationResult:
        """부서 성과 평가 실행.

        Args:
            dept_id: 부서 ID (예: engineering, design).
            period_start: 평가 시작일 (YYYY-MM-DD).
            period_end: 평가 종료일 (YYYY-MM-DD).
            period_type: 평가 유형 (quarterly/monthly).

        Returns:
            EvaluationResult.
        """
        criteria = await self._calculate_criteria(dept_id)
        overall = self._weighted_score(criteria)
        grade = self._grade(overall)
        strengths = self._identify_strengths(criteria)
        weaknesses = self._identify_weaknesses(criteria)
        prompt_fragment = self._generate_prompt_fragment(
            dept_id, grade, strengths, weaknesses,
        )

        # DB 저장
        await self._db.save_performance_evaluation(
            dept_id=dept_id,
            period_start=period_start,
            period_end=period_end,
            period_type=period_type,
            overall_score=overall,
            grade=grade,
            criteria_scores=json.dumps(criteria),
            strengths=json.dumps(strengths, ensure_ascii=False),
            weaknesses=json.dumps(weaknesses, ensure_ascii=False),
            prompt_fragment=prompt_fragment,
        )

        logger.info(
            f"[PerformanceEval] {dept_id}: {grade} ({overall:.1f}점)"
        )

        return EvaluationResult(
            dept_id=dept_id,
            period_start=period_start,
            period_end=period_end,
            period_type=period_type,
            overall_score=overall,
            grade=grade,
            criteria_scores=criteria,
            strengths=strengths,
            weaknesses=weaknesses,
            prompt_fragment=prompt_fragment,
        )

    async def _calculate_criteria(
        self, dept_id: str,
    ) -> dict[str, float]:
        """평가 기준별 점수 산출 (0~100)."""
        # 해당 부서의 Task 목록 조회
        all_tasks = await self._db.get_goals_by_type(
            GoalType.TASK.value,
        )
        dept_tasks = [
            t for t in all_tasks
            if t.get("created_by") == dept_id
        ]

        completion_rate = self._calc_completion_rate(dept_tasks)
        speed = self._calc_speed(dept_tasks)
        kr_contribution = await self._calc_kr_contribution(dept_tasks)

        return {
            "completion_rate": completion_rate,
            "quality": 70.0,  # 기본값 (LLM 평가 미연동 시)
            "speed": speed,
            "kr_contribution": kr_contribution,
            "collaboration": 60.0,  # 기본값 (COLLAB 추적 미연동 시)
        }

    def _calc_completion_rate(self, tasks: list[dict]) -> float:
        """완료율 산출."""
        if not tasks:
            return 0.0
        completed = sum(
            1 for t in tasks
            if t.get("status") in ("achieved", "done", "completed")
        )
        return (completed / len(tasks)) * 100

    def _calc_speed(self, tasks: list[dict]) -> float:
        """속도 점수 (deadline 준수율 기반)."""
        if not tasks:
            return 70.0  # 기본값
        on_time = 0
        with_deadline = 0
        for t in tasks:
            if t.get("deadline") and t.get("status") in (
                "achieved", "done", "completed",
            ):
                with_deadline += 1
                # updated_at <= deadline이면 on-time
                updated = t.get("updated_at", "")
                if updated and updated[:10] <= t["deadline"]:
                    on_time += 1
        if with_deadline == 0:
            return 70.0
        return (on_time / with_deadline) * 100

    async def _calc_kr_contribution(
        self, tasks: list[dict],
    ) -> float:
        """KR 기여도 — Task가 KR에 연결된 비율."""
        if not tasks:
            return 0.0
        linked = 0
        for t in tasks:
            kr = await self._tracker.trace_to_kr(t.get("id", ""))
            if kr:
                linked += 1
        return (linked / len(tasks)) * 100

    def _weighted_score(self, criteria: dict[str, float]) -> float:
        """가중 평균 종합 점수."""
        total = 0.0
        for key, weight in self.CRITERIA_WEIGHTS.items():
            total += criteria.get(key, 0) * weight
        return round(total, 1)

    def _grade(self, score: float) -> str:
        """종합 점수 → 등급."""
        if score >= 90:
            return "S"
        if score >= 80:
            return "A"
        if score >= 70:
            return "B"
        if score >= 50:
            return "C"
        if score >= 30:
            return "D"
        return "F"

    def _identify_strengths(
        self, criteria: dict[str, float],
    ) -> list[str]:
        """강점 식별 (80점 이상 기준)."""
        labels = {
            "completion_rate": "목표 완료율",
            "quality": "산출물 품질",
            "speed": "실행 속도",
            "kr_contribution": "KR 기여도",
            "collaboration": "협업",
        }
        return [
            labels.get(k, k)
            for k, v in criteria.items()
            if v >= 80
        ]

    def _identify_weaknesses(
        self, criteria: dict[str, float],
    ) -> list[str]:
        """약점 식별 (50점 미만 기준)."""
        labels = {
            "completion_rate": "목표 완료율",
            "quality": "산출물 품질",
            "speed": "실행 속도",
            "kr_contribution": "KR 기여도",
            "collaboration": "협업",
        }
        return [
            labels.get(k, k)
            for k, v in criteria.items()
            if v < 50
        ]

    def _generate_prompt_fragment(
        self,
        dept_id: str,
        grade: str,
        strengths: list[str],
        weaknesses: list[str],
    ) -> str:
        """성격 진화용 프롬프트 프래그먼트 생성.

        BotCharacterEvolution에 주입할 수 있는 형태의
        성격 진화 지시문을 생성한다.
        """
        parts = [f"[성과 평가 결과: {grade}등급]"]

        if strengths:
            parts.append(
                f"강점을 살려라: {', '.join(strengths)}. "
                "이 영역에서 자신감을 갖고 더 적극적으로 행동하라."
            )

        if weaknesses:
            parts.append(
                f"개선이 필요하다: {', '.join(weaknesses)}. "
                "이 영역에서 더 신중하고 꼼꼼하게 접근하라."
            )

        grade_personality = {
            "S": "최고 성과자답게 리더십과 멘토링에 더 힘써라.",
            "A": "높은 성과를 유지하되, 한 단계 더 도약하라.",
            "B": "안정적인 수행을 보이고 있다. 강점을 더 극대화하라.",
            "C": "기본기를 다져야 한다. 약점 개선에 집중하라.",
            "D": "심각한 개선이 필요하다. 기본에 충실하라.",
            "F": "긴급 개선 모드. 모든 역량을 핵심 업무에 집중하라.",
        }
        parts.append(grade_personality.get(grade, ""))

        return "\n".join(parts)
