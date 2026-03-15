#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== 봇 안전 재시작 시작 ==="
bash "$SCRIPT_DIR/bot_control.sh" stop all
sleep 2
bash "$SCRIPT_DIR/start_all.sh"
echo "=== 재시작 완료 ==="
