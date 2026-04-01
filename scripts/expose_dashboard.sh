#!/usr/bin/env bash
# AIMesh 대시보드 외부 공개 — ngrok 또는 cloudflared 자동 탐지

set -euo pipefail

PORT="${DASHBOARD_PORT:-8000}"

if command -v ngrok &>/dev/null; then
    echo "ngrok으로 포트 ${PORT} 공개 중..."
    ngrok http "${PORT}"
elif command -v cloudflared &>/dev/null; then
    echo "cloudflared로 포트 ${PORT} 공개 중..."
    cloudflared tunnel --url "http://localhost:${PORT}"
else
    echo "❌ ngrok 또는 cloudflared가 설치되어 있지 않습니다."
    echo "   설치 방법:"
    echo "     brew install ngrok/ngrok/ngrok"
    echo "     brew install cloudflared"
    exit 1
fi
