"""core.api.routes.metrics — API 메트릭 엔드포인트 (Phase 3-A).

엔드포인트:
    GET /api/v1/metrics  — 인메모리 API 요청 통계 반환
"""
from __future__ import annotations

from fastapi import APIRouter

from core.api import API_VERSION
from core.api.metrics import get_metrics_snapshot

router = APIRouter(prefix=f"/api/{API_VERSION}", tags=["metrics"])


@router.get("/metrics", summary="API 메트릭 조회")
async def get_metrics() -> dict:
    """API 요청 통계를 반환합니다.

    인증이 필요하지 않습니다.

    Returns:
        uptime_seconds, total_requests, 엔드포인트별 통계.
    """
    return get_metrics_snapshot()
