#!/usr/bin/env bash
# SubagentStart 에이전트 감사 로그
# 에이전트 시작 시 이름과 시각을 로그 파일에 기록한다.

INPUT=$(cat)
AGENT_NAME=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('agent_name', d.get('subagent_type', 'unknown')))" 2>/dev/null || echo "unknown")

LOG_FILE="$HOME/.ai-org-agent-audit.log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] SubagentStart: ${AGENT_NAME}" >> "$LOG_FILE" 2>/dev/null || true

exit 0
