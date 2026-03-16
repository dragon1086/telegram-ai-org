"""봇 특성 진화 — AgentPersonaMemory stats 기반 자동 업데이트."""
from __future__ import annotations

from core.agent_persona_memory import AgentPersonaMemory

SUCCESS_RATE_THRESHOLD = 0.80   # 80% 이상 성공률 → strengths 추가
SUCCESS_MIN_COUNT = 3           # agent_persona_memory STRENGTH_THRESHOLD=3 과 동일 기준
FAILURE_MIN_COUNT = 3           # 3회 이상 실패 카테고리 → weaknesses 추가


class BotCharacterEvolution:
    """AgentPersonaMemory stats 기반으로 봇 특성 텍스트 자동 업데이트."""

    def __init__(self, persona_memory: AgentPersonaMemory | None = None):
        # persona_memory: AgentPersonaMemory 인스턴스 (duck typing)
        # None이면 기본 DB_PATH로 AgentPersonaMemory() 생성
        self.persona_memory = persona_memory or AgentPersonaMemory()

    def evolve(self, agent_id: str) -> dict:
        """
        AgentPersonaMemory stats 기반으로 봇 특성 업데이트:
        - success_patterns에서 특정 task_type 성공률 > 80% (최소 5회) → strengths에 추가
        - failure_patterns에서 특정 failure_category 3회+ → weaknesses에 추가
        - synergy_scores에서 가장 높은 파트너 → "best_partner" 필드
        반환: {"strengths": [...], "weaknesses": [...], "best_partner": str|None, "agent_id": str}
        """
        result: dict = {
            "agent_id": agent_id,
            "strengths": [],
            "weaknesses": [],
            "best_partner": None,
        }

        stats = self.persona_memory.get_stats(agent_id)
        if stats is None:
            return result

        # strengths: success_patterns[task_type] >= SUCCESS_MIN_COUNT (count 기준)
        # agent_persona_memory의 STRENGTH_THRESHOLD=3 과 동일 기준으로 통일
        for task_type, count in stats.success_patterns.items():
            if count >= SUCCESS_MIN_COUNT:
                if task_type not in result["strengths"]:
                    result["strengths"].append(task_type)

        # weaknesses: failure_patterns[category] >= 3
        for category, count in stats.failure_patterns.items():
            if count >= FAILURE_MIN_COUNT:
                if category not in result["weaknesses"]:
                    result["weaknesses"].append(category)

        # best_partner: synergy_scores 중 max
        if stats.synergy_scores:
            best = max(stats.synergy_scores, key=lambda k: stats.synergy_scores[k])
            result["best_partner"] = best

        return result

    def evolve_all(self) -> list[dict]:
        """모든 에이전트에 대해 evolve() 실행. 결과 list 반환."""
        all_stats = self.persona_memory.get_all_stats()
        return [self.evolve(s.agent_id) for s in all_stats]

    def get_evolution_summary(self, agent_id: str) -> str:
        """봇의 성장 요약 텍스트 (Telegram용).

        예: "{agent_id}은(는) 지난 30일간 {top_task_type} 태스크 성공률 {rate}%를 기록,
             {weakness} 패턴이 {n}회 발생했고 {best_partner}와 높은 시너지를 보이고 있습니다."
        stats가 없으면 "{agent_id}에 대한 성장 데이터가 없습니다." 반환.
        """
        stats = self.persona_memory.get_stats(agent_id)
        if stats is None or stats.total_tasks == 0:
            return f"{agent_id}에 대한 성장 데이터가 없습니다."

        evolved = self.evolve(agent_id)

        # top task_type by success count
        top_task_type: str | None = None
        top_rate: float = 0.0
        if stats.success_patterns and stats.total_tasks > 0:
            best_task = max(stats.success_patterns, key=lambda k: stats.success_patterns[k])
            top_task_type = best_task
            top_rate = stats.success_patterns[best_task] / stats.total_tasks * 100

        # top weakness by failure count
        top_weakness: str | None = None
        top_failure_count: int = 0
        if stats.failure_patterns:
            top_weakness = max(stats.failure_patterns, key=lambda k: stats.failure_patterns[k])
            top_failure_count = stats.failure_patterns[top_weakness]

        best_partner = evolved["best_partner"]

        parts: list[str] = []

        if top_task_type:
            parts.append(
                f"{agent_id}은(는) {top_task_type} 태스크 성공률 {top_rate:.0f}%를 기록"
            )
        else:
            parts.append(f"{agent_id}은(는) 아직 성공 태스크 기록이 없음")

        if top_weakness:
            parts.append(f"{top_weakness} 패턴이 {top_failure_count}회 발생했고")
        else:
            parts.append("실패 패턴 없음,")

        if best_partner:
            parts.append(f"{best_partner}와 높은 시너지를 보이고 있습니다.")
        else:
            parts.append("시너지 파트너 데이터 없음.")

        return " ".join(parts)
