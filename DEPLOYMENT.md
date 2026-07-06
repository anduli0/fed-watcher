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

## Daily 8AM (KST) auto-update — waking the sleeping instance

The backend already schedules everything itself (07:30 KST briefing, 08:00 KST
publish, forecast cycles). The only failure mode is a **sleeping Render free
instance**: while asleep, the internal APScheduler never fires, so the site
stays stale until someone visits. The fix is simply to have something **ping
the service before 8AM KST** — waking it triggers the startup warm-up
(`RUN_CYCLE_ON_STARTUP=true`, forecast + briefing) and keeps the internal
07:30 / 08:00 jobs on schedule. Three independent layers do this, in order of
preference:

1. **Claude cloud scheduled session (primary, active now).** A Claude Code
   trigger (`Fed-Watcher 매일 아침 8시 자동 업데이트`) fires daily at 22:20 UTC
   (07:20 KST) in the cloud — it runs regardless of whether the owner's PC or
   phone is on, pings `/health` with retries through the 08:05 KST window, and
   sends a push notification with the result. Managed from any Claude Code
   session via the claude-code-remote trigger tools.
2. **GitHub Actions (backup, no Claude involved).**
   `.github/workflows/daily-wakeup.yml` pings `/health` at 07:15 / 07:35 /
   07:55 KST with retry logic. Scheduled workflows only run from the default
   branch, so this activates once merged to `master`. Can also be fired
   manually (*Actions → Daily wake-up → Run workflow*).
3. **PC Task Scheduler (last-resort fallback).** `scheduler/daily_update.ps1`
   does the same from Windows — registration command is in the script header.

Interpretation note for all pingers: **any** HTTP response from the app —
including `403 Forbidden` from the IP-whitelist middleware — proves the
instance is awake and counts as success. Only connection failures / Render
router 5xx during cold start warrant retries.
