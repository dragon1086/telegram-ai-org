#!/usr/bin/env bash
# watchdog.sh — 모든 봇 프로세스 감시. 다운 시 개별 재시작, 연속 3회 크래시 시 비활성화 + 알림.
#
# 사용법: bash scripts/watchdog.sh [--interval 30]
#   --interval N  : 확인 주기 (초, 기본 30)
#
# 백그라운드 실행: nohup bash scripts/watchdog.sh > ~/.ai-org/watchdog.log 2>&1 &

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WATCHDOG_PID_FILE="$HOME/.ai-org/watchdog.pid"
CRASH_COUNT_DIR="$HOME/.ai-org/crash_counts"
DISABLED_BOTS_DIR="$HOME/.ai-org/disabled_bots"
CHECK_INTERVAL=30
MAX_CRASHES=3

# 옵션 파싱
while [[ $# -gt 0 ]]; do
    case "$1" in
        --interval) CHECK_INTERVAL="$2"; shift 2 ;;
        *) echo "알 수 없는 옵션: $1"; exit 1 ;;
    esac
done

mkdir -p "$CRASH_COUNT_DIR" "$DISABLED_BOTS_DIR" "$HOME/.ai-org/bots"

# 이미 실행 중인 watchdog 확인
if [ -f "$WATCHDOG_PID_FILE" ]; then
    OLD_WD_PID=$(cat "$WATCHDOG_PID_FILE")
    if ps -p "$OLD_WD_PID" > /dev/null 2>&1; then
        echo "watchdog 이미 실행 중 (PID: $OLD_WD_PID)"
        exit 0
    fi
fi
echo $$ > "$WATCHDOG_PID_FILE"

cleanup() {
    rm -f "$WATCHDOG_PID_FILE"
    echo "[watchdog] 종료됨"
}
trap cleanup EXIT INT TERM

# Telegram 알림 전송 (환경변수 설정 시)
send_alert() {
    local msg="$1"
    local chat_id="${WATCHDOG_CHAT_ID:-}"
    local token="${WATCHDOG_BOT_TOKEN:-}"
    if [ -n "$chat_id" ] && [ -n "$token" ]; then
        curl -s -X POST "https://api.telegram.org/bot${token}/sendMessage" \
            -d "chat_id=${chat_id}" \
            -d "text=🚨 [watchdog] ${msg}" > /dev/null 2>&1 || true
    fi
    echo "[watchdog] ALERT: $msg"
}

# 봇 목록 로드
get_bot_ids() {
    cd "$PROJECT_DIR"
    ./.venv/bin/python3 - 2>/dev/null <<'PY' || echo ""
from core.orchestration_config import load_orchestration_config
cfg = load_orchestration_config(force_reload=True)
for org in cfg.list_orgs():
    if org.token and org.chat_id is not None:
        print(org.id)
PY
}

# 봇 생존 확인
is_bot_alive() {
    local org_id="$1"
    for pid_file in "/tmp/telegram-ai-org-${org_id}.pid" "$HOME/.ai-org/bots/${org_id}.pid"; do
        if [ -f "$pid_file" ]; then
            local pid
            pid=$(cat "$pid_file" 2>/dev/null || echo "")
            if [ -n "$pid" ] && ps -p "$pid" > /dev/null 2>&1; then
                return 0
            fi
        fi
    done
    # ps 스캔으로 직접 확인
    if ps eww -ax -o "command=" 2>/dev/null | grep -q "PM_ORG_NAME=${org_id}"; then
        return 0
    fi
    return 1
}

# 개별 봇 재시작
restart_bot() {
    local org_id="$1"
    echo "[watchdog] $(date '+%Y-%m-%d %H:%M:%S') $org_id 재시작 중..."
    cd "$PROJECT_DIR"
    if [ -f .env ]; then set -a; source .env; set +a; fi
    # bot_manager로 개별 시작 시도, 실패 시 전체 restart fallback
    ./.venv/bin/python3 scripts/bot_manager.py start_by_id "$org_id" 2>&1 || \
        bash "$SCRIPT_DIR/restart_bots.sh" 2>&1 || true
    echo "[watchdog] $(date '+%Y-%m-%d %H:%M:%S') $org_id 재시작 시도 완료"
}

# 크래시 카운터
get_crash_count() {
    local f="$CRASH_COUNT_DIR/${1}.count"
    [ -f "$f" ] && cat "$f" || echo "0"
}
increment_crash_count() {
    local f="$CRASH_COUNT_DIR/${1}.count"
    echo $(( $(get_crash_count "$1") + 1 )) > "$f"
}
reset_crash_count() {
    echo "0" > "$CRASH_COUNT_DIR/${1}.count"
}
is_bot_disabled() {
    [ -f "$DISABLED_BOTS_DIR/${1}.disabled" ]
}
disable_bot() {
    local org_id="$1"
    touch "$DISABLED_BOTS_DIR/${org_id}.disabled"
    send_alert "$org_id 연속 ${MAX_CRASHES}회 크래시 — 자동 재시작 비활성화. 수동 확인 필요."
}

echo "[watchdog] 시작 — 확인 주기: ${CHECK_INTERVAL}초"

# 초기 봇 목록
BOT_IDS_LIST=$(get_bot_ids)
[ -z "$BOT_IDS_LIST" ] && BOT_IDS_LIST="aiorg_pm_bot"
echo "[watchdog] 감시 봇: $(echo "$BOT_IDS_LIST" | tr '\n' ' ')"

LOOP_COUNT=0
while true; do
    sleep "$CHECK_INTERVAL"
    LOOP_COUNT=$((LOOP_COUNT + 1))

    # 5분마다 봇 목록 갱신
    if (( LOOP_COUNT % (300 / CHECK_INTERVAL) == 0 )); then
        NEW_LIST=$(get_bot_ids 2>/dev/null) && [ -n "$NEW_LIST" ] && BOT_IDS_LIST="$NEW_LIST"
    fi

    while IFS= read -r org_id; do
        [ -z "$org_id" ] && continue
        is_bot_disabled "$org_id" && continue

        if ! is_bot_alive "$org_id"; then
            increment_crash_count "$org_id"
            crash_count=$(get_crash_count "$org_id")
            echo "[watchdog] $(date '+%Y-%m-%d %H:%M:%S') $org_id DOWN (크래시 #${crash_count})"
            if [ "$crash_count" -ge "$MAX_CRASHES" ]; then
                disable_bot "$org_id"
            else
                restart_bot "$org_id"
            fi
        else
            # 정상 동작 → 크래시 카운터 리셋
            if [ "$(get_crash_count "$org_id")" != "0" ]; then
                reset_crash_count "$org_id"
                echo "[watchdog] $(date '+%Y-%m-%d %H:%M:%S') $org_id 복구됨"
            fi
        fi
    done <<< "$BOT_IDS_LIST"
done
