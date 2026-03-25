#!/usr/bin/env bash
# =============================================================================
# scripts/setup.sh — telegram-ai-org 원클릭 설치 스크립트
#
# 실행 흐름:
#   1. 3엔진 자동 감지 (claude / codex / gemini)
#   2. Python 버전 및 의존성 설치 (venv + pip)
#   3. Node/npm 존재 여부 확인
#   4. .env 파일 생성 (.env.example → .env 복사 + 자동 치환)
#   5. 초기화 검증 (패키지 import + 엔진 바이너리 실행 확인)
#
# 사용법:
#   bash scripts/setup.sh
#   bash scripts/setup.sh --skip-verify   # 검증 단계 건너뜀
#   bash scripts/setup.sh --no-venv       # 가상환경 생성 건너뜀
#   bash scripts/setup.sh --yes           # 비대화형 자동 설치 (CI 환경)
#   bash scripts/setup.sh --docker        # Docker Compose 실행 모드 (감지 후 자동 실행)
#   bash scripts/setup.sh --yes --docker  # CI 환경 + Docker Compose 자동 실행
# =============================================================================

set -euo pipefail

# ── 색상 정의 ─────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

ok()   { echo -e "${GREEN}✅ $*${RESET}"; }
warn() { echo -e "${YELLOW}⚠️  $*${RESET}"; }
err()  { echo -e "${RED}❌ $*${RESET}"; }
info() { echo -e "${CYAN}ℹ️  $*${RESET}"; }
step() { echo -e "\n${BOLD}${BLUE}▶ $*${RESET}"; }

# ── 인수 파싱 ──────────────────────────────────────────────────────────────────
SKIP_VERIFY=false
NO_VENV=false
NON_INTERACTIVE=false  # --yes / --non-interactive: CI 환경 무인 설치 (프롬프트 건너뜀)
USE_DOCKER=false       # --docker: Docker Compose 실행 모드 (감지 후 docker compose up 진행)
for arg in "$@"; do
    case "$arg" in
        --skip-verify)                SKIP_VERIFY=true ;;
        --no-venv)                    NO_VENV=true ;;
        --yes|-y|--non-interactive)   NON_INTERACTIVE=true ;;
        --docker)                     USE_DOCKER=true ;;
    esac
done

# ── OS 감지 ────────────────────────────────────────────────────────────────────
OS_TYPE="$(uname -s)"
case "$OS_TYPE" in
    Darwin) OS_NAME="macOS" ;;
    Linux)  OS_NAME="Linux" ;;
    *)      OS_NAME="Unknown ($OS_TYPE)" ;;
esac

echo -e "${BOLD}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║        telegram-ai-org — 원클릭 설치 스크립트               ║"
echo "║        3-Engine Auto-Detect Setup (claude/codex/gemini)      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${RESET}"
info "운영체제: $OS_NAME"
info "작업 디렉토리: $(pwd)"

# ── 프로젝트 루트 확인 ─────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [ ! -f "pyproject.toml" ] && [ ! -f ".env.example" ]; then
    err "프로젝트 루트를 찾을 수 없습니다: $PROJECT_ROOT"
    exit 1
fi
info "프로젝트 루트: $PROJECT_ROOT"

# =============================================================================
# main() — 원클릭 설치 진입점
#   탐지(Step 1) → Python 환경(Step 2) → 의존성(Step 3)
#   → .env 생성(Step 4) → 초기화 검증(Step 5) → 요약 출력
# =============================================================================
main() {

# =============================================================================
# STEP 1: 3엔진 자동 감지
# =============================================================================
step "Step 1/5: AI 엔진 자동 감지"

CLAUDE_PATH=""
CODEX_PATH=""
GEMINI_CLI_PATH=""
DETECTED_ENGINES=()

# =============================================================================
# [함수] _show_engine_guide — 미설치 엔진별 설치 URL·명령어 출력
# =============================================================================
_show_engine_guide() {
    local engine="$1"
    case "$engine" in
        claude-code)
            echo -e "  ${CYAN}[ claude-code 설치 가이드 ]${RESET}"
            echo "    npm install -g @anthropic-ai/claude-code"
            echo "    (또는) https://claude.ai/code 에서 직접 설치"
            echo ""
            ;;
        codex)
            echo -e "  ${CYAN}[ codex 설치 가이드 ]${RESET}"
            echo "    npm install -g @openai/codex"
            echo "    Node.js 18+ 필요: https://nodejs.org"
            echo ""
            ;;
        gemini-cli)
            echo -e "  ${CYAN}[ gemini-cli 설치 가이드 ]${RESET}"
            if [ "${OS_NAME:-}" = "macOS" ]; then
                echo "    brew install gemini-cli"
                echo "    (또는) npm install -g @google/gemini-cli"
            else
                echo "    npm install -g @google/gemini-cli"
            fi
            echo "    인증: gemini auth login"
            echo ""
            ;;
    esac
}

# =============================================================================
# [함수] detect_claude_code — claude CLI PATH 탐지 + 버전 검증
#   우선순위: ~/.local/bin/claude → ~/bin/claude → /opt/homebrew/bin/claude
#             → /usr/local/bin/claude → PATH (command -v)
#   결과: CLAUDE_PATH, _claude_version 설정 / DETECTED_ENGINES 에 추가
# =============================================================================
detect_claude_code() {
    CLAUDE_PATH=""
    _claude_version=""
    # 일반적인 설치 경로 우선 탐색 (PATH 미등록 시에도 감지)
    for _c_candidate in \
        "$HOME/.local/bin/claude" \
        "$HOME/bin/claude" \
        "/opt/homebrew/bin/claude" \
        "/usr/local/bin/claude"; do
        if [ -x "$_c_candidate" ]; then
            CLAUDE_PATH="$_c_candidate"
            break
        fi
    done
    # PATH 에서 탐색 (fallback)
    if [ -z "$CLAUDE_PATH" ]; then
        CLAUDE_PATH=$(command -v claude 2>/dev/null) || true
    fi
    if [ -n "$CLAUDE_PATH" ]; then
        _claude_version=$("$CLAUDE_PATH" --version 2>/dev/null | head -1 || echo "버전 확인 불가")
        ok "claude-code 감지됨: $CLAUDE_PATH  ($_claude_version)"
        DETECTED_ENGINES+=("claude-code")
        return 0
    fi
    warn "claude CLI 미감지"
    _show_engine_guide "claude-code"
    return 1
}

