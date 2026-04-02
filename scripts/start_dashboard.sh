#!/usr/bin/env bash
# AIMesh 대시보드 서버 시작 — 통합 대시보드 (캐릭터 + 태스크)

set -euo pipefail
PROJECT_DIR="/Users/rocky/telegram-ai-org"
cd "${PROJECT_DIR}"

PORT="${DASHBOARD_PORT:-8080}"
HOST="${DASHBOARD_HOST:-0.0.0.0}"

# DB 경로 자동 감지: Docker 컨테이너가 실행 중이면 ./data/context.db, 아니면 기본값 (~/.ai-org/context.db)
if [ -z "${AIMESH_DB_PATH:-}" ]; then
    if docker compose ps --status running -q 2>/dev/null | grep -q .; then
        export AIMESH_DB_PATH="${PROJECT_DIR}/data/context.db"
        echo "🐳 Docker 모드 감지 — DB: ${AIMESH_DB_PATH}"
    else
        # dashboard.py 기본값 (~/.ai-org/context.db) 사용
        echo "💻 로컬 모드 — DB: ~/.ai-org/context.db (기본값)"
    fi
fi

echo "🚀 AIMesh Dashboard: http://${HOST}:${PORT}/"
echo "📊 API Docs:          http://${HOST}:${PORT}/api/docs"
echo "🔁 SSE Stream:        http://${HOST}:${PORT}/api/v1/events/stream"

.venv/bin/python dashboard.py --host "${HOST}" --port "${PORT}"
