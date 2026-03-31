"""GoalTracker 브릿지 — RetroActionItem을 GoalTracker에 등록하는 어댑터.

파싱된 RetroActionItem 리스트를 GoalTracker.start_goal()에 연결하여
goal_id를 반환한다. GoalTracker 인스턴스가 없으면 dry-run 모드로 동작한다.

사용 예::

    bridge = GoalTrackerBridge(goal_tracker=gt_instance, chat_id=12345)
    goal_ids = await bridge.register_actions(retro_items)
    # goal_ids: ["G-aiorg_pm_bot-001", "G-aiorg_pm_bot-002"]
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional
from uuid import uuid4

from retro_action_parser import RetroActionItem

logger = logging.getLogger(__name__)

# 부서명 표시용 매핑
ORG_DEPT_DISPLAY: dict[str, str] = {
    "aiorg_engineering_bot": "개발실",
    "aiorg_ops_bot": "운영실",
    "aiorg_design_bot": "디자인실",
    "aiorg_product_bot": "기획실",
    "aiorg_growth_bot": "성장실",
    "aiorg_research_bot": "리서치실",
    "aiorg_pm_bot": "PM",
}


class GoalTrackerBridge:
    """파싱된 RetroActionItem을 GoalTracker에 등록하는 브릿지.

    Args:
        goal_tracker: GoalTracker 인스턴스. None이면 dry-run 모드.
        chat_id: Telegram 채팅방 ID.
    """

    def __init__(
        self,
        goal_tracker=None,
        chat_id: int = 0,
    ) -> None:
        self._gt = goal_tracker
        self._chat_id = chat_id
        self._dry_run = goal_tracker is None
        if self._dry_run:
            logger.info("[GoalTrackerBridge] dry-run 모드 — goal_tracker 없음")

    async def register_action(self, item: RetroActionItem) -> Optional[str]:
        """단일 RetroActionItem을 GoalTracker에 등록.

        Args:
            item: 등록할 RetroActionItem.

        Returns:
            goal_id 문자열. 실패 시 None.
        """
        title = self._build_goal_title(item)
        description = self._build_goal_description(item)
        meta = self._build_goal_meta(item)
        org_id = item.assigned_dept or "aiorg_pm_bot"

        if self._dry_run:
            goal_id = f"DRYRUN-{uuid4().hex[:8]}"
            logger.info(f"[GoalTrackerBridge][dry-run] {goal_id} — {title[:60]}")
            return goal_id

        try:
            # 중복 체크
            existing = await self._gt.get_goals_by_title(title)
            for g in existing:
                if g.get("status") in ("active", "achieved"):
                    logger.info(
                        f"[GoalTrackerBridge] 중복 스킵 — {g['id']} (title={title[:40]})"
                    )
                    return g["id"]

            goal_id = await self._gt.start_goal(
                title=title,
                description=description,
                meta=meta,
                chat_id=self._chat_id,
                org_id=org_id,
            )
            logger.info(f"[GoalTrackerBridge] 등록 완료 — {goal_id}: {title[:60]}")
            return goal_id
        except Exception as e:
            logger.error(f"[GoalTrackerBridge] 등록 실패 ({title[:40]}): {e}")
            return None

    async def register_actions(self, items: list[RetroActionItem]) -> list[str]:
        """복수 RetroActionItem을 GoalTracker에 등록.

        Args:
            items: 등록할 RetroActionItem 리스트.

        Returns:
            등록된 goal_id 목록 (실패 항목 제외).
        """
        goal_ids: list[str] = []
        for item in items:
            try:
                goal_id = await self.register_action(item)
                if goal_id:
                    goal_ids.append(goal_id)
            except Exception as e:
                logger.error(
                    f"[GoalTrackerBridge] register_actions 중 예외 "
                    f"({item.description[:40]}): {e}"
                )
        logger.info(
            f"[GoalTrackerBridge] register_actions 완료 — "
            f"{len(goal_ids)}/{len(items)}개 등록"
        )
        return goal_ids

    def _build_goal_title(self, item: RetroActionItem) -> str:
        """goal title 생성 (80자 이내).

        Args:
            item: RetroActionItem.

        Returns:
            80자 이내 title 문자열.
        """
        today = date.today().isoformat()
        prefix_parts: list[str] = []
        if item.retro_id:
            prefix_parts.append(f"[{item.retro_id}]")
        prefix_parts.append(f"[{today}]")

        prefix = " ".join(prefix_parts)
        desc_limit = 80 - len(prefix) - 1
        desc_truncated = item.description[:max(desc_limit, 10)]
        return f"{prefix} {desc_truncated}"

    def _build_goal_meta(self, item: RetroActionItem) -> dict:
        """meta_json 구성.

        반드시 포함: source, retro_id, priority, assignee, due_date, tags

        Args:
            item: RetroActionItem.

        Returns:
            meta dict.
        """
        from datetime import datetime, timezone

        dept_display = ORG_DEPT_DISPLAY.get(item.assigned_dept or "", item.assigned_dept or "")
        return {
            "source": "daily_retro",
            "retro_id": item.retro_id,
            "priority": item.priority,
            "assignee": item.assigned_dept or "",
            "assignee_name": dept_display,
            "due_date": item.due_date or "",
            "tags": item.tags,
            "confidence": item.confidence,
            "org_emoji": item.org_emoji,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }

    def _build_goal_description(self, item: RetroActionItem) -> str:
        """description 생성.

        Args:
            item: RetroActionItem.

        Returns:
            GoalTracker description 문자열.
        """
        dept_display = ORG_DEPT_DISPLAY.get(item.assigned_dept or "", item.assigned_dept or "")
        lines: list[str] = [
            f"## {item.description}",
            "",
            f"**출처**: 일일회고 (daily_retro)",
        ]
        if item.retro_id:
            lines.append(f"**RETRO ID**: {item.retro_id}")
        if item.assigned_dept:
            lines.append(f"**담당**: {dept_display} ({item.assigned_dept})")
        if item.due_date:
            lines.append(f"**기한**: {item.due_date}")
        if item.priority != "medium":
            lines.append(f"**우선순위**: {item.priority}")
        if item.source_text:
            lines.append(f"**원문**: {item.source_text[:100]}")
        return "\n".join(lines)