# =============================================================================
# [함수] detect_codex — codex CLI PATH 탐지 + 버전 검증
#   우선순위: ~/.local/bin/codex → ~/bin/codex → /opt/homebrew/bin/codex
#             → /usr/local/bin/codex → PATH (command -v)
#   결과: CODEX_PATH, _codex_version 설정 / DETECTED_ENGINES 에 추가
# =============================================================================
detect_codex() {
    CODEX_PATH=""
    _codex_version=""
    # 일반적인 설치 경로 우선 탐색 (PATH 미등록 시에도 감지)
    for _d_candidate in \
        "$HOME/.local/bin/codex" \
        "$HOME/bin/codex" \
        "/opt/homebrew/bin/codex" \
        "/usr/local/bin/codex"; do
        if [ -x "$_d_candidate" ]; then
            CODEX_PATH="$_d_candidate"
            break
        fi
    done
    # PATH 에서 탐색 (fallback)
    if [ -z "$CODEX_PATH" ]; then
        CODEX_PATH=$(command -v codex 2>/dev/null) || true
    fi
    if [ -n "$CODEX_PATH" ]; then
        _codex_version=$("$CODEX_PATH" --version 2>/dev/null | head -1 || echo "버전 확인 불가")
        ok "codex 감지됨:      $CODEX_PATH  ($_codex_version)"
        DETECTED_ENGINES+=("codex")
        return 0
    fi
    warn "codex CLI 미감지"
    _show_engine_guide "codex"
    return 1
}

# =============================================================================
# [함수] detect_gemini_cli — gemini CLI PATH 탐지 + 버전 검증
#   우선순위: /opt/homebrew/bin/gemini → ~/.local/bin/gemini → PATH
#   결과: GEMINI_CLI_PATH, _gemini_version 설정 / DETECTED_ENGINES 에 추가
# =============================================================================
detect_gemini_cli() {
    GEMINI_CLI_PATH=""
    _gemini_version=""
    for _g_candidate in "/opt/homebrew/bin/gemini" "$HOME/.local/bin/gemini" "$HOME/bin/gemini"; do
        if [ -x "$_g_candidate" ]; then
            GEMINI_CLI_PATH="$_g_candidate"
            break
        fi
    done
    if [ -z "$GEMINI_CLI_PATH" ]; then
        GEMINI_CLI_PATH=$(command -v gemini 2>/dev/null) || true
    fi
    if [ -n "$GEMINI_CLI_PATH" ]; then
        _gemini_version=$("$GEMINI_CLI_PATH" --version 2>/dev/null | head -1 || echo "버전 확인 불가")
        ok "gemini-cli 감지됨: $GEMINI_CLI_PATH  ($_gemini_version)"
        DETECTED_ENGINES+=("gemini-cli")
        return 0
    fi
    warn "gemini CLI 미감지"
    _show_engine_guide "gemini-cli"
    return 1
}

# ── 엔진 자동 설치 헬퍼 ──────────────────────────────────────────────────────
# _try_install_engine <engine-name>: npm/brew로 엔진 자동 설치 시도
_try_install_engine() {
    local engine="$1"
    if [ "$NON_INTERACTIVE" = false ]; then
        read -rp "  ❓ $engine 를 자동 설치하시겠습니까? [Y/n]: " _install_ans
        _install_ans="${_install_ans:-Y}"
        [[ "$_install_ans" =~ ^[Nn]$ ]] && return 1
    else
        info "--yes 모드: $engine 자동 설치 시도"
    fi

    case "$engine" in
        claude-code)
            if command -v npm &>/dev/null; then
                info "npm으로 claude-code 설치 중..."
                npm install -g @anthropic-ai/claude-code && return 0
            elif command -v brew &>/dev/null && [ "$OS_NAME" = "macOS" ]; then
                info "brew로 claude-code 설치 중..."
                brew install claude && return 0
            else
                warn "npm/brew를 찾을 수 없어 자동 설치 실패. 수동 설치: https://claude.ai/code"
                return 1
            fi
            ;;
        codex)
            if command -v npm &>/dev/null; then
                info "npm으로 codex 설치 중..."
                npm install -g @openai/codex && return 0
            else
                warn "npm을 찾을 수 없어 자동 설치 실패. Node.js 설치 후 재시도하세요."
                return 1
            fi
            ;;
        gemini-cli)
            if command -v brew &>/dev/null && [ "$OS_NAME" = "macOS" ]; then
                info "brew로 gemini-cli 설치 중..."
                brew install gemini-cli && return 0
            elif command -v npm &>/dev/null; then
                info "npm으로 gemini-cli 설치 중..."
                npm install -g @google/gemini-cli && return 0
            else
                warn "brew/npm을 찾을 수 없어 자동 설치 실패."
                return 1
            fi
            ;;
    esac
    return 1
}

# claude-code 감지 → 미감지 시 자동 설치 시도
if ! detect_claude_code; then
    if _try_install_engine "claude-code"; then
        detect_claude_code || CLAUDE_PATH=""
    else
        CLAUDE_PATH=""
    fi
fi

# codex 감지 → 미감지 시 자동 설치 시도
if ! detect_codex; then
    if _try_install_engine "codex"; then
        detect_codex || CODEX_PATH=""
    else
        CODEX_PATH=""
    fi
fi

# gemini-cli 감지 → 미감지 시 자동 설치 시도
if ! detect_gemini_cli; then
    if _try_install_engine "gemini-cli"; then
        detect_gemini_cli || GEMINI_CLI_PATH=""
    else
        GEMINI_CLI_PATH=""
    fi
fi

