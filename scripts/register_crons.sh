#!/usr/bin/env bash
# openclaw cron 등록 스크립트
# Rocky가 한 번 실행하면 OpenClaw agent cron이 등록됩니다.
# 실행: bash scripts/register_crons.sh

set -euo pipefail

PROJ="/Users/rocky/telegram-ai-org"
TZ_NAME="Asia/Seoul"

register_job() {
  local name="$1"
  local cron_expr="$2"
  local description="$3"
  local message="$4"

  openclaw cron add \
    --name "$name" \
    --cron "$cron_expr" \
    --tz "$TZ_NAME" \
    --session isolated \
    --no-deliver \
    --description "$description" \
    --message "$message"
}

echo "=== openclaw cron 등록 시작 ==="

# ── 기존 크론 (협업 프로세스) ────────────────────────────────────────────────

# 1. 주간 회의 — 매주 월요일 09:00 KST
register_job \
  "weekly_standup" \
  "0 9 * * 1" \
  "주간 회의: 매주 월요일 09:00 KST" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/weekly_standup.py >> logs/standup.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] weekly_standup 등록"

# 2. 일일 회고 — 매일 23:30 KST
register_job \
  "daily_retro" \
  "30 23 * * *" \
  "일일 회고: 매일 23:30 KST" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/daily_retro.py >> logs/retro.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] daily_retro 등록"

# 3. 일일 메트릭 — 매일 08:00 KST
register_job \
  "daily_metrics" \
  "0 8 * * *" \
  "일일 메트릭: 매일 08:00 KST" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/daily_metrics.py >> logs/metrics.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] daily_metrics 등록"

# 4. 월간 리뷰 — 매월 1일 10:00 KST
register_job \
  "monthly_review" \
  "0 10 1 * *" \
  "월간 리뷰: 매월 1일 10:00 KST" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/monthly_review.py >> logs/monthly.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] monthly_review 등록"

# ── 자율 iter & 협업 크론 (신규) ────────────────────────────────────────────

# 5. 일일 목표 파이프라인 — 매일 09:05 KST
register_job \
  "daily_goal_pipeline" \
  "5 9 * * *" \
  "일일 목표 파이프라인: 매일 09:05 KST — iter 자동 재개 트리거" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/daily_goal_pipeline.py >> logs/goal_pipeline.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] daily_goal_pipeline 등록"

# 6. 주간회의 멀티봇 — 매주 월요일 09:03 KST
register_job \
  "weekly_meeting_multibot" \
  "3 9 * * 1" \
  "주간회의 멀티봇: 매주 월요일 09:03 KST — 봇 간 자율 협업 회의" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/weekly_meeting_multibot.py >> logs/weekly_meeting.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] weekly_meeting_multibot 등록"

# 7. 하네스 감사 (harness-audit) — 매주 금요일 17:05 KST
register_job \
  "weekly_harness_audit" \
  "5 17 * * 5" \
  "주간 하네스 감사: 매주 금요일 17:05 KST — 시스템 건강도 + 자율 iter 재개" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/run_harness_audit.py >> logs/harness_audit.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] weekly_harness_audit 등록"

# 8. 아침 목표 설정 — 매일 09:00 KST
register_job \
  "morning_goals" \
  "0 9 * * *" \
  "아침 목표 설정: 매일 09:00 KST" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/morning_goals.py >> logs/morning_goals.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] morning_goals 등록"

echo ""
echo "=== 등록 완료 (총 8개) ==="
echo "확인: openclaw cron list"
echo ""
echo "등록된 크론 목록:"
echo "  1. weekly_standup       — 매주 월요일 09:00 KST"
echo "  2. daily_retro          — 매일 23:30 KST"
echo "  3. daily_metrics        — 매일 08:00 KST"
echo "  4. monthly_review       — 매월 1일 10:00 KST"
echo "  5. daily_goal_pipeline  — 매일 09:05 KST (자율 iter 트리거)"
echo "  6. weekly_meeting_multibot — 매주 월요일 09:03 KST (봇 간 협업 회의)"
echo "  7. weekly_harness_audit — 매주 금요일 17:05 KST (시스템 감사)"
echo "  8. morning_goals        — 매일 09:00 KST (아침 목표)"
