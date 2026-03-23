#!/usr/bin/env bash
# install-daemon.sh — bot-watchdog를 OS 네이티브 데몬으로 등록/해제한다.
#
# 사용법:
#   bash scripts/install-daemon.sh           # 설치
#   bash scripts/install-daemon.sh --uninstall  # 해제
#
# 지원 플랫폼:
#   macOS  → ~/Library/LaunchAgents/ (launchctl)
#   Linux  → ~/.config/systemd/user/ (systemd --user)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TMPL_DIR="$SCRIPT_DIR/templates"
UNINSTALL=false

for arg in "$@"; do
  [[ "$arg" == "--uninstall" ]] && UNINSTALL=true
done

# ── 경로 해석 ────────────────────────────────────────────────────────────────
VENV_PYTHON=""
for candidate in \
    "$PROJECT_DIR/.venv/bin/python3" \
    "$PROJECT_DIR/.venv/bin/python" \
    "$(command -v python3 2>/dev/null || true)"; do
  if [ -x "$candidate" ]; then
    VENV_PYTHON="$candidate"
    break
  fi
done

if [ -z "$VENV_PYTHON" ]; then
  echo "❌ Python 실행 파일을 찾을 수 없습니다. .venv를 먼저 생성하세요."
  exit 1
fi

# ── 플랫폼 감지 ──────────────────────────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in
  Darwin) PLATFORM="macos" ;;
  Linux)  PLATFORM="linux" ;;
  *)
    echo "❌ 지원하지 않는 플랫폼: $OS (macOS 또는 Linux만 지원)"
    exit 1
    ;;
esac

# ── 템플릿 → 실제 파일 치환 헬퍼 ────────────────────────────────────────────
render_template() {
  local tmpl="$1" dest="$2"
  sed \
    -e "s|@@HOME@@|$HOME|g" \
    -e "s|@@PROJECT_DIR@@|$PROJECT_DIR|g" \
    -e "s|@@VENV_PYTHON@@|$VENV_PYTHON|g" \
    "$tmpl" > "$dest"
}

# ════════════════════════════════════════════════════════════════════════════
# macOS — LaunchAgent
# ════════════════════════════════════════════════════════════════════════════
if [ "$PLATFORM" = "macos" ]; then
  LABEL="ai.telegram-ai-org.bot-watchdog"
  PLIST_DIR="$HOME/Library/LaunchAgents"
  PLIST="$PLIST_DIR/$LABEL.plist"

  if [ "$UNINSTALL" = true ]; then
    echo "▶ LaunchAgent 해제 중..."
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || \
      launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "✅ 해제 완료: $PLIST"
    exit 0
  fi

  mkdir -p "$PLIST_DIR"
  render_template "$TMPL_DIR/bot-watchdog.plist.tmpl" "$PLIST"
  chmod 644 "$PLIST"

  # 이미 로드된 경우 먼저 해제
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || \
    launchctl unload "$PLIST" 2>/dev/null || true

  launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || \
    launchctl load "$PLIST"

  echo "✅ LaunchAgent 등록 완료"
  echo "   라벨: $LABEL"
  echo "   plist: $PLIST"
  echo "   Python: $VENV_PYTHON"
  echo "   로그: $HOME/.ai-org/bot-watchdog.log"

# ════════════════════════════════════════════════════════════════════════════
# Linux — systemd user unit
# ════════════════════════════════════════════════════════════════════════════
elif [ "$PLATFORM" = "linux" ]; then
  UNIT_NAME="telegram-ai-org-watchdog"
  UNIT_DIR="$HOME/.config/systemd/user"
  UNIT_FILE="$UNIT_DIR/$UNIT_NAME.service"

  if [ "$UNINSTALL" = true ]; then
    echo "▶ systemd user unit 해제 중..."
    systemctl --user disable --now "$UNIT_NAME" 2>/dev/null || true
    rm -f "$UNIT_FILE"
    systemctl --user daemon-reload
    echo "✅ 해제 완료: $UNIT_FILE"
    exit 0
  fi

  if ! systemctl --user status > /dev/null 2>&1; then
    echo "⚠️  systemd user session이 활성화되어 있지 않습니다."
    echo "   loginctl enable-linger \$USER 를 먼저 실행하세요."
    exit 1
  fi

  mkdir -p "$UNIT_DIR"
  render_template "$TMPL_DIR/bot-watchdog.service.tmpl" "$UNIT_FILE"

  systemctl --user daemon-reload
  systemctl --user enable --now "$UNIT_NAME"

  echo "✅ systemd user unit 등록 완료"
  echo "   유닛: $UNIT_NAME.service"
  echo "   파일: $UNIT_FILE"
  echo "   Python: $VENV_PYTHON"
  echo "   로그: $HOME/.ai-org/bot-watchdog.log"
  echo ""
  echo "   상태 확인: systemctl --user status $UNIT_NAME"
fi
