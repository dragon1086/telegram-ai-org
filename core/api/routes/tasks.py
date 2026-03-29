"""core.api.routes.tasks — 태스크 CRUD REST 엔드포인트 (Phase 2-A).

엔드포인트:
    POST   /api/v1/tasks              — 태스크 생성 (201)
    GET    /api/v1/tasks              — 태스크 목록 (status 필터 옵션)
    GET    /api/v1/tasks/{task_id}    — 단일 태스크 조회 (200 / 404)
    DELETE /api/v1/tasks/{task_id}    — 태스크 취소 (204 / 404)
"""
from __future__ import annotations

import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.api import API_VERSION
from core.api.audit_log import write_audit_event
from core.api.auth import verify_api_key
from core.api.rate_limiter import check_rate_limit

router = APIRouter(
    prefix=f"/api/{API_VERSION}/tasks",
    tags=["tasks"],
    dependencies=[Depends(verify_api_key), Depends(check_rate_limit)],
)

# ---------------------------------------------------------------------------
# Pydantic 스키마
# ---------------------------------------------------------------------------


class TaskCreateRequest(BaseModel):
    """태스크 생성 요청 본문."""

    description: str = Field(..., min_length=1, description="태스크 설명")
    org_id: str = Field("dev", description="담당 조직 ID (기본값: dev)")


class TaskResponse(BaseModel):
    """태스크 응답 스키마."""

    task_id: str
    org_id: str
    description: str
    status: str
    created_at: float
    updated_at: float
    result: Optional[str] = None


# ---------------------------------------------------------------------------
# 의존성
# ---------------------------------------------------------------------------


def _get_repo(request: Request):
    """app.state에서 TaskRepository 인스턴스를 가져옵니다."""
    repo = getattr(request.app.state, "task_repo", None)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TaskRepository가 초기화되지 않았습니다.",
        )
    return repo


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TaskResponse)
async def create_task(request: Request, body: TaskCreateRequest, repo=Depends(_get_repo)) -> TaskResponse:
    """새 태스크를 생성하고 반환합니다.

    Args:
        request: FastAPI Request 객체 (감사 로그용).
        body: description, org_id 포함 요청 본문.

    Returns:
        생성된 TaskResponse (HTTP 201).
    """
    now = time.time()
    task_id = str(uuid.uuid4())
    task = {
        "task_id": task_id,
        "org_id": body.org_id,
        "description": body.description,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "result": None,
    }
    await repo.save(task)
    write_audit_event(
        action="task_created",
        task_id=task_id,
        org_id=body.org_id,
        api_key=request.headers.get("X-API-Key", ""),
        client_ip=request.client.host if request.client else "",
    )
    return TaskResponse(**task)


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    status: Optional[str] = None,
    repo=Depends(_get_repo),
) -> list[TaskResponse]:
    """태스크 목록을 반환합니다.

    Args:
        status: 필터링할 상태값 (pending / in_progress / done / failed / cancelled).
                생략 시 전체 반환.

    Returns:
        TaskResponse 목록.
    """
    if status:
        tasks = await repo.list_by_status(status)
    else:
        tasks = await repo.list_all()
    return [TaskResponse(**t) for t in tasks]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, request: Request, repo=Depends(_get_repo)) -> TaskResponse:
    """task_id로 태스크를 조회합니다.

    Args:
        task_id: 조회할 태스크의 UUID.
        request: FastAPI Request 객체 (감사 로그용).

    Returns:
        TaskResponse (HTTP 200).

    Raises:
        HTTPException(404): 태스크를 찾을 수 없는 경우.
    """
    task = await repo.get(task_id)
    if task is None:
        write_audit_event(
            action="task_not_found",
            task_id=task_id,
            api_key=request.headers.get("X-API-Key", ""),
            client_ip=request.client.host if request.client else "",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task not found: {task_id}",
        )
    return TaskResponse(**task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_task(task_id: str, request: Request, repo=Depends(_get_repo)) -> None:
    """태스크를 취소(cancelled) 상태로 변경합니다.

    Args:
        task_id: 취소할 태스크의 UUID.
        request: FastAPI Request 객체 (감사 로그용).

    Returns:
        HTTP 204 (No Content).

    Raises:
        HTTPException(404): 태스크를 찾을 수 없는 경우.
    """
    task = await repo.get(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task not found: {task_id}",
        )
    await repo.delete(task_id)
    write_audit_event(
        action="task_deleted",
        task_id=task_id,
        org_id=task.get("org_id", ""),
        api_key=request.headers.get("X-API-Key", ""),
        client_ip=request.client.host if request.client else "",
    )
