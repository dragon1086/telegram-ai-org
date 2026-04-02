#!/bin/sh
set -eu

# ── Gemini OAuth: host ~/.gemini → container ~/.gemini ──
GEMINI_HOST_DIR="/gemini-oauth"
GEMINI_HOME="${HOME:-/home/aiorg}/.gemini"
if [ -d "$GEMINI_HOST_DIR" ]; then
    mkdir -p "$GEMINI_HOME"
    cp -R "$GEMINI_HOST_DIR"/. "$GEMINI_HOME"/ 2>/dev/null || true
fi

# ── Claude Code: host ~/.claude → container ~/.claude ──
# Provides: agent personas (agents/*.md), settings.json, OAuth token
CLAUDE_HOST_DIR="/claude-config"
CLAUDE_HOME="${HOME:-/home/aiorg}/.claude"
if [ -d "$CLAUDE_HOST_DIR" ]; then
    mkdir -p "$CLAUDE_HOME"
    # Copy only what's needed — avoid special files/cache/debug dirs
    # 1) Agent personas (required for agent_teams mode)
    if [ -d "$CLAUDE_HOST_DIR/agents" ]; then
        mkdir -p "$CLAUDE_HOME/agents"
        cp -R "$CLAUDE_HOST_DIR/agents/"*.md "$CLAUDE_HOME/agents/" 2>/dev/null || true
    fi
    # 2) Settings (experimental features, auth config)
    for f in settings.json oauth-token; do
        if [ -e "$CLAUDE_HOST_DIR/$f" ]; then
            cp "$CLAUDE_HOST_DIR/$f" "$CLAUDE_HOME/$f" 2>/dev/null || true
        fi
    done
fi

exec python -m telegram_ai_org "$@"
