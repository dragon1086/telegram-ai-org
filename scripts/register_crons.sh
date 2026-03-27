#!/usr/bin/env bash
# openclaw cron 등록 스크립트
# Rocky가 한 번 실행하면 OpenClaw agent cron이 등록됩니다.
# 실행: bash scripts/register_crons.sh

set -euo pipefail

PROJ="/Users/rocky/telegram-ai-org"
TZ_NAME="Asia/Seoul"
OPENCLAW_TIMEOUT_MS="${OPENCLAW_TIMEOUT_MS:-60000}"
OPENCLAW_LIST_RETRIES="${OPENCLAW_LIST_RETRIES:-3}"
OPENCLAW_LIST_RETRY_DELAY_SEC="${OPENCLAW_LIST_RETRY_DELAY_SEC:-2}"

list_jobs_json() {
  local attempt output rc

  for ((attempt = 1; attempt <= OPENCLAW_LIST_RETRIES; attempt++)); do
    if output="$(openclaw cron list --all --json --timeout "$OPENCLAW_TIMEOUT_MS")"; then
      printf '%s\n' "$output"
      return 0
    fi
    rc=$?
    echo "[WARN] openclaw cron list 실패 (${attempt}/${OPENCLAW_LIST_RETRIES})" >&2
    if (( attempt < OPENCLAW_LIST_RETRIES )); then
      sleep "$OPENCLAW_LIST_RETRY_DELAY_SEC"
    fi
  done

  echo "[ERROR] openclaw cron list가 반복 실패하여 등록을 중단합니다." >&2
  return "${rc:-1}"
}

find_job_ids_by_name() {
  local name="$1"
  list_jobs_json | python3 -c '
import json
import sys

name = sys.argv[1]
payload = json.load(sys.stdin)
jobs = payload if isinstance(payload, list) else payload.get("jobs", payload.get("items", []))
for job in jobs:
    if job.get("name") == name:
        print(job.get("id", ""))
' "$name"
}

ensure_job() {
  local name="$1"
  local cron_expr="$2"
  local description="$3"
  local message="$4"
  local ids_text existing_id dup_id seen_first

  ids_text="$(find_job_ids_by_name "$name")"
  existing_id="$(printf '%s\n' "$ids_text" | awk 'NF { print; exit }')"

  seen_first=0
  while IFS= read -r dup_id; do
    [[ -n "$dup_id" ]] || continue
    if [[ $seen_first -eq 0 ]]; then
      seen_first=1
      continue
    fi
      openclaw cron rm "$dup_id" --timeout "$OPENCLAW_TIMEOUT_MS" >/dev/null
      echo "[CLEANUP] duplicate removed: $name ($dup_id)"
  done <<EOF
$ids_text
EOF

  if [[ -n "$existing_id" ]]; then
    openclaw cron edit "$existing_id" \
      --name "$name" \
      --cron "$cron_expr" \
      --tz "$TZ_NAME" \
      --session isolated \
      --no-deliver \
      --description "$description" \
      --message "$message" \
      --timeout "$OPENCLAW_TIMEOUT_MS" >/dev/null
    echo "[SYNC] $name 업데이트"
  else
    openclaw cron add \
      --name "$name" \
      --cron "$cron_expr" \
      --tz "$TZ_NAME" \
      --session isolated \
      --no-deliver \
      --description "$description" \
      --message "$message" \
      --timeout "$OPENCLAW_TIMEOUT_MS" >/dev/null
    echo "[ADD] $name 등록"
  fi
}

echo "=== openclaw cron 등록 시작 ==="

# ── 기존 크론 (협업 프로세스) ────────────────────────────────────────────────

# 1. 주간 회의 — 매주 월요일 09:00 KST
ensure_job \
  "weekly_standup" \
  "0 9 * * 1" \
  "주간 회의: 매주 월요일 09:00 KST" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/weekly_standup.py >> logs/standup.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] weekly_standup 등록"

# 2. 일일 회고 — 매일 23:30 KST
ensure_job \
  "daily_retro" \
  "30 23 * * *" \
  "일일 회고: 매일 23:30 KST" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/daily_retro.py >> logs/retro.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] daily_retro 등록"

# 3. 일일 메트릭 — 매일 08:00 KST
ensure_job \
  "daily_metrics" \
  "0 8 * * *" \
  "일일 메트릭: 매일 08:00 KST" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/daily_metrics.py >> logs/metrics.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] daily_metrics 등록"

# 4. 월간 리뷰 — 매월 1일 10:00 KST
ensure_job \
  "monthly_review" \
  "0 10 1 * *" \
  "월간 리뷰: 매월 1일 10:00 KST" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/monthly_review.py >> logs/monthly.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] monthly_review 등록"

# ── 자율 iter & 협업 크론 (신규) ────────────────────────────────────────────

# 5. 일일 목표 파이프라인 — 매일 09:05 KST
ensure_job \
  "daily_goal_pipeline" \
  "5 9 * * *" \
  "일일 목표 파이프라인: 매일 09:05 KST — iter 자동 재개 트리거" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/daily_goal_pipeline.py >> logs/goal_pipeline.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] daily_goal_pipeline 등록"

