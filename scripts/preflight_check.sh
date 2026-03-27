#!/usr/bin/env bash
# scripts/preflight_check.sh — E2E 실행 전 인프라 체크리스트
#
# 사용법:
#   bash scripts/preflight_check.sh           # 기본 실행
#   bash scripts/preflight_check.sh --quiet   # PASS 항목 숨김
#   bash scripts/preflight_check.sh --fail-fast  # 첫 번째 FAIL 즉시 중단
#
# 종료 코드:
#   0 — PASS 또는 WARN (실행 가능)
#   1 — FAIL (실행 불가)
#
# RETRO-01: pre-flight 체크 자동화 (2026-03-27)

set -euo pipefail

# ---------------------------------------------------------------------------
# 색상 / 출력 헬퍼
# ---------------------------------------------------------------------------
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
DIM='\033[2m'
RESET='\033[0m'

QUIET=false
FAIL_FAST=false
FAIL_COUNT=0
WARN_COUNT=0
PASS_COUNT=0

for arg in "$@"; do
    case "$arg" in
        --quiet)    QUIET=true ;;
        --fail-fast) FAIL_FAST=true ;;
    esac
done

log_pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
    if [ "$QUIET" = false ]; then
        printf "  ${GREEN}[PASS]${RESET}  %s\n" "$1"
    fi
}

log_warn() {
    WARN_COUNT=$((WARN_COUNT + 1))
    printf "  ${YELLOW}[WARN]${RESET}  %s\n" "$1"
}

log_fail() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    printf "  ${RED}[FAIL]${RESET}  %s\n" "$1" >&2
    if [ "$FAIL_FAST" = true ]; then
        echo ""
        printf "${RED}pre-flight ABORTED (fail-fast)${RESET}\n" >&2
        exit 1
    fi
}

log_section() {
    printf "\n${CYAN}── %s ${DIM}%s${RESET}\n" "$1" "$2"
}

# ---------------------------------------------------------------------------
# 프로젝트 루트 결정 (스크립트 위치 기준)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

printf "\n${CYAN}╔══════════════════════════════════════════════════╗${RESET}\n"
printf "${CYAN}║  telegram-ai-org  Pre-Flight Check               ║${RESET}\n"
printf "${CYAN}║  $(date '+%Y-%m-%d %H:%M:%S KST')                        ║${RESET}\n"
printf "${CYAN}╚══════════════════════════════════════════════════╝${RESET}\n"

# ---------------------------------------------------------------------------
# CHECK 1: Python venv 존재 및 활성화 여부
# ---------------------------------------------------------------------------
log_section "CHECK 1" "Python venv"

VENV_PATH="$PROJECT_ROOT/.venv"
if [ -d "$VENV_PATH" ]; then
    log_pass "venv 존재: $VENV_PATH"
else
    log_fail "venv 없음: $VENV_PATH — 'python -m venv .venv && .venv/bin/pip install -e .' 실행 필요"
fi

PYTHON_BIN="$VENV_PATH/bin/python"
if [ -x "$PYTHON_BIN" ]; then
    PY_VER=$("$PYTHON_BIN" --version 2>&1 || echo "unknown")
    log_pass "Python 실행 가능: $PY_VER"
else
    log_fail "Python 바이너리 없음: $PYTHON_BIN"
    PYTHON_BIN="python3"
fi

# venv 활성화 상태 체크 (VIRTUAL_ENV 환경변수)
if [ -n "${VIRTUAL_ENV:-}" ]; then
    log_pass "venv 활성화됨: $VIRTUAL_ENV"
else
    log_warn "venv 미활성화 (source .venv/bin/activate 권장) — 실행은 가능"
fi

# ---------------------------------------------------------------------------
# CHECK 2: 필수 환경변수 설정 여부
# ---------------------------------------------------------------------------
log_section "CHECK 2" "필수 환경변수"

# .env 로드 (존재 시)
ENV_FILE="$PROJECT_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE" 2>/dev/null || true
    set +a
    log_pass ".env 로드됨: $ENV_FILE"
else
    log_warn ".env 파일 없음: cp .env.example .env 후 값 설정 필요"
fi

