#!/bin/bash
# =============================================================================
# issue_dashboard_url.sh
# ngrok 터널 URL 조회 → .env DASHBOARD_URL 자동 갱신 → Telegram 알림 발송
#
# 사용법:
#   ./scripts/issue_dashboard_url.sh
#
# 전제조건:
#   - ngrok 실행 중 (LaunchAgent 또는 수동 실행)
#   - .env 파일 존재 (TELEGRAM_BOT_TOKEN, TELEGRAM_GROUP_CHAT_ID 포함)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"
NGROK_API="http://localhost:4040/api/tunnels"
NGROK_TIMEOUT=5

# 색상 출력
info()  { echo "[INFO]  $*"; }
warn()  { echo "[WARN]  $*" >&2; }
error() { echo "[ERROR] $*" >&2; }

# ---------------------------------------------------------------------------
# 1. .env 파일 로드
# ---------------------------------------------------------------------------
if [[ ! -f "${ENV_FILE}" ]]; then
    error ".env 파일을 찾을 수 없습니다: ${ENV_FILE}"
    exit 1
fi

# .env에서 키=값 읽기 (주석·빈 줄 제외)
while IFS='=' read -r key value; do
    [[ "${key}" =~ ^#.*$ || -z "${key}" ]] && continue
    # 앞뒤 공백 제거
    key="${key// /}"
    value="${value%"${value##*[![:space:]]}"}"
    export "${key}=${value}" 2>/dev/null || true
done < <(grep -v '^#' "${ENV_FILE}" | grep -v '^$')

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_GROUP_CHAT_ID="${TELEGRAM_GROUP_CHAT_ID:-}"

# ---------------------------------------------------------------------------
# 2. ngrok 실행 여부 확인
# ---------------------------------------------------------------------------
info "ngrok 프로세스 확인 중..."
if ! pgrep -x ngrok > /dev/null 2>&1; then
    error "ngrok 프로세스가 실행 중이지 않습니다."
    error "다음 명령으로 시작하세요: ngrok http 8000 --log=stdout &"
    exit 2
fi
info "ngrok 프로세스 확인됨."

# ---------------------------------------------------------------------------
# 3. ngrok 로컬 API에서 public_url 조회
# ---------------------------------------------------------------------------
info "ngrok 로컬 API에서 URL 조회 중: ${NGROK_API}"

TUNNELS_JSON=$(curl -s --max-time "${NGROK_TIMEOUT}" "${NGROK_API}" 2>/dev/null || true)

if [[ -z "${TUNNELS_JSON}" ]]; then
    error "ngrok 로컬 API 응답 없음 (타임아웃 ${NGROK_TIMEOUT}s). ngrok가 아직 초기화 중일 수 있습니다."
    exit 3
fi

# public_url 파싱 (python3 또는 grep+sed 폴백)
if command -v python3 &>/dev/null; then
    PUBLIC_URL=$(python3 -c "
import json, sys
data = json.loads('''${TUNNELS_JSON}''')
tunnels = data.get('tunnels', [])
# https 터널 우선, 없으면 첫 번째
https = [t['public_url'] for t in tunnels if t.get('public_url','').startswith('https')]
http  = [t['public_url'] for t in tunnels if t.get('public_url','').startswith('http')]
result = https[0] if https else (http[0] if http else '')
print(result)
" 2>/dev/null || true)
else
    # python3 없을 경우 grep/sed 폴백
    PUBLIC_URL=$(echo "${TUNNELS_JSON}" | grep -o '"public_url":"https://[^"]*"' | head -1 | sed 's/"public_url":"//;s/"//')
fi

if [[ -z "${PUBLIC_URL}" ]]; then
    error "ngrok 터널 URL을 파싱할 수 없습니다. 응답:"
    echo "${TUNNELS_JSON}" >&2
    exit 4
fi

info "조회된 public URL: ${PUBLIC_URL}"

# ---------------------------------------------------------------------------
# 4. .env DASHBOARD_URL 항목 갱신
# ---------------------------------------------------------------------------
if grep -q '^DASHBOARD_URL=' "${ENV_FILE}"; then
    # 기존 항목 업데이트
    # macOS sed는 -i '' 필요
    sed -i '' "s|^DASHBOARD_URL=.*|DASHBOARD_URL=${PUBLIC_URL}|" "${ENV_FILE}"
    info ".env DASHBOARD_URL 업데이트 완료."
else
    # 항목 없으면 추가
    printf '\n# 터널 URL (scripts/issue_dashboard_url.sh가 자동 갱신)\nDASHBOARD_URL=%s\nDASHBOARD_PORT=8000\n' "${PUBLIC_URL}" >> "${ENV_FILE}"
    info ".env에 DASHBOARD_URL 항목 추가 완료."
fi

# ---------------------------------------------------------------------------
# 5. Telegram 알림 발송
# ---------------------------------------------------------------------------
if [[ -n "${TELEGRAM_BOT_TOKEN}" && -n "${TELEGRAM_GROUP_CHAT_ID}" ]]; then
    HOSTNAME=$(hostname -s 2>/dev/null || echo "unknown")
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    MESSAGE="[Dashboard URL 갱신]
호스트: ${HOSTNAME}
시각: ${TIMESTAMP}
URL: ${PUBLIC_URL}
포트: 8000 (FastAPI uvicorn)"

    SEND_RESULT=$(curl -s --max-time 10 \
        -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_GROUP_CHAT_ID}" \
        --data-urlencode "text=${MESSAGE}" \
        2>/dev/null || true)

    if echo "${SEND_RESULT}" | grep -q '"ok":true'; then
        info "Telegram 알림 발송 완료."
    else
        warn "Telegram 알림 발송 실패 (봇 토큰/채팅 ID 확인 필요). 응답: ${SEND_RESULT}"
    fi
else
    warn "TELEGRAM_BOT_TOKEN 또는 TELEGRAM_GROUP_CHAT_ID 미설정 — Telegram 알림 생략."
fi

# ---------------------------------------------------------------------------
# 6. 결과 출력
# ---------------------------------------------------------------------------
echo ""
echo "============================================"
echo "  Dashboard URL: ${PUBLIC_URL}"
echo "============================================"
