#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

PYTHON_BIN="./.venv/bin/python"
[ ! -x "$PYTHON_BIN" ] && PYTHON_BIN="python3"

mkdir -p "$HOME/.ai-org"

if [ -f "$HOME/.ai-org/config.yaml" ]; then
  set -a
  source "$HOME/.ai-org/config.yaml"
  set +a
fi
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

"$PYTHON_BIN" tools/orchestration_cli.py auto-improve-recent \
  --hours 24 \
  --review-engine claude-code \
  --apply-engine claude-code \
  --push-branch \
  --create-pr \
  --upload \
  >> "$HOME/.ai-org/daily-review.log" 2>&1
