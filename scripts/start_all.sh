#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# 워크트리 내부에서 호출된 경우 실제 프로젝트 루트로 보정
case "$PROJECT_DIR" in
  */.worktrees/*) PROJECT_DIR="${PROJECT_DIR%%/.worktrees/*}" ;;
esac

echo "=== telegram-ai-org 봇 시작 ==="

# ── bot-runtime 워크트리 설정 (main 브랜치 고정) ──────────────────────────
BOT_RUNTIME="$PROJECT_DIR/.worktrees/bot-runtime"
if [ ! -d "$BOT_RUNTIME/core" ]; then
  echo "▶ bot-runtime 워크트리 생성 (main 고정)..."
  mkdir -p "$PROJECT_DIR/.worktrees"
  git -C "$PROJECT_DIR" worktree add "$BOT_RUNTIME" main 2>/dev/null || true
fi
# main 최신화
git -C "$BOT_RUNTIME" checkout main 2>/dev/null || true
git -C "$BOT_RUNTIME" pull --ff-only 2>/dev/null || true
# .venv, .env symlink (워크트리에는 없으므로)
[ ! -e "$BOT_RUNTIME/.venv" ] && ln -s "$PROJECT_DIR/.venv" "$BOT_RUNTIME/.venv"
[ -f "$PROJECT_DIR/.env" ] && [ ! -e "$BOT_RUNTIME/.env" ] && ln -s "$PROJECT_DIR/.env" "$BOT_RUNTIME/.env"
echo "✅ bot-runtime 워크트리 준비 완료 (main)"

cd "$BOT_RUNTIME"

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

# Cleanup stale tmux sessions before starting bots
if command -v python3 &>/dev/null; then
    python3 "$(dirname "$0")/cleanup_tmux.py" 2>/dev/null || true
fi

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

# agent_monitor 데몬 시작 (aiorg Claude agent 세션 stuck 감지 + 자동 응답)
MONITOR_PID_FILE="/tmp/agent-monitor.pid"
_monitor_running=false
if [ -f "$MONITOR_PID_FILE" ]; then
  _mpid="$(cat "$MONITOR_PID_FILE" 2>/dev/null)"
  # PID가 살아있고, 실제로 agent_monitor 프로세스인지 확인
  if [ -n "$_mpid" ] && ps -p "$_mpid" > /dev/null 2>&1 \
     && ps -p "$_mpid" -o args= 2>/dev/null | grep -q "agent_monitor"; then
    _monitor_running=true
  fi
fi

if [ "$_monitor_running" = true ]; then
  echo "✅ agent_monitor 이미 실행 중 (PID: $_mpid)"
else
  # 좀비 PID 파일 정리
  [ -f "$MONITOR_PID_FILE" ] && rm -f "$MONITOR_PID_FILE"
  nohup "$PYTHON_BIN" "$SCRIPT_DIR/agent_monitor.py" \
    >> "$HOME/.ai-org/agent-monitor.log" 2>&1 &
  echo $! > "$MONITOR_PID_FILE"
  echo "▶ agent_monitor 시작 (PID: $!)"
fi

# bot_watchdog 데몬 시작 (봇 프로세스 crash 감지 + 자동 재시작 + Telegram 알림)
WATCHDOG_PID_FILE="/tmp/bot-watchdog.pid"
_watchdog_running=false
if [ -f "$WATCHDOG_PID_FILE" ]; then
  _wpid="$(cat "$WATCHDOG_PID_FILE" 2>/dev/null)"
  if [ -n "$_wpid" ] && ps -p "$_wpid" > /dev/null 2>&1 \
     && ps -p "$_wpid" -o args= 2>/dev/null | grep -q "bot_watchdog"; then
    _watchdog_running=true
  fi
fi

if [ "$_watchdog_running" = true ]; then
  echo "✅ bot_watchdog 이미 실행 중 (PID: $_wpid)"
else
  [ -f "$WATCHDOG_PID_FILE" ] && rm -f "$WATCHDOG_PID_FILE"
  nohup "$PYTHON_BIN" "$SCRIPT_DIR/bot_watchdog.py" \
    >> "$HOME/.ai-org/bot-watchdog.log" 2>&1 &
  echo $! > "$WATCHDOG_PID_FILE"
  echo "▶ bot_watchdog 시작 (PID: $!)"
fi
