#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

echo "=== telegram-ai-org 봇 시작 ==="

CONFIG="$HOME/.ai-org/config.yaml"
LOADED_SOURCES=()
if [ -f "$CONFIG" ]; then
  set -a
  source "$CONFIG"
  set +a
  LOADED_SOURCES+=("$CONFIG")
fi
if [ -f .env ]; then
  set -a
  source .env
  set +a
  LOADED_SOURCES+=(".env")
fi
if [ ${#LOADED_SOURCES[@]} -eq 0 ]; then
  echo "❌ 설정 파일 없음. 먼저 /setup 또는 scripts/setup_wizard.py 를 실행하세요."
  exit 1
fi
echo "✅ 설정 로드: ${LOADED_SOURCES[*]}"

PYTHON_BIN="./.venv/bin/python3"
[ ! -x "$PYTHON_BIN" ] && PYTHON_BIN="python3"

BOT_ROWS=$("$PYTHON_BIN" - <<'PY'
from core.orchestration_config import load_orchestration_config

cfg = load_orchestration_config(force_reload=True)
for org in cfg.list_orgs():
    token = org.token
    chat_id = org.chat_id
    if not token or chat_id is None:
        continue
    print(f"{org.id}\t{token}\t{chat_id}")
PY
)

if [ -z "$BOT_ROWS" ]; then
  echo "⚠️  시작 가능한 조직이 없습니다. organizations.yaml / orchestration.yaml 을 확인하세요."
  exit 0
fi

while IFS=$'\t' read -r ORG_ID TOKEN CHAT_ID; do
  [ -z "$ORG_ID" ] && continue
  echo "▶ $ORG_ID 시작 중..."
  "$PYTHON_BIN" scripts/bot_manager.py start "$TOKEN" "$ORG_ID" "$CHAT_ID"
  sleep 2
done <<< "$BOT_ROWS"

echo "=== 모든 조직 봇 시작 완료 ==="
