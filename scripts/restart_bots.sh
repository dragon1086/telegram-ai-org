#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== 봇 안전 재시작 시작 ==="
bash "$SCRIPT_DIR/bot_control.sh" stop all
sleep 1

# 모든 aiorg 봇 tmux 세션 종료 (메인 + claude 서브세션, context 완전 리셋)
# aiorg_global 제외 — 전역 설정 세션
echo "--- aiorg tmux 세션 정리 중 (context 완전 리셋) ---"
tmux list-sessions -F "#{session_name}" 2>/dev/null \
  | grep -E '^aiorg_' \
  | grep -v '^aiorg_global$' \
  | while read -r sess; do
      tmux kill-session -t "$sess" 2>/dev/null && echo "✅ 종료: $sess" || true
    done

# session JSON 파일에서 context 관련 필드 리셋 (context_budget 0% 초기화)
echo "--- session 파일 context 리셋 중 ---"
python3 - <<'PY'
import json, glob, pathlib

SESSION_DIR = pathlib.Path.home() / ".ai-org" / "sessions"
RESET_KEYS = {"context_percent", "msg_count", "input_tokens", "output_tokens",
              "total_tokens", "output_chars", "compact_count"}

for f in SESSION_DIR.glob("pm_*.json"):
    try:
        data = json.loads(f.read_text())
        changed = False
        for k in RESET_KEYS:
            if k in data and data[k] not in (None, 0):
                data[k] = 0
                changed = True
        if changed:
            f.write_text(json.dumps(data, indent=2))
            print(f"✅ 리셋: {f.name}")
        else:
            print(f"· 스킵: {f.name} (이미 0)")
    except Exception as e:
        print(f"⚠️  {f.name}: {e}")
PY

sleep 1
bash "$SCRIPT_DIR/start_all.sh"
echo "=== 재시작 완료 (context 0% 리셋) ==="
