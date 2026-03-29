"""core.services.orchestration_service — 오케스트레이션 서비스 (Phase 2a 스캐폴딩).

OrchestrationServiceInterface를 구현하는 구체 서비스 클래스입니다.
실제 오케스트레이션 로직은 Phase 2a 구현 시 채워집니다.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.interfaces import TaskRepositoryInterface, BaseRunner

# ---------------------------------------------------------------------------
# 피처 플래그
# ---------------------------------------------------------------------------

ENABLE_ORCHESTRATION_SERVICE: bool = (
    os.environ.get("ENABLE_ORCHESTRATION_SERVICE", "0") == "1"
)
"""True일 때 신규 OrchestrationService 코드 경로를 활성화합니다."""


# ---------------------------------------------------------------------------
# OrchestrationService 클래스
# ---------------------------------------------------------------------------


class OrchestrationService:
    """태스크 오케스트레이션 비즈니스 서비스.

    OrchestrationServiceInterface 프로토콜과 호환됩니다.

    사용 예시::

        service = OrchestrationService(task_repo=repo, runner=runner)
        task_id = await service.orchestrate("기능 개발 태스크", "dev")
    """

    def __init__(
        self,
        task_repo: TaskRepositoryInterface,
        runner: BaseRunner,
    ) -> None:
        self._task_repo = task_repo
        self._runner = runner

    async def orchestrate(self, task_description: str, org_id: str) -> str:
        """태스크를 오케스트레이션하고 생성된 task_id를 반환합니다."""
        # TODO(Phase 2a): 태스크 생성 → 러너 실행 → 결과 저장 구현
        raise NotImplementedError("OrchestrationService.orchestrate — Phase 2a 구현 예정")

    async def cancel_task(self, task_id: str) -> bool:
        """실행 중인 태스크를 취소합니다. 성공 시 True를 반환합니다."""
        # TODO(Phase 2a): 러너에 취소 신호 전달 + 상태 갱신 구현
        raise NotImplementedError("OrchestrationService.cancel_task — Phase 2a 구현 예정")

    async def get_task_status(self, task_id: str) -> str | None:
        """task_id의 현재 상태를 반환합니다. 없으면 None."""
        # TODO(Phase 2a): task_repo 조회 후 status 필드 반환 구현
        raise NotImplementedError("OrchestrationService.get_task_status — Phase 2a 구현 예정")