# 하나도 없으면 경고 후 종료
if [ ${#DETECTED_ENGINES[@]} -eq 0 ]; then
    err "AI 엔진이 하나도 감지되지 않았습니다."
    err "최소 하나의 엔진을 설치해주세요:"
    echo "  • claude:  npm install -g @anthropic-ai/claude-code"
    echo "             (또는 https://claude.ai/code 에서 직접 설치)"
    echo "  • codex:   npm install -g @openai/codex"
    echo "  • gemini:  npm install -g @google/gemini-cli"
    if [ "$OS_NAME" = "macOS" ]; then
        echo "             (또는 brew install gemini-cli)"
    fi
    exit 1
fi

echo -e "\n감지된 엔진: ${BOLD}${GREEN}${DETECTED_ENGINES[*]}${RESET} (총 ${#DETECTED_ENGINES[@]}개)"

# ── 엔진 선택 (복수 감지 시 사용자 선택 프롬프트) ─────────────────────────────
SELECTED_ENGINE=""
if [ ${#DETECTED_ENGINES[@]} -eq 1 ]; then
    SELECTED_ENGINE="${DETECTED_ENGINES[0]}"
    info "기본 엔진 자동 선택: $SELECTED_ENGINE"
elif [ "$NON_INTERACTIVE" = true ]; then
    # --yes 플래그: claude-code 우선, 없으면 감지 순서 첫 번째
    SELECTED_ENGINE="${DETECTED_ENGINES[0]}"
    for _e in "${DETECTED_ENGINES[@]}"; do
        [ "$_e" = "claude-code" ] && SELECTED_ENGINE="claude-code" && break
    done
    info "--yes 모드: 기본 엔진 자동 선택 → $SELECTED_ENGINE"
else
    echo ""
    echo -e "${BOLD}${YELLOW}복수의 엔진이 감지되었습니다. 기본 엔진을 선택해주세요:${RESET}"
    for _i in "${!DETECTED_ENGINES[@]}"; do
        echo "  $((_i+1)). ${DETECTED_ENGINES[$_i]}"
    done
    echo ""
    while true; do
        read -rp "  선택 [1-${#DETECTED_ENGINES[@]}] (기본값: 1, claude-code 권장): " _eng_choice
        _eng_choice="${_eng_choice:-1}"
        if [[ "$_eng_choice" =~ ^[0-9]+$ ]] && \
           [ "$_eng_choice" -ge 1 ] && \
           [ "$_eng_choice" -le "${#DETECTED_ENGINES[@]}" ]; then
            SELECTED_ENGINE="${DETECTED_ENGINES[$((_eng_choice-1))]}"
            break
        fi
        warn "올바른 번호를 입력해주세요 (1-${#DETECTED_ENGINES[@]})"
    done
    ok "선택된 기본 엔진: $SELECTED_ENGINE"
fi

# =============================================================================
# STEP 2: Python 버전 확인
# =============================================================================
step "Step 2/5: Python 환경 확인"

# Python 3.10+ 탐색: 명시적 버전 순으로 시도 (macOS 시스템 python3 = 3.9 우회)
PYTHON_BIN=""
PYTHON_VERSION=""
for _candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$_candidate" &>/dev/null; then
        _ver=$("$_candidate" --version 2>&1 | awk '{print $2}')
        _major=$(echo "$_ver" | cut -d. -f1)
        _minor=$(echo "$_ver" | cut -d. -f2)
        # pyproject.toml requires-python = ">=3.11"
        if [ "$_major" -ge 3 ] && [ "$_minor" -ge 11 ]; then
            PYTHON_BIN="$_candidate"
            PYTHON_VERSION="$_ver"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    # 시스템 python3 버전 정보도 출력해서 원인 파악 용이하게
    _sys_ver=$(python3 --version 2>&1 | awk '{print $2}' 2>/dev/null || echo "미설치")
    err "Python 3.11 이상을 찾을 수 없습니다 (시스템 python3: $_sys_ver)"
    err "(pyproject.toml requires-python = \">=3.11\" 기준)"
    case "$OS_NAME" in
        macOS) err "설치: brew install python@3.11" ;;
        Linux) err "설치: sudo apt-get install python3.11 (Debian/Ubuntu)" ;;
    esac
    exit 1
fi

ok "Python $PYTHON_VERSION ($PYTHON_BIN) — 요구사항 충족"

# ── 가상환경 생성 ──────────────────────────────────────────────────────────────
VENV_DIR=".venv"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

if [ "$NO_VENV" = false ]; then
    if [ ! -x "$VENV_PYTHON" ]; then
        info "가상환경 생성 중: $VENV_DIR/  ($PYTHON_BIN 사용)"
        "$PYTHON_BIN" -m venv "$VENV_DIR"
        ok "가상환경 생성 완료"
    else
        _venv_ver=$("$VENV_PYTHON" --version 2>&1 | awk '{print $2}')
        ok "가상환경 이미 존재: $VENV_DIR/ (Python $_venv_ver)"
    fi
else
    warn "--no-venv 옵션: 가상환경 생성 건너뜀"
    VENV_PYTHON="$PYTHON_BIN"
    VENV_PIP="$PYTHON_BIN -m pip"
fi

# =============================================================================
# STEP 3: 의존성 설치
# =============================================================================
step "Step 3/5: Python 의존성 설치"

if [ "$NO_VENV" = false ]; then
    info "pip 업그레이드 중..."
    "$VENV_PYTHON" -m pip install --upgrade pip --quiet
fi

# pyproject.toml에서 의존성 추출하는 헬퍼 (tomllib 내장, Python 3.11+)
extract_deps() {
    "$VENV_PYTHON" - <<'PYEOF'
import sys, json
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        sys.exit(0)  # tomllib/tomli 없으면 빈 출력
with open("pyproject.toml", "rb") as f:
    data = tomllib.load(f)
proj = data.get("project", {})
deps = proj.get("dependencies", [])
dev_deps = proj.get("optional-dependencies", {}).get("dev", [])
print("\n".join(deps + dev_deps))
PYEOF
}

# 설치 시도: editable → deps-only fallback
install_deps() {
    # uv가 있으면 먼저 시도
    if command -v uv &>/dev/null; then
        info "uv 감지됨 — 빠른 설치 모드 사용"
        if uv pip install --python "$VENV_PYTHON" -e ".[dev]" --quiet 2>/dev/null; then
            ok "의존성 설치 완료 (uv editable)"
            return 0
        fi
        warn "uv editable 설치 실패 — deps-only 모드로 재시도"
        DEPS=$(extract_deps)
        if [ -n "$DEPS" ]; then
            echo "$DEPS" | xargs uv pip install --python "$VENV_PYTHON" --quiet
            ok "의존성 설치 완료 (uv deps-only)"
            return 0
        fi
    fi

    # pip으로 editable 시도
    info "pip으로 의존성 설치 중 (pyproject.toml [dev])..."
    if "$VENV_PYTHON" -m pip install -e ".[dev]" --quiet 2>/dev/null; then
        ok "의존성 설치 완료 (pip editable)"
        return 0
    fi

    # fallback: pyproject.toml deps 직접 읽어서 설치
    warn "editable 설치 실패 (hatchling 패키지 구조 문제) — deps-only 모드로 재시도"
    DEPS=$(extract_deps)
    if [ -n "$DEPS" ]; then
        info "pyproject.toml 의존성 직접 설치 중..."
        echo "$DEPS" | while IFS= read -r dep; do
            [ -n "$dep" ] && "$VENV_PYTHON" -m pip install "$dep" --quiet
        done
        ok "의존성 설치 완료 (pip deps-only)"
    else
        warn "pyproject.toml 파싱 실패 — 수동으로 .venv/bin/pip install -e '.[dev]' 실행해주세요"
    fi
}

install_deps

# ── requirements.txt 추가 설치 (존재하는 경우) ────────────────────────────────
if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
    info "requirements.txt 감지됨 — pip install -r requirements.txt 실행 중..."
    if [ "$NO_VENV" = false ]; then
        "$VENV_PYTHON" -m pip install -r "$PROJECT_ROOT/requirements.txt" --quiet \
            && ok "requirements.txt 의존성 설치 완료" \
            || warn "requirements.txt 일부 패키지 설치 실패 — 수동 확인 필요"
    else
        pip install -r "$PROJECT_ROOT/requirements.txt" --quiet \
            && ok "requirements.txt 의존성 설치 완료" \
            || warn "requirements.txt 일부 패키지 설치 실패 — 수동 확인 필요"
    fi
else
    info "requirements.txt 없음 — pyproject.toml 의존성만 사용"
fi

# ── 엔진별 추가 패키지 설치 (감지된 모든 엔진 대상) ──────────────────────────
# 봇별로 다른 엔진을 사용하므로 감지된 엔진의 SDK는 모두 설치
echo ""
info "엔진별 SDK 확인 중 (감지된 엔진: ${DETECTED_ENGINES[*]})..."

# claude-code: anthropic SDK (pyproject.toml base deps에 포함, 감지 여부와 무관하게 체크)
if "$VENV_PYTHON" -c "import anthropic" 2>/dev/null; then
    ok "anthropic SDK 설치됨 (claude-code)"
else
    info "anthropic SDK 설치 중..."
    "$VENV_PYTHON" -m pip install anthropic --quiet && ok "anthropic 설치 완료"
fi

# codex: openai SDK (pyproject.toml base deps에 포함, 감지 여부와 무관하게 체크)
if "$VENV_PYTHON" -c "import openai" 2>/dev/null; then
    ok "openai SDK 설치됨 (codex)"
else
    info "openai SDK 설치 중..."
    "$VENV_PYTHON" -m pip install openai --quiet && ok "openai 설치 완료"
fi

# gemini-cli: google-genai SDK (선택적 의존성 — gemini 감지 시 설치)
# pyproject.toml [gemini] extra: google-genai>=1.0 (import: google.genai)
if [ -n "$GEMINI_CLI_PATH" ]; then
    if "$VENV_PYTHON" -c "import google.genai" 2>/dev/null; then
        ok "google-genai SDK 설치됨 (gemini-cli)"
    else
        info "gemini-cli용 google-genai SDK 설치 중..."
        "$VENV_PYTHON" -m pip install google-genai --quiet && ok "google-genai 설치 완료"
    fi
else
    info "gemini-cli 미감지 — google-genai SDK 설치 건너뜀 (필요시: pip install google-genai)"
fi

# ── Node/npm 존재 여부 확인 (codex 설치 시 필요) ───────────────────────────────
if [ -n "$CODEX_PATH" ]; then
    if command -v node &>/dev/null && command -v npm &>/dev/null; then
        NODE_VER=$(node --version)
        NPM_VER=$(npm --version)
        ok "Node.js $NODE_VER / npm $NPM_VER 감지됨"
    else
        warn "Node.js / npm 미감지 — codex CLI를 npm 없이 사용 중 (바이너리 직접 설치)"
    fi
fi

# 추가: workspace 디렉토리 생성
mkdir -p ~/.ai-org/workspace
info "컨텍스트 DB 디렉토리 준비: ~/.ai-org/"

# 프로젝트 로컬 디렉토리 생성 (logs/, data/, reports/)
mkdir -p logs data reports
info "프로젝트 디렉토리 준비: logs/, data/, reports/"

# =============================================================================
# [함수] configure_engine — 선택된 엔진의 인증 상태 확인 및 안내
# =============================================================================
configure_engine() {
    local engine="$1"
    echo ""
    info "엔진 인증 상태 확인: $engine"

    case "$engine" in
        claude-code)
            # ANTHROPIC_API_KEY 확인 (scoring용; claude CLI 자체는 OAuth 브라우저 인증)
            if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
                ok "ANTHROPIC_API_KEY 감지됨 — claude-code scoring 사용 가능"
            else
                warn "ANTHROPIC_API_KEY 미설정 — .env에서 입력하거나 claude CLI OAuth 인증 사용"
                info "  → claude 첫 실행 시 브라우저 인증 자동 진행 (CLAUDE_CODE_OAUTH_TOKEN)"
            fi
            ;;
        codex)
            # OPENAI_API_KEY 확인 (codex CLI는 ~/.codex/auth.json OAuth 우선)
            if [ -n "${OPENAI_API_KEY:-}" ]; then
                ok "OPENAI_API_KEY 감지됨 — codex API 키 인증 사용 가능"
            elif [ -f "$HOME/.codex/auth.json" ]; then
                ok "~/.codex/auth.json 감지됨 — codex OAuth 인증 완료"
            else
                warn "OPENAI_API_KEY 미설정, ~/.codex/auth.json 없음"
                info "  → codex 인증: codex login 실행 (OAuth 브라우저 인증)"
                info "  → 또는 .env에 OPENAI_API_KEY 입력"
            fi
            ;;
        gemini-cli)
            # OAuth 인증 파일 존재 확인
            if [ -f "$HOME/.gemini/oauth_creds.json" ]; then
                ok "~/.gemini/oauth_creds.json 감지됨 — gemini-cli OAuth 인증 완료"
            else
                warn "~/.gemini/oauth_creds.json 없음 — gemini-cli 인증 필요"
                if [ -n "$GEMINI_CLI_PATH" ] && [ -x "$GEMINI_CLI_PATH" ]; then
                    info "  → 인증 명령: $GEMINI_CLI_PATH auth login"
                else
                    info "  → 인증 명령: gemini auth login"
                fi
                info "  → 브라우저에서 Google 계정 로그인 후 자동 완료"
            fi
            ;;
    esac
}

