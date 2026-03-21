#!/usr/bin/env bash
# quality-gate/scripts/lint-only.sh
# PostToolUse:Write 훅용 경량 린트 검사 (ruff만, pytest 제외)
# 항상 exit 0 — 경고만 출력, 절대 차단하지 않음

PROJECT_ROOT="${1:-$(pwd)}"
VENV="$PROJECT_ROOT/.venv"

if [ -f "$VENV/bin/ruff" ]; then
    RUFF_OUT=$("$VENV/bin/ruff" check "$PROJECT_ROOT" --exit-zero 2>&1)
    ERROR_COUNT=$(echo "$RUFF_OUT" | grep -c "error\|E[0-9]" || true)
    if [ "$ERROR_COUNT" -gt 0 ]; then
        echo "⚠️  [lint-hook] ruff 오류 ${ERROR_COUNT}개 발견:"
        echo "$RUFF_OUT" | grep "error\|E[0-9]" | head -5
    fi
fi

# 항상 성공 — 차단하지 않음
exit 0