# 필수 환경변수 목록 (최소 1개 이상 설정되어야 정상 동작)
REQUIRED_VARS=(
    "TELEGRAM_BOT_TOKEN"
    "TELEGRAM_GROUP_CHAT_ID"
)
# API 키: 하나 이상 설정되면 OK
API_KEY_VARS=(
    "GEMINI_API_KEY"
    "ANTHROPIC_API_KEY"
    "OPENAI_API_KEY"
    "GOOGLE_API_KEY"
)

for var in "${REQUIRED_VARS[@]}"; do
    val="${!var:-}"
    if [ -n "$val" ]; then
        masked="${val:0:4}****"
        log_pass "$var 설정됨 ($masked...)"
    else
        log_fail "$var 미설정 — .env 파일 확인 필요"
    fi
done

# API 키: 하나 이상 설정 확인
API_KEY_SET=false
for var in "${API_KEY_VARS[@]}"; do
    val="${!var:-}"
    if [ -n "$val" ]; then
        API_KEY_SET=true
        log_pass "API 키 설정됨: $var"
        break
    fi
done
if [ "$API_KEY_SET" = false ]; then
    log_fail "API 키 없음 (GEMINI_API_KEY / ANTHROPIC_API_KEY 중 하나 이상 필요)"
fi

# ---------------------------------------------------------------------------
# CHECK 3: DB 파일 존재 여부
# ---------------------------------------------------------------------------
log_section "CHECK 3" "데이터베이스 파일"

DB_FILES=(
    "ai_org.db"
    "tasks.db"
)
# logs/tasks.db는 선택적
OPTIONAL_DB_FILES=(
    "logs/tasks.db"
    "data/self_fix_rate.json"
)

for db in "${DB_FILES[@]}"; do
    if [ -f "$PROJECT_ROOT/$db" ]; then
        SIZE=$(du -sh "$PROJECT_ROOT/$db" 2>/dev/null | cut -f1 || echo "?")
        log_pass "$db 존재 ($SIZE)"
    else
        log_warn "$db 없음 — 첫 실행 시 자동 생성됩니다"
    fi
done

for db in "${OPTIONAL_DB_FILES[@]}"; do
    if [ -f "$PROJECT_ROOT/$db" ]; then
        log_pass "$db 존재 (선택)"
    else
        log_warn "$db 없음 (선택 파일 — 영향 없음)"
    fi
done

# ---------------------------------------------------------------------------
# CHECK 4: 핵심 설정 파일 존재 여부
# ---------------------------------------------------------------------------
log_section "CHECK 4" "핵심 설정 파일"

CONFIG_FILES=(
    "orchestration.yaml"
    "organizations.yaml"
    "workers.yaml"
    "agent_hints.yaml"
)

for cfg in "${CONFIG_FILES[@]}"; do
    if [ -f "$PROJECT_ROOT/$cfg" ]; then
        log_pass "$cfg 존재"
    else
        log_fail "$cfg 없음 — 설정 파일 누락"
    fi
done

