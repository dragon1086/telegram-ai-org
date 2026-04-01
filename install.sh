#!/usr/bin/env bash
# =============================================================================
# install.sh — telegram-ai-org 원클릭 셋업 스크립트 (프로젝트 루트 진입점)
#
# 이 스크립트가 정식 원클릭 설치 진입점입니다.
# 고급 옵션(Docker Compose, 자동 엔진 설치, 대화형 토큰 수집)은
# bash scripts/setup.sh 를 사용하세요.
#
# 실행 흐름:
#   ① 3엔진 자동 감지   (claude-code / codex / gemini-cli)
#   ② .env 자동 생성    (.env.example 템플릿 기반 + ENGINE 경로 자동 주입)
#   ③ 의존성 자동 설치  (Python venv + pip / npm 존재 여부 확인)
#   ④ 헬스체크          (엔진 --version + Python import → ✅/❌ 출력)
#   ⑤ 봇 자동 기동      (--start 플래그 사용 시, 헬스체크 전 통과 조건)
#
# 사용법:
#   bash install.sh                   # 기본 설치 (대화형)
#   bash install.sh --yes             # 비대화형 자동 설치 (CI 환경)
#   bash install.sh --no-venv         # 가상환경 생성 건너뜀
#   bash install.sh --skip-verify     # 헬스체크 단계 건너뜀
#   bash install.sh --health-only     # 헬스체크만 실행 (설치 없음)
#   bash install.sh --start           # 헬스체크 통과 후 봇 자동 기동
#   bash install.sh --yes --start     # CI 환경 + 봇 자동 기동
#   bash install.sh --quickstart      # 초보자용 간편 설치 (quickstart.sh 호출)
#
# 설계 문서: docs/INSTALL_FLOW.md
# =============================================================================

set -euo pipefail

# ── 색상 정의 ──────────────────────────────────────────────────────────────────
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
NO_VENV=false
NON_INTERACTIVE=false
SKIP_VERIFY=false
HEALTH_ONLY=false
AUTO_START=false

for arg in "$@"; do
    case "$arg" in
        --no-venv)                    NO_VENV=true ;;
        --yes|-y|--non-interactive)   NON_INTERACTIVE=true ;;
        --skip-verify)                SKIP_VERIFY=true ;;
        --health-only)                HEALTH_ONLY=true; SKIP_VERIFY=false ;;
        --start)                      AUTO_START=true ;;
        --quickstart)
            echo "→ 초보자용 간편 설치로 전환합니다..."
            exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/quickstart.sh"
            ;;
    esac
done

# ── 프로젝트 루트 설정 ─────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
cd "$PROJECT_ROOT"

if [ ! -f "pyproject.toml" ] && [ ! -f ".env.example" ]; then
    err "프로젝트 루트를 찾을 수 없습니다: $PROJECT_ROOT"
    err "telegram-ai-org 리포지토리 루트에서 실행해주세요."
    exit 1
fi

# ── OS 감지 ────────────────────────────────────────────────────────────────────
OS_TYPE="$(uname -s)"
case "$OS_TYPE" in
    Darwin) OS_NAME="macOS" ;;
    Linux)  OS_NAME="Linux" ;;
    *)      OS_NAME="Unknown ($OS_TYPE)" ;;
esac

echo -e "${BOLD}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     telegram-ai-org — install.sh 원클릭 셋업 스크립트       ║"
echo "║     3-Engine Auto-Detect: claude-code / codex / gemini-cli  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${RESET}"
info "OS: $OS_NAME  |  프로젝트 루트: $PROJECT_ROOT"
[ "$HEALTH_ONLY" = true ] && info "모드: --health-only (헬스체크만 실행)"

# =============================================================================
# ① STEP 1: 3엔진 자동 감지
# =============================================================================
step "① 3엔진 자동 감지"

CLAUDE_PATH=""
CODEX_PATH=""
GEMINI_CLI_PATH_DETECTED=""
DETECTED_ENGINES=()