# =============================================================================
# [함수] setup_env — .env 파일에 선택된 엔진명 및 CLI 경로 자동 기재
# =============================================================================
setup_env() {
    local engine="$1"
    local env_file="$2"
    local os_name="$3"

    # sed 헬퍼: OS별 분기
    _sed_inplace() {
        local pattern="$1"
        if [ "$os_name" = "macOS" ]; then
            sed -i '' "$pattern" "$env_file"
        else
            sed -i "$pattern" "$env_file"
        fi
    }

    # _set_or_append: 키가 있으면 sed 치환, 없으면 파일 끝에 추가
    _set_or_append() {
        local key="$1"
        local value="$2"
        if grep -q "^${key}=" "$env_file" 2>/dev/null; then
            _sed_inplace "s|^${key}=.*|${key}=${value}|"
        else
            echo "${key}=${value}" >> "$env_file"
        fi
    }

    # CLAUDE_CLI_PATH 자동 치환
    if [ -n "$CLAUDE_PATH" ]; then
        _set_or_append "CLAUDE_CLI_PATH" "$CLAUDE_PATH"
        info "CLAUDE_CLI_PATH → $CLAUDE_PATH (자동 설정)"
    fi

    # CODEX_CLI_PATH 자동 치환
    if [ -n "$CODEX_PATH" ]; then
        _set_or_append "CODEX_CLI_PATH" "$CODEX_PATH"
        info "CODEX_CLI_PATH → $CODEX_PATH (자동 설정)"
    fi

    # GEMINI_CLI_PATH 자동 치환
    if [ -n "$GEMINI_CLI_PATH" ]; then
        _set_or_append "GEMINI_CLI_PATH" "$GEMINI_CLI_PATH"
        info "GEMINI_CLI_PATH → $GEMINI_CLI_PATH (자동 설정)"
        # GEMINI_CLI_DEFAULT_TIMEOUT_SEC 이 미설정이면 기본값 주입
        if grep -q "^GEMINI_CLI_DEFAULT_TIMEOUT_SEC=$" "$env_file" 2>/dev/null; then
            _sed_inplace "s|^GEMINI_CLI_DEFAULT_TIMEOUT_SEC=$|GEMINI_CLI_DEFAULT_TIMEOUT_SEC=1800|"
            info "GEMINI_CLI_DEFAULT_TIMEOUT_SEC → 1800 (기본값 자동 설정)"
        fi
    fi

    # AI_ENGINE= 자동 세팅 (표준 진입점 — 런타임 우선 참조 변수)
    if grep -q "^AI_ENGINE=" "$env_file" 2>/dev/null; then
        _sed_inplace "s|^AI_ENGINE=.*|AI_ENGINE=$engine|"
    else
        echo "AI_ENGINE=$engine" >> "$env_file"
    fi
    info "AI_ENGINE → $engine (자동 설정)"

    # ENGINE= 자동 세팅
    if grep -q "^ENGINE=" "$env_file" 2>/dev/null; then
        _sed_inplace "s|^ENGINE=.*|ENGINE=$engine|"
    else
        echo "ENGINE=$engine" >> "$env_file"
    fi
    info "ENGINE → $engine (자동 설정)"

    # ACTIVE_ENGINE= 자동 세팅 (ENGINE= 과 병기 — 런타임 참조 표준 변수)
    if grep -q "^ACTIVE_ENGINE=" "$env_file" 2>/dev/null; then
        _sed_inplace "s|^ACTIVE_ENGINE=.*|ACTIVE_ENGINE=$engine|"
    else
        echo "ACTIVE_ENGINE=$engine" >> "$env_file"
    fi
    info "ACTIVE_ENGINE → $engine (자동 설정)"

    # DEFAULT_ENGINE= 자동 세팅 (런타임 기본 엔진 참조 표준 변수)
    if grep -q "^DEFAULT_ENGINE=" "$env_file" 2>/dev/null; then
        _sed_inplace "s|^DEFAULT_ENGINE=.*|DEFAULT_ENGINE=$engine|"
    else
        echo "DEFAULT_ENGINE=$engine" >> "$env_file"
    fi
    info "DEFAULT_ENGINE → $engine (자동 설정)"
}

