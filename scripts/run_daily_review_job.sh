#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

PYTHON_BIN="./.venv/bin/python"
[ ! -x "$PYTHON_BIN" ] && PYTHON_BIN="python3"

mkdir -p "$HOME/.ai-org"

"$PYTHON_BIN" tools/orchestration_cli.py review-recent \
  --hours 24 \
  --engine claude-code \
  --upload \
  >> "$HOME/.ai-org/daily-review.log" 2>&1
