#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== 봇 안전 재시작 시작 ==="
bash "$SCRIPT_DIR/bot_control.sh" stop all
sleep 1

# claude 프로세스 tmux 세션 종료 (context 리셋)
echo "--- claude tmux 세션 정리 중 ---"
tmux list-sessions -F "#{session_name}" 2>/dev/null \
  | grep -E '^aiorg_.*_claude' \
  | while read -r sess; do
      tmux kill-session -t "$sess" 2>/dev/null && echo "✅ 종료: $sess" || true
    done

sleep 1
bash "$SCRIPT_DIR/start_all.sh"
echo "=== 재시작 완료 (context 0% 리셋) ==="