# config/ 디렉토리 내 파일 확인
if [ -d "$PROJECT_ROOT/config" ]; then
    CFG_COUNT=$(find "$PROJECT_ROOT/config" -name "*.yaml" -o -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$CFG_COUNT" -gt 0 ]; then
        log_pass "config/ 디렉토리: $CFG_COUNT 개 설정 파일"
    else
        log_warn "config/ 디렉토리 비어있음"
    fi
else
    log_warn "config/ 디렉토리 없음 (선택)"
fi

# ---------------------------------------------------------------------------
# CHECK 5: infra-baseline.yaml 존재 여부
# ---------------------------------------------------------------------------
log_section "CHECK 5" "infra-baseline.yaml"

BASELINE="$PROJECT_ROOT/infra-baseline.yaml"
if [ -f "$BASELINE" ]; then
    VERSION=$(grep -E "^version:" "$BASELINE" 2>/dev/null | head -1 | awk '{print $2}' || echo "unknown")
    log_pass "infra-baseline.yaml 존재 (version: $VERSION)"
else
    log_fail "infra-baseline.yaml 없음 — 인프라 파라미터 기준 미정의 (RETRO-03 참조)"
fi

# ---------------------------------------------------------------------------
# CHECK 6: gemini-2.0-flash 사용 여부 (프로덕션 코드)
# ---------------------------------------------------------------------------
log_section "CHECK 6" "Deprecated 모델 버전 탐지"

DEPRECATED_MODEL="gemini-2.0-flash"
# core/, scripts/, bots/, tools/ 에서만 탐색 (docs/ 제외)
DEPRECATED_FOUND=$(grep -rn "$DEPRECATED_MODEL" \
    "$PROJECT_ROOT/core/" \
    "$PROJECT_ROOT/scripts/" \
    "$PROJECT_ROOT/bots/" \
    "$PROJECT_ROOT/tools/" \
    "$PROJECT_ROOT/main.py" \
    "$PROJECT_ROOT/cli.py" \
    2>/dev/null \
    | grep -v "__pycache__" \
    | grep -v ".pyc" \
    | grep -v "preflight_check.sh" \
    | grep -v "preflight_check.py" \
    || true)

if [ -z "$DEPRECATED_FOUND" ]; then
    log_pass "프로덕션 코드에 $DEPRECATED_MODEL 없음"
else
    log_fail "Deprecated 모델 발견 ($DEPRECATED_MODEL) — gemini-2.5-flash로 교체 필요:"
    echo "$DEPRECATED_FOUND" | head -5 | while IFS= read -r line; do
        printf "        %s\n" "$line"
    done
fi

# ---------------------------------------------------------------------------
# CHECK 7: TelegramRelay import 테스트
# ---------------------------------------------------------------------------
log_section "CHECK 7" "핵심 모듈 import"

IMPORT_RESULT=$("$VENV_PATH/bin/python" -c "from core.telegram_relay import TelegramRelay; print('ok')" 2>&1 || true)
if echo "$IMPORT_RESULT" | grep -q "^ok$"; then
    log_pass "core.telegram_relay.TelegramRelay import OK"
else
    log_fail "TelegramRelay import 실패: $IMPORT_RESULT"
fi

# 추가 핵심 모듈 import 체크
for module in "core.env_guard" "core.bot_commands"; do
    MOD_RESULT=$("$VENV_PATH/bin/python" -c "import $module; print('ok')" 2>&1 || true)
    if echo "$MOD_RESULT" | grep -q "^ok$"; then
        log_pass "$module import OK"
    else
        log_warn "$module import 실패: $MOD_RESULT"
    fi
done

# ---------------------------------------------------------------------------
# CHECK 8: Ruff lint (core/)
# ---------------------------------------------------------------------------
log_section "CHECK 8" "Ruff lint (core/)"

if "$VENV_PATH/bin/python" -m ruff --version >/dev/null 2>&1; then
    RUFF_RESULT=$("$VENV_PATH/bin/python" -m ruff check "$PROJECT_ROOT/core/" --quiet 2>&1 || true)
    if [ -z "$RUFF_RESULT" ]; then
        log_pass "ruff check core/ — 린트 이슈 없음"
    else
        ISSUE_COUNT=$(echo "$RUFF_RESULT" | grep -c "E\|W\|F" 2>/dev/null || echo "?")
        log_warn "ruff 린트 이슈 $ISSUE_COUNT 건 (--quiet 출력 생략 — 'ruff check core/' 직접 실행)"
    fi
else
    log_warn "ruff 미설치 — '.venv/bin/pip install ruff' 권장"
fi

# ---------------------------------------------------------------------------
# 최종 요약
# ---------------------------------------------------------------------------
printf "\n${CYAN}════════════════════════════════════════════════════${RESET}\n"
printf "  PASS: ${GREEN}%d${RESET}  WARN: ${YELLOW}%d${RESET}  FAIL: ${RED}%d${RESET}\n" \
    "$PASS_COUNT" "$WARN_COUNT" "$FAIL_COUNT"

if [ "$FAIL_COUNT" -eq 0 ]; then
    if [ "$WARN_COUNT" -gt 0 ]; then
        printf "  ${YELLOW}STATUS: WARN — 실행 가능하나 위 경고 항목 확인 권장${RESET}\n"
    else
        printf "  ${GREEN}STATUS: PASS — 모든 체크 통과${RESET}\n"
    fi
    printf "${CYAN}════════════════════════════════════════════════════${RESET}\n\n"
    exit 0
else
    printf "  ${RED}STATUS: FAIL — 위 FAIL 항목 해결 후 재실행${RESET}\n"
    printf "${CYAN}════════════════════════════════════════════════════${RESET}\n\n"
    exit 1
fi
