#!/usr/bin/env bash
set -euo pipefail

echo "=== telegram-ai-org 봇 시작 ==="

# ~/.ai-org/config.yaml 또는 .env 로드
CONFIG="$HOME/.ai-org/config.yaml"
if [ -f "$CONFIG" ]; then
    set -a
    source "$CONFIG"
    set +a
    echo "✅ 설정 로드: $CONFIG"
elif [ -f .env ]; then
    set -a
    source .env
    set +a
    echo "✅ 설정 로드: .env"
else
    echo "❌ 설정 파일 없음. 먼저 실행하세요:"
    echo "   python scripts/setup_wizard.py"
    exit 1
fi

# 필수 환경변수 확인
required_vars=(PM_BOT_TOKEN TELEGRAM_GROUP_CHAT_ID)
for var in "${required_vars[@]}"; do
    if [ -z "${!var:-}" ]; then
        echo "❌ $var가 설정되지 않았습니다."
        exit 1
    fi
done

PIDS=()

# PM 봇 시작
python3 -m core.pm_bot &
PM_PID=$!
PIDS+=($PM_PID)
echo "✅ pm_bot 시작 (PID: $PM_PID)"

# workers.yaml에서 워커 목록 읽어서 각 봇 시작
WORKERS_FILE="workers.yaml"
if [ -f "$WORKERS_FILE" ]; then
    WORKER_NAMES=$(python3 - <<'EOF'
import yaml, sys
try:
    with open("workers.yaml") as f:
        cfg = yaml.safe_load(f) or {}
    for w in cfg.get("workers", []):
        print(w["name"])
except Exception as e:
    print(f"# error: {e}", file=sys.stderr)
EOF
)
    for name in $WORKER_NAMES; do
        python3 -m core.run_worker --name "$name" &
        WORKER_PID=$!
        PIDS+=($WORKER_PID)
        echo "✅ ${name}_bot 시작 (PID: $WORKER_PID)"
    done
else
    echo "⚠️  workers.yaml 없음 — 워커 봇 없이 PM만 실행"
fi

echo ""
echo "모든 봇 실행 중. Ctrl+C로 종료."
echo "PIDs: ${PIDS[*]}"

# 종료 시 모든 봇 종료
cleanup() {
    echo ""
    echo "봇 종료 중..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    exit 0
}
trap cleanup SIGINT SIGTERM

wait
