#!/bin/bash
# =============================================================================
# tunnel_healthcheck.sh
# ngrok 터널 상태 확인 + 자동 복구 + Telegram 알림
#
# 사용법:
#   ./scripts/tunnel_healthcheck.sh
#
# cron 등록 (5분 간격):
#   */5 * * * * /Users/rocky/telegram-ai-org/scripts/tunnel_healthcheck.sh >> /Users/rocky/telegram-ai-org/logs/tunnel_healthcheck.log 2>&1
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"
NGROK_API="http://localhost:4040/api/tunnels"
NGROK_TIMEOUT=5
LOG_TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# 색상 없는 로그 (cron 환경 대응)
info()  { echo "[${LOG_TIMESTAMP}][INFO]  $*"; }
warn()  { echo "[${LOG_TIMESTAMP}][WARN]  $*"; }
error() { echo "[${LOG_TIMESTAMP}][ERROR] $*" >&2; }

# ---------------------------------------------------------------------------
# .env 로드
# ---------------------------------------------------------------------------
if [[ -f "${ENV_FILE}" ]]; then
    while IFS='=' read -r key value; do
        [[ "${key}" =~ ^#.*$ || -z "${key}" ]] && continue
        key="${key// /}"
        value="${value%"${value##*[![:space:]]}"}"
        export "${key}=${value}" 2>/dev/null || true
    done < <(grep -v '^#' "${ENV_FILE}" | grep -v '^$')
fi

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_GROUP_CHAT_ID="${TELEGRAM_GROUP_CHAT_ID:-}"

# ---------------------------------------------------------------------------
# Telegram 알림 함수
# ---------------------------------------------------------------------------
send_telegram() {
    local message="$1"
    if [[ -n "${TELEGRAM_BOT_TOKEN}" && -n "${TELEGRAM_GROUP_CHAT_ID}" ]]; then
        curl -s --max-time 10 \
            -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_GROUP_CHAT_ID}" \
            --data-urlencode "text=${message}" \
            > /dev/null 2>&1 || warn "Telegram 알림 발송 실패"
    fi
}

# ---------------------------------------------------------------------------
# ngrok 복구 함수
# ---------------------------------------------------------------------------
recover_ngrok() {
    info "ngrok 복구 시도 중..."

    # ngrok 프로세스 종료 (있다면)
    if pgrep -x ngrok > /dev/null 2>&1; then
        warn "ngrok 프로세스 발견 — 강제 종료 후 재시작 시도"
        pkill -x ngrok 2>/dev/null || true
        sleep 3
    fi

    # LaunchAgent로 관리 중이라면 launchctl kickstart 시도
    if launchctl list com.telegram-ai-org.ngrok-dashboard > /dev/null 2>&1; then
        info "LaunchAgent를 통해 ngrok 재시작 시도..."
        launchctl kickstart -k "gui/$(id -u)/com.telegram-ai-org.ngrok-dashboard" > /dev/null 2>&1 || true
        sleep 5
    else
        # 직접 백그라운드 실행 (fallback)
        warn "LaunchAgent 없음 — ngrok 직접 실행 시도"
        if command -v ngrok &>/dev/null; then
            nohup ngrok http 8000 --log=stdout >> "${PROJECT_ROOT}/logs/ngrok.log" 2>&1 &
            sleep 5
        else
            error "ngrok 바이너리를 찾을 수 없습니다. 'brew install ngrok/ngrok/ngrok' 로 설치하세요."
            send_telegram "[터널 헬스체크 CRITICAL]
ngrok 바이너리 없음 — 수동 설치 필요
시각: ${LOG_TIMESTAMP}
명령: brew install ngrok/ngrok/ngrok"
            exit 5
        fi
    fi

    # URL 재발급 시도
    info "URL 재발급 실행: issue_dashboard_url.sh"
    if bash "${SCRIPT_DIR}/issue_dashboard_url.sh" 2>&1; then
        RECOVERED_URL=$(grep '^DASHBOARD_URL=' "${ENV_FILE}" | cut -d'=' -f2-)
        info "복구 성공. 새 URL: ${RECOVERED_URL}"
        send_telegram "[터널 헬스체크 RECOVERED]
ngrok 터널 복구 완료
새 URL: ${RECOVERED_URL}
시각: ${LOG_TIMESTAMP}"
    else
        error "URL 재발급 실패. 수동 확인 필요."
        send_telegram "[터널 헬스체크 FAILED]
ngrok 복구 실패 — 수동 확인 필요
시각: ${LOG_TIMESTAMP}
명령: bash /Users/rocky/telegram-ai-org/scripts/issue_dashboard_url.sh"
        exit 6
    fi
}

# ---------------------------------------------------------------------------
# 1. ngrok 프로세스 확인
# ---------------------------------------------------------------------------
info "헬스체크 시작..."

if ! pgrep -x ngrok > /dev/null 2>&1; then
    warn "ngrok 프로세스가 실행 중이지 않습니다 — 복구 시도"
    send_telegram "[터널 헬스체크 ALERT]
ngrok 프로세스 없음 감지
시각: ${LOG_TIMESTAMP}
조치: 자동 복구 시도 중..."
    recover_ngrok
    exit 0
fi

# ---------------------------------------------------------------------------
# 2. ngrok 로컬 API 응답 확인
# ---------------------------------------------------------------------------
info "ngrok 로컬 API 응답 확인 중: ${NGROK_API}"
TUNNELS_JSON=$(curl -s --max-time "${NGROK_TIMEOUT}" "${NGROK_API}" 2>/dev/null || true)

if [[ -z "${TUNNELS_JSON}" ]]; then
    warn "ngrok 로컬 API 응답 없음 (타임아웃 ${NGROK_TIMEOUT}s) — 복구 시도"
    send_telegram "[터널 헬스체크 ALERT]
ngrok API 무응답 감지 (포트 4040)
시각: ${LOG_TIMESTAMP}
조치: 자동 복구 시도 중..."
    recover_ngrok
    exit 0
fi

# ---------------------------------------------------------------------------
# 3. public_url 파싱 및 출력
# ---------------------------------------------------------------------------
if command -v python3 &>/dev/null; then
    PUBLIC_URL=$(python3 -c "
import json
data = json.loads('''${TUNNELS_JSON}''')
tunnels = data.get('tunnels', [])
https = [t['public_url'] for t in tunnels if t.get('public_url','').startswith('https')]
http  = [t['public_url'] for t in tunnels if t.get('public_url','').startswith('http')]
result = https[0] if https else (http[0] if http else '')
print(result)
" 2>/dev/null || true)
else
    PUBLIC_URL=$(echo "${TUNNELS_JSON}" | grep -o '"public_url":"https://[^"]*"' | head -1 | sed 's/"public_url":"//;s/"//')
fi

if [[ -z "${PUBLIC_URL}" ]]; then
    warn "터널 URL 파싱 실패 — 복구 시도"
    recover_ngrok
    exit 0
fi

# ---------------------------------------------------------------------------
# 4. 성공: 현재 URL 출력
# ---------------------------------------------------------------------------
info "헬스체크 통과."
echo ""
echo "  [OK] 현재 Dashboard URL: ${PUBLIC_URL}"
echo ""
