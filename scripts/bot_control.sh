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
      "$PYTHON_BIN" scripts/bot_manager.py stop "$TARGET" || true
      sleep 1
      # 개별 봇 재시작: orchestration config에서 token/chat_id 조회 후 start
      "$PYTHON_BIN" - "$TARGET" <<'PY'
import sys
from core.orchestration_config import load_orchestration_config
from scripts.bot_manager import start_bot

target = sys.argv[1]
cfg = load_orchestration_config(force_reload=True)
for org in cfg.list_orgs():
    if org.id == target:
        pid = start_bot(token=org.token, org_id=org.id, chat_id=org.chat_id)
        print(f"✅ {org.id} 재시작 (PID={pid})")
        break
else:
    print(f"❌ {target} 조직을 찾을 수 없습니다.")
    sys.exit(1)
PY
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
