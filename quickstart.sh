#!/usr/bin/env bash
# =============================================================================
# quickstart.sh — 완전 초보자를 위한 초간단 설치
#
# 목표: "딸깍 한 번"에 최대한 자동 설정
# 사용자가 입력할 것: Telegram 봇 토큰 1개 + 그룹 Chat ID 1개 (둘 다 선택사항)
#
# 사용법:
#   bash quickstart.sh
# =============================================================================

set -euo pipefail

# ── 색상 ─────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; MAGENTA='\033[0;35m'
BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

ok()   { echo -e "  ${GREEN}✅ $*${RESET}"; }
warn() { echo -e "  ${YELLOW}⚠️  $*${RESET}"; }
err()  { echo -e "  ${RED}❌ $*${RESET}"; }
info() { echo -e "  ${CYAN}ℹ️  $*${RESET}"; }

# ── 프로젝트 루트 ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f "pyproject.toml" ] && [ ! -f ".env.example" ]; then
    err "telegram-ai-org 프로젝트 폴더에서 실행해주세요."
    exit 1
fi

# ── OS 감지 ──────────────────────────────────────────────────────────────────
OS_TYPE="$(uname -s)"
case "$OS_TYPE" in
    Darwin) OS_NAME="macOS" ;;
    Linux)  OS_NAME="Linux" ;;
    *)      OS_NAME="$OS_TYPE" ;;
esac

# =============================================================================
# 환영 배너
# =============================================================================
clear 2>/dev/null || true
echo ""
echo -e "${BOLD}${CYAN}"
echo "  ╔═══════════════════════════════════════════════════════╗"
echo "  ║                                                       ║"
echo "  ║   🤖 telegram-ai-org 퀵스타트                        ║"
echo "  ║                                                       ║"
echo "  ║   AI 조직 봇을 가장 쉽게 설치하는 방법               ║"
echo "  ║   대부분 자동으로 설정됩니다                          ║"
echo "  ║                                                       ║"
echo "  ╚═══════════════════════════════════════════════════════╝"
echo -e "${RESET}"
echo ""

# =============================================================================
# STEP 1: 사전 요구사항 자동 점검
# =============================================================================
echo -e "${BOLD}${BLUE}  [1/4] 환경 점검 중...${RESET}"
echo ""

PREFLIGHT_OK=true

# ── Python 점검 ──────────────────────────────────────────────────────────────
PYTHON_BIN=""
for _py in python3.14 python3.13 python3.12 python3.11 python3.10 \
           /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 \
           /opt/homebrew/bin/python3.11 /usr/local/bin/python3.12 \
           /usr/local/bin/python3.11 python3; do
    if command -v "$_py" &>/dev/null || [ -x "$_py" 2>/dev/null ]; then
        _ver=$("$_py" --version 2>&1 | awk '{print $2}')
        _major=$(echo "$_ver" | cut -d. -f1)
        _minor=$(echo "$_ver" | cut -d. -f2)
        if [ "$_major" -ge 3 ] && [ "$_minor" -ge 10 ]; then
            PYTHON_BIN="$_py"
            break
        fi
    fi
done

if [ -n "$PYTHON_BIN" ]; then
    ok "Python $("$PYTHON_BIN" --version 2>&1 | awk '{print $2}')"
else
    err "Python 3.10 이상이 필요합니다"
    echo ""
    echo -e "  ${BOLD}설치 방법:${RESET}"
    case "$OS_NAME" in
        macOS)
            echo -e "    ${CYAN}brew install python@3.12${RESET}"
            echo -e "    ${DIM}(Homebrew 없으면: https://brew.sh 에서 먼저 설치)${RESET}"
            ;;
        Linux)
            echo -e "    ${CYAN}sudo apt install python3.12 python3.12-venv${RESET}  (Ubuntu/Debian)"
            echo -e "    ${CYAN}sudo dnf install python3.12${RESET}                  (Fedora/RHEL)"
            ;;
    esac
    echo ""
    echo -e "  설치 후 다시 실행: ${BOLD}bash quickstart.sh${RESET}"
    exit 1
fi

# ── Node.js 점검 ─────────────────────────────────────────────────────────────
if command -v node &>/dev/null; then
    _node_ver=$(node --version)
    _node_major=$(echo "$_node_ver" | sed 's/v//' | cut -d. -f1)
    if [ "$_node_major" -ge 18 ]; then
        ok "Node.js $_node_ver"
    else
        warn "Node.js $_node_ver (18+ 권장) — AI 엔진 CLI 설치에 필요"
        echo -e "    ${CYAN}업그레이드: https://nodejs.org${RESET}"
    fi
