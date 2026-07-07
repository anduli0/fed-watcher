#!/bin/sh
set -e

# ── Claude auth: SUBSCRIPTION ONLY ───────────────────────────────────────────
# This service runs on the owner's Claude subscription via `claude -p`. The
# Claude API is intentionally NOT used. Auth precedence:
#   CLAUDE_CODE_OAUTH_TOKEN  → CLAUDE_CREDENTIALS (~/.claude/.credentials.json)
# Any ANTHROPIC_API_KEY is UNSET here so it can never shadow the subscription
# token (the exact 401 that silently degraded the watchers). app/claude_cli.py
# also scrubs it from every CLI child as defense-in-depth.
if [ -n "$ANTHROPIC_API_KEY" ]; then
    echo "[entrypoint] NOTE: ANTHROPIC_API_KEY present — unsetting it (subscription-only; API never used)."
    unset ANTHROPIC_API_KEY
fi
unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL 2>/dev/null || true

if [ -n "$CLAUDE_CODE_OAUTH_TOKEN" ]; then
    echo "[entrypoint] Claude auth: CLAUDE_CODE_OAUTH_TOKEN (subscription OAuth token)"
elif [ -n "$CLAUDE_CREDENTIALS" ]; then
    mkdir -p /root/.claude
    printf '%s' "$CLAUDE_CREDENTIALS" > /root/.claude/.credentials.json
    chmod 600 /root/.claude/.credentials.json
    echo "[entrypoint] Claude auth: restored ~/.claude/.credentials.json from CLAUDE_CREDENTIALS (subscription)"
else
    echo "[entrypoint] WARNING: no subscription credential set"
    echo "[entrypoint]   (need CLAUDE_CODE_OAUTH_TOKEN or CLAUDE_CREDENTIALS)."
    echo "[entrypoint]   AI analyses will fail with HTTP 401 until one is provided."
fi

exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
