"""core.api.app — AIMesh FastAPI 앱 팩토리 (Phase 2-A).

피처 플래그: ENABLE_REST_API (기본 false)
  - false: create_app() 호출 시 최소 앱 반환 (기존 시스템 영향 없음)
  - true: 전체 REST API 활성화

사용 예시::

    # 직접 실행
    import os
    os.environ["ENABLE_REST_API"] = "true"
    os.environ["ENABLE_REPOSITORY_PATTERN"] = "1"
    from core.api.app import create_app
    app = create_app()

    # uvicorn:
    # ENABLE_REST_API=true uvicorn core.api.app:create_app --factory --port 8000
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import time as _time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from core.api import API_VERSION
from core.api.metrics import record_request
from core.api.routes.health import router as health_router
from core.api.routes.metrics import router as metrics_router
from core.api.routes.tasks import router as tasks_router

# ---------------------------------------------------------------------------
# 피처 플래그
# ---------------------------------------------------------------------------

ENABLE_REST_API: bool = os.environ.get("ENABLE_REST_API", "true").lower() in ("true", "1")
"""True일 때 전체 REST API 라우터를 활성화합니다."""

DEFAULT_DB_PATH: str = os.environ.get("AIMESH_DB_PATH", "data/tasks.db")


# ---------------------------------------------------------------------------
# 의존성 주입: TaskRepository
# ---------------------------------------------------------------------------


def _make_lifespan(db_path: str):
    """TaskRepository 초기화/정리 lifespan 팩토리."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        from core.repositories.task_repository import TaskRepository

        repo = TaskRepository(db_path=db_path)
        await repo.initialize()
        app.state.task_repo = repo
        yield
        # 정리: :memory: DB 영속 연결 닫기
        await repo.close()
        app.state.task_repo = None

    return lifespan


# ---------------------------------------------------------------------------
# 앱 팩토리
# ---------------------------------------------------------------------------


def create_app(db_path: str | None = None) -> FastAPI:
    """AIMesh FastAPI 애플리케이션을 생성하고 반환합니다.

    Args:
        db_path: SQLite DB 파일 경로.
                 None이면 AIMESH_DB_PATH 환경변수 또는 기본값 사용.

    Returns:
        구성된 FastAPI 인스턴스.
    """
    resolved_db = db_path or DEFAULT_DB_PATH

    app = FastAPI(
        title="AIMesh REST API",
        description=(
            "Telegram-native AI Dev Team OS — HTTP API 레이어.\n\n"
            "Telegram 봇 외에도 CI/CD, 웹 대시보드 등 모든 HTTP 클라이언트에서 "
            "AIMesh 오케스트레이션 기능을 사용할 수 있습니다."
        ),
        version=API_VERSION,
        docs_url="/api/docs" if ENABLE_REST_API else None,
        redoc_url="/api/redoc" if ENABLE_REST_API else None,
        lifespan=_make_lifespan(resolved_db),
    )

    # CORS (개발 환경 — 프로덕션에서는 origin 제한 필요)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # HTTP 미들웨어: 메트릭 기록
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next) -> Response:
        start = _time.time()
        response = await call_next(request)
        duration_ms = (_time.time() - start) * 1000
        record_request(request.method, request.url.path, response.status_code, duration_ms)
        return response

    # 라우터 등록
    app.include_router(health_router)
    app.include_router(metrics_router)
    if ENABLE_REST_API:
        app.include_router(tasks_router)

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {
            "service": "AIMesh REST API",
            "version": API_VERSION,
            "docs": "/api/docs" if ENABLE_REST_API else "disabled",
        }

    return app
