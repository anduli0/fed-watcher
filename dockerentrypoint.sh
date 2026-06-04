#!/bin/sh
set -e

# ── Claude CLI authentication ────────────────────────────────────────────────
# The forecast/briefing engine shells out to `claude -p`, which authenticates
# via (priority order): CLAUDE_CODE_OAUTH_TOKEN, ANTHROPIC_API_KEY, or a
# ~/.claude/.credentials.json file. Configure exactly ONE in the deployment env.
if [ -n "$CLAUDE_CODE_OAUTH_TOKEN" ]; then
    echo "[entrypoint] Claude auth: CLAUDE_CODE_OAUTH_TOKEN (long-lived OAuth token)"
elif [ -n "$ANTHROPIC_API_KEY" ]; then
    echo "[entrypoint] Claude auth: ANTHROPIC_API_KEY"
elif [ -n "$CLAUDE_CREDENTIALS" ]; then
    mkdir -p /root/.claude
    printf '%s' "$CLAUDE_CREDENTIALS" > /root/.claude/.credentials.json
    chmod 600 /root/.claude/.credentials.json
    echo "[entrypoint] Claude auth: restored ~/.claude/.credentials.json from CLAUDE_CREDENTIALS"
    echo "[entrypoint]   NOTE: OAuth credential snapshots expire and do not survive token"
    echo "[entrypoint]   rotation. Prefer CLAUDE_CODE_OAUTH_TOKEN (run \`claude setup-token\`)."
else
    echo "[entrypoint] WARNING: no Claude credential set"
    echo "[entrypoint]   (CLAUDE_CODE_OAUTH_TOKEN / ANTHROPIC_API_KEY / CLAUDE_CREDENTIALS)."
    echo "[entrypoint]   Forecasts & briefings will fail with HTTP 401 until one is provided."
fi

# Start backend (use python -m so we don't depend on the uvicorn script being on PATH)
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
