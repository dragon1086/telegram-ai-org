#!/usr/bin/env bash
# AIMesh 대시보드 서버 시작 — 통합 대시보드 (캐릭터 + 태스크)

set -euo pipefail
PROJECT_DIR="/Users/rocky/telegram-ai-org"
cd "${PROJECT_DIR}"

PORT="${DASHBOARD_PORT:-8080}"
HOST="${DASHBOARD_HOST:-0.0.0.0}"

echo "🚀 AIMesh Dashboard: http://${HOST}:${PORT}/"
echo "📊 API Docs:          http://${HOST}:${PORT}/api/docs"
echo "🔁 SSE Stream:        http://${HOST}:${PORT}/api/v1/events/stream"

.venv/bin/python dashboard.py --host "${HOST}" --port "${PORT}"
