"""core.api.routes.health — 헬스체크 & 준비 상태 엔드포인트 (Phase 2-A).

엔드포인트:
    GET /api/v1/health  — 기본 헬스체크 (인증 불필요)
    GET /api/v1/ready   — 준비 상태 (DB 연결 포함, 인증 불필요)
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from core.api import API_VERSION

router = APIRouter(prefix=f"/api/{API_VERSION}", tags=["health"])


@router.get("/health", summary="헬스체크")
async def health() -> dict:
    """서비스 생존 여부를 반환합니다.

    인증이 필요하지 않습니다.

    Returns:
        {"status": "ok", "version": "v1"}
    """
    return {"status": "ok", "version": API_VERSION}


@router.get("/ready", summary="준비 상태 확인")
async def ready(request: Request) -> dict:
    """DB 연결을 포함한 전체 준비 상태를 반환합니다.

    인증이 필요하지 않습니다.
    app.state.task_repo 가 없으면 db 상태를 "not_configured" 로 표시합니다.

    Returns:
        {"ready": bool, "checks": {"db": "ok" | "error" | "not_configured"}}
    """
    db_status = "not_configured"
    ready_flag = True

    task_repo = getattr(request.app.state, "task_repo", None)
    if task_repo is not None:
        try:
            # 간단한 연결 확인: list_all 호출
            await task_repo.list_all()
            db_status = "ok"
        except Exception:
            db_status = "error"
            ready_flag = False

    return {
        "ready": ready_flag,
        "checks": {"db": db_status},
    }
