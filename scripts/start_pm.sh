#!/usr/bin/env bash
# PM 오케스트레이터 봇 시작 스크립트
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# .env 로드
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# PM 봇 환경 설정
export PM_ORG_NAME="aiorg_pm_bot"
export PM_BOT_TOKEN="${PM_BOT_TOKEN:?PM_BOT_TOKEN 환경변수 필요}"
export ENABLE_PM_ORCHESTRATOR=1

echo "[PM] 총괄PM 오케스트레이터 시작 (org=${PM_ORG_NAME})"
exec "$PROJECT_DIR/.venv/bin/python3" main.py
