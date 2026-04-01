#!/usr/bin/env bash
# AIMesh 대시보드 서버 시작 — FastAPI + uvicorn (http://localhost:8000/dashboard)

set -euo pipefail
PROJECT_DIR="/Users/rocky/telegram-ai-org"
cd "${PROJECT_DIR}"

export ENABLE_REST_API=true
export ENABLE_REPOSITORY_PATTERN=1

PORT="${DASHBOARD_PORT:-8000}"
HOST="${DASHBOARD_HOST:-0.0.0.0}"

echo "🚀 AIMesh Dashboard: http://${HOST}:${PORT}/dashboard"
echo "📊 API Docs:          http://${HOST}:${PORT}/api/docs"

.venv/bin/uvicorn core.api.app:create_app --factory \
    --host "${HOST}" --port "${PORT}" \
    --reload --log-level info
