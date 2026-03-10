#!/usr/bin/env bash
set -euo pipefail

echo "=== telegram-ai-org 봇 시작 ==="

# .env 로드
if [ -f .env ]; then
    set -a
    source .env
    set +a
else
    echo "❌ .env 파일이 없습니다. ./scripts/setup.sh를 먼저 실행하세요."
    exit 1
fi

# 필수 환경변수 확인
required_vars=(PM_BOT_TOKEN DEV_BOT_TOKEN ANALYST_BOT_TOKEN DOCS_BOT_TOKEN TELEGRAM_GROUP_CHAT_ID)
for var in "${required_vars[@]}"; do
    if [ -z "${!var:-}" ]; then
        echo "❌ $var가 설정되지 않았습니다."
        exit 1
    fi
done

echo "모든 봇 시작 중..."

# 각 봇을 백그라운드로 실행
python3 -m bots.dev_bot &
DEV_PID=$!
echo "✅ dev_bot 시작 (PID: $DEV_PID)"

python3 -m bots.analyst_bot &
ANALYST_PID=$!
echo "✅ analyst_bot 시작 (PID: $ANALYST_PID)"

python3 -m bots.docs_bot &
DOCS_PID=$!
echo "✅ docs_bot 시작 (PID: $DOCS_PID)"

python3 -m core.pm_bot &
PM_PID=$!
echo "✅ pm_bot 시작 (PID: $PM_PID)"

echo ""
echo "모든 봇 실행 중. Ctrl+C로 종료."
echo "PIDs: pm=$PM_PID dev=$DEV_PID analyst=$ANALYST_PID docs=$DOCS_PID"

# 종료 시 모든 봇 종료
trap "echo '봇 종료 중...'; kill $PM_PID $DEV_PID $ANALYST_PID $DOCS_PID 2>/dev/null; exit 0" SIGINT SIGTERM

wait
