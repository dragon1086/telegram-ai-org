#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

PYTHON_BIN="./.venv/bin/python3"
[ ! -x "$PYTHON_BIN" ] && PYTHON_BIN="python3"
TARGET="${2:-all}"

start_all() {
  bash "$SCRIPT_DIR/start_all.sh"
}

stop_one() {
  local org_id="$1"
  "$PYTHON_BIN" scripts/bot_manager.py stop "$org_id" >/dev/null 2>&1 || true
  echo "✅ 중지: $org_id"
}

stop_all() {
  BOT_IDS=$("$PYTHON_BIN" - <<'PY'
from core.orchestration_config import load_orchestration_config

cfg = load_orchestration_config(force_reload=True)
for org in cfg.list_orgs():
    print(org.id)
PY
)
  while IFS= read -r ORG_ID; do
    [ -z "$ORG_ID" ] && continue
    stop_one "$ORG_ID"
  done <<< "$BOT_IDS"
}

status_all() {
  "$PYTHON_BIN" scripts/bot_manager.py list
}

case "${1:-}" in
  start)
    if [ "$TARGET" = "all" ]; then
      start_all
    else
      echo "개별 start는 start_all.sh 또는 bot_manager.py를 사용하세요."
      exit 1
    fi
    ;;
  stop)
    if [ "$TARGET" = "all" ]; then
      stop_all
    else
      stop_one "$TARGET"
    fi
    ;;
  restart)
    if [ "$TARGET" = "all" ]; then
      bash "$SCRIPT_DIR/restart_bots.sh"
    else
      stop_one "$TARGET"
      sleep 1
      bash "$SCRIPT_DIR/start_all.sh"
    fi
    ;;
  status)
    status_all
    ;;
  *)
    echo "사용법: $0 {start|stop|restart|status} [all|org_id]"
    exit 1
    ;;
esac
