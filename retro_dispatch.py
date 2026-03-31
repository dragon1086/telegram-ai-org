"""Retro Dispatch — GoalTracker 등록 완료 후 부서 봇에 자동 dispatch.

파싱+등록된 RetroActionItem을 해당 부서 채팅방에 COLLAB 태그 포맷으로 전송하고,
결과를 /logs/retro_dispatch.jsonl에 JSON Lines 형식으로 기록한다.

사용 예::

    dispatcher = RetroDispatch(send_func=telegram_send, admin_chat_id=12345)
    result = await dispatcher.dispatch_all(retro_items, goal_ids)
    # result: {"success": ["G-001"], "failed": [], "skipped": []}
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Optional

from retro_action_parser import RetroActionItem

logger = logging.getLogger(__name__)

# 로그 파일 경로
_RETRO_DISPATCH_LOG = Path(__file__).resolve().parent / "logs" / "retro_dispatch.jsonl"

# 부서별 환경변수 키 (collab_dispatcher와 동일 패턴)
_DEPT_CHAT_ID_ENV: dict[str, str] = {
    "aiorg_engineering_bot": "ENGINEERING_BOT_CHAT_ID",
    "aiorg_design_bot":      "DESIGN_BOT_CHAT_ID",
    "aiorg_product_bot":     "PRODUCT_BOT_CHAT_ID",
    "aiorg_growth_bot":      "GROWTH_BOT_CHAT_ID",
    "aiorg_ops_bot":         "OPS_BOT_CHAT_ID",
    "aiorg_research_bot":    "RESEARCH_BOT_CHAT_ID",
    "aiorg_pm_bot":          "PM_BOT_CHAT_ID",
}

# 부서 표시명
_DEPT_DISPLAY: dict[str, str] = {
    "aiorg_engineering_bot": "개발실",
    "aiorg_ops_bot":         "운영실",
    "aiorg_design_bot":      "디자인실",
    "aiorg_product_bot":     "기획실",
    "aiorg_growth_bot":      "성장실",
    "aiorg_research_bot":    "리서치실",
    "aiorg_pm_bot":          "PM",
}


class RetroDispatch:
    """GoalTracker 등록 완료 후 부서 봇에 자동 dispatch하는 클래스.

    Args:
        send_func: (chat_id: int, text: str) → Awaitable[None] 시그니처 전송 함수.
                   None이면 dry-run 모드 (로그만 기록).
        admin_chat_id: 관리자 채팅방 ID (알림용).
    """

    def __init__(
        self,
        send_func: Optional[Callable[[int, str], Awaitable[None]]] = None,
        admin_chat_id: int = 0,
    ) -> None:
        self._send = send_func
        self._admin_chat_id = admin_chat_id
        self._dry_run = send_func is None
        if self._dry_run:
            logger.info("[RetroDispatch] dry-run 모드 — send_func 없음")

    async def notify_dispatch(
        self, item: RetroActionItem, goal_id: str
    ) -> bool:
        """단일 RetroActionItem을 해당 부서에 dispatch.

        COLLAB 태그 포맷으로 메시지를 구성하여 대상 부서 채팅방에 전송한다.

        Args:
            item: dispatch할 RetroActionItem.
            goal_id: 이미 등록된 GoalTracker goal_id.

        Returns:
            성공 여부 (True/False).
        """
        payload = self._build_collab_payload(item, goal_id)
        dept_id = item.assigned_dept or ""
        chat_id = self._resolve_chat_id(dept_id)

        if not dept_id:
            logger.warning(f"[RetroDispatch] assigned_dept 없음 — {goal_id} 스킵")
            self._write_log(self._build_dispatch_log_entry(item, goal_id, success=False))
            return False

        if self._dry_run:
            logger.info(
                f"[RetroDispatch][dry-run] {goal_id} → {dept_id}\n{payload}"
            )
            self._write_log(self._build_dispatch_log_entry(item, goal_id, success=True))
            return True

        if chat_id is None:
            env_key = _DEPT_CHAT_ID_ENV.get(dept_id, "N/A")
            logger.warning(
                f"[RetroDispatch] chat_id 없음 — {dept_id} "
                f"(env: {env_key}) → dispatch 스킵"
            )
            self._write_log(self._build_dispatch_log_entry(item, goal_id, success=False))
            return False

        try:
            await self._send(chat_id, payload)  # type: ignore[misc]
            logger.info(f"[RetroDispatch] dispatch 완료 — {goal_id} → {dept_id}")
            self._write_log(self._build_dispatch_log_entry(item, goal_id, success=True))
            return True
        except Exception as e:
            logger.error(f"[RetroDispatch] dispatch 실패 — {goal_id} → {dept_id}: {e}")
            self._write_log(self._build_dispatch_log_entry(item, goal_id, success=False))
            return False

    async def dispatch_all(
        self,
        items: list[RetroActionItem],
        goal_ids: list[str],
    ) -> dict[str, list[str]]:
        """전체 RetroActionItem을 해당 부서에 dispatch.

        items와 goal_ids는 동일 인덱스로 대응된다.
        길이가 다르면 짧은 쪽 기준으로 처리한다.

        Args:
            items: dispatch할 RetroActionItem 리스트.
            goal_ids: 대응하는 goal_id 리스트.

        Returns:
            {
                "success": [goal_id, ...],
                "failed":  [goal_id, ...],
                "skipped": [goal_id, ...],
            }
        """
        result: dict[str, list[str]] = {
            "success": [],
            "failed": [],
            "skipped": [],
        }

        pairs = list(zip(items, goal_ids))
        for item, goal_id in pairs:
            if not item.assigned_dept:
                result["skipped"].append(goal_id)
                logger.debug(f"[RetroDispatch] {goal_id} 스킵 — assigned_dept 없음")
                continue
            try:
                success = await self.notify_dispatch(item, goal_id)
                if success:
                    result["success"].append(goal_id)
                else:
                    result["failed"].append(goal_id)
            except Exception as e:
                logger.error(f"[RetroDispatch] dispatch_all 예외 — {goal_id}: {e}")
                result["failed"].append(goal_id)

        logger.info(
            f"[RetroDispatch] dispatch_all 완료 — "
            f"success={len(result['success'])}, "
            f"failed={len(result['failed'])}, "
            f"skipped={len(result['skipped'])}"
        )
        return result

    def _build_collab_payload(self, item: RetroActionItem, goal_id: str) -> str:
        """COLLAB 태그 포맷 메시지 구성.

        포맷: [COLLAB:작업설명|맥락: RETRO-N, goal_id=G-xxx]

        Args:
            item: RetroActionItem.
            goal_id: GoalTracker goal_id.

        Returns:
            COLLAB 태그 포맷 메시지 문자열.
        """
        task_desc = item.description[:200]
        context_parts: list[str] = []
        if item.retro_id:
            context_parts.append(item.retro_id)
        context_parts.append(f"goal_id={goal_id}")
        if item.priority != "medium":
            context_parts.append(f"priority={item.priority}")
        if item.due_date:
            context_parts.append(f"due={item.due_date}")

        context = ", ".join(context_parts)
        return f"[COLLAB:{task_desc}|맥락: {context}]"

    def _build_dispatch_log_entry(
        self,
        item: RetroActionItem,
        goal_id: str,
        success: bool,
    ) -> dict:
        """로그 엔트리 dict 생성.

        Args:
            item: RetroActionItem.
            goal_id: GoalTracker goal_id.
            success: dispatch 성공 여부.

        Returns:
            JSON 직렬화 가능한 로그 엔트리 dict.
        """
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "goal_id": goal_id,
            "retro_id": item.retro_id,
            "assigned_dept": item.assigned_dept or "",
            "description": item.description[:100],
            "priority": item.priority,
            "due_date": item.due_date or "",
            "success": success,
            "dry_run": self._dry_run,
        }

    def _resolve_chat_id(self, dept_id: str) -> Optional[int]:
        """환경변수에서 dept_id에 대응하는 chat_id 조회.

        Args:
            dept_id: 부서 org_id.

        Returns:
            chat_id 정수. 없거나 변환 실패 시 None.
        """
        env_key = _DEPT_CHAT_ID_ENV.get(dept_id)
        if not env_key:
            return None
        val = os.environ.get(env_key)
        if val is None:
            return None
        try:
            return int(val)
        except ValueError:
            logger.warning(f"[RetroDispatch] {env_key}={val!r} — int 변환 실패")
            return None

    def _write_log(self, entry: dict) -> None:
        """로그 엔트리를 JSONL 파일에 기록.

        Args:
            entry: 로그 엔트리 dict.
        """
        try:
            _RETRO_DISPATCH_LOG.parent.mkdir(parents=True, exist_ok=True)
            with _RETRO_DISPATCH_LOG.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning(f"[RetroDispatch] 로그 기록 실패: {e}")