# ── claude-code 감지 ──────────────────────────────────────────────────────────
# 우선순위: ~/.local/bin/claude → ~/bin/claude → /opt/homebrew/bin/claude
#           → /usr/local/bin/claude → PATH (command -v)
for _c in "$HOME/.local/bin/claude" "$HOME/bin/claude" \
          "/opt/homebrew/bin/claude" "/usr/local/bin/claude"; do
    [ -x "$_c" ] && CLAUDE_PATH="$_c" && break
done
[ -z "$CLAUDE_PATH" ] && CLAUDE_PATH=$(command -v claude 2>/dev/null || true)

if [ -n "$CLAUDE_PATH" ]; then
    _cv=$("$CLAUDE_PATH" --version 2>/dev/null | head -1 || echo "버전 확인 불가")
    ok "claude-code  감지됨: $CLAUDE_PATH  ($_cv)"
    DETECTED_ENGINES+=("claude-code")
else
    warn "claude-code  미감지 → 설치: npm install -g @anthropic-ai/claude-code"
fi

# ── codex 감지 ────────────────────────────────────────────────────────────────
# 우선순위: ~/.local/bin/codex → ~/bin/codex → /opt/homebrew/bin/codex
#           → /usr/local/bin/codex → PATH (command -v)
for _d in "$HOME/.local/bin/codex" "$HOME/bin/codex" \
          "/opt/homebrew/bin/codex" "/usr/local/bin/codex"; do
    [ -x "$_d" ] && CODEX_PATH="$_d" && break
done
[ -z "$CODEX_PATH" ] && CODEX_PATH=$(command -v codex 2>/dev/null || true)

if [ -n "$CODEX_PATH" ]; then
    _dv=$("$CODEX_PATH" --version 2>/dev/null | head -1 || echo "버전 확인 불가")
    ok "codex        감지됨: $CODEX_PATH  ($_dv)"
    DETECTED_ENGINES+=("codex")
else
    warn "codex        미감지 → 설치: npm install -g @openai/codex"
fi

# ── gemini-cli 감지 ───────────────────────────────────────────────────────────
# 우선순위: /opt/homebrew/bin/gemini → ~/.local/bin/gemini → ~/bin/gemini → PATH
for _g in "/opt/homebrew/bin/gemini" "$HOME/.local/bin/gemini" "$HOME/bin/gemini"; do
    [ -x "$_g" ] && GEMINI_CLI_PATH_DETECTED="$_g" && break
done
[ -z "$GEMINI_CLI_PATH_DETECTED" ] && \
    GEMINI_CLI_PATH_DETECTED=$(command -v gemini 2>/dev/null || true)

if [ -n "$GEMINI_CLI_PATH_DETECTED" ]; then
    _gv=$("$GEMINI_CLI_PATH_DETECTED" --version 2>/dev/null | head -1 || echo "버전 확인 불가")
    ok "gemini-cli   감지됨: $GEMINI_CLI_PATH_DETECTED  ($_gv)"
    DETECTED_ENGINES+=("gemini-cli")
else
    warn "gemini-cli   미감지 → 설치: brew install gemini-cli  (또는 npm install -g @google/gemini-cli)"
fi

# ── 감지 결과 요약 ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}── 엔진 감지 요약 ──────────────────────────────────────────────${RESET}"
_engine_col() {
    local name="$1" path="$2"
    if [ -n "$path" ]; then
        printf "  ${GREEN}✅${RESET} %-14s %s\n" "$name" "$path"
    else
        printf "  ${YELLOW}⬜${RESET} %-14s %s\n" "$name" "(미감지)"
    fi
}
_engine_col "claude-code"  "$CLAUDE_PATH"
_engine_col "codex"        "$CODEX_PATH"
_engine_col "gemini-cli"   "$GEMINI_CLI_PATH_DETECTED"
echo -e "${BOLD}${CYAN}────────────────────────────────────────────────────────────────${RESET}"