# =============================================================================
# [함수] print_engine_summary — 감지된 3엔진 상태 요약표 출력
# =============================================================================
print_engine_summary() {
    local _claude_status _codex_status _gemini_status
    local _claude_disp _codex_disp _gemini_disp

    # claude-code
    if [ -n "$CLAUDE_PATH" ]; then
        _claude_status="${GREEN}✅ 감지됨${RESET}"
        _claude_disp="$CLAUDE_PATH"
    else
        _claude_status="${YELLOW}⬜ 미감지${RESET}"
        _claude_disp="(미설치 — npm install -g @anthropic-ai/claude-code)"
    fi

    # codex
    if [ -n "$CODEX_PATH" ]; then
        _codex_status="${GREEN}✅ 감지됨${RESET}"
        _codex_disp="$CODEX_PATH"
    else
        _codex_status="${YELLOW}⬜ 미감지${RESET}"
        _codex_disp="(미설치 — npm install -g @openai/codex)"
    fi

    # gemini-cli
    if [ -n "$GEMINI_CLI_PATH" ]; then
        _gemini_status="${GREEN}✅ 감지됨${RESET}"
        _gemini_disp="$GEMINI_CLI_PATH"
    else
        _gemini_status="${YELLOW}⬜ 미감지${RESET}"
        _gemini_disp="(미설치 — brew install gemini-cli / npm install -g @google/gemini-cli)"
    fi

    echo ""
    echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "${BOLD}${CYAN}  🔍 AI 엔진 감지 요약${RESET}"
    echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    printf "  %-14s  %-8s  %s\n" "엔진" "상태" "경로"
    echo "  ──────────────────────────────────────────────────────────────"
    printf "  %-14s  " "claude-code"
    echo -e "${_claude_status}  ${_claude_disp}"
    printf "  %-14s  " "codex"
    echo -e "${_codex_status}  ${_codex_disp}"
    printf "  %-14s  " "gemini-cli"
    echo -e "${_gemini_status}  ${_gemini_disp}"
    echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "  선택된 기본 엔진: ${BOLD}${GREEN}$SELECTED_ENGINE${RESET}"
    echo ""
}

# =============================================================================
# STEP 4: .env 파일 처리
# =============================================================================
step "Step 4/5: 환경 변수 파일 설정"

ENV_FILE=".env"
ENV_EXAMPLE=".env.example"

if [ ! -f "$ENV_EXAMPLE" ]; then
    warn ".env.example 파일이 없습니다. 필수 템플릿을 자동 생성합니다..."
    cat > "$ENV_EXAMPLE" << 'ENV_TEMPLATE'
# =============================================================================
# telegram-ai-org 환경변수 설정 파일 (자동 생성)
# 이 파일을 .env 로 복사한 뒤 각 값을 채워주세요:
#   cp .env.example .env
#
# 오픈소스 원클릭 설치:
#   bash scripts/setup.sh          # 엔진 자동 감지 + 경로 자동 설정
#   bash scripts/setup.sh --yes    # 비대화형 자동 설치
# =============================================================================

# =============================================================================
# [필수] 텔레그램 봇 토큰 — @BotFather 에서 발급
# =============================================================================
TELEGRAM_BOT_TOKEN=
PM_BOT_TOKEN=
TELEGRAM_GROUP_CHAT_ID=
ADMIN_CHAT_ID=

# 부서 봇 토큰 (필수 — 해당 부서를 사용할 경우)
BOT_TOKEN_AIORG_PRODUCT_BOT=
BOT_TOKEN_AIORG_ENGINEERING_BOT=
BOT_TOKEN_AIORG_DESIGN_BOT=
BOT_TOKEN_AIORG_GROWTH_BOT=
BOT_TOKEN_AIORG_OPS_BOT=
BOT_TOKEN_AIORG_RESEARCH_BOT=

