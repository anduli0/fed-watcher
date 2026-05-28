#!/bin/bash
set -e

# Restore claude CLI credentials from env var (set after first auth on Railway)
if [ -n "$CLAUDE_CREDENTIALS" ]; then
    mkdir -p /root/.claude
    echo "$CLAUDE_CREDENTIALS" > /root/.claude/.credentials.json
    echo "[entrypoint] Claude credentials restored from env var"
fi

# Start backend
exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
