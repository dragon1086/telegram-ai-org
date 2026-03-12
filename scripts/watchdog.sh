#!/usr/bin/env bash
# watchdog.sh — pm_bot 프로세스 감시, 죽으면 restart_bots.sh로 자동 복구
#
# 사용법: bash scripts/watchdog.sh [--interval 30]
#   --interval N  : 확인 주기 (초, 기본 30)
#
# 백그라운드 실행: nohup bash scripts/watchdog.sh > ~/.ai-org/watchdog.log 2>&1 &

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PM_PID_FILE="$HOME/.ai-org/pm_bot.pid"
WATCHDOG_PID_FILE="$HOME/.ai-org/watchdog.pid"
CHECK_INTERVAL=30

# 옵션 파싱
while [[ $# -gt 0 ]]; do
    case "$1" in
        --interval) CHECK_INTERVAL="$2"; shift 2 ;;
        *) echo "알 수 없는 옵션: $1"; exit 1 ;;
    esac
done

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

echo "[watchdog] 시작 — 확인 주기: ${CHECK_INTERVAL}초, PM PID 파일: $PM_PID_FILE"

while true; do
    sleep "$CHECK_INTERVAL"

    PM_ALIVE=false
    if [ -f "$PM_PID_FILE" ]; then
        PM_PID=$(cat "$PM_PID_FILE")
        if ps -p "$PM_PID" > /dev/null 2>&1; then
            PM_ALIVE=true
        fi
    fi

    if [ "$PM_ALIVE" = false ]; then
        echo "[watchdog] $(date '+%Y-%m-%d %H:%M:%S') pm_bot 다운 감지 — 재시작 중..."
        bash "$SCRIPT_DIR/restart_bots.sh" >> "$HOME/.ai-org/watchdog.log" 2>&1 || true
        echo "[watchdog] $(date '+%Y-%m-%d %H:%M:%S') 재시작 완료"
    fi
done
