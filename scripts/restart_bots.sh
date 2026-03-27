#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== 봇 안전 재시작 시작 ==="
bash "$SCRIPT_DIR/bot_control.sh" stop all

# agent_monitor도 함께 종료 (start_all.sh에서 새로 시작됨)
MONITOR_PID_FILE="/tmp/agent-monitor.pid"
if [ -f "$MONITOR_PID_FILE" ]; then
  _mpid="$(cat "$MONITOR_PID_FILE" 2>/dev/null)"
  if [ -n "$_mpid" ] && ps -p "$_mpid" > /dev/null 2>&1; then
    kill "$_mpid" 2>/dev/null && echo "✅ agent_monitor 종료 (PID: $_mpid)" || true
  fi
  rm -f "$MONITOR_PID_FILE"
fi

# bot_watchdog도 함께 종료 (start_all.sh에서 새로 시작됨)
WATCHDOG_PID_FILE="/tmp/bot-watchdog.pid"
if [ -f "$WATCHDOG_PID_FILE" ]; then
  _wpid="$(cat "$WATCHDOG_PID_FILE" 2>/dev/null)"
  if [ -n "$_wpid" ] && ps -p "$_wpid" > /dev/null 2>&1; then
    kill "$_wpid" 2>/dev/null && echo "✅ bot_watchdog 종료 (PID: $_wpid)" || true
  fi
  rm -f "$WATCHDOG_PID_FILE"
fi

sleep 1

# 고아 claude_agent_sdk / codex 프로세스 정리 (PPID=1 = 부모 봇이 이미 죽은 자식)
echo "--- 고아 에이전트 프로세스 정리 중 ---"
_orphan_count=0
while IFS= read -r _opid; do
  [ -z "$_opid" ] && continue
  kill "$_opid" 2>/dev/null && _orphan_count=$((_orphan_count + 1)) || true
done < <(ps -eo pid,ppid,command | awk '(/claude_agent_sdk|codex/ && !/awk/) && $2==1 {print $1}')
if [ "$_orphan_count" -gt 0 ]; then
  echo "✅ 고아 프로세스 ${_orphan_count}개 종료"
else
  echo "· 고아 프로세스 없음"
fi

sleep 1

# 모든 aiorg 봇 tmux 세션 종료 (메인 + claude 서브세션, context 완전 리셋)
# aiorg_global 제외 — 전역 설정 세션
echo "--- aiorg tmux 세션 정리 중 (context 완전 리셋) ---"
aiorg_sessions="$(tmux list-sessions -F '#{session_name}' 2>/dev/null | grep -E '^aiorg_' | grep -v '^aiorg_global$' || true)"
if [ -n "$aiorg_sessions" ]; then
  echo "$aiorg_sessions" | while read -r sess; do
    tmux kill-session -t "$sess" 2>/dev/null && echo "✅ 종료: $sess" || true
  done
else
  echo "· tmux 세션 없음 (이미 정리됨)"
fi

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
