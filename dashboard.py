#!/usr/bin/env python3
"""dashboard.py — AIMesh 실시간 대시보드 진입점 (Phase 2).

실행 방법:
    python dashboard.py                   # 기본 포트 8080
    python dashboard.py --port 8081       # 포트 지정
    uvicorn dashboard:app --port 8080     # uvicorn 직접 사용

환경변수:
    DASHBOARD_PORT         = 8080  (기본)
    DASHBOARD_POLL_INTERVAL= 5     (폴링 주기, 초)
    AIMESH_DB_PATH         = data/tasks.db
    ENABLE_REST_API        = true
    ENABLE_API_AUTH        = false (대시보드 공개 접근)

접속:
    http://localhost:8080          — 대시보드 UI
    http://localhost:8080/api/docs — REST API 문서
    http://localhost:8080/api/v1/events/stream — SSE 스트림
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# 환경 설정
# ---------------------------------------------------------------------------

os.environ.setdefault("ENABLE_REST_API", "true")
os.environ.setdefault("ENABLE_API_AUTH", "false")
os.environ.setdefault("ENABLE_REPOSITORY_PATTERN", "1")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DASHBOARD_DIR = Path(__file__).parent / "dashboard"
POLL_INTERVAL = float(os.environ.get("DASHBOARD_POLL_INTERVAL", "5"))
DB_PATH = os.environ.get(
    "AIMESH_DB_PATH",
    str(Path.home() / ".ai-org" / "context.db"),
)

# ---------------------------------------------------------------------------
# Lifespan — DashboardPusher 시작/중단
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from core.dashboard.pusher import DashboardPusher

    pusher = DashboardPusher(poll_interval=POLL_INTERVAL, db_path=DB_PATH)
    app.state.pusher = pusher
    await pusher.start()
    logger.info("✅ DashboardPusher 가동 완료 (폴링 주기: %ss)", POLL_INTERVAL)
    yield
    await pusher.stop()
    logger.info("⛔ DashboardPusher 중단")


# ---------------------------------------------------------------------------
# FastAPI 앱 구성
# ---------------------------------------------------------------------------

from core.api.app import create_app as _create_core_app  # noqa: E402

# 기존 core API 앱 (라우터 포함)
_core_app = _create_core_app(db_path=DB_PATH)

# 대시보드 전용 앱 (lifespan 포함)
app = FastAPI(
    title="AIMesh Dashboard",
    description="실시간 작업 시각화 대시보드 — 만화 캐릭터 컨셉",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# 라우터 마운트 (core API 라우터 재사용)
# ---------------------------------------------------------------------------

from core.api.routes.dashboard import router as dashboard_router  # noqa: E402
from core.api.routes.events import router as events_router  # noqa: E402
from core.api.routes.health import router as health_router  # noqa: E402
from core.api.routes.metrics import router as metrics_router  # noqa: E402
from core.api.routes.streams import router as streams_router  # noqa: E402
from core.api.routes.tasks import router as tasks_router  # noqa: E402

app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(tasks_router)
app.include_router(events_router)
app.include_router(streams_router)  # Phase 2: 채널별 전용 SSE 스트림
app.include_router(dashboard_router)  # Phase 2-B: 대시보드 데이터 API (snapshot 포함)


# ---------------------------------------------------------------------------
# 정적 파일 서빙 (dashboard/ 디렉토리)
# ---------------------------------------------------------------------------

if DASHBOARD_DIR.exists():
    # dashboard/ 하위 모든 JS 모듈 경로 서빙
    for _subdir in ("styles", "components", "services", "hooks", "api", "utils"):
        _d = DASHBOARD_DIR / _subdir
        if _d.exists():
            app.mount(f"/{_subdir}", StaticFiles(directory=str(_d)), name=_subdir)
    _static_dir = DASHBOARD_DIR / "static"
    if _static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(_static_dir)), name="dashboard-static")


_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_dashboard():
    """대시보드 메인 HTML 서빙."""
    index_html = DASHBOARD_DIR / "index.html"
    if index_html.exists():
        return FileResponse(str(index_html), headers=_NO_CACHE_HEADERS)
    return HTMLResponse(
        content="<h1>⚠️ dashboard/index.html 없음</h1><p>dashboard/ 디렉토리를 확인하세요.</p>",
        status_code=404,
    )


# ---------------------------------------------------------------------------
# 직접 실행
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="AIMesh 실시간 대시보드")
    parser.add_argument("--host", default="0.0.0.0", help="바인딩 호스트 (기본: 0.0.0.0)")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("DASHBOARD_PORT", "8080")),
        help="포트 (기본: 8080)",
    )
    parser.add_argument("--reload", action="store_true", help="개발 모드 자동 리로드")
    args = parser.parse_args()

    logger.info("🚀 AIMesh Dashboard 시작 — http://%s:%s", args.host, args.port)
    uvicorn.run(
        "dashboard:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
