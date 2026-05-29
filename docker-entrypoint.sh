#!/bin/sh
set -e

# Restore claude CLI credentials from env var (set after first auth)
if [ -n "$CLAUDE_CREDENTIALS" ]; then
    mkdir -p /root/.claude
    printf '%s' "$CLAUDE_CREDENTIALS" > /root/.claude/.credentials.json
    chmod 600 /root/.claude/.credentials.json
    echo "[entrypoint] Claude credentials restored from env var"
fi

# Start backend (use python -m so we don't depend on the uvicorn script being on PATH)
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
