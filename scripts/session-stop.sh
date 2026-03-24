#!/usr/bin/env bash
# session-stop.sh — Stop 이벤트 훅: 작업 로그 + 미완료 태스크 요약 저장
set -euo pipefail

PROJECT_DIR="/Users/rocky/telegram-ai-org"
LOG_DIR="/Users/rocky/.ai-org"
TIMESTAMP=$(date +"%Y%m%dT%H%M%SZ")
STOP_LOG="${LOG_DIR}/session-stop-${TIMESTAMP}.log"

echo "[session-stop] ${TIMESTAMP} — 세션 종료 처리 시작" | tee -a "${STOP_LOG}"

# 1. 미완료 태스크 조회
echo "## 미완료 태스크" >> "${STOP_LOG}"
cd "${PROJECT_DIR}"
"${PROJECT_DIR}/.venv/bin/python" tools/orchestration_cli.py list-tasks --status assigned,running 2>/dev/null   | head -50 >> "${STOP_LOG}" || echo "(태스크 조회 실패)" >> "${STOP_LOG}"

# 2. 최근 로그 스냅샷 (마지막 30줄)
echo "## PM 봇 마지막 로그" >> "${STOP_LOG}"
tail -30 "${LOG_DIR}/aiorg_pm_bot.log" >> "${STOP_LOG}" 2>/dev/null || true

# 3. 실행 중인 봇 프로세스 목록
echo "## 실행 중 봇 프로세스" >> "${STOP_LOG}"
pgrep -fl "telegram_relay\|start_all\|bot_watchdog" >> "${STOP_LOG}" 2>/dev/null || echo "(없음)" >> "${STOP_LOG}"

echo "[session-stop] 완료 → ${STOP_LOG}"
