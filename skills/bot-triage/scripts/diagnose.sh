#!/usr/bin/env bash
# bot-triage/scripts/diagnose.sh
# 봇 장애 자동 진단 스크립트
# 사용법: bash skills/bot-triage/scripts/diagnose.sh

set -uo pipefail

PROJECT_ROOT="${1:-$(cd "$(dirname "$0")/../../.." && pwd)}"
LOG_DIR="$HOME/.ai-org"

echo "🔍 봇 장애 진단 시작"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "시각: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 1. 봇 프로세스 상태
echo "## 1. 봇 프로세스 상태"
BOT_PIDS=$(ps aux | grep "[b]ot_runner" || true)
if [ -z "$BOT_PIDS" ]; then
    echo "❌ 실행 중인 봇 프로세스 없음"
else
    echo "$BOT_PIDS" | while read -r line; do
        PID=$(echo "$line" | awk '{print $2}')
        CMD=$(echo "$line" | awk '{for(i=11;i<=NF;i++) printf "%s ",$i; print ""}')
        echo "  ✅ PID=$PID | $CMD"
    done
fi
echo ""

# 2. Watchdog 상태
echo "## 2. Watchdog 상태"
WD_PID_FILE="/tmp/bot-watchdog.pid"
if [ -f "$WD_PID_FILE" ]; then
    WD_PID=$(cat "$WD_PID_FILE")
    if kill -0 "$WD_PID" 2>/dev/null; then
        echo "  ✅ watchdog 실행 중 (PID=$WD_PID)"
    else
        echo "  ❌ watchdog PID 파일 존재하나 프로세스 죽음 (stale PID=$WD_PID)"
    fi
else
    echo "  ❌ watchdog 미실행 (PID 파일 없음)"
fi
echo ""

# 3. 최근 로그 에러
echo "## 3. 최근 로그 에러 (최근 100줄)"
if [ -d "$LOG_DIR" ]; then
    for logfile in "$LOG_DIR"/bot-*.log; do
        [ -f "$logfile" ] || continue
        BOTNAME=$(basename "$logfile" .log)
        ERRORS=$(tail -100 "$logfile" 2>/dev/null | grep -i "error\|exception\|traceback\|critical" | tail -5)
        if [ -n "$ERRORS" ]; then
            echo "  ⚠️  $BOTNAME:"
            echo "$ERRORS" | sed 's/^/    /'
        else
            echo "  ✅ $BOTNAME: 최근 에러 없음"
        fi
    done
else
    echo "  ⚠️  로그 디렉토리 없음: $LOG_DIR"
fi
echo ""

# 4. 시스템 리소스
echo "## 4. 시스템 리소스"
DISK_USAGE=$(df -h / | tail -1 | awk '{print $5}')
echo "  디스크 사용률: $DISK_USAGE"

if command -v vm_stat &>/dev/null; then
    # macOS
    FREE_PAGES=$(vm_stat | grep "Pages free" | awk '{print $3}' | tr -d '.')
    SPEC_PAGES=$(vm_stat | grep "Pages speculative" | awk '{print $3}' | tr -d '.' 2>/dev/null || echo 0)
    FREE_MB=$(( (FREE_PAGES + SPEC_PAGES) * 4096 / 1048576 ))
    echo "  여유 메모리: ~${FREE_MB}MB"
else
    free -m 2>/dev/null | grep Mem | awk '{print "  여유 메모리: "$4"MB / 전체: "$2"MB"}' || echo "  메모리 정보 불가"
fi
echo ""

# 5. 환경변수 검증
echo "## 5. 환경변수 검증"
ENV_FILE="$PROJECT_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    for KEY in TELEGRAM_BOT_TOKEN ANTHROPIC_API_KEY; do
        if grep -q "^${KEY}=" "$ENV_FILE" 2>/dev/null; then
            echo "  ✅ $KEY 설정됨"
        else
            echo "  ❌ $KEY 미설정"
        fi
    done
else
    echo "  ❌ .env 파일 없음"
fi
echo ""

# 6. 네트워크
echo "## 6. 네트워크 연결"
if curl -s --max-time 5 "https://api.telegram.org" >/dev/null 2>&1; then
    echo "  ✅ Telegram API 접근 가능"
else
    echo "  ❌ Telegram API 접근 불가"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "진단 완료"
