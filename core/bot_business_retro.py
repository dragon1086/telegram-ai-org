"""봇별 비즈니스 회고 생성기 — 주간 성과 리포트."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from core.context_db import ContextDB

logger = logging.getLogger(__name__)


class BotBusinessRetro:
    """봇별 주간 비즈니스 성과 리포트 생성.

    신규 봇: 첫 task_completion 시 자동 등록 — 별도 초기화 불필요.
    삭제된 봇: 해당 주 데이터 없으면 결과에서 자동 제외.
    """

    def __init__(self, context_db: ContextDB) -> None:
        self._db = context_db

    async def generate_weekly(
        self, week: str | None = None,
    ) -> list[dict]:
        """전체 봇의 주간 비즈니스 회고 생성.

        Returns:
            list of dicts: bot_id, week, task_count, success_rate,
                           peer_rank, total_bots, avg_latency_sec, action_items
        """
        if week is None:
            now = datetime.now(UTC)
            week = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"
        all_perf = await self._db.get_all_bot_performance(week)
        if not all_perf:
            return []

        total_bots = len(all_perf)
        results: list[dict] = []
        for rank, perf in enumerate(all_perf, start=1):
            tc = perf["task_count"]
            sc = perf["success_count"]
            rate = sc / tc if tc > 0 else 0.0
            action_items = self._derive_action_items(rate, rank, total_bots)
            results.append({
                "bot_id": perf["bot_id"],
                "week": week,
                "task_count": tc,
                "success_rate": round(rate, 3),
                "peer_rank": rank,
                "total_bots": total_bots,
                "avg_latency_sec": perf.get("avg_latency_sec", 0.0),
                "action_items": action_items,
            })
        return results

    @staticmethod
    def _derive_action_items(
        rate: float, rank: int, total: int,
    ) -> list[str]:
        """성과 기반 액션 아이템 도출."""
        items: list[str] = []
        if rate < 0.7:
            items.append("성공률 70% 미만 — 실패 원인 분석 필요")
        if rank > max(1, int(total * 0.7)):
            items.append("하위 30% — 태스크 난이도 조정 또는 지원 검토")
        if rate >= 0.9 and rank <= max(1, total // 3):
            items.append("상위 성과 — 베스트 프랙티스 공유 권장")
        if not items:
            items.append("현재 성과 유지")
        return items

    def format_telegram(self, retros: list[dict]) -> str:
        """Telegram 메시지 포맷."""
        if not retros:
            return "이번 주 봇 성과 데이터가 없습니다."
        week = retros[0].get("week", "?")
        lines = [f"[봇 비즈니스 회고 — {week}]\n"]
        for r in retros:
            rate_pct = f"{r['success_rate']:.0%}"
            lines.append(
                f"  {r['peer_rank']}위 {r['bot_id']}: "
                f"{r['task_count']}건, 성공률 {rate_pct}"
            )
            for item in r["action_items"]:
                lines.append(f"    → {item}")
        return "\n".join(lines)
