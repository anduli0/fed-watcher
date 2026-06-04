# Fed-Watcher — Deployment & Authentication

This document covers the one operational requirement that makes the live site
actually produce **rate forecasts** and the **daily briefing**: a valid Claude
credential in the backend environment.

## Architecture

```
fed-watcher.vercel.app  ──/api/* proxy (vercel.json)──▶  Render backend (FastAPI)
                                                          ├─ 21 AI agents  ─┐
                                                          ├─ briefing engine ┼─▶ `claude -p` CLI
                                                          └─ scheduler        ┘
```

- The **frontend** is a static Next.js export. It is served two ways: from
  Vercel (which proxies `/api/*` and `/auth/*` to the Render backend via
  `frontend/vercel.json`) and from the **same** Render backend (unified deploy,
  `Dockerfile`).
- The **backend** runs the forecast cycle and briefing pipeline by shelling out
  to the **Claude Code CLI** (`claude -p`) instead of using a paid API key
  directly. That CLI needs to be authenticated **inside the Render container**.

## The #1 requirement: authenticate the Claude CLI on Render

If the CLI is not authenticated, every agent call returns
`API Error: 401 Invalid authentication credentials`, all 21 agents fail, and the
dashboard shows an empty / neutral forecast and no briefing. This is the single
root cause of "the site doesn't work".

Set **exactly one** of these environment variables on the Render service
(Dashboard → your service → *Environment*):

| Variable | How to get it | Notes |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | Run `claude setup-token` on your machine (logs in with your Claude Pro/Max account) and copy the printed token. | **Recommended.** Long-lived; does not have the rotating-refresh-token problem. |
| `ANTHROPIC_API_KEY` | Anthropic Console → API Keys. | Pay-per-token billing. |
| `CLAUDE_CREDENTIALS` | The JSON contents of `~/.claude/.credentials.json` after an interactive login. | **Fragile** — OAuth access tokens expire and refresh tokens rotate, so a static snapshot stops working. Kept only as a fallback. |

> The backend reads these automatically (`backend/claude_cli.py`) and
> `docker-entrypoint.sh` logs which mode is active at boot.

### Verify it worked

```bash
curl https://<your-render-host>/health
# → "claude_auth": { "ok": true, "mode": "oauth_token (CLAUDE_CODE_OAUTH_TOKEN)", ... }

curl https://<your-render-host>/api/forecast
# → a forecast object (not {"status":"no_forecast"})
```

If `claude_auth.ok` is `false`, the `detail` field and the container logs tell
you exactly why (`AUTH:` vs `TRANSIENT:`).

## What runs automatically

- **Startup warm-up** (`RUN_CYCLE_ON_STARTUP=true`, default): on every boot the
  backend collects data, checks auth, then runs one forecast cycle **and** the
  daily briefing — so a freshly deployed container is populated within minutes
  instead of waiting for the next scheduled KST slot. If auth is missing it logs
  a clear fix-it banner and does nothing heavy.
- **Scheduled cycles** (KST): forecast at 12:30 / 16:30 / 20:30 / 00:30 / 05:00,
  publish flag at 08:00, daily briefing at 07:30. Every cycle does a one-shot
  auth preflight and aborts fast (no 21×retry storm) if the CLI can't authenticate.
- **Data collection** every 30 min (no AI tokens).

### Relevant env vars

| Variable | Default | Purpose |
|---|---|---|
| `RUN_CYCLE_ON_STARTUP` | `true` | Run a forecast + briefing on boot. |
| `STARTUP_WARMUP_DELAY` | `8` | Seconds to wait after boot before the warm-up. |
| `CLAUDE_MAX_CONCURRENT` | `1` | Parallel `claude` processes (raise on bigger instances). |
| `CLAUDE_NODE_MAX_OLD_SPACE_MB` | `256` | V8 heap cap per `claude` child (OOM guard on 512 MB hosts). |
| `MODEL_ID` | `claude-sonnet-4-6` | Model label. |
| `FRED_API_KEY`, `JWT_SECRET`, `ADMIN_PASSWORD_HASH`, `ALLOWED_IPS` | — | See `.env.example`. |

## Deploying code changes

The Render service **auto-deploys from `master`**. Code pushed to a feature
branch (e.g. `claude/adoring-ritchie-58LBc`) is **not** live until it is merged
to `master`.

### One-secret CI deploy (recommended)

The GitHub Actions workflow `.github/workflows/deploy-railway.yml`
(*Actions → Deploy to Render → Run workflow*) creates/redeploys the Render
service and injects env vars from repo secrets. To make the live site
authenticate, add this **one** GitHub repo secret, then run the workflow:

```
Settings → Secrets and variables → Actions → New repository secret
  Name : CLAUDE_CODE_OAUTH_TOKEN
  Value: <output of `claude setup-token`>
```

The workflow now forwards `CLAUDE_CODE_OAUTH_TOKEN` to Render (preferred over the
expiring `CLAUDE_CREDENTIALS` snapshot). Other secrets it uses: `RENDER_API_KEY`,
`JWT_SECRET`, `ADMIN_PASSWORD_HASH`, `FRED_API_KEY`.
