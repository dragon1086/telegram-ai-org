"""core.interfaces — 의존성 주입용 Protocol/ABC 정의 (Phase 1-B 스캐폴딩).

이 모듈은 Protocol 선언만 포함합니다.
core 내부 구현 모듈을 임포트하지 않습니다 (순환 참조 방지).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# 엔진 러너 인터페이스
# ---------------------------------------------------------------------------


@runtime_checkable
class BaseRunner(Protocol):
    """LLM 엔진 러너 추상 인터페이스.

    claude-code / codex / gemini-cli 등 모든 엔진 러너가 구현해야 합니다.
    """

    engine_name: str

    async def run(self, task: str, persona: str | None = None) -> str:
        """태스크 문자열을 엔진에 전달하고 결과 문자열을 반환합니다."""
        ...

    async def health_check(self) -> bool:
        """엔진이 정상 응답 가능한지 확인합니다."""
        ...


# ---------------------------------------------------------------------------
# Telegram 전송 인터페이스
# ---------------------------------------------------------------------------


@runtime_checkable
class TelegramInterface(Protocol):
    """Telegram 메시지 전송 추상 인터페이스."""

    async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
        """텍스트 메시지를 지정 chat_id로 전송합니다."""
        ...

    async def send_document(self, chat_id: int, document: bytes, filename: str) -> None:
        """바이트 문서를 파일로 전송합니다."""
        ...


# ---------------------------------------------------------------------------
# Repository 인터페이스
# ---------------------------------------------------------------------------


@runtime_checkable
class TaskRepositoryInterface(Protocol):
    """태스크 CRUD 저장소 인터페이스."""

    async def get(self, task_id: str) -> dict | None:
        """task_id로 태스크를 조회합니다. 없으면 None 반환."""
        ...

    async def save(self, task: dict) -> None:
        """태스크를 저장(신규 또는 갱신)합니다."""
        ...

    async def list_by_status(self, status: str) -> list[dict]:
        """상태값으로 필터링된 태스크 목록을 반환합니다."""
        ...

    async def delete(self, task_id: str) -> None:
        """task_id에 해당하는 태스크를 삭제합니다."""
        ...


@runtime_checkable
class MessageRepositoryInterface(Protocol):
    """메시지 저장소 인터페이스."""

    async def save(self, message: dict) -> None:
        """메시지를 저장합니다."""
        ...

    async def get_by_task(self, task_id: str) -> list[dict]:
        """특정 태스크에 연결된 메시지 목록을 반환합니다."""
        ...


@runtime_checkable
class BotStateRepositoryInterface(Protocol):
    """봇 상태 저장소 인터페이스."""

    async def get_state(self, bot_id: str) -> dict | None:
        """bot_id의 현재 상태를 반환합니다. 없으면 None."""
        ...

    async def update_state(self, bot_id: str, state: dict) -> None:
        """bot_id의 상태를 갱신합니다."""
        ...

    async def get_all_alive(self) -> list[dict]:
        """is_alive=True인 모든 봇 상태 목록을 반환합니다."""
        ...


# ---------------------------------------------------------------------------
# Service 인터페이스
# ---------------------------------------------------------------------------


@runtime_checkable
class DispatchServiceInterface(Protocol):
    """디스패치 비즈니스 서비스 인터페이스."""

    async def dispatch(self, task_id: str, target_org: str, message: str) -> bool:
        """메시지를 target_org로 디스패치합니다. 성공 시 True."""
        ...

    async def get_dispatch_status(self, task_id: str) -> str:
        """task_id의 디스패치 상태 문자열을 반환합니다."""
        ...


@runtime_checkable
class OrchestrationServiceInterface(Protocol):
    """오케스트레이션 서비스 인터페이스."""

    async def orchestrate(self, task_description: str, org_id: str) -> str:
        """태스크를 오케스트레이션하고 결과 task_id를 반환합니다."""
        ...

    async def cancel_task(self, task_id: str) -> bool:
        """실행 중인 태스크를 취소합니다. 성공 시 True."""
        ...
