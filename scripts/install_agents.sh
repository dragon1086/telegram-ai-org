#!/usr/bin/env bash
# agency-agents + superpowers 설치 스크립트
# 사용법: bash scripts/install_agents.sh [engine]
#   engine: claude-code | codex | both (기본: both)

set -euo pipefail

ENGINE="${1:-both}"
AGENTS_DIR="$HOME/.ai-org/agents"
REPO_URL="https://github.com/msitarzewski/agency-agents.git"
TMP_DIR="$(mktemp -d)"

echo "📦 agency-agents 설치 중..."

# 1. Clone & copy .md files
git clone --depth 1 "$REPO_URL" "$TMP_DIR/agency-agents" 2>/dev/null
mkdir -p "$AGENTS_DIR"

# Copy agent .md files (skip README, LICENSE etc)
find "$TMP_DIR/agency-agents" -maxdepth 2 -name "*.md" \
  ! -iname "README*" ! -iname "LICENSE*" ! -iname "CONTRIBUTING*" \
  -exec cp {} "$AGENTS_DIR/" \;

AGENT_COUNT=$(ls "$AGENTS_DIR"/*.md 2>/dev/null | wc -l | tr -d ' ')
echo "✅ $AGENT_COUNT 에이전트 설치됨 → $AGENTS_DIR"

# 2. Claude Code 심볼릭 링크 (엔진이 claude-code 또는 both일 때만)
if [[ "$ENGINE" == "claude-code" || "$ENGINE" == "both" ]]; then
  CLAUDE_AGENTS="$HOME/.claude/agents"
  if [[ -d "$CLAUDE_AGENTS" ]]; then
    echo "ℹ️  ~/.claude/agents/ 이미 존재 — 심볼릭 링크 스킵"
  else
    mkdir -p "$(dirname "$CLAUDE_AGENTS")"
    ln -sf "$AGENTS_DIR" "$CLAUDE_AGENTS"
    echo "🔗 ~/.claude/agents → $AGENTS_DIR 심볼릭 링크 생성"
  fi
fi

# 3. Cleanup
rm -rf "$TMP_DIR"

# 4. superpowers 안내
echo ""
echo "🦸 superpowers 설치:"
if [[ "$ENGINE" == "claude-code" || "$ENGINE" == "both" ]]; then
  echo "  Claude Code: /plugin install superpowers@claude-plugins-official"
fi
if [[ "$ENGINE" == "codex" || "$ENGINE" == "both" ]]; then
  echo "  Codex: codex exec 'Fetch and follow instructions from https://raw.githubusercontent.com/obra/superpowers/refs/heads/main/.codex/INSTALL.md'"
fi

echo ""
echo "✅ 설치 완료!"
