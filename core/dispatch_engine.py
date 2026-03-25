"""자동 디스패치 엔진 — 태스크 완료 시 의존성 충족된 후속 태스크 자동 발송.

Feature flag: ENABLE_AUTO_DISPATCH (환경변수, 기본 off)
"""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from loguru import logger

from core.collab_dispatcher import CollabDispatcher
from core.context_db import ContextDB
from core.pm_orchestrator import KNOWN_DEPTS
from core.task_graph import TaskGraph

ENABLE_AUTO_DISPATCH = os.environ.get("ENABLE_AUTO_DISPATCH", "0") == "1"

# 정체 판정 기준 (분)
DEFAULT_STALL_MINUTES = 30


class DispatchEngine:
    """ContextDB 기반 자동 디스패치 엔진.

    태스크 완료 시 TaskGraph에서 새로 실행 가능한 태스크를 찾아
    Telegram으로 자동 발송한다.
    """

    def __init__(
        self,
        context_db: ContextDB,
        task_graph: TaskGraph,
        telegram_send_func: Callable[[int, str], Awaitable[None]],
        stall_minutes: int = DEFAULT_STALL_MINUTES,
        collab_dispatcher: CollabDispatcher | None = None,
    ):
        self._db = context_db
        self._graph = task_graph
        self._send = telegram_send_func
        self._stall_minutes = stall_minutes
        # ST-11: COLLAB 위임 디스패처 (None이면 기존 라우팅만 사용)
        self._collab_dispatcher = collab_dispatcher or CollabDispatcher(
            send_func=telegram_send_func
        )

    async def on_task_complete(self, task_id: str, result: str,
                               chat_id: int) -> list[str]:
        """태스크 완료 처리 → 의존성 충족된 후속 태스크 자동 디스패치.

        Returns:
            디스패치된 태스크 ID 목록.
        """
        # 1. TaskGraph에서 완료 처리 + 새로 unblock된 태스크 확인
        newly_ready = await self._graph.mark_complete(task_id)

        # 2. result 저장
        await self._db.update_pm_task_status(task_id, "done", result=result)

        dispatched: list[str] = []

        # 3. 새로 ready된 태스크 자동 발송
        for tid in newly_ready:
            task = await self._db.get_pm_task(tid)
            if not task:
                continue
            dept = task["assigned_dept"]
            dept_name = KNOWN_DEPTS.get(dept, dept)
            task_meta = task.get("metadata") or {}
            _task_type = task_meta.get("task_type", "")
            _allow_fc = task_meta.get("allow_file_change")
            _type_line = f"\n태스크 유형: {_task_type}" if _task_type else ""
            _fc_line = (
                f"\n파일·코드 변경 허용: {'예' if _allow_fc else '아니오'}"
                if _allow_fc is not None else ""
            )
            msg = (
                f"[PM_TASK:{tid}|dept:{dept}] {dept_name}에 배정"
                f"{_type_line}{_fc_line}\n{task['description'][:300]}"
            )

            # ST-11: task_type이 COLLAB이면 CollabDispatcher로 부서 분기 전달
            if _task_type.upper() == "COLLAB":
                collab_targets = await self._collab_dispatcher.dispatch(
                    task_id=tid,
                    task_text=task["description"],
                    source_dept=dept,
                    context=task_meta.get("context", ""),
                )
                if collab_targets:
                    logger.info(
                        f"[AutoDispatch] {tid} COLLAB 분기 전달 완료 → {collab_targets}"
                    )
                    await self._db.update_pm_task_status(tid, "assigned")
                    dispatched.append(tid)
                    continue  # 일반 발송 생략

            await self._send(chat_id, msg)
            await self._db.update_pm_task_status(tid, "assigned")
            dispatched.append(tid)
            logger.info(f"[AutoDispatch] {task_id} 완료 → {tid} 자동 발송 ({dept_name})")

        # 4. 의존성 진행률 상태 메시지
        task_info = await self._db.get_pm_task(task_id)
        if task_info and task_info.get("parent_id"):
            parent_id = task_info["parent_id"]
            status_msg = await self.build_status_display(parent_id)
            if status_msg:
                await self._send(chat_id, status_msg)

        return dispatched

    async def check_stalled_chains(self) -> list[str]:
        """정체된 태스크 체인 감지.

        stall_minutes 이상 진행 없는 assigned/in_progress 태스크를 반환.
        """
        return await self._db.get_stalled_tasks(self._stall_minutes)

    async def build_status_display(self, parent_id: str) -> str:
        """부모 태스크의 의존성 진행률을 시각적으로 표시."""
        subtasks = await self._db.get_subtasks(parent_id)
        if not subtasks:
            return ""

        status_icons = {
            "done": "✅",
            "assigned": "🔄",
            "in_progress": "🔄",
            "pending": "⏳",
            "failed": "❌",
        }

        lines: list[str] = []
        total = len(subtasks)
        done_count = sum(1 for s in subtasks if s["status"] == "done")

        for st in subtasks:
            icon = status_icons.get(st["status"], "❓")
            dept_name = KNOWN_DEPTS.get(st.get("assigned_dept", ""), "?")
            desc = st["description"][:40]
            lines.append(f"{icon} {st['id']} {dept_name}: {desc}")

        progress = f"📊 진행률: {done_count}/{total}"
        return f"{progress}\n" + "\n".join(lines)
