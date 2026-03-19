#!/usr/bin/env bash
# quality-gate/scripts/run.sh
# 프로젝트 품질 게이트 자동 실행 스크립트
# 사용법: bash skills/quality-gate/scripts/run.sh [project_root]

set -euo pipefail

PROJECT_ROOT="${1:-$(pwd)}"
VENV="$PROJECT_ROOT/.venv"
PASS=0
WARN=0
FAIL=0

echo "🔍 Quality Gate 시작: $PROJECT_ROOT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Ruff 린트
echo -n "린트 (Ruff): "
if [ -f "$VENV/bin/ruff" ]; then
    RUFF_OUT=$("$VENV/bin/ruff" check "$PROJECT_ROOT" --exit-zero 2>&1)
    ERROR_COUNT=$(echo "$RUFF_OUT" | grep -c "error\|E[0-9]" || true)
    WARN_COUNT=$(echo "$RUFF_OUT" | grep -c "warning\|W[0-9]" || true)
    if [ "$ERROR_COUNT" -eq 0 ] && [ "$WARN_COUNT" -eq 0 ]; then
        echo "✅ 오류 없음"
        PASS=$((PASS+1))
    elif [ "$ERROR_COUNT" -eq 0 ]; then
        echo "⚠️  경고 ${WARN_COUNT}개"
        WARN=$((WARN+1))
    else
        echo "❌ 오류 ${ERROR_COUNT}개"
        echo "$RUFF_OUT" | head -10
        FAIL=$((FAIL+1))
    fi
else
    echo "⚠️  ruff 미설치 (스킵)"
    WARN=$((WARN+1))
fi

# 2. pytest
echo -n "테스트 (pytest): "
if [ -f "$VENV/bin/pytest" ]; then
    TEST_OUT=$("$VENV/bin/pytest" "$PROJECT_ROOT/tests" -q --tb=short 2>&1 | tail -5)
    if echo "$TEST_OUT" | grep -q "passed" && ! echo "$TEST_OUT" | grep -q "failed\|error"; then
        PASSED=$(echo "$TEST_OUT" | grep -oP '\d+ passed' | grep -oP '\d+' || echo "?")
        echo "✅ ${PASSED} passed"
        PASS=$((PASS+1))
    else
        FAILED=$(echo "$TEST_OUT" | grep -oP '\d+ failed' | grep -oP '\d+' || echo "?")
        echo "❌ ${FAILED} failed"
        echo "$TEST_OUT"
        FAIL=$((FAIL+1))
    fi
else
    echo "⚠️  pytest 미설치 (스킵)"
    WARN=$((WARN+1))
fi

# 3. Import 검증
echo -n "Import 검증: "
if "$VENV/bin/python" -c "import core" 2>/dev/null; then
    echo "✅ OK"
    PASS=$((PASS+1))
else
    echo "❌ import core 실패"
    FAIL=$((FAIL+1))
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 최종 판정
if [ "$FAIL" -gt 0 ]; then
    echo "판정: ❌ FAIL (오류 ${FAIL}개)"
    exit 1
elif [ "$WARN" -gt 0 ]; then
    echo "판정: ⚠️  WARN (경고 ${WARN}개)"
    exit 0
else
    echo "판정: ✅ PASS"
    exit 0
fi
