#!/usr/bin/env bash
# openclaw cron 등록 스크립트
# Rocky가 한 번 실행하면 4개 크론이 등록됩니다.
# 실행: bash scripts/register_crons.sh

set -euo pipefail

PROJ="/Users/rocky/telegram-ai-org"
VENV="$PROJ/.venv/bin/python"

echo "=== openclaw cron 등록 시작 ==="

# 1. 주간 회의 — 매주 월요일 09:00 KST = UTC 일요일 00:00
openclaw cron add \
  --name "weekly_standup" \
  --schedule "0 0 * * 0" \
  --command "cd $PROJ && source .venv/bin/activate && python scripts/weekly_standup.py >> logs/standup.log 2>&1" \
  --description "주간 회의: 매주 월요일 09:00 KST"

echo "[OK] weekly_standup 등록"

# 2. 일일 회고 — 매일 23:30 KST = UTC 14:30
openclaw cron add \
  --name "daily_retro" \
  --schedule "30 14 * * *" \
  --command "cd $PROJ && source .venv/bin/activate && python scripts/daily_retro.py >> logs/retro.log 2>&1" \
  --description "일일 회고: 매일 23:30 KST"

echo "[OK] daily_retro 등록"

# 3. 일일 메트릭 — 매일 08:00 KST = UTC 23:00 (전날)
openclaw cron add \
  --name "daily_metrics" \
  --schedule "0 23 * * *" \
  --command "cd $PROJ && source .venv/bin/activate && python scripts/daily_metrics.py >> logs/metrics.log 2>&1" \
  --description "일일 메트릭: 매일 08:00 KST"

echo "[OK] daily_metrics 등록"

# 4. 월간 리뷰 — 매월 1일 10:00 KST = UTC 01:00
openclaw cron add \
  --name "monthly_review" \
  --schedule "0 1 1 * *" \
  --command "cd $PROJ && source .venv/bin/activate && python scripts/monthly_review.py >> logs/monthly.log 2>&1" \
  --description "월간 리뷰: 매월 1일 10:00 KST"

echo "[OK] monthly_review 등록"

echo ""
echo "=== 등록 완료 ==="
echo "확인: openclaw cron list"