# =============================================================================
# [필수] API 키
# =============================================================================
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
OPENAI_API_KEY=

# =============================================================================
# [엔진] Claude Code
# =============================================================================
CLAUDE_CODE_OAUTH_TOKEN=
CLAUDE_CLI_PATH=
CLAUDE_DEFAULT_TIMEOUT_SEC=14400

# =============================================================================
# [엔진] Codex
# =============================================================================
CODEX_CLI_PATH=
CODEX_DEFAULT_TIMEOUT_SEC=1800

# =============================================================================
# [엔진] Gemini CLI
# =============================================================================
GEMINI_CLI_PATH=/opt/homebrew/bin/gemini
GEMINI_CLI_MODEL=gemini-2.5-flash
GEMINI_CLI_DEFAULT_TIMEOUT_SEC=1800
GEMINI_OAUTH_CREDS_PATH=~/.gemini/oauth_creds.json

# =============================================================================
# [엔진 선택] 기본 엔진 (setup.sh 자동 감지 후 기재)
# 선택 가능한 값: claude-code | codex | gemini-cli
# =============================================================================
# 런타임 우선 참조 변수 — setup.sh 자동 감지 시 기재
AI_ENGINE=
DEFAULT_ENGINE=
ENGINE=
ACTIVE_ENGINE=
ENGINE_TYPE=

# =============================================================================
# [기능 플래그]
# =============================================================================
ENABLE_PM_ORCHESTRATOR=1
ENABLE_DISCUSSION_PROTOCOL=1
ENABLE_AUTO_DISPATCH=1
ENABLE_CROSS_VERIFICATION=1
ENABLE_GOAL_TRACKER=1

# =============================================================================
# [DB/스토리지]
# =============================================================================
CONTEXT_DB_PATH=~/.ai-org/context.db
SHARED_MEMORY_PATH=~/.ai-org/shared_memory.json
AIORG_REPORT_DIR=./reports

# =============================================================================
# [로깅]
# =============================================================================
LOG_LEVEL=INFO
AIORG_DEBUG=false
AUTONOMOUS_MODE=false
ENV_TEMPLATE
    ok ".env.example 자동 생성 완료"
fi

if [ -f "$ENV_FILE" ]; then
    if [ "$NON_INTERACTIVE" = true ]; then
        ok ".env 파일 이미 존재 — --yes 모드: 덮어쓰기 건너뜀"
        ENV_EXISTS=true
    else
        echo ""
        echo -e "${YELLOW}⚠️  .env 파일이 이미 존재합니다.${RESET}"
        read -rp "  .env.example로 덮어쓰시겠습니까? 기존 값이 모두 초기화됩니다. [y/N]: " _overwrite
        _overwrite="${_overwrite:-N}"
        if [[ "$_overwrite" =~ ^[Yy]$ ]]; then
            cp "$ENV_EXAMPLE" "$ENV_FILE"
            ok ".env 파일 덮어쓰기 완료 (.env.example 기준으로 초기화)"
            ENV_EXISTS=false
        else
            ok ".env 파일 유지 — 기존 설정 보존"
            ENV_EXISTS=true
        fi
    fi
else
    info ".env.example → .env 복사 중..."
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    ok ".env 파일 생성 완료"
    ENV_EXISTS=false
fi

# ── 엔진 CLI 경로·ENGINE 변수 자동 기재 (setup_env 함수 사용) ─────────────────
setup_env "$SELECTED_ENGINE" "$ENV_FILE" "$OS_NAME"

# ── 선택된 엔진 인증 상태 확인 (configure_engine 함수 사용) ────────────────────
configure_engine "$SELECTED_ENGINE"

# ── 인터랙티브 필수 키 수집 (신규 .env 파일인 경우, --yes 아닐 때) ──────────────
if [ "$ENV_EXISTS" = false ] && [ "$NON_INTERACTIVE" = false ]; then
    echo ""
    echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "${BOLD}${CYAN}  🔑 Telegram 봇 필수 정보를 입력해주세요 (나중에 .env에서 수정 가능)${RESET}"
    echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""

    # PM_BOT_TOKEN + TELEGRAM_BOT_TOKEN (동일 토큰 — 두 변수 동시 설정)
    read -rp "  PM 봇 토큰 (@BotFather에서 발급, 스킵: Enter): " _pm_token
    if [ -n "$_pm_token" ]; then
        if [ "$OS_NAME" = "macOS" ]; then
            sed -i '' "s|^PM_BOT_TOKEN=.*|PM_BOT_TOKEN=$_pm_token|" "$ENV_FILE"
            sed -i '' "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=$_pm_token|" "$ENV_FILE"
        else
            sed -i "s|^PM_BOT_TOKEN=.*|PM_BOT_TOKEN=$_pm_token|" "$ENV_FILE"
            sed -i "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=$_pm_token|" "$ENV_FILE"
        fi
        ok "PM_BOT_TOKEN / TELEGRAM_BOT_TOKEN 설정 완료"
    else
        warn "PM 봇 토큰 미입력 — .env 파일에서 PM_BOT_TOKEN / TELEGRAM_BOT_TOKEN 직접 입력하세요"
    fi

    # TELEGRAM_GROUP_CHAT_ID
    read -rp "  TELEGRAM_GROUP_CHAT_ID (그룹 chat_id, 예: -100xxxxxxxxxx, 스킵: Enter): " _chat_id
    if [ -n "$_chat_id" ]; then
        if [ "$OS_NAME" = "macOS" ]; then
            sed -i '' "s|^TELEGRAM_GROUP_CHAT_ID=.*|TELEGRAM_GROUP_CHAT_ID=$_chat_id|" "$ENV_FILE"
        else
            sed -i "s|^TELEGRAM_GROUP_CHAT_ID=.*|TELEGRAM_GROUP_CHAT_ID=$_chat_id|" "$ENV_FILE"
        fi
        ok "TELEGRAM_GROUP_CHAT_ID 설정 완료"
    else
        warn "TELEGRAM_GROUP_CHAT_ID 미입력 — .env 파일에서 직접 입력하세요"
    fi
    echo ""
fi

