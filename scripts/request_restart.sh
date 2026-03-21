#!/usr/bin/env bash
# request_restart.sh — 봇 재기동을 직접 하지 않고 플래그만 남긴다.
# watchdog가 플래그를 감지하여 안전하게 재기동을 수행한다.
#
# Usage:
#   bash scripts/request_restart.sh              # 전체 재기동 요청
#   bash scripts/request_restart.sh <org_id>     # 특정 봇 재기동 요청
#   bash scripts/request_restart.sh --reason "parse_mode 수정 반영"

set -euo pipefail

FLAG_DIR="$HOME/.ai-org"
FLAG_FILE="$FLAG_DIR/restart_requested"

TARGET="all"
REASON=""
REQUESTED_BY="${AIORG_ORG_ID:-unknown}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --reason)
            REASON="$2"
            shift 2
            ;;
        *)
            TARGET="$1"
            shift
            ;;
    esac
done

mkdir -p "$FLAG_DIR"

cat > "$FLAG_FILE" <<EOF
{
    "target": "$TARGET",
    "reason": "$REASON",
    "requested_by": "$REQUESTED_BY",
    "requested_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

echo "✅ 재기동 요청 등록 완료 (target=$TARGET). watchdog가 안전하게 처리합니다."
