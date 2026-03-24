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
for arg in "$@"; do
    case "$arg" in
        --skip-verify)                SKIP_VERIFY=true ;;
        --no-venv)                    NO_VENV=true ;;
        --yes|-y|--non-interactive)   NON_INTERACTIVE=true ;;
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
# STEP 1: 3엔진 자동 감지
# =============================================================================
step "Step 1/5: AI 엔진 자동 감지"

CLAUDE_PATH=""
CODEX_PATH=""
GEMINI_PATH=""
DETECTED_ENGINES=()

# claude-code 감지 — which로 경로 확인 후 --version으로 실행 가능 여부 검증
if CLAUDE_PATH=$(which claude 2>/dev/null); then
    _claude_ver=$(claude --version 2>/dev/null | head -1 || echo "버전 확인 불가")
    ok "claude-code 감지됨: $CLAUDE_PATH  ($_claude_ver)"
    DETECTED_ENGINES+=("claude-code")
else
    warn "claude CLI 미감지 (설치: https://claude.ai/code)"
    CLAUDE_PATH=""
fi

# codex 감지 — which로 경로 확인 후 --version으로 실행 가능 여부 검증
if CODEX_PATH=$(which codex 2>/dev/null); then
    _codex_ver=$(codex --version 2>/dev/null | head -1 || echo "버전 확인 불가")
    ok "codex 감지됨:  $CODEX_PATH  ($_codex_ver)"
    DETECTED_ENGINES+=("codex")
else
    warn "codex CLI 미감지 (설치: npm install -g @openai/codex)"
    CODEX_PATH=""
fi

# gemini-cli 감지 — /opt/homebrew/bin/gemini 우선, 이후 PATH 탐색 후 --version 검증
GEMINI_PATH=""
for _g_candidate in "/opt/homebrew/bin/gemini" "$HOME/.local/bin/gemini" "$HOME/bin/gemini"; do
    if [ -x "$_g_candidate" ]; then
        GEMINI_PATH="$_g_candidate"
        break
    fi
done
if [ -z "$GEMINI_PATH" ]; then
    GEMINI_PATH=$(which gemini 2>/dev/null) || true
fi
if [ -n "$GEMINI_PATH" ]; then
    _gemini_ver=$("$GEMINI_PATH" --version 2>/dev/null | head -1 || echo "버전 확인 불가")
    ok "gemini-cli 감지됨: $GEMINI_PATH  ($_gemini_ver)"
    DETECTED_ENGINES+=("gemini-cli")
else
    warn "gemini CLI 미감지. 설치 방법:"
    if [ "$OS_NAME" = "macOS" ]; then
        echo "    macOS:  brew install gemini-cli"
        echo "            또는 npm install -g @google/gemini-cli"
    else
        echo "    Linux:  npm install -g @google/gemini-cli"
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
if [ -n "$GEMINI_PATH" ]; then
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
                if [ -n "$GEMINI_PATH" ] && [ -x "$GEMINI_PATH" ]; then
                    info "  → 인증 명령: $GEMINI_PATH auth login"
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

    # CLAUDE_CLI_PATH 자동 치환
    if [ -n "$CLAUDE_PATH" ]; then
        _sed_inplace "s|CLAUDE_CLI_PATH=.*|CLAUDE_CLI_PATH=$CLAUDE_PATH|"
        info "CLAUDE_CLI_PATH → $CLAUDE_PATH (자동 설정)"
    fi

    # CODEX_CLI_PATH 자동 치환
    if [ -n "$CODEX_PATH" ]; then
        _sed_inplace "s|CODEX_CLI_PATH=.*|CODEX_CLI_PATH=$CODEX_PATH|"
        info "CODEX_CLI_PATH → $CODEX_PATH (자동 설정)"
    fi

    # GEMINI_CLI_PATH 자동 치환
    if [ -n "$GEMINI_PATH" ]; then
        _sed_inplace "s|GEMINI_CLI_PATH=.*|GEMINI_CLI_PATH=$GEMINI_PATH|"
        info "GEMINI_CLI_PATH → $GEMINI_PATH (자동 설정)"
        # GEMINI_CLI_DEFAULT_TIMEOUT_SEC 이 미설정이면 기본값 주입
        if grep -q "^GEMINI_CLI_DEFAULT_TIMEOUT_SEC=$" "$env_file" 2>/dev/null; then
            _sed_inplace "s|^GEMINI_CLI_DEFAULT_TIMEOUT_SEC=$|GEMINI_CLI_DEFAULT_TIMEOUT_SEC=1800|"
            info "GEMINI_CLI_DEFAULT_TIMEOUT_SEC → 1800 (기본값 자동 설정)"
        fi
    fi

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
}

# =============================================================================
# STEP 4: .env 파일 처리
# =============================================================================
step "Step 4/5: 환경 변수 파일 설정"

ENV_FILE=".env"
ENV_EXAMPLE=".env.example"

if [ ! -f "$ENV_EXAMPLE" ]; then
    err ".env.example 파일이 없습니다. 저장소가 완전히 클론되었는지 확인하세요."
    exit 1
fi

if [ -f "$ENV_FILE" ]; then
    ok ".env 파일 이미 존재 — 덮어쓰기 건너뜀"
    ENV_EXISTS=true
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
    [ -n "$GEMINI_PATH" ] && echo "    # Gemini: gemini auth login 실행 필요 (~/.gemini/oauth_creds.json)"
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
    check_engine "gemini" "$GEMINI_PATH"

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
# 완료 메시지
# =============================================================================
echo ""
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
echo -e "       ${BOLD}bash scripts/start_all.sh${RESET}"
echo ""
[ -n "$GEMINI_PATH" ] && echo -e "  ${CYAN}Gemini CLI 인증 (미인증 시):${RESET} $GEMINI_PATH auth login"
[ -n "$CODEX_PATH"  ] && echo -e "  ${CYAN}Codex CLI 인증 (미인증 시):${RESET}  codex login"
echo ""
echo -e "  ${CYAN}CI/자동화 환경:${RESET} bash scripts/setup.sh --yes  (프롬프트 없이 실행)"
echo ""
info "선택된 기본 엔진: ${BOLD}$SELECTED_ENGINE${RESET}"
echo ""
