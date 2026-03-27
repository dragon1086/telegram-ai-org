#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# 워크트리 내부에서 호출된 경우 실제 프로젝트 루트로 보정
case "$PROJECT_DIR" in
  */.worktrees/*) PROJECT_DIR="${PROJECT_DIR%%/.worktrees/*}" ;;
esac

echo "=== telegram-ai-org 봇 시작 ==="

# ── bot-runtime 워크트리 설정 (detached HEAD — 브랜치 비점유) ────────────
# 개발자가 main 브랜치에서 작업 중일 때도 충돌 없이 동작한다.
# 신규 사용자가 main에서 바로 start_all.sh를 실행해도 문제 없다.
BOT_RUNTIME="$PROJECT_DIR/.worktrees/bot-runtime"
if [ ! -d "$BOT_RUNTIME/core" ]; then
  echo "▶ bot-runtime 워크트리 생성 (detached HEAD)..."
  # 기존 깨진 디렉토리가 있으면 정리
  if [ -d "$BOT_RUNTIME" ]; then
    git -C "$PROJECT_DIR" worktree remove --force "$BOT_RUNTIME" 2>/dev/null || true
    rm -rf "$BOT_RUNTIME"
  fi
  mkdir -p "$PROJECT_DIR/.worktrees"
  git -C "$PROJECT_DIR" worktree add --detach "$BOT_RUNTIME" HEAD
fi
# HEAD 최신화 (detached — 브랜치 체크아웃 없이 reset만)
git -C "$BOT_RUNTIME" reset --hard "$(git -C "$PROJECT_DIR" rev-parse HEAD)" 2>/dev/null || true
# .venv, .env symlink (워크트리에는 없으므로)
[ ! -e "$BOT_RUNTIME/.venv" ] && ln -s "$PROJECT_DIR/.venv" "$BOT_RUNTIME/.venv"
[ -f "$PROJECT_DIR/.env" ] && [ ! -e "$BOT_RUNTIME/.env" ] && ln -s "$PROJECT_DIR/.env" "$BOT_RUNTIME/.env"
echo "✅ bot-runtime 워크트리 준비 완료 (detached HEAD)"

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

# ── macOS TCC 권한 체크 + Telegram 사전 알림 ─────────────────────────────────
# Python 프로세스가 TCC 팝업에 막혀 hang되기 전에 미리 경고 메시지를 보낸다.
# curl만 사용하므로 Python 없이도 동작. PM_BOT_TOKEN + ADMIN_CHAT_ID 필요.
_send_tg_notice() {
  local msg="$1"
  local token="${PM_BOT_TOKEN:-}"
  local chat_id="${ADMIN_CHAT_ID:-}"
  if [ -n "${token}" ] && [ -n "${chat_id}" ]; then
    curl -s -X POST "https://api.telegram.org/bot${token}/sendMessage" \
      -d "chat_id=${chat_id}" \
      -d "text=${msg}" \
      -d "parse_mode=HTML" > /dev/null 2>&1 || true
  fi
}

if [[ "$(uname)" == "Darwin" ]]; then
  # Full Disk Access 여부: TCC.db 읽기 가능 여부로 판단
  if ! cat /Library/Application\ Support/com.apple.TCC/TCC.db > /dev/null 2>&1; then
    echo "⚠️  [macOS] Full Disk Access 미부여 감지 — 봇 실행 중 권한 팝업이 뜰 수 있습니다."
    echo "   → 시스템 설정 > 개인 정보 보호 및 보안 > 전체 디스크 접근 > Terminal(또는 iTerm2) 추가"
    _send_tg_notice "⚠️ <b>봇 시작 알림</b>

macOS 권한 팝업이 뜰 수 있습니다.
화면에 <b>\"Python이 접근하는 것을 허용\"</b> 팝업이 보이면 <b>허용</b>을 눌러주세요.

영구 해결: 시스템 설정 → 개인 정보 보호 및 보안 → 전체 디스크 접근 → Terminal 추가"
  else
    _send_tg_notice "✅ <b>봇 시작 중</b> — macOS 권한 정상 (Full Disk Access 확인됨)"
  fi
fi

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