else
    warn "Node.js 미감지 — AI 엔진이 이미 설치되어 있다면 무시해도 됩니다"
    echo -e "    ${DIM}없으면: https://nodejs.org 에서 LTS 버전 설치${RESET}"
fi

# ── AI 엔진 점검 ─────────────────────────────────────────────────────────────
ENGINE_COUNT=0
CLAUDE_PATH=$(command -v claude 2>/dev/null || true)
CODEX_PATH=$(command -v codex 2>/dev/null || true)
GEMINI_PATH=$(command -v gemini 2>/dev/null || true)

[ -n "$CLAUDE_PATH" ] && { ok "Claude Code 감지됨"; ENGINE_COUNT=$((ENGINE_COUNT + 1)); }
[ -n "$CODEX_PATH" ]  && { ok "Codex 감지됨";      ENGINE_COUNT=$((ENGINE_COUNT + 1)); }
[ -n "$GEMINI_PATH" ] && { ok "Gemini CLI 감지됨";  ENGINE_COUNT=$((ENGINE_COUNT + 1)); }

if [ "$ENGINE_COUNT" -eq 0 ]; then
    warn "AI 엔진이 감지되지 않았습니다"
    echo ""
    echo -e "  ${BOLD}최소 1개를 설치하세요:${RESET}"
    echo -e "    ${CYAN}npm install -g @anthropic-ai/claude-code${RESET}  (Claude)"
    echo -e "    ${CYAN}npm install -g @openai/codex${RESET}              (Codex)"
    echo -e "    ${CYAN}npm install -g @google/gemini-cli${RESET}         (Gemini)"
    echo ""
    echo -e "  설치 후 다시 실행: ${BOLD}bash quickstart.sh${RESET}"
    exit 1
fi

echo ""
ok "환경 점검 완료 (엔진 ${ENGINE_COUNT}개 감지)"
echo ""

# =============================================================================
# STEP 2: Telegram 봇 정보 입력 (인라인 가이드 포함)
# =============================================================================
echo -e "${BOLD}${BLUE}  [2/4] Telegram 봇 설정${RESET}"
echo ""

# ── 구조 설명 ────────────────────────────────────────────────────────────────
echo -e "  ${CYAN}┌─ AI 조직 봇 구성 ───────────────────────────────────┐${RESET}"
echo -e "  ${CYAN}│${RESET}                                                    ${CYAN}│${RESET}"
echo -e "  ${CYAN}│${RESET}  이 시스템은 ${BOLD}PM 봇 1개${RESET}로 바로 시작할 수 있습니다.  ${CYAN}│${RESET}"
echo -e "  ${CYAN}│${RESET}                                                    ${CYAN}│${RESET}"
echo -e "  ${CYAN}│${RESET}  전체 구성 (선택사항 — 나중에 추가 가능):          ${CYAN}│${RESET}"
echo -e "  ${CYAN}│${RESET}    PM 봇     — 총괄 관리자 ${BOLD}(지금 설정)${RESET}             ${CYAN}│${RESET}"
echo -e "  ${CYAN}│${RESET}    기획실 봇 — 기획/PRD 작성                       ${CYAN}│${RESET}"
echo -e "  ${CYAN}│${RESET}    개발실 봇 — 코드 구현                           ${CYAN}│${RESET}"
echo -e "  ${CYAN}│${RESET}    디자인실 봇 — UI/UX 디자인                      ${CYAN}│${RESET}"
echo -e "  ${CYAN}│${RESET}    성장실 봇 — 마케팅/그로스                       ${CYAN}│${RESET}"
echo -e "  ${CYAN}│${RESET}    운영실 봇 — 인프라/운영                         ${CYAN}│${RESET}"
echo -e "  ${CYAN}│${RESET}    리서치실 봇 — 조사/분석                         ${CYAN}│${RESET}"
echo -e "  ${CYAN}│${RESET}                                                    ${CYAN}│${RESET}"
echo -e "  ${CYAN}│${RESET}  ${DIM}각 부서 봇은 별도 토큰이 필요합니다.${RESET}              ${CYAN}│${RESET}"
echo -e "  ${CYAN}│${RESET}  ${DIM}부서 봇 추가: python scripts/setup_wizard.py${RESET}      ${CYAN}│${RESET}"
echo -e "  ${CYAN}│${RESET}                                                    ${CYAN}│${RESET}"
echo -e "  ${CYAN}└────────────────────────────────────────────────────┘${RESET}"
echo ""
echo -e "  ${DIM}봇 토큰이 없으면 아래 가이드를 따라 만드세요.${RESET}"
echo -e "  ${DIM}나중에 설정하려면 Enter를 눌러 건너뛰세요.${RESET}"
echo ""

