#!/usr/bin/env bash
# =============================================================================
# run_daily_ai_news.sh — 일일 AI 뉴스 파이프라인 래퍼 스크립트
# =============================================================================
# 실행 순서:
#   1) 리서치 단계: daily_ai_news.py  → reports/daily_ai_news/YYYY-MM-DD_*.md
#   2) PM 필터링:   pm_filter_ai_news.py  → 텔레그램 Rocky 보고
# 각 단계 성공/실패 및 시각을 logs/daily_ai_news_cron.log 에 ISO 8601 형식으로 기록
# =============================================================================

set -euo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$PROJ/.venv/bin/python3"
LOG_FILE="$PROJ/logs/daily_ai_news_cron.log"
DATE_STR="$(date -u +%Y-%m-%d)"

# ── 로그 헬퍼 ────────────────────────────────────────────────────────────────
log_entry() {
  local stage="$1"
  local status="$2"
  local message="$3"
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '{"ts":"%s","date":"%s","stage":"%s","status":"%s","message":"%s"}\n' \
    "$ts" "$DATE_STR" "$stage" "$status" "$message" >> "$LOG_FILE"
}

mkdir -p "$PROJ/logs"

# ── 로그 로테이션 (30일 / ~150라인 기준) ─────────────────────────────────────
# LOG_FILE이 1500줄 초과 시 최근 1200줄만 유지 (30일 × ~5줄/일 기준)
rotate_log() {
  local file="$1"
  local max_lines=1500
  local keep_lines=1200
  if [[ -f "$file" ]]; then
    local line_count
    line_count="$(wc -l < "$file")"
    if (( line_count > max_lines )); then
      local tmp
      tmp="$(mktemp)"
      tail -n "$keep_lines" "$file" > "$tmp"
      mv "$tmp" "$file"
      printf '{"ts":"%s","date":"%s","stage":"logrotate","status":"info","message":"로그 로테이션 실행: %d줄 → %d줄 유지"}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$DATE_STR" "$line_count" "$keep_lines" >> "$file"
    fi
  fi
}
rotate_log "$LOG_FILE"

# ── 파이프라인 시작 ───────────────────────────────────────────────────────────
log_entry "pipeline" "start" "일일 AI 뉴스 파이프라인 시작"

# ── Stage 1: 리서치 ───────────────────────────────────────────────────────────
echo "[$(date -u +%H:%M:%SZ)] Stage 1: 리서치 시작" >&2
RESEARCH_START="$(date +%s)"

REPORT_PATH=""
if REPORT_PATH="$("$PYTHON" "$PROJ/scripts/daily_ai_news.py" 2>>"$LOG_FILE".stderr)"; then
  RESEARCH_END="$(date +%s)"
  DURATION=$(( RESEARCH_END - RESEARCH_START ))
  REPORT_PATH="${REPORT_PATH:-}"
  log_entry "research" "success" "리포트 저장: ${REPORT_PATH} (${DURATION}s)"
  echo "[$(date -u +%H:%M:%SZ)] Stage 1: 완료 → $REPORT_PATH (${DURATION}s)" >&2
else
  RESEARCH_END="$(date +%s)"
  DURATION=$(( RESEARCH_END - RESEARCH_START ))
  log_entry "research" "failure" "daily_ai_news.py 실행 실패 (${DURATION}s)"
  echo "[$(date -u +%H:%M:%SZ)] Stage 1: 실패 — 파이프라인 중단" >&2
  log_entry "pipeline" "failure" "Stage 1 실패로 파이프라인 조기 종료"
  exit 1
fi

# ── Stage 2: PM 필터링 + 텔레그램 보고 ───────────────────────────────────────
echo "[$(date -u +%H:%M:%SZ)] Stage 2: PM 필터링 + 텔레그램 보고 시작" >&2
PM_START="$(date +%s)"

if "$PYTHON" "$PROJ/scripts/pm_filter_ai_news.py" "${REPORT_PATH}" 2>>"$LOG_FILE".stderr; then
  PM_END="$(date +%s)"
  DURATION=$(( PM_END - PM_START ))
  log_entry "pm_filter" "success" "PM 필터링 + 텔레그램 보고 완료 (${DURATION}s)"
  echo "[$(date -u +%H:%M:%SZ)] Stage 2: 완료 (${DURATION}s)" >&2
else
  PM_END="$(date +%s)"
  DURATION=$(( PM_END - PM_START ))
  log_entry "pm_filter" "failure" "pm_filter_ai_news.py 실행 실패 (${DURATION}s)"
  echo "[$(date -u +%H:%M:%SZ)] Stage 2: 실패 (비치명적 — 리서치 결과는 저장됨)" >&2
fi

log_entry "pipeline" "success" "일일 AI 뉴스 파이프라인 완료"
echo "[$(date -u +%H:%M:%SZ)] 파이프라인 완료" >&2
