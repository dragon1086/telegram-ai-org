#!/usr/bin/env bash
# validate-dangerous-patterns.sh — 코드베이스 위험 패턴 검사 (오탐 최소화 버전)
set -euo pipefail

PROJECT_DIR="/Users/rocky/telegram-ai-org"
ERRORS=0
WARNINGS=0

echo "🔍 위험 패턴 검사 시작: ${PROJECT_DIR}"
echo "========================================"

# 헬퍼 함수
check_pattern() {
  local desc="$1"; local pattern="$2"; local level="$3"
  local results
  # 제외: 테스트 파일, 주석, 이 스크립트 자체, .venv
  results=$(grep -rn --include="*.py" --include="*.sh"     --exclude-dir=".venv" --exclude-dir="__pycache__" --exclude-dir=".git"     -E "${pattern}" "${PROJECT_DIR}" 2>/dev/null     | grep -v "# " | grep -v "validate-dangerous-patterns" | grep -v "test_"     | grep -v ".pyc" || true)
  if [ -n "${results}" ]; then
    if [ "${level}" = "ERROR" ]; then
      echo "❌ [ERROR] ${desc}"
      echo "${results}" | head -5
      ERRORS=$((ERRORS+1))
    else
      echo "⚠️  [WARN] ${desc}"
      echo "${results}" | head -3
      WARNINGS=$((WARNINGS+1))
    fi
    echo ""
  fi
}

# 홈/루트 재귀 탐색 (가장 위험)
check_pattern "홈 디렉토리 전체 재귀 glob"   "glob\(.*Path\.home\(\).*recursive=True" "ERROR"
check_pattern "루트 재귀 glob"   "glob\('/\*\*'" "ERROR"
check_pattern "홈 디렉토리 os.walk"   "os\.walk\(.*home\(\)" "ERROR"

# API 키 하드코딩
check_pattern "API 키 하드코딩 의심"   "(api_key|API_KEY|secret|token)\s*=\s*['"][A-Za-z0-9_\-]{20,}" "ERROR"

# subprocess shell=True + 미검증 입력
check_pattern "subprocess shell=True (주의 필요)"   "subprocess\.run\(.*shell=True" "WARN"

# sys.exit() in 봇 코드 (core/, bots/)
results=$(grep -rn --include="*.py" -E "sys\.exit\(" "${PROJECT_DIR}/core" "${PROJECT_DIR}/bots" 2>/dev/null   | grep -v "# " | grep -v "test_" || true)
if [ -n "${results}" ]; then
  echo "⚠️  [WARN] 봇 코드에서 sys.exit() 직접 호출"
  echo "${results}" | head -3
  WARNINGS=$((WARNINGS+1))
  echo ""
fi

echo "========================================"
echo "결과: ❌ ERROR ${ERRORS}건 | ⚠️  WARN ${WARNINGS}건"
[ "${ERRORS}" -gt 0 ] && exit 1 || exit 0
