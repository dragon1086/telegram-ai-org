#!/usr/bin/env bash
# 봇 안전 재시작 — pm_bot + 모든 조직봇을 순서대로 재시작
# Telegram 409 Conflict 방지를 위해 각 봇 사이 2초 딜레이
#
# 사용법: bash scripts/restart_bots.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_DIR="$HOME/.ai-org/bots"
LOG_FILE="$HOME/.ai-org/pm_bot.log"
PM_PID_FILE="$HOME/.ai-org/pm_bot.pid"

echo "=== 봇 안전 재시작 시작 ==="

# ── 1. pm_bot 재시작 ─────────────────────────────────────────────────────────
echo "▶ pm_bot 재시작 중..."
if [ -f "$PM_PID_FILE" ]; then
    OLD_PID=$(cat "$PM_PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        kill -TERM "$OLD_PID" 2>/dev/null || true
        sleep 1
        kill -9 "$OLD_PID" 2>/dev/null || true
    fi
    rm -f "$PM_PID_FILE"
fi
# 잔여 프로세스 정리
pkill -9 -if "python.*main.py" 2>/dev/null || true
sleep 1

cd "$BOT_DIR"
nohup .venv/bin/python3 -u main.py > "$LOG_FILE" 2>&1 &
NEW_PM_PID=$!
echo "$NEW_PM_PID" > "$PM_PID_FILE"
echo "  ✅ pm_bot 시작됨 (PID: $NEW_PM_PID)"

sleep 2

# ── 2. 조직봇 재시작 ─────────────────────────────────────────────────────────
if [ ! -d "$PID_DIR" ]; then
    echo "ℹ️  조직봇 PID 디렉토리 없음 ($PID_DIR) — 조직봇 없이 완료"
    echo "=== 재시작 완료 ==="
    exit 0
fi

shopt -s nullglob
PID_FILES=("$PID_DIR"/*.pid)

if [ ${#PID_FILES[@]} -eq 0 ]; then
    echo "ℹ️  등록된 조직봇 없음 — pm_bot만 재시작됨"
    echo "=== 재시작 완료 ==="
    exit 0
fi

for pid_file in "${PID_FILES[@]}"; do
    org_id="$(basename "$pid_file" .pid)"
    meta_json="$PID_DIR/${org_id}.json"
    meta_yaml="$BOT_DIR/bots/${org_id}.yaml"

    # 기존 프로세스 종료
    if [ -f "$pid_file" ]; then
        OLD_PID=$(cat "$pid_file")
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            kill -TERM "$OLD_PID" 2>/dev/null || true
            sleep 0.5
            kill -9 "$OLD_PID" 2>/dev/null || true
        fi
        rm -f "$pid_file"
    fi

    # 메타데이터(토큰, chat_id) 읽기: json 우선, 없으면 yaml 폴백
    if [ -f "$meta_json" ]; then
        TOKEN=$(python3 -c "import json; d=json.load(open('$meta_json')); print(d['token'])")
        CHAT_ID=$(python3 -c "import json; d=json.load(open('$meta_json')); print(d['chat_id'])")
    elif [ -f "$meta_yaml" ]; then
        TOKEN_ENV=$(python3 -c "
import re
content = open('$meta_yaml').read()
m = re.search(r'token_env:\s*[\"\\']?([^\"\\'\\n]+)[\"\\']?', content)
print(m.group(1).strip() if m else '')
")
        TOKEN="${!TOKEN_ENV}"
        CHAT_ID=$(python3 -c "
import re
content = open('$meta_yaml').read()
m = re.search(r'chat_id:\s*(-?[0-9]+)', content)
print(m.group(1) if m else '')
")
        if [ -z "$TOKEN" ]; then
            echo "  ⚠️  $org_id: 환경변수 \$TOKEN_ENV 미설정 — 건너뜀"
            continue
        fi
    else
        echo "  ⚠️  $org_id: 메타데이터 없음 (json/yaml 모두 없음) — 건너뜀"
        continue
    fi

    echo "▶ $org_id 재시작 중..."
    NEW_PID=$(cd "$BOT_DIR" && python3 scripts/bot_manager.py start "$TOKEN" "$org_id" "$CHAT_ID" 2>/dev/null | grep -oE 'PID=[0-9]+' | cut -d= -f2 || echo "")

    if [ -n "$NEW_PID" ]; then
        echo "  ✅ $org_id 시작됨 (PID: $NEW_PID)"
    else
        echo "  ❌ $org_id 시작 실패"
    fi

    sleep 2
done

echo "=== 재시작 완료 ==="
