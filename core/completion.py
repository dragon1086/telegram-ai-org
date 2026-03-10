"""완료 검증 프로토콜."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from loguru import logger

from core.task_manager import Task, TaskManager, TaskStatus


ACK_TIMEOUT_SECONDS = 120  # 2분 내 응답 없으면 타임아웃


class CompletionProtocol:
    """AI 조직 완료 검증 프로토콜.

    흐름:
    1. PM이 완료 판단 → waiting_ack 상태로 전환
    2. 전체 봇에 확인 요청 전송
    3. 각 봇의 ack 수집
    4. 전체 확인 시 CLOSED 처리
    5. 타임아웃 시 미응답 봇 기록 후 강제 CLOSED
    """

    def __init__(self, task_manager: TaskManager, send_message_fn) -> None:
        self.task_manager = task_manager
        self.send_message = send_message_fn  # async fn(text: str) -> None

    async def initiate_completion(self, task: Task) -> None:
        """완료 프로토콜 시작."""
        await self.task_manager.update_status(task.id, TaskStatus.WAITING_ACK)
        msg = (
            f"[TO: ALL | FROM: @pm_bot | TASK: {task.id} | TYPE: query]\n"
            f"{task.id} 완료로 보입니다. 각자 담당 파트 확인해주세요. ✅ 확인 시 ACK 응답 바랍니다."
        )
        await self.send_message(msg)
        logger.info(f"완료 확인 요청 전송: {task.id}")

    async def receive_ack(self, task_id: str, bot_handle: str) -> bool:
        """봇의 ACK 수신. 모두 완료되면 True 반환."""
        task = await self.task_manager.record_ack(task_id, bot_handle)
        if task.all_acked():
            await self.task_manager.update_status(task_id, TaskStatus.CLOSED)
            msg = (
                f"[TO: ALL | FROM: @pm_bot | TASK: {task_id} | TYPE: complete]\n"
                f"✅ {task_id} CLOSED — 모든 팀원 확인 완료."
            )
            await self.send_message(msg)
            logger.info(f"태스크 완료 처리: {task_id}")
            return True
        remaining = set(task.assigned_to) - set(task.acks)
        logger.info(f"ACK 대기 중: {task_id} — 남은 봇: {remaining}")
        return False

    async def wait_for_completion(self, task_id: str, timeout: int = ACK_TIMEOUT_SECONDS) -> bool:
        """타임아웃까지 완료 대기."""
        deadline = datetime.utcnow() + timedelta(seconds=timeout)
        while datetime.utcnow() < deadline:
            task = self.task_manager.get_task(task_id)
            if task and task.status == TaskStatus.CLOSED:
                return True
            await asyncio.sleep(5)

        # 타임아웃 처리
        task = self.task_manager.get_task(task_id)
        if task:
            missing = set(task.assigned_to) - set(task.acks)
            logger.warning(f"완료 타임아웃: {task_id} — 미응답: {missing}")
            await self.task_manager.update_status(task_id, TaskStatus.CLOSED, result=f"타임아웃 (미응답: {missing})")
        return False
