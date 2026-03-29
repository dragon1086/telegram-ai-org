"""core.services.dispatch_service — 디스패치 비즈니스 서비스 (Phase 2a 스캐폴딩).

DispatchServiceInterface를 구현하는 구체 서비스 클래스입니다.
실제 비즈니스 로직은 Phase 2a 구현 시 채워집니다.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.interfaces import TaskRepositoryInterface, TelegramInterface

# ---------------------------------------------------------------------------
# 피처 플래그
# ---------------------------------------------------------------------------

ENABLE_DISPATCH_SERVICE: bool = os.environ.get("ENABLE_DISPATCH_SERVICE", "0") == "1"
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
        """메시지를 target_org로 디스패치합니다. 성공 시 True를 반환합니다."""
        # TODO(Phase 2a): 태스크 조회 → 대상 봇 결정 → Telegram 전송 구현
        raise NotImplementedError("DispatchService.dispatch — Phase 2a 구현 예정")

    async def get_dispatch_status(self, task_id: str) -> str:
        """task_id의 디스패치 상태 문자열을 반환합니다."""
        # TODO(Phase 2a): task_repo에서 상태 조회 후 반환 구현
        raise NotImplementedError("DispatchService.get_dispatch_status — Phase 2a 구현 예정")

    async def cancel_dispatch(self, task_id: str) -> bool:
        """진행 중인 디스패치를 취소합니다. 성공 시 True를 반환합니다."""
        # TODO(Phase 2a): 태스크 상태를 'cancelled'로 갱신 구현
        raise NotImplementedError("DispatchService.cancel_dispatch — Phase 2a 구현 예정")
