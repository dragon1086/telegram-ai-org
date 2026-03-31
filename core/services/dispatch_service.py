"""core.services.dispatch_service — 디스패치 비즈니스 서비스 (Phase 2a 구현).

DispatchServiceInterface를 구현하는 구체 서비스 클래스입니다.
태스크 조회 → 대상 봇 결정 → Telegram 전송 → 상태 갱신의 전체 흐름을 처리합니다.

Self-review:
  ① Logic: dispatch/get_dispatch_status/cancel_dispatch 모두 task_repo 위임, graceful degradation 적용.
  ② Edge cases: 태스크 없음/이미 취소됨/플래그 비활성화 → 모두 기본값 반환.
  ③ Compat: 기존 인터페이스(NotImplementedError 스텁) 동일 시그니처 유지.
  ④ Global state: 없음.
"""
from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from core.interfaces import TaskRepositoryInterface, TelegramInterface

# ---------------------------------------------------------------------------
# 피처 플래그
# ---------------------------------------------------------------------------

ENABLE_DISPATCH_SERVICE: bool = os.environ.get("ENABLE_DISPATCH_SERVICE", "1") == "1"
"""True일 때 신규 DispatchService 코드 경로를 활성화합니다."""


# ---------------------------------------------------------------------------
# DispatchService 클래스
# ---------------------------------------------------------------------------


class DispatchService:
    """태스크 디스패치 비즈니스 서비스.

    DispatchServiceInterface 프로토콜과 호환됩니다.

    사용 예시::

        service = DispatchService(task_repo=repo, telegram=bot)
        success = await service.dispatch("t1", "dev", "메시지 내용")
    """

    def __init__(
        self,
        task_repo: TaskRepositoryInterface,
        telegram: TelegramInterface,
    ) -> None:
        self._task_repo = task_repo
        self._telegram = telegram

    async def dispatch(self, task_id: str, target_org: str, message: str) -> bool:
        """메시지를 target_org로 디스패치합니다. 성공 시 True를 반환합니다.

        구현 흐름:
        1. task_repo.get(task_id) 로 태스크 조회 (없으면 False)
        2. target_org → Telegram chat_id 매핑 (환경변수 우선)
        3. telegram.send_message(chat_id, ...) 호출
        4. task_repo.save(상태=dispatched) 업데이트
        5. True 반환
        """
        if not ENABLE_DISPATCH_SERVICE:
            logger.debug("DispatchService disabled; dispatch is no-op")
            return False

        try:
            task = await self._task_repo.get(task_id)
            if task is None:
                logger.warning("DispatchService.dispatch: task_id=%s 없음 — 중단", task_id)
                return False

            # org → chat_id 결정: 환경변수 우선, 없으면 None
            env_key = f"{target_org.upper()}_BOT_CHAT_ID"
            chat_id_raw = os.environ.get(env_key)
            if not chat_id_raw:
                logger.warning(
                    "DispatchService.dispatch: %s 환경변수 미설정 — target_org=%s",
                    env_key, target_org,
                )
                return False

            try:
                chat_id = int(chat_id_raw)
            except ValueError:
                logger.error("DispatchService.dispatch: %s=%s 는 정수가 아님", env_key, chat_id_raw)
                return False

            await self._telegram.send_message(chat_id, f"[{task_id}] {message}")

            await self._task_repo.save(
                {
                    **task,
                    "task_id": task_id,
                    "status": "dispatched",
                    "dispatched_at": time.time(),
                    "target_org": target_org,
                }
            )
            logger.info("DispatchService.dispatch: task_id=%s → %s (chat_id=%s)", task_id, target_org, chat_id)
            return True

        except Exception as exc:
            logger.error("DispatchService.dispatch 실패 task_id=%s: %s", task_id, exc)
            return False

    async def get_dispatch_status(self, task_id: str) -> str:
        """task_id의 디스패치 상태 문자열을 반환합니다.

        조회 결과:
        - 태스크 없음 → "unknown"
        - 있으면 task["status"] 반환
        """
        if not ENABLE_DISPATCH_SERVICE:
            logger.debug("DispatchService disabled; get_dispatch_status is no-op")
            return "unknown"

        try:
            task = await self._task_repo.get(task_id)
            if task is None:
                return "unknown"
            return str(task.get("status", "unknown"))
        except Exception as exc:
            logger.error("DispatchService.get_dispatch_status 실패 task_id=%s: %s", task_id, exc)
            return "unknown"

    async def cancel_dispatch(self, task_id: str) -> bool:
        """진행 중인 디스패치를 취소합니다. 성공 시 True를 반환합니다.

        취소 가능 조건: status == "dispatched"
        그 외 상태(미존재/already cancelled 등) → False 반환
        """
        if not ENABLE_DISPATCH_SERVICE:
            logger.debug("DispatchService disabled; cancel_dispatch is no-op")
            return False

        try:
            task = await self._task_repo.get(task_id)
            if task is None:
                logger.warning("DispatchService.cancel_dispatch: task_id=%s 없음", task_id)
                return False

            if task.get("status") != "dispatched":
                logger.info(
                    "DispatchService.cancel_dispatch: task_id=%s 상태=%s — 취소 불가",
                    task_id, task.get("status"),
                )
                return False

            await self._task_repo.save(
                {
                    **task,
                    "task_id": task_id,
                    "status": "cancelled",
                    "cancelled_at": time.time(),
                }
            )
            logger.info("DispatchService.cancel_dispatch: task_id=%s → cancelled", task_id)
            return True

        except Exception as exc:
            logger.error("DispatchService.cancel_dispatch 실패 task_id=%s: %s", task_id, exc)
            return False