# ── STEP A: BotFather에서 봇 만들기 ─────────────────────────────────────────
echo -e "  ${MAGENTA}┌─ STEP A: 봇 만들기 (1분 소요) ──────────────────────┐${RESET}"
echo -e "  ${MAGENTA}│${RESET}                                                    ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}│${RESET}  1. Telegram에서 ${BOLD}@BotFather${RESET} 검색 후 대화 시작      ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}│${RESET}  2. ${BOLD}/newbot${RESET} 입력                                    ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}│${RESET}  3. 봇 이름 입력 (예: 우리팀 AI봇)                 ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}│${RESET}  4. 봇 유저네임 입력 (예: myteam_ai_bot)           ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}│${RESET}  5. 나오는 토큰 복사 (${BOLD}1234567890:ABC...${RESET} 형식)      ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}│${RESET}                                                    ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}└────────────────────────────────────────────────────┘${RESET}"
echo ""

# PM 봇 토큰 입력
read -rp "  PM 봇 토큰 (Enter로 건너뛰기): " INPUT_BOT_TOKEN

echo ""

# ── STEP B: 봇을 그룹에 초대 ────────────────────────────────────────────────
echo -e "  ${MAGENTA}┌─ STEP B: 봇을 그룹에 초대 ─────────────────────────┐${RESET}"
echo -e "  ${MAGENTA}│${RESET}                                                    ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}│${RESET}  1. Telegram 그룹 채팅방 열기 (없으면 새로 만들기) ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}│${RESET}  2. 그룹 설정 → ${BOLD}멤버 추가${RESET}                         ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}│${RESET}  3. 방금 만든 봇 유저네임 검색 후 추가             ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}│${RESET}  4. ${BOLD}관리자 권한 부여${RESET} (그룹 설정 → 관리자 → 봇 추가)${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}│${RESET}     → 메시지 읽기/쓰기 권한 필요                   ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}│${RESET}                                                    ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}└────────────────────────────────────────────────────┘${RESET}"
echo ""

if [ -n "${INPUT_BOT_TOKEN:-}" ]; then
    echo -e "  ${DIM}초대 후 그룹에 아무 메시지를 보내세요. Chat ID를 알아낼 수 있습니다.${RESET}"
    echo ""
fi

# ── STEP C: Chat ID 알아내기 ─────────────────────────────────────────────────
echo -e "  ${MAGENTA}┌─ STEP C: 그룹 Chat ID 알아내기 ────────────────────┐${RESET}"
echo -e "  ${MAGENTA}│${RESET}                                                    ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}│${RESET}  1. 봇을 그룹에 초대한 뒤 아무 메시지 전송         ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}│${RESET}  2. 브라우저에서 아래 주소 열기:                    ${MAGENTA}│${RESET}"
if [ -n "${INPUT_BOT_TOKEN:-}" ]; then
echo -e "  ${MAGENTA}│${RESET}     ${BOLD}https://api.telegram.org/bot${INPUT_BOT_TOKEN:0:10}..../getUpdates${RESET}  ${MAGENTA}│${RESET}"
else
echo -e "  ${MAGENTA}│${RESET}     ${BOLD}https://api.telegram.org/bot<토큰>/getUpdates${RESET}  ${MAGENTA}│${RESET}"
fi
echo -e "  ${MAGENTA}│${RESET}  3. \"chat\":{\"id\":${BOLD}-100xxxxxxxxxx${RESET}} 부분이 Chat ID   ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}│${RESET}                                                    ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}│${RESET}  ${DIM}팁: -100으로 시작하는 숫자입니다 (음수)${RESET}           ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}│${RESET}                                                    ${MAGENTA}│${RESET}"
echo -e "  ${MAGENTA}└────────────────────────────────────────────────────┘${RESET}"
echo ""

# Chat ID 입력
read -rp "  그룹 Chat ID (Enter로 건너뛰기): " INPUT_CHAT_ID

echo ""

# =============================================================================
# STEP 3: 자동 설치 (install.sh --yes 호출)
# =============================================================================
echo -e "${BOLD}${BLUE}  [3/4] 자동 설치 중... (1~3분 소요)${RESET}"
echo ""

# install.sh를 non-interactive로 실행
bash "$SCRIPT_DIR/install.sh" --yes --skip-verify 2>&1 | while IFS= read -r line; do
    echo "  $line"
done