# API 키 입력 안내 메시지
if [ "$ENV_EXISTS" = false ]; then
    echo ""
    echo -e "${BOLD}${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "${BOLD}${YELLOW}  📝 .env 파일에 아래 항목을 직접 입력해주세요:${RESET}"
    echo -e "${BOLD}${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""
    echo "  필수 항목:"
    echo "    PM_BOT_TOKEN=           # @BotFather에서 발급"
    echo "    TELEGRAM_GROUP_CHAT_ID= # Telegram 그룹 chat_id (음수, 예: -100xxxxxxxxxx)"
    echo ""
    echo "  엔진별 API 키 (사용하는 엔진만 입력):"
    [ -n "$CLAUDE_PATH" ] && echo "    CLAUDE_CODE_OAUTH_TOKEN= # claude CLI OAuth 토큰 (claude --oauth)"
    [ -n "$CODEX_PATH" ]  && echo "    # Codex: ~/.codex/auth.json OAuth 자동 사용 (별도 입력 불필요)"
    [ -n "$GEMINI_CLI_PATH" ] && echo "    # Gemini: gemini auth login 실행 필요 (~/.gemini/oauth_creds.json)"
    echo ""
    echo "  scoring용 (권장, 선택):"
    echo "    GEMINI_API_KEY=         # Gemini scoring"
    echo "    ANTHROPIC_API_KEY=      # Anthropic scoring (대체)"
    echo ""
    echo -e "  편집: ${BOLD}nano .env${RESET}  또는  ${BOLD}code .env${RESET}"
    echo -e "${BOLD}${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
fi

# =============================================================================
# STEP 5: 초기화 검증
# =============================================================================
if [ "$SKIP_VERIFY" = true ]; then
    warn "--skip-verify: 검증 단계 건너뜀"
else
    step "Step 5/5: 초기화 검증"

    VERIFY_PASS=0
    VERIFY_FAIL=0

    # ── Python 패키지 import 검증 ────────────────────────────────────────────────
    info "핵심 패키지 import 검증 중..."

    check_import() {
        local pkg="$1"
        local label="${2:-$1}"
        if "$VENV_PYTHON" -c "import $pkg" 2>/dev/null; then
            ok "  import $label"
            VERIFY_PASS=$((VERIFY_PASS + 1))
        else
            err "  import $label — 실패"
            VERIFY_FAIL=$((VERIFY_FAIL + 1))
        fi
    }

    check_import "anthropic"
    check_import "telegram"          "python-telegram-bot"
    check_import "pydantic"
    check_import "aiosqlite"
    check_import "dotenv"            "python-dotenv"
    check_import "loguru"
    check_import "yaml"              "PyYAML"
    check_import "apscheduler"

    # ── 엔진 바이너리 실행 가능 여부 재확인 ─────────────────────────────────────
    echo ""
    info "AI 엔진 바이너리 실행 가능 여부 확인 중..."

    check_engine() {
        local name="$1"
        local path="$2"
        if [ -n "$path" ] && [ -x "$path" ]; then
            ok "  $name: $path [실행 가능]"
            VERIFY_PASS=$((VERIFY_PASS + 1))
        elif [ -n "$path" ]; then
            err "  $name: $path [실행 불가 — 권한 확인 필요]"
            VERIFY_FAIL=$((VERIFY_FAIL + 1))
        fi
    }

    check_engine "claude" "$CLAUDE_PATH"
    check_engine "codex"  "$CODEX_PATH"
    check_engine "gemini" "$GEMINI_CLI_PATH"

    # ── 검증 결과 출력 ────────────────────────────────────────────────────────────
    echo ""
    TOTAL=$((VERIFY_PASS + VERIFY_FAIL))
    if [ "$VERIFY_FAIL" -eq 0 ]; then
        echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
        echo -e "${GREEN}${BOLD}  검증 완료: $VERIFY_PASS/$TOTAL 항목 통과 — 모두 정상${RESET}"
        echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    else
        echo -e "${YELLOW}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
        echo -e "${YELLOW}${BOLD}  검증 결과: $VERIFY_PASS/$TOTAL 통과, ${VERIFY_FAIL}개 실패${RESET}"
        echo -e "${YELLOW}${BOLD}  위 ❌ 항목을 확인하고 재설치 후 다시 실행하세요.${RESET}"
        echo -e "${YELLOW}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    fi
fi

# =============================================================================
# 권한 설정: 실행 파일에 chmod +x 적용
# =============================================================================
step "Step 5.5/5: 실행 파일 권한 설정"

# scripts/*.sh — 모든 셸 스크립트
_chmod_count=0
while IFS= read -r -d '' _sh_file; do
    chmod +x "$_sh_file"
    _chmod_count=$((_chmod_count + 1))
done < <(find "$SCRIPT_DIR" -maxdepth 1 -name "*.sh" -print0 2>/dev/null)
ok "scripts/*.sh → chmod +x 적용 (${_chmod_count}개)"

# tools/*.py — 도구 스크립트
_py_chmod_count=0
if [ -d "$PROJECT_ROOT/tools" ]; then
    while IFS= read -r -d '' _py_file; do
        chmod +x "$_py_file"
        _py_chmod_count=$((_py_chmod_count + 1))
    done < <(find "$PROJECT_ROOT/tools" -maxdepth 1 -name "*.py" -print0 2>/dev/null)
    ok "tools/*.py → chmod +x 적용 (${_py_chmod_count}개)"
fi

# main.py / cli.py (프로젝트 루트 진입점)
for _entry in "$PROJECT_ROOT/main.py" "$PROJECT_ROOT/cli.py"; do
    [ -f "$_entry" ] && chmod +x "$_entry" && info "$(basename "$_entry") → chmod +x"
done

# =============================================================================
# macOS 권한 자동 설정 (quarantine 제거 + TCC 등록 시도)
# =============================================================================
if [ "$OS_NAME" = "macOS" ]; then
    bash "$(dirname "${BASH_SOURCE[0]}")/setup_macos_permissions.sh" || true
fi

# =============================================================================
# STEP 6: Docker 환경 감지 및 실행 옵션 제공
# =============================================================================
step "Step 6/6: Docker 환경 감지"

DOCKER_BIN=""
DOCKER_COMPOSE_BIN=""
DOCKER_AVAILABLE=false

# docker 바이너리 감지
if command -v docker &>/dev/null; then
    DOCKER_BIN=$(command -v docker)
    ok "docker 감지됨: $DOCKER_BIN"
    # docker compose (v2 플러그인) 지원 여부 확인
    if docker compose version &>/dev/null 2>&1; then
        DOCKER_COMPOSE_BIN="docker compose"
        ok "docker compose (v2 플러그인) 지원됨"
        DOCKER_AVAILABLE=true
    elif command -v docker-compose &>/dev/null; then
        DOCKER_COMPOSE_BIN="docker-compose"
        ok "docker-compose (v1 독립 실행) 감지됨: $(command -v docker-compose)"
        DOCKER_AVAILABLE=true
    else
        warn "docker는 있으나 docker compose / docker-compose 미감지"
    fi
