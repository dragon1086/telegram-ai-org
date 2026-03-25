#!/usr/bin/env bash
# macOS 권한 자동 설정 — quarantine 제거 + TCC.db 등록 (setup.sh에서 자동 호출)
set -euo pipefail

[[ "$(uname)" != "Darwin" ]] && exit 0

echo "=== macOS 권한 자동 설정 ==="

# ── 1. 대상 바이너리 동적 탐색 ────────────────────────────────────────────────
BINS=()

# Python (venv 또는 brew)
for candidate in \
    "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.venv/bin/python3" \
    "$(command -v python3 2>/dev/null || true)"; do
  [[ -z "$candidate" || ! -e "$candidate" ]] && continue
  real="$(realpath "$candidate" 2>/dev/null || true)"
  [[ -n "$real" ]] && BINS+=("$real")
  break
done

# Python framework 디렉토리 (재귀 quarantine 제거용)
PY_FRAMEWORK_DIR=""
if command -v python3 &>/dev/null; then
  PY_FRAMEWORK_DIR="$(python3 -c 'import sys; print(sys.prefix)' 2>/dev/null || true)"
fi

# tmux
if command -v tmux &>/dev/null; then
  real="$(realpath "$(command -v tmux)" 2>/dev/null || true)"
  [[ -n "$real" ]] && BINS+=("$real")
fi

# claude CLI
for candidate in \
    "${HOME}/.local/bin/claude" \
    "$(command -v claude 2>/dev/null | grep -v alias || true)"; do
  [[ -z "$candidate" || ! -e "$candidate" ]] && continue
  real="$(realpath "$candidate" 2>/dev/null || true)"
  [[ -n "$real" ]] && BINS+=("$real") && break
done

# ── 2. quarantine 플래그 제거 (Gatekeeper 팝업 방지) ─────────────────────────
echo "▶ quarantine 플래그 제거 중..."

if [[ -n "$PY_FRAMEWORK_DIR" && -d "$PY_FRAMEWORK_DIR" ]]; then
  xattr -dr com.apple.quarantine "${PY_FRAMEWORK_DIR}" 2>/dev/null \
    && echo "  ✅ Python framework: ${PY_FRAMEWORK_DIR}" || true
fi

for BIN in "${BINS[@]}"; do
  [[ -e "$BIN" ]] || continue
  xattr -d com.apple.quarantine "${BIN}" 2>/dev/null \
    && echo "  ✅ ${BIN}" || echo "  - (quarantine 없음) ${BIN}"
done

# ── 3. 사용자 TCC.db 등록 (sudo 불필요) ──────────────────────────────────────
USER_TCC="${HOME}/Library/Application Support/com.apple.TCC/TCC.db"
_tcc_insert() {
  local db="$1" bin="$2"
  sqlite3 "${db}" \
    "INSERT OR REPLACE INTO access
       (service, client, client_type, auth_value, auth_reason, auth_version,
        indirect_object_identifier_type, indirect_object_identifier)
     VALUES
       ('kTCCServiceSystemPolicyAllFiles', '${bin}', 1, 2, 4, 1, NULL, 'UNUSED');" \
    2>/dev/null && return 0 || return 1
}

if [[ -f "$USER_TCC" ]]; then
  echo "▶ 사용자 TCC.db 등록 시도..."
  for BIN in "${BINS[@]}"; do
    [[ -e "$BIN" ]] || continue
    if _tcc_insert "$USER_TCC" "$BIN"; then
      echo "  ✅ TCC 사용자 등록: ${BIN}"
    else
      echo "  - TCC 사용자 등록 불가 (잠김): ${BIN}"
    fi
  done
else
  echo "  - 사용자 TCC.db 없음 (건너뜀)"
fi

# ── 4. 시스템 TCC.db 등록 (sudo 필요 — 가능한 경우만) ───────────────────────
SYS_TCC="/Library/Application Support/com.apple.TCC/TCC.db"
if [[ -w "$SYS_TCC" ]] || sudo -n true 2>/dev/null; then
  echo "▶ 시스템 TCC.db 등록 시도 (sudo)..."
  for BIN in "${BINS[@]}"; do
    [[ -e "$BIN" ]] || continue
    if sudo sqlite3 "${SYS_TCC}" \
        "INSERT OR REPLACE INTO access
           (service, client, client_type, auth_value, auth_reason, auth_version,
            indirect_object_identifier_type, indirect_object_identifier)
         VALUES
           ('kTCCServiceSystemPolicyAllFiles', '${BIN}', 1, 2, 4, 1, NULL, 'UNUSED');" \
        2>/dev/null; then
      echo "  ✅ TCC 시스템 등록: ${BIN}"
    else
      echo "  - TCC 시스템 등록 불가 (SIP 활성화됨 — 수동 필요)"
    fi
  done
else
  echo "  - sudo 비활성화 상태 — 시스템 TCC 등록 건너뜀"
fi

# ── 5. tmux 서버 재기동 권고 (FDA 상속을 위해) ───────────────────────────────
if command -v tmux &>/dev/null && tmux list-sessions &>/dev/null 2>&1; then
  echo ""
  echo "⚠️  tmux 서버가 실행 중입니다."
  echo "   권한 적용을 위해 다음 명령 실행을 권장합니다:"
  echo "   tmux kill-server && bash scripts/start_all.sh"
fi

echo ""
echo "=== macOS 권한 설정 완료 ==="
echo "   수동 팝업이 계속 뜨면: 시스템 설정 → 개인 정보 보호 → 전체 디스크 접근"
echo "   → iTerm2/Ghostty 체크 확인 후 tmux kill-server 실행"