# 6. 주간회의 멀티봇 — 매주 월요일 09:03 KST
ensure_job \
  "weekly_meeting_multibot" \
  "3 9 * * 1" \
  "주간회의 멀티봇: 매주 월요일 09:03 KST — 봇 간 자율 협업 회의" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/weekly_meeting_multibot.py >> logs/weekly_meeting.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] weekly_meeting_multibot 등록"

# 7. 하네스 감사 (harness-audit) — 매주 금요일 17:05 KST
ensure_job \
  "weekly_harness_audit" \
  "5 17 * * 5" \
  "주간 하네스 감사: 매주 금요일 17:05 KST — 시스템 건강도 + 자율 iter 재개" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/run_harness_audit.py >> logs/harness_audit.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] weekly_harness_audit 등록"

# 8. 아침 목표 설정 — 매일 09:00 KST
ensure_job \
  "morning_goals" \
  "0 9 * * *" \
  "아침 목표 설정: 매일 09:00 KST" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/morning_goals.py >> logs/morning_goals.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] morning_goals 등록"

# 9~12. GoalTracker 루프 스테이지 — 매시 20/25/30/35분 KST
ensure_job \
  "goal_tracker_idle" \
  "20 * * * *" \
  "GoalTracker idle stage: 매시 20분 KST — 활성 목표 스냅샷" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/goal_tracker_stage_runner.py --stage idle >> logs/goal_tracker_idle.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] goal_tracker_idle 등록"

ensure_job \
  "goal_tracker_evaluate" \
  "25 * * * *" \
  "GoalTracker evaluate stage: 매시 25분 KST — 활성 목표 진척 평가" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/goal_tracker_stage_runner.py --stage evaluate >> logs/goal_tracker_evaluate.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] goal_tracker_evaluate 등록"

ensure_job \
  "goal_tracker_replan" \
  "30 * * * *" \
  "GoalTracker replan stage: 매시 30분 KST — 재계획 큐 생성" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/goal_tracker_stage_runner.py --stage replan >> logs/goal_tracker_replan.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] goal_tracker_replan 등록"

ensure_job \
  "goal_tracker_dispatch" \
  "35 * * * *" \
  "GoalTracker dispatch stage: 매시 35분 KST — 재계획 태스크 배분" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/goal_tracker_stage_runner.py --stage dispatch >> logs/goal_tracker_dispatch.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] goal_tracker_dispatch 등록"

# 13. 전 조직 배포 상태 자동 검증 — 매시 12분/42분 KST
ensure_job \
  "bot_deploy_healthcheck" \
  "12,42 * * * *" \
  "전 조직 봇 배포 상태 자동 검증: 30분 간격 헬스체크 + watchdog 상태 확인" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/bot_deploy_healthcheck.py >> logs/bot_deploy_healthcheck.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] bot_deploy_healthcheck 등록"

# 14. PRISM 앱스토어 주간 점검 체크리스트 — 매주 월요일 09:02 KST
ensure_job \
  "appstore_weekly_checklist" \
  "2 9 * * 1" \
  "PRISM 앱스토어 주간 점검 체크리스트: 매주 월요일 09:02 KST — Rocky 수동 확인 알림 전송" \
  "Repository: $PROJ. Run \`cd $PROJ && ./.venv/bin/python scripts/appstore_weekly_checklist.py >> logs/appstore_checklist.log 2>&1\` and finish with a one-line success/failure summary."

echo "[OK] appstore_weekly_checklist 등록"

# 15. 일일 AI 뉴스 파이프라인 — 매일 08:57 KST (리서치실 수명 업무)
# 래퍼 스크립트: research → PM 필터링 → 텔레그램 보고 전 단계 포함
ensure_job \
  "daily_ai_news" \
  "57 8 * * *" \
  "일일 AI 뉴스 파이프라인: 매일 08:57 KST — 리서치(gemini-3-flash-preview) + PM 필터링 + Rocky 텔레그램 보고" \
  "Repository: $PROJ. Run \`cd $PROJ && bash scripts/run_daily_ai_news.sh >> logs/daily_ai_news_cron.log 2>&1\` and finish with a one-line summary: HIGH items count, top actionable item, report path. Log: logs/daily_ai_news_cron.log"

echo "[OK] daily_ai_news 등록"

echo ""
echo "=== 등록 완료 (총 15개) ==="
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
echo "  9. goal_tracker_idle    — 매시 20분 KST"
echo " 10. goal_tracker_evaluate — 매시 25분 KST"
echo " 11. goal_tracker_replan  — 매시 30분 KST"
echo " 12. goal_tracker_dispatch — 매시 35분 KST"
echo " 13. bot_deploy_healthcheck — 매시 12분/42분 KST"
echo " 14. appstore_weekly_checklist — 매주 월요일 09:02 KST (PRISM 앱스토어 점검 알림)"
echo " 15. daily_ai_news        — 매일 08:57 KST (AI 뉴스 리서치 + 적용 가능성 평가)"