# ── 토큰/Chat ID를 .env에 주입 ──────────────────────────────────────────────
ENV_FILE="$SCRIPT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    _sed_env() {
        if [ "$OS_NAME" = "macOS" ]; then
            sed -i '' "$1" "$ENV_FILE"
        else
            sed -i "$1" "$ENV_FILE"
        fi
    }

    _set_or_append() {
        local key="$1" val="$2"
        if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
            _sed_env "s|^${key}=.*|${key}=${val}|"
        else
            echo "${key}=${val}" >> "$ENV_FILE"
        fi
    }

    if [ -n "${INPUT_BOT_TOKEN:-}" ]; then
        _set_or_append "PM_BOT_TOKEN"        "$INPUT_BOT_TOKEN"
        _set_or_append "TELEGRAM_BOT_TOKEN"  "$INPUT_BOT_TOKEN"
        ok "봇 토큰 설정 완료"
    fi

    if [ -n "${INPUT_CHAT_ID:-}" ]; then
        _set_or_append "TELEGRAM_GROUP_CHAT_ID" "$INPUT_CHAT_ID"
        ok "그룹 Chat ID 설정 완료"
    fi
fi

echo ""

# =============================================================================
# STEP 4: 최종 헬스체크 + 완료
# =============================================================================
echo -e "${BOLD}${BLUE}  [4/4] 최종 점검${RESET}"
echo ""

bash "$SCRIPT_DIR/install.sh" --health-only 2>&1 | while IFS= read -r line; do
    echo "  $line"
done

echo ""

# =============================================================================
# 완료 배너
# =============================================================================
echo -e "${BOLD}${GREEN}"
echo "  ╔═══════════════════════════════════════════════════════╗"
echo "  ║                                                       ║"
echo "  ║   설치 완료!                                          ║"
echo "  ║                                                       ║"
echo "  ╚═══════════════════════════════════════════════════════╝"
echo -e "${RESET}"

# ── 미설정 항목 안내 ─────────────────────────────────────────────────────────
NEED_SETUP=false

if [ -z "${INPUT_BOT_TOKEN:-}" ]; then
    NEED_SETUP=true
    warn "봇 토큰 미설정 — 나중에 .env 파일에서 설정하세요:"
    echo -e "    ${BOLD}nano .env${RESET}  →  PM_BOT_TOKEN=여기에붙여넣기"
    echo ""
fi

if [ -z "${INPUT_CHAT_ID:-}" ]; then
    NEED_SETUP=true
    warn "Chat ID 미설정 — 나중에 .env 파일에서 설정하세요:"
    echo -e "    ${BOLD}nano .env${RESET}  →  TELEGRAM_GROUP_CHAT_ID=-100xxxxxxxxxx"
    echo ""
fi

# ── 다음 단계 ────────────────────────────────────────────────────────────────
echo -e "  ${BOLD}다음 단계:${RESET}"
echo ""
if [ "$NEED_SETUP" = true ]; then
    echo -e "    1. ${BOLD}nano .env${RESET}  →  빈 항목 채우기"
    echo -e "    2. ${BOLD}bash scripts/start_all.sh${RESET}  →  봇 실행"
else
    echo -e "    ${BOLD}bash scripts/start_all.sh${RESET}  →  봇 실행!"
fi
echo ""

# ── 조직 편집 안내 ───────────────────────────────────────────────────────────
echo -e "  ${DIM}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "  ${CYAN}💡 조직 구성은 기호에 따라 자유롭게 편집할 수 있습니다.${RESET}"
echo ""
echo -e "  ${BOLD}부서 봇 추가하기 (선택사항):${RESET}"
echo -e "    @BotFather에서 부서별 봇을 추가로 만든 뒤"
echo -e "    .env 파일에 각 토큰을 입력하세요:"
echo ""
echo -e "    ${DIM}BOT_TOKEN_AIORG_PRODUCT_BOT=     # 기획실${RESET}"
echo -e "    ${DIM}BOT_TOKEN_AIORG_ENGINEERING_BOT= # 개발실${RESET}"
echo -e "    ${DIM}BOT_TOKEN_AIORG_DESIGN_BOT=      # 디자인실${RESET}"
echo -e "    ${DIM}BOT_TOKEN_AIORG_GROWTH_BOT=      # 성장실${RESET}"
echo -e "    ${DIM}BOT_TOKEN_AIORG_OPS_BOT=         # 운영실${RESET}"
echo -e "    ${DIM}BOT_TOKEN_AIORG_RESEARCH_BOT=    # 리서치실${RESET}"
echo ""
echo -e "    ${DIM}각 봇도 그룹에 초대 + 관리자 권한 부여가 필요합니다.${RESET}"
echo ""
echo -e "  ${BOLD}조직 구조 변경:${RESET}"
echo -e "     봇 역할/이름 편집:  ${BOLD}bots/*.yaml${RESET}"
echo -e "     대화형 설정:        ${BOLD}python scripts/setup_wizard.py${RESET}"
echo ""
echo -e "  ${DIM}PM 봇 하나만으로도 충분히 사용 가능하며,${RESET}"
echo -e "  ${DIM}필요할 때 부서 봇을 추가하면 됩니다.${RESET}"
echo ""
