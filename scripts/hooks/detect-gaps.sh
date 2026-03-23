#!/usr/bin/env bash
# detect-gaps.sh — 세션 시작 시 harness 불일치(gap) 자동 탐지
# 등록: settings.local.json > hooks > SessionStart
# 체크 항목 5가지:
#   1. core/ 파일 중 module-level docstring 없는 파일
#   2. skills/ 중 SKILL.md 없는 디렉토리
#   3. bots/ YAML 중 system_prompt 누락 봇
#   4. scripts/hooks/ 중 settings.local.json 미등록 스크립트
#   5. tests/ 커버리지 없는 core 모듈 (test_<module>.py 존재 여부)

PROJECT_ROOT="/Users/rocky/telegram-ai-org"
WARN=0
OUTPUT_LINES=()

log_warn() {
  WARN=$((WARN + 1))
  OUTPUT_LINES+=("⚠️  GAP-$WARN: $1")
}

# ─── CHECK 1: core/ 파일 중 module-level docstring 없는 파일 ───────────────
MISSING_DOCSTRING=()
for f in "$PROJECT_ROOT/core/"*.py; do
  [[ -f "$f" ]] || continue
  basename_f=$(basename "$f")
  # 첫 5줄 안에 """로 시작하는 docstring 있는지 확인
  if ! head -5 "$f" 2>/dev/null | grep -qE '"""'; then
    MISSING_DOCSTRING+=("$basename_f")
  fi
done
if [[ ${#MISSING_DOCSTRING[@]} -gt 0 ]]; then
  log_warn "core/ 모듈 docstring 누락 (${#MISSING_DOCSTRING[@]}개): ${MISSING_DOCSTRING[*]:0:5}$([ ${#MISSING_DOCSTRING[@]} -gt 5 ] && echo ' ...')"
fi

# ─── CHECK 2: skills/ 중 SKILL.md 없는 디렉토리 ───────────────────────────
MISSING_SKILL_MD=()
for d in "$PROJECT_ROOT/skills"/*/; do
  [[ -d "$d" ]] || continue
  dir_name=$(basename "$d")
  # _shared 같은 내부 디렉토리는 제외
  [[ "$dir_name" == _* ]] && continue
  if [[ ! -f "$d/SKILL.md" ]]; then
    MISSING_SKILL_MD+=("$dir_name")
  fi
done
if [[ ${#MISSING_SKILL_MD[@]} -gt 0 ]]; then
  log_warn "skills/ SKILL.md 누락 디렉토리 (${#MISSING_SKILL_MD[@]}개): ${MISSING_SKILL_MD[*]}"
fi

# ─── CHECK 3: bots/ YAML 중 system_prompt 누락 봇 ─────────────────────────
MISSING_PROMPT=()
for f in "$PROJECT_ROOT/bots/"*.yaml "$PROJECT_ROOT/bots/"*.yml; do
  [[ -f "$f" ]] || continue
  if ! grep -qE "system_prompt|instruction" "$f" 2>/dev/null; then
    MISSING_PROMPT+=("$(basename "$f")")
  fi
done
if [[ ${#MISSING_PROMPT[@]} -gt 0 ]]; then
  log_warn "bots/ system_prompt 누락 (${#MISSING_PROMPT[@]}개): ${MISSING_PROMPT[*]}"
fi

# ─── CHECK 4: scripts/hooks/ 중 settings.local.json 미등록 스크립트 ────────
SETTINGS_FILE="$PROJECT_ROOT/.claude/settings.local.json"
UNREGISTERED_HOOKS=()
if [[ -f "$SETTINGS_FILE" ]]; then
  for f in "$PROJECT_ROOT/scripts/hooks/"*.sh; do
    [[ -f "$f" ]] || continue
    script_name=$(basename "$f")
    if ! grep -q "$script_name" "$SETTINGS_FILE" 2>/dev/null; then
      UNREGISTERED_HOOKS+=("$script_name")
    fi
  done
fi
if [[ ${#UNREGISTERED_HOOKS[@]} -gt 0 ]]; then
  log_warn "scripts/hooks/ 미등록 스크립트 (${#UNREGISTERED_HOOKS[@]}개): ${UNREGISTERED_HOOKS[*]}"
fi

# ─── CHECK 5: tests/ 커버리지 없는 core 모듈 ──────────────────────────────
MISSING_TESTS=()
for f in "$PROJECT_ROOT/core/"*.py; do
  [[ -f "$f" ]] || continue
  module_name=$(basename "$f" .py)
  # __init__, __main__ 등 제외
  [[ "$module_name" == __* ]] && continue
  if [[ ! -f "$PROJECT_ROOT/tests/test_${module_name}.py" ]]; then
    MISSING_TESTS+=("$module_name")
  fi
done
if [[ ${#MISSING_TESTS[@]} -gt 0 ]]; then
  log_warn "tests/ 커버리지 없는 core 모듈 (${#MISSING_TESTS[@]}개): ${MISSING_TESTS[*]:0:5}$([ ${#MISSING_TESTS[@]} -gt 5 ] && echo ' ...')"
fi

# ─── 결과 출력 ──────────────────────────────────────────────────────────────
if [[ $WARN -eq 0 ]]; then
  echo "✅ detect-gaps: 5개 체크 모두 정상 — gap 없음"
else
  echo "🔍 detect-gaps 결과: ${WARN}개 gap 감지됨 ($(date '+%Y-%m-%d %H:%M'))"
  for line in "${OUTPUT_LINES[@]}"; do
    echo "  $line"
  done
  echo "  → 자세한 내용: /harness-audit 스킬 실행 권장"
fi

exit 0
