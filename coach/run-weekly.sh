#!/usr/bin/env bash
# Headless weekly coach run — invoked by launchd (or manually for a dry run).
set -euo pipefail

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

cd "$(dirname "$0")/.."
mkdir -p logs data

LOG_FILE="logs/coach-$(date +%Y-%m-%d-%H%M).log"

claude -p "$(cat coach/COACH.md)" \
  --mcp-config .mcp.json \
  --allowedTools "mcp__garmin-coach" \
  --max-turns 50 \
  --output-format text \
  >"$LOG_FILE" 2>&1

echo "coach run complete: $LOG_FILE"