else
    info "docker 미감지 — 로컬 직접 실행 모드 사용"
fi

# Docker 실행 분기: --docker 플래그 또는 대화형 선택
if [ "$DOCKER_AVAILABLE" = true ]; then
    _run_docker=false
    if [ "$USE_DOCKER" = true ]; then
        _run_docker=true
        info "--docker 플래그: Docker Compose 자동 실행 모드"
    elif [ "$NON_INTERACTIVE" = false ]; then
        echo ""
        echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
        echo -e "${BOLD}${CYAN}  🐳 Docker Compose로 봇을 실행하시겠습니까?${RESET}"
        echo -e "${CYAN}     (로컬 직접 실행은 'N' — bash scripts/start_all.sh 사용)${RESET}"
        echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
        read -rp "  Docker Compose로 시작? [y/N]: " _docker_ans
        _docker_ans="${_docker_ans:-N}"
        [[ "$_docker_ans" =~ ^[Yy]$ ]] && _run_docker=true
    fi

    if [ "$_run_docker" = true ]; then
        # .env 파일 존재 확인
        if [ ! -f ".env" ]; then
            warn ".env 파일이 없습니다. Docker 실행 전 .env 파일을 설정해주세요."
            warn "  cp .env.example .env && nano .env"
        else
            # 필수 토큰 입력 여부 확인
            _bot_token=$(grep -E "^(TELEGRAM_BOT_TOKEN|PM_BOT_TOKEN)=.+" ".env" 2>/dev/null | head -1 || true)
            if [ -z "$_bot_token" ]; then
                warn "TELEGRAM_BOT_TOKEN / PM_BOT_TOKEN 이 .env에 미설정됩니다."
                warn "  먼저 .env를 편집한 뒤 docker compose를 수동 실행하세요:"
                warn "  nano .env && docker compose --profile claude up -d"
            else
                # 감지된 엔진 기준으로 --profile 결정
                _profiles=""
                [ -n "$CLAUDE_PATH" ] && _profiles="$_profiles --profile claude"
                [ -n "$CODEX_PATH"  ] && _profiles="$_profiles --profile codex"
                [ -n "$GEMINI_CLI_PATH" ] && _profiles="$_profiles --profile gemini"
                # 빌드 후 실행
                echo ""
                info "Docker 이미지 빌드 중... (최초 실행 시 수 분 소요)"
                # shellcheck disable=SC2086
                if $DOCKER_COMPOSE_BIN $(_profiles_arr=($profiles); printf '%s ' "${_profiles_arr[@]}") build --quiet 2>/dev/null || \
                   eval "$DOCKER_COMPOSE_BIN $_profiles build --quiet 2>/dev/null"; then
                    ok "Docker 이미지 빌드 완료"
                    eval "$DOCKER_COMPOSE_BIN $_profiles up -d"
                    ok "Docker Compose 시작 완료"
                    echo ""
                    eval "$DOCKER_COMPOSE_BIN ps"
                    echo ""
                    info "로그 확인: $DOCKER_COMPOSE_BIN logs -f aiorg-pm"
                    info "종료:     $DOCKER_COMPOSE_BIN down"
                else
                    warn "Docker 빌드 실패 — 로컬 직접 실행을 권장합니다: bash scripts/start_all.sh"
                fi
            fi
        fi
    else
        info "Docker 실행 건너뜀 — 로컬 직접 실행: bash scripts/start_all.sh"
        if [ "$DOCKER_AVAILABLE" = true ]; then
            echo ""
            echo -e "  ${CYAN}Docker Compose 실행법 (나중에):${RESET}"
            echo "    # 전체 실행:"
            echo "    docker compose --profile claude --profile codex --profile gemini up -d"
            echo "    # 감지된 엔진만 실행:"
            _p=""
            [ -n "$CLAUDE_PATH" ]       && _p="$_p --profile claude"
            [ -n "$CODEX_PATH"  ]       && _p="$_p --profile codex"
            [ -n "$GEMINI_CLI_PATH" ]   && _p="$_p --profile gemini"
            [ -n "$_p" ] && echo "    docker compose${_p} up -d"
        fi
    fi
else
    info "Docker 미감지 — 로컬 직접 실행: bash scripts/start_all.sh"
    echo -e "  ${CYAN}Docker 설치 방법:${RESET} https://docs.docker.com/get-docker/"
fi

# =============================================================================
# 완료 메시지 + 엔진 요약표
# =============================================================================

# 엔진 감지 요약표 출력
print_engine_summary

echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║                  설치 완료!  다음 단계:                      ║${RESET}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════════╝${RESET}"
echo ""
echo "  1. .env 파일에 Telegram 봇 토큰 입력:"
echo -e "       ${BOLD}nano .env${RESET}"
echo ""
echo "  2. 설치 마법사 실행 (대화형 봇 설정):"
echo -e "       ${BOLD}./.venv/bin/python scripts/setup_wizard.py${RESET}"
echo ""
echo "  3. 모든 봇 시작:"
echo ""
echo -e "     ${BOLD}[로컬 직접 실행]${RESET}"
echo -e "       ${BOLD}bash scripts/start_all.sh${RESET}"
echo ""
if [ "$DOCKER_AVAILABLE" = true ]; then
    echo -e "     ${BOLD}[Docker Compose 실행]${RESET}"
    _p=""
    [ -n "$CLAUDE_PATH" ]     && _p="$_p --profile claude"
    [ -n "$CODEX_PATH"  ]     && _p="$_p --profile codex"
    [ -n "$GEMINI_CLI_PATH" ] && _p="$_p --profile gemini"
    echo -e "       ${BOLD}docker compose${_p} up -d${RESET}   # 감지된 엔진만"
    echo -e "       ${BOLD}docker compose --profile claude --profile codex --profile gemini up -d${RESET}   # 전체"
    echo ""
fi
[ -n "$GEMINI_CLI_PATH" ] && echo -e "  ${CYAN}Gemini CLI 인증 (미인증 시):${RESET} $GEMINI_CLI_PATH auth login"
[ -n "$CODEX_PATH"  ] && echo -e "  ${CYAN}Codex CLI 인증 (미인증 시):${RESET}  codex login"
echo ""
echo -e "  ${CYAN}CI/자동화 환경:${RESET}        bash scripts/setup.sh --yes   (프롬프트 없이 실행)"
echo -e "  ${CYAN}Docker 자동 실행 포함:${RESET} bash scripts/setup.sh --yes --docker"
echo ""

} # end main()

# =============================================================================
# 스크립트 진입점 — main() 호출 (탐지→검증→가이드출력→.env생성 순서 실행)
# =============================================================================
main "$@"