if [ ${#DETECTED_ENGINES[@]} -eq 0 ]; then
    err "엔진이 하나도 감지되지 않았습니다. 최소 1개 엔진을 설치하세요."
    if [ "$HEALTH_ONLY" = false ]; then exit 1; fi
else
    ok "감지된 엔진 (${#DETECTED_ENGINES[@]}개): ${DETECTED_ENGINES[*]}"
fi

# ── 기본 엔진 선택 (claude-code 우선, 없으면 감지 순서 첫 번째) ────────────────
SELECTED_ENGINE=""
if [ ${#DETECTED_ENGINES[@]} -gt 0 ]; then
    SELECTED_ENGINE="${DETECTED_ENGINES[0]}"
    for _e in "${DETECTED_ENGINES[@]}"; do
        [ "$_e" = "claude-code" ] && SELECTED_ENGINE="claude-code" && break
    done
    info "기본 엔진 선택: $SELECTED_ENGINE (텔레그램에서 /set_engine 으로 변경 가능)"
fi

# =============================================================================
# ② STEP 2: .env 자동 생성  (--health-only 시 건너뜀)
# =============================================================================
if [ "$HEALTH_ONLY" = false ]; then
    step "② .env 자동 생성"

    ENV_FILE=".env"
    ENV_EXAMPLE=".env.example"

    if [ ! -f "$ENV_EXAMPLE" ]; then
        err ".env.example 파일이 없습니다. 리포지토리를 올바르게 클론했는지 확인하세요."
        exit 1
    fi

    if [ -f "$ENV_FILE" ]; then
        ok ".env 이미 존재 — 기존 설정 유지 (ENGINE 변수 및 CLI 경로만 갱신)"
    else
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        ok ".env.example → .env 복사 완료"
    fi

    # ── OS별 sed 헬퍼 ───────────────────────────────────────────────────────────
    _sed_env() {
        if [ "$OS_NAME" = "macOS" ]; then
            sed -i '' "$1" "$ENV_FILE"
        else
            sed -i "$1" "$ENV_FILE"
        fi
    }

    # _set_or_append: 키가 있으면 sed 치환, 없으면 파일 끝에 추가
    _set_or_append() {
        local key="$1" val="$2"
        if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
            _sed_env "s|^${key}=.*|${key}=${val}|"
        else
            echo "${key}=${val}" >> "$ENV_FILE"
        fi
    }

    # ENGINE 변수 자동 주입 (감지된 엔진 기준)
    if [ -n "$SELECTED_ENGINE" ]; then
        _set_or_append "AI_ENGINE"      "$SELECTED_ENGINE"
        _set_or_append "DEFAULT_ENGINE" "$SELECTED_ENGINE"
        _set_or_append "ENGINE"         "$SELECTED_ENGINE"
        _set_or_append "ACTIVE_ENGINE"  "$SELECTED_ENGINE"
        ok "ENGINE 변수 자동 설정: $SELECTED_ENGINE  (AI_ENGINE / DEFAULT_ENGINE / ENGINE / ACTIVE_ENGINE)"
    fi

    # CLI 경로 자동 주입
    if [ -n "$CLAUDE_PATH" ]; then
        _set_or_append "CLAUDE_CLI_PATH" "$CLAUDE_PATH"
        info "CLAUDE_CLI_PATH → $CLAUDE_PATH"
    fi
    if [ -n "$CODEX_PATH" ]; then
        _set_or_append "CODEX_CLI_PATH" "$CODEX_PATH"
        info "CODEX_CLI_PATH  → $CODEX_PATH"
    fi
    if [ -n "$GEMINI_CLI_PATH_DETECTED" ]; then
        _set_or_append "GEMINI_CLI_PATH" "$GEMINI_CLI_PATH_DETECTED"
        info "GEMINI_CLI_PATH → $GEMINI_CLI_PATH_DETECTED"
        # GEMINI_CLI_DEFAULT_TIMEOUT_SEC 미설정 시 기본값 주입
        if grep -q "^GEMINI_CLI_DEFAULT_TIMEOUT_SEC=$" "$ENV_FILE" 2>/dev/null; then
            _sed_env "s|^GEMINI_CLI_DEFAULT_TIMEOUT_SEC=$|GEMINI_CLI_DEFAULT_TIMEOUT_SEC=1800|"
            info "GEMINI_CLI_DEFAULT_TIMEOUT_SEC → 1800 (기본값)"
        fi
    fi

    echo ""
    warn "아래 항목은 .env 에서 직접 입력이 필요합니다:"
    echo "    TELEGRAM_BOT_TOKEN=      # PM 봇 토큰 (@BotFather)"
    echo "    TELEGRAM_GROUP_CHAT_ID=  # 그룹 채팅 ID (음수, 예: -100xxxxxxxxxx)"
    echo "    + 부서 봇 토큰 (BOT_TOKEN_AIORG_*)"
    echo -e "  편집: ${BOLD}nano .env${RESET}  또는  ${BOLD}code .env${RESET}"
fi

# =============================================================================
# ③ STEP 3: 의존성 자동 설치  (--health-only 시 건너뜀)
# =============================================================================
VENV_PYTHON=""   # Step 4 (헬스체크)에서도 사용

if [ "$HEALTH_ONLY" = false ]; then
    step "③ 의존성 자동 설치"

    # Python 3.10+ 탐색 (높은 버전 우선; Homebrew/pyenv 경로 포함)
    PYTHON_BIN=""
    _py_candidates=(
        python3.14 python3.13 python3.12 python3.11 python3.10
        /opt/homebrew/bin/python3.14 /opt/homebrew/bin/python3.13
        /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11
        /usr/local/bin/python3.12 /usr/local/bin/python3.11
        "$HOME/.pyenv/shims/python3" python3
    )
    for _py in "${_py_candidates[@]}"; do
        if command -v "$_py" &>/dev/null || [ -x "$_py" ]; then
            _ver=$("$_py" --version 2>&1 | awk '{print $2}')
            _major=$(echo "$_ver" | cut -d. -f1)
            _minor=$(echo "$_ver" | cut -d. -f2)
            if [ "$_major" -ge 3 ] && [ "$_minor" -ge 10 ]; then
                PYTHON_BIN="$_py"
                break
            fi
        fi
    done

    if [ -z "$PYTHON_BIN" ]; then
        _sys_ver=$(python3 --version 2>&1 | awk '{print $2}' 2>/dev/null || echo "미설치")
        err "Python 3.10+ 를 찾을 수 없습니다 (시스템: $_sys_ver)"
        case "$OS_NAME" in
            macOS) err "설치: brew install python@3.11" ;;
            Linux) err "설치: sudo apt-get install python3.11" ;;
        esac
        exit 1
    fi
    ok "Python $("$PYTHON_BIN" --version 2>&1 | awk '{print $2}') ($PYTHON_BIN)"

    # ── 가상환경 생성 ──────────────────────────────────────────────────────────
    VENV_DIR=".venv"
    if [ "$NO_VENV" = false ]; then
        if [ ! -x "$VENV_DIR/bin/python" ]; then
            info "가상환경 생성 중: $VENV_DIR/  ($PYTHON_BIN 사용)"
            "$PYTHON_BIN" -m venv "$VENV_DIR"
            ok "가상환경 생성 완료: $VENV_DIR/"
        else
            _venv_ver=$("$VENV_DIR/bin/python" --version 2>&1 | awk '{print $2}')
            ok "가상환경 이미 존재: $VENV_DIR/ (Python $_venv_ver)"
        fi
        VENV_PYTHON="$VENV_DIR/bin/python"
    else
        warn "--no-venv: 가상환경 생성 건너뜀 (시스템 Python 사용)"
        VENV_PYTHON="$PYTHON_BIN"
    fi

    # ── pip 업그레이드 ─────────────────────────────────────────────────────────
    "$VENV_PYTHON" -m pip install --upgrade pip --quiet
    ok "pip 최신 버전으로 업그레이드"

    # ── pyproject.toml 의존성 설치 ────────────────────────────────────────────
    info "pyproject.toml 의존성 설치 중..."
    if "$VENV_PYTHON" -m pip install -e ".[dev]" --quiet 2>/dev/null; then
        ok "pip install -e .[dev] 완료 (editable 모드)"
    else
        warn "editable 설치 실패 — 핵심 패키지 직접 설치 시도"
        if [ -f "requirements.txt" ]; then
            info "requirements.txt 설치 중..."
            "$VENV_PYTHON" -m pip install -r requirements.txt --quiet \
                && ok "requirements.txt 설치 완료" \
                || warn "requirements.txt 일부 실패 — 수동 확인 필요"
        else
            # 최소 핵심 패키지 직접 설치
            "$VENV_PYTHON" -m pip install --quiet \
                "python-telegram-bot>=22.0" "pydantic>=2.0" "aiosqlite>=0.19" \
                "httpx>=0.25" "python-dotenv>=1.0" "loguru>=0.7" \
                "anthropic>=0.80" "openai>=2.0" "PyYAML>=6.0" \
                "apscheduler>=3.10" && ok "핵심 패키지 설치 완료"
        fi
    fi

    # ── gemini-cli 감지 시 google-genai 추가 설치 ─────────────────────────────
    if [ -n "$GEMINI_CLI_PATH_DETECTED" ]; then
        if ! "$VENV_PYTHON" -c "import google.genai" 2>/dev/null; then
            info "google-genai SDK 설치 중 (gemini-cli 감지됨)..."
            "$VENV_PYTHON" -m pip install google-genai --quiet \
                && ok "google-genai 설치 완료"
        else
            ok "google-genai 이미 설치됨"
        fi
    fi

    # ── Node.js / npm 확인 ────────────────────────────────────────────────────
    echo ""
    if command -v node &>/dev/null && command -v npm &>/dev/null; then
        _node_ver=$(node --version)
        _npm_ver=$(npm --version)
        _node_major=$(echo "$_node_ver" | sed 's/v//' | cut -d. -f1)
        if [ "$_node_major" -ge 18 ]; then
            ok "Node.js $_node_ver / npm $_npm_ver (18+ 요구사항 충족)"
        else
            warn "Node.js $_node_ver 감지 — 18+ 필요 (엔진 설치 시 업그레이드 권장)"
        fi
    else
        warn "Node.js / npm 미감지 — 엔진 CLI 설치 시 필요: https://nodejs.org"
    fi

    # ── 필요 디렉토리 생성 ────────────────────────────────────────────────────
    mkdir -p ~/.ai-org/workspace logs data reports
    ok "작업 디렉토리 준비: ~/.ai-org/workspace  logs/  data/  reports/"

    # ── 실행 권한 설정 ─────────────────────────────────────────────────────────
    find "$PROJECT_ROOT/scripts" -maxdepth 1 -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true
    chmod +x "$PROJECT_ROOT/install.sh"
    ok "scripts/*.sh + install.sh → chmod +x 완료"

else
    # --health-only: venv python 탐색 (기존 .venv 우선)
    if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
        VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
        info "기존 venv 감지: $VENV_PYTHON"
    else
        VENV_PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)
        [ -n "$VENV_PYTHON" ] && info "시스템 Python 사용: $VENV_PYTHON"
    fi
fi

# =============================================================================
# ④ STEP 4: 헬스체크  (--skip-verify 시 건너뜀)
# =============================================================================
if [ "$SKIP_VERIFY" = true ]; then
    warn "--skip-verify: 헬스체크 단계 건너뜀"
else
    step "④ 헬스체크"

    HC_PASS=0
    HC_FAIL=0

    _hc_ok()   { echo -e "  ${GREEN}✅ $*${RESET}";  HC_PASS=$((HC_PASS + 1)); }
    _hc_fail() { echo -e "  ${RED}❌ $*${RESET}";   HC_FAIL=$((HC_FAIL + 1)); }
    _hc_skip() { echo -e "  ${YELLOW}⬜ $*${RESET} (미감지 — 건너뜀)"; }

    # ── 엔진 헬스체크 ──────────────────────────────────────────────────────────
    echo ""
    echo -e "${BOLD}${CYAN}── 엔진 헬스체크 ────────────────────────────────────────────────${RESET}"

    # claude-code
    if [ -n "$CLAUDE_PATH" ] && [ -x "$CLAUDE_PATH" ]; then
        _cv=$("$CLAUDE_PATH" --version 2>/dev/null | head -1 || true)
        if [ -n "$_cv" ]; then
            _hc_ok "claude-code  [$CLAUDE_PATH]  → $_cv"
        else
            _hc_fail "claude-code  [$CLAUDE_PATH]  → --version 응답 없음"
        fi
    else
        _hc_skip "claude-code"
    fi

    # ── Node.js 기반 CLI 공통 helper ─────────────────────────────────────────
    # codex / gemini-cli 는 Node.js 런타임 필요 → node 미감지 시 ⚠️ 진단
    _NODE_IN_PATH=$(command -v node 2>/dev/null || true)

    # codex
    if [ -n "$CODEX_PATH" ] && [ -x "$CODEX_PATH" ]; then
        _dv=$("$CODEX_PATH" --version 2>/dev/null | head -1 || true)
        if [ -n "$_dv" ]; then
            _hc_ok "codex        [$CODEX_PATH]  → $_dv"
        elif [ -z "$_NODE_IN_PATH" ]; then
            _hc_fail "codex        [$CODEX_PATH]  → Node.js 미감지 (node not in PATH) — brew install node"
        else
            _hc_fail "codex        [$CODEX_PATH]  → --version 응답 없음"
        fi
    else
        _hc_skip "codex"
    fi

    # gemini-cli
    if [ -n "$GEMINI_CLI_PATH_DETECTED" ] && [ -x "$GEMINI_CLI_PATH_DETECTED" ]; then
        _gv=$("$GEMINI_CLI_PATH_DETECTED" --version 2>/dev/null | head -1 || true)
        if [ -n "$_gv" ]; then
            _hc_ok "gemini-cli   [$GEMINI_CLI_PATH_DETECTED]  → $_gv"
        elif [ -z "$_NODE_IN_PATH" ]; then
            _hc_fail "gemini-cli   [$GEMINI_CLI_PATH_DETECTED]  → Node.js 미감지 (node not in PATH) — brew install node"
        else
            _hc_fail "gemini-cli   [$GEMINI_CLI_PATH_DETECTED]  → --version 응답 없음"
        fi
    else
        _hc_skip "gemini-cli"
    fi

    # ── Python 패키지 헬스체크 ────────────────────────────────────────────────
    echo ""
    echo -e "${BOLD}${CYAN}── Python 패키지 헬스체크 ───────────────────────────────────────${RESET}"

    if [ -z "$VENV_PYTHON" ]; then
        warn "Python 인터프리터 미감지 — 패키지 헬스체크 건너뜀"
    else
        info "Python: $VENV_PYTHON  ($("$VENV_PYTHON" --version 2>&1 | awk '{print $2}'))"
        echo ""

        _pycheck() {
            local pkg="$1" label="${2:-$1}"
            if "$VENV_PYTHON" -c "import $pkg" 2>/dev/null; then
                _hc_ok "import $label"
            else
                _hc_fail "import $label  →  pip install $pkg"
            fi
        }

        _pycheck "anthropic"
        _pycheck "telegram"       "python-telegram-bot (telegram)"
        _pycheck "pydantic"
        _pycheck "aiosqlite"
        _pycheck "dotenv"         "python-dotenv (dotenv)"
        _pycheck "loguru"
        _pycheck "yaml"           "PyYAML (yaml)"
        _pycheck "apscheduler"

        # gemini-cli 감지 시 google-genai 추가 확인
        [ -n "$GEMINI_CLI_PATH_DETECTED" ] && _pycheck "google.genai" "google-genai (google.genai)"
    fi

    # ── 헬스체크 결과 요약 ────────────────────────────────────────────────────
    echo ""
    TOTAL=$((HC_PASS + HC_FAIL))
    echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    if [ "$HC_FAIL" -eq 0 ]; then
        echo -e "${GREEN}${BOLD}  헬스체크 결과: ✅ $HC_PASS/$TOTAL 모두 정상${RESET}"
    else
        echo -e "${YELLOW}${BOLD}  헬스체크 결과: ✅ $HC_PASS/$TOTAL 통과  ❌ ${HC_FAIL}개 실패${RESET}"
        echo -e "${YELLOW}  위 ❌ 항목을 확인한 뒤 install.sh 를 다시 실행하세요.${RESET}"
    fi
    echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

    # ── --start 플래그: 헬스체크 전 통과 시 봇 자동 기동 ─────────────────────────
    if [ "$AUTO_START" = true ]; then
        if [ "$HC_FAIL" -eq 0 ]; then
            echo ""
            step "⑤ 봇 자동 기동 (--start 플래그)"
            START_SH="$PROJECT_ROOT/scripts/start_all.sh"
            if [ -f "$START_SH" ]; then
                ok "헬스체크 전 통과 — 봇 기동 시작"
                info "실행: bash $START_SH"
                bash "$START_SH"
            elif [ -f "$PROJECT_ROOT/main.py" ] && [ -n "$VENV_PYTHON" ]; then
                ok "헬스체크 전 통과 — python main.py 실행"
                info "실행: $VENV_PYTHON $PROJECT_ROOT/main.py"
                "$VENV_PYTHON" "$PROJECT_ROOT/main.py"
            else
                warn "--start 플래그 사용 중이나 기동 스크립트를 찾을 수 없습니다."
                warn "수동으로 실행하세요: bash scripts/start_all.sh"
            fi
        else
            warn "--start 플래그가 있으나 헬스체크 ❌ ${HC_FAIL}개 실패 — 봇 기동 건너뜀"
            warn "위 ❌ 항목을 수정한 뒤 'bash install.sh --start' 재실행하세요."
        fi
    fi
fi

# =============================================================================
# 완료 요약
# =============================================================================
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════════╗${RESET}"
if [ "$HEALTH_ONLY" = true ]; then
    echo -e "${BOLD}${GREEN}║  install.sh --health-only 완료                               ║${RESET}"
else
    echo -e "${BOLD}${GREEN}║  install.sh 완료 — 다음 단계를 진행하세요                   ║${RESET}"
fi
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════════╝${RESET}"
echo ""

if [ "$HEALTH_ONLY" = false ]; then
    echo -e "${BOLD}  다음 단계:${RESET}"
    echo -e "  1. ${BOLD}nano .env${RESET}"
    echo "        TELEGRAM_BOT_TOKEN=     ← PM 봇 토큰 (@BotFather)"
    echo "        TELEGRAM_GROUP_CHAT_ID= ← 그룹 채팅 ID"
    echo "        + 부서 봇 토큰 (BOT_TOKEN_AIORG_*)"
    echo ""
    [ -n "$CLAUDE_PATH" ] && echo -e "  2. claude 첫 실행 → 브라우저 OAuth 인증 자동 진행"
    [ -n "$GEMINI_CLI_PATH_DETECTED" ] && \
        echo -e "  2. ${BOLD}$GEMINI_CLI_PATH_DETECTED auth login${RESET}  → Google 계정 인증"
    [ -n "$CODEX_PATH" ] && \
        echo -e "  2. ${BOLD}$CODEX_PATH login${RESET}  → OpenAI 계정 인증"
    echo ""
    echo -e "  3. ${BOLD}bash scripts/start_all.sh${RESET}  → 모든 봇 실행"
    echo ""
    info "고급 옵션 (Docker / 엔진 자동 설치 / 대화형): bash scripts/setup.sh [--docker] [--yes]"
fi
