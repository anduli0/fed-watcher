import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.auth.mac_validator import validate_or_exit
from backend.auth.middleware import SecurityMiddleware
from backend.config import settings
from backend.database.init_db import init_db, AsyncSessionLocal
from backend.stabilizer.forecast_stabilizer import stabilize, QUANTIZE_BPS, StabilizationResult
from backend.routes.auth_routes import router as auth_router
from backend.routes.dashboard_routes import router as dashboard_router
from backend.routes.admin_routes import router as admin_router
from backend.routes.briefing_routes import router as briefing_router
from backend.routes.trading_routes import router as trading_router
from backend.routes.accuracy_routes import router as accuracy_router
from backend.routes.state_routes import router as state_router
from backend.scheduler.window_manager import init_scheduler, scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("fed_watcher")

validate_or_exit()


# ── Continuous data collection (no AI tokens) ────────────────────────────────
async def run_data_collection():
    from backend.data.collector import collect_web_data
    try:
        await collect_web_data()
    except Exception as e:
        logger.error("Data collection failed: %s", e)


# ── Core AI cycle ────────────────────────────────────────────────────────────
# The startup warm-up, the KST schedule, and the manual trigger endpoint can all
# call trigger_cycle — without a guard they overlap (a warm-up cycle still
# running when the next scheduled slot fires), which on a 512 MB host means OOM
# and double token burn for a single forecast. Skip instead of queueing: the
# already-running cycle produces the same forecast the new request wanted.
_cycle_lock = asyncio.Lock()


async def trigger_cycle(cycle_type: str = "scheduled"):
    if _cycle_lock.locked():
        from backend.data import activity_log as AL
        AL.emit("system", "System",
                f"Cycle '{cycle_type}' skipped — another cycle is already running",
                "#DD6B20", "info")
        logger.warning("Cycle '%s' skipped — another cycle is already running", cycle_type)
        return
    async with _cycle_lock:
        await _trigger_cycle_inner(cycle_type)


async def _trigger_cycle_inner(cycle_type: str = "scheduled"):
    """Run a full Orchestrator cycle (uses latest collected data; no fresh scraping)."""
    from backend.agents.orchestrator import run_full_cycle, HORIZONS
    from backend.agents.base_agent import AgentContext
    from backend.data.collector import get_latest_snapshot, collect_web_data
    from backend.stabilizer.event_calendar import get_today_event
    from backend.stabilizer.forecast_stabilizer import stabilize
    from backend.stabilizer.change_justifier import justify_change
    from backend.mock_trading.feedback_loop import get_negative_examples, generate_feedback
    from backend.database import crud
    from backend.claude_cli import verify_auth
    from backend.data import activity_log as AL

    logger.info("Starting cycle: %s", cycle_type)

    # ── Auth preflight ──────────────────────────────────────────────────────
    # One tiny claude ping before dispatching 21 agents. If credentials are
    # missing/expired the whole cycle would otherwise produce 21×(retries)
    # doomed 401 calls and an all-zero "forecast". Fail fast with a clear,
    # actionable message instead.
    ok, detail = await verify_auth()
    if not ok:
        AL.emit("system", "System",
                f"Cycle '{cycle_type}' aborted — Claude CLI not authenticated",
                "#E53E3E", "error")
        logger.error(
            "Cycle '%s' aborted: Claude CLI auth check failed: %s\n"
            "  → Fix: set CLAUDE_CODE_OAUTH_TOKEN (run `claude setup-token` locally) "
            "or ANTHROPIC_API_KEY in the deployment environment.",
            cycle_type, detail,
        )
        return

    # Ensure we have data — collect now if cache is empty
    snapshot = get_latest_snapshot()
    if snapshot["macro_snapshot"] is None:
        logger.info("No cached data; running collector first…")
        await collect_web_data()
        snapshot = get_latest_snapshot()

    async with AsyncSessionLocal() as db:
        event = await get_today_event()
        neg_examples = await get_negative_examples(db)

        # Market-implied path prior: the 2Y-DFF spread scaled by the empirical
        # pass-through (~0.7) is every agent's anchor; deviations must be argued.
        market_prior_text = ""
        try:
            from backend.data.fred_client import get_macro_snapshot
            macro = await get_macro_snapshot()
            dff_v, gs2_v = macro.get("DFF"), macro.get("GS2")
            if dff_v is not None and gs2_v is not None:
                spread_bps = (gs2_v - dff_v) * 100.0
                prior_12m = spread_bps * 0.7
                prior_6m = prior_12m * 0.5
                market_prior_text = (
                    f"DFF (effective fed funds): {dff_v:.2f}% · 2Y Treasury: {gs2_v:.2f}% "
                    f"→ 2Y-DFF spread {spread_bps:+.0f}bps.\n"
                    f"Market-implied prior: 12m {prior_12m:+.0f}bps · 6m {prior_6m:+.0f}bps "
                    f"(spread × 0.7 pass-through)."
                )
        except Exception as e:
            logger.warning("Market prior unavailable: %s", e)

        # Previous cycle's process self-review, injected as guidance
        self_critique = None
        try:
            from backend.routes.accuracy_routes import latest_critique
            self_critique = await latest_critique(db)
        except Exception:
            pass

        # Forward-guidance signals injected into every agent: (1) an operator
        # override for the quarterly SEP dot plot / specific quotes the user
        # supplies (FED_FORWARD_SIGNALS env — durable across redeploys), and
        # (2) auto-captured recent Fed-policy headlines from the same news feed
        # the daily briefing already scrapes (surfaces remarks by current or
        # prospective Fed leadership — e.g. potential-chair nominees — that the
        # federalreserve.gov-only speech scraper misses). No fabricated numbers:
        # the model only sees real operator input and real scraped headlines.
        fed_forward_signals = ""
        try:
            parts = []
            override = os.getenv("FED_FORWARD_SIGNALS", "").strip()
            if override:
                parts.append("OPERATOR-PROVIDED (SEP dot plot / key signals):\n" + override)
            # Real SEP dot-plot median path scraped live from federalreserve.gov.
            try:
                from backend.data.scrapers.dot_plot_scraper import fetch_dot_plot
                dp = await fetch_dot_plot()
                if dp and dp.summary_text:
                    parts.append(dp.summary_text)
            except Exception as e:
                logger.warning("Dot-plot scrape unavailable: %s", e)
            try:
                from backend.briefing.fetcher import fetch_all_sources
                arts = await fetch_all_sources()
                fed_arts = [
                    a for a in arts
                    if any(t in ("fed", "monetary_policy") for t in (a.get("topic_tags") or []))
                ][:8]
                if fed_arts:
                    lines = "\n".join(
                        f"- {a['title']}" + (f" — {a['snippet'][:140]}" if a.get("snippet") else "")
                        for a in fed_arts
                    )
                    parts.append("RECENT FED-POLICY HEADLINES (auto-scraped):\n" + lines)
            except Exception as e:
                logger.warning("Fed-news digest unavailable: %s", e)
            fed_forward_signals = "\n\n".join(parts)
        except Exception as e:
            logger.warning("Forward-guidance signals unavailable: %s", e)

        ctx = AgentContext(
            macro_snapshot_text=snapshot["macro_text"],
            speeches_text=snapshot["speeches_text"],
            fomc_minutes_texts=snapshot["minutes"],
            beige_book_text=snapshot["beige_book"],
            regional_stances_text=snapshot["regional_text"],
            cme_probabilities=snapshot["cme"],
            negative_examples=neg_examples,
            material_event=event.get("label") if event else None,
            market_prior_text=market_prior_text,
            self_critique=self_critique,
            fed_forward_signals=fed_forward_signals,
        )

        # Compute adaptive weights before running agents
        from backend.agents.orchestrator import compute_adaptive_weights
        await compute_adaptive_weights(db, event)

        run = await crud.create_run(db, cycle_type)
        try:
            result = await run_full_cycle(ctx, cycle_type)
        except Exception as e:
            await crud.complete_run(db, run.id, "failed")
            logger.error("Cycle failed: %s", e)
            return

        # Persist agent outputs
        import json
        for ar in result["agent_results"]:
            await crud.save_agent_output(db, {
                "run_id": run.id,
                "agent_id": ar["agent_id"],
                "agent_name": ar["agent_name"],
                "round": ar.get("round", 1),
                "signal": ar["signal"],
                "rate_path_delta_bps": ar["rate_path_delta_bps"],
                "horizons_json": json.dumps(ar.get("horizons", {})),
                "confidence": ar["confidence"],
                "weight_applied": ar["weight_applied"],
                "duration_ms": ar["duration_ms"],
                "limited_mode": ar["limited_mode"],
                "raw_json": json.dumps(ar),
            })

        collab_rounds = 2 if result.get("collaboration", {}).get("agents_revised") else 1
        await crud.complete_run(db, run.id, "completed", collab_rounds)

        # The published call is the committee's OWN weighted decision. The
        # market-implied path is already injected into every agent's context as a
        # shared anchor (market_prior_text), so agents have priced it in; the
        # aggregate delta and its confidence are published as-is. Earlier post-hoc
        # steps (shrink toward the prior, neutralize on dispersion, cap confidence
        # by agent agreement) made the call timid and collapsed confidence into
        # the low-10%s — removed in favor of the committee's native output.

        # ── Stabilize and persist all 4 horizons ──
        # Always publish immediately — cloud is always-on, no "morning publish" gate needed
        immediate_publish = True
        report_ko = result.get("report_ko", result.get("report_text", ""))
        report_en = result.get("report_en", "")
        changed_horizons: list[str] = []
        for h in HORIZONS:
            agg = result["horizons"][h]

            # The published call IS the committee's own weighted decision. The
            # market-implied prior is already injected into every agent's context
            # as an anchor (see market_prior_text), so agents have priced it in —
            # we do NOT additionally shrink the aggregate toward it here, and we
            # do NOT cap confidence by cross-agent agreement. Both post-hoc steps
            # made the published call timid and collapsed confidence into the
            # low-10%s; the committee's aggregate + confidence is the signal.
            prev = await crud.get_latest_horizon_forecast(db, h)
            prev_delta = prev.published_delta if prev else 0.0
            prev_streak = prev.unchanged_streak_days if prev else 0

            # Pull recent raw deltas for this horizon → adaptive alpha selection
            recent_raw = []
            try:
                hist = await crud.get_horizon_history(db, h, limit=8)
                recent_raw = [float(x.raw_delta_bps) for x in hist if x.raw_delta_bps is not None]
            except Exception:
                pass

            stabilized = stabilize(
                new_raw_delta=agg["weighted_delta_bps"],
                new_confidence=agg["confidence"],
                prev_published_delta=prev_delta,
                prev_streak=prev_streak,
                event=event,
                bypass_ema=(cycle_type == "forced"),
                recent_raw_deltas=recent_raw,
            )

            published_delta = stabilized.published_delta

            if abs(published_delta - (prev_delta or 0.0)) >= 1.0:
                changed_horizons.append(h)

            conf_published = agg["confidence"]

            justification = None
            if stabilized.changed:
                try:
                    justification = await justify_change(
                        stabilized.published_delta, prev_delta, event, result["agent_results"]
                    )
                except Exception:
                    justification = None

            # Determine signal from published delta
            sig = "hawkish" if published_delta >= 25 else \
                  "dovish" if published_delta <= -25 else "neutral"

            await crud.save_horizon_forecast(db, {
                "run_id": run.id,
                "horizon": h,
                "target_date": date.today().isoformat(),
                "raw_delta_bps": stabilized.raw_delta,
                "smoothed_delta": stabilized.smoothed_delta,
                "published_delta": published_delta,
                "confidence": conf_published,
                "signal": sig,
                "trigger_event": event.get("label") if event else None,
                "unchanged_streak_days": stabilized.unchanged_streak,
                "change_justification": justification,
                "is_published": immediate_publish,
                # Master report only stored on 12m record to avoid duplication
                "report_text": report_ko if h == "12m" else None,
                "report_text_en": report_en if h == "12m" else None,
            })

        # Backward-compat 12m PublishedForecast — mirror horizon_forecast[12m] exactly
        # (avoids double stabilization with diverging prev values)
        h12m = await crud.get_latest_horizon_forecast(db, "12m")
        if h12m:
            await crud.save_published_forecast(db, {
                "target_date": h12m.target_date,
                "raw_delta_bps": h12m.raw_delta_bps,
                "smoothed_delta": h12m.smoothed_delta,
                "published_delta": h12m.published_delta,
                "confidence": h12m.confidence,
                "trigger_event": h12m.trigger_event,
                "unchanged_streak_days": h12m.unchanged_streak_days,
                "change_justification": h12m.change_justification,
                "is_published": immediate_publish,
            })

        await generate_feedback(db, run.id, result["agent_results"])

        # ── Mock trading: roll the paper book on the fresh 12M call ─────────
        # Close any open positions at the current 2Y yield mark, then open new
        # ones mapped from the published 12M delta. Failures here must never
        # fail the cycle — the forecast is already persisted.
        try:
            from sqlalchemy import select
            from backend.database.models import MockTrade
            from backend.mock_trading.portfolio import (
                Position, build_positions_from_forecast,
            )
            from backend.mock_trading.simulator import calculate_pnl
            from backend.data.fred_client import get_macro_snapshot

            macro = await get_macro_snapshot()
            mark = macro.get("GS2")
            if mark is not None:
                open_res = await db.execute(
                    select(MockTrade).where(MockTrade.exit_rate.is_(None))
                )
                for t in open_res.scalars().all():
                    t.exit_rate = mark
                    t.pnl = calculate_pnl(
                        Position(t.instrument, t.direction, t.entry_rate, t.rationale or ""),
                        current_rate=mark, entry_rate=t.entry_rate or mark,
                    )
                h12_now = await crud.get_latest_horizon_forecast(db, "12m")
                delta12 = float(h12_now.published_delta) if h12_now and h12_now.published_delta is not None else 0.0
                for pos in build_positions_from_forecast(delta12):
                    db.add(MockTrade(
                        run_id=run.id,
                        instrument=pos.instrument,
                        direction=pos.direction,
                        entry_rate=mark,
                        rationale=pos.rationale,
                    ))
                await db.commit()
                logger.info("Mock trading book rolled at %s=%.2f (12m %+0.0f bps)",
                            "GS2", mark, delta12)
        except Exception as e:
            logger.warning("Mock trading step failed (non-fatal): %s", e)

    logger.info(
        "Cycle done. 6m %+.0f / 12m %+.0f / 3y %+.0f / 10y %+.0f bps · revised: %s",
        result["horizons"]["6m"]["weighted_delta_bps"],
        result["horizons"]["12m"]["weighted_delta_bps"],
        result["horizons"]["3y"]["weighted_delta_bps"],
        result["horizons"]["10y"]["weighted_delta_bps"],
        result.get("collaboration", {}).get("agents_revised", []),
    )

    # ── Push the derivation report to Telegram (SMS-style) ─────────────────
    # Fires when a horizon changed, or once for the day's first cycle. Idempotent
    # + never fatal — the forecast is already persisted above.
    try:
        from backend.telegram_notify import notify_derivation_report
        await notify_derivation_report(report_ko, changed=changed_horizons)
    except Exception as e:
        logger.warning("Telegram derivation-report notify failed (non-fatal): %s", e)


async def publish_morning_forecast():
    """Flip is_published=True at 08:00 KST on latest unpublished horizons + legacy."""
    async with AsyncSessionLocal() as db:
        # PostgreSQL-compatible: use TRUE/FALSE for boolean, DISTINCT ON for latest per horizon
        await db.execute(text("""
            UPDATE horizon_forecast SET is_published = TRUE
            WHERE id IN (
                SELECT MAX(id) FROM horizon_forecast
                WHERE is_published = FALSE
                GROUP BY horizon
            )
        """))
        await db.execute(text("""
            UPDATE published_forecast SET is_published = TRUE
            WHERE id = (SELECT id FROM published_forecast ORDER BY id DESC LIMIT 1)
        """))
        await db.commit()
    logger.info("Morning forecasts published.")


async def graceful_shutdown():
    # No-op on cloud — Railway keeps the server running 24/7
    logger.info("graceful_shutdown called (no-op in cloud deployment)")


def _restore_admin_weights():
    """Re-apply admin-set weight overrides from JSON file after restart."""
    from backend.routes.admin_routes import WEIGHTS_FILE, load_weights
    from backend.agents.orchestrator import apply_weight_override
    weights = load_weights()
    if weights:
        for agent_id_str, w in weights.items():
            apply_weight_override(int(agent_id_str), float(w))
        logger.info("Restored %d admin weight overrides from disk", len(weights))


# ── Startup warm-up: produce a forecast + briefing immediately on boot ───────
# Without this the dashboard stays empty until the next scheduled KST cycle
# (12:30/16:30/20:30/00:30/05:00). Runs in the background so the HTTP server
# (and Render's /health check) comes up instantly. Disable with
# RUN_CYCLE_ON_STARTUP=false.
STARTUP_WARMUP_DELAY = float(os.getenv("STARTUP_WARMUP_DELAY", "8"))


async def _startup_warmup():
    from backend.claude_cli import verify_auth, auth_mode

    # Let the server finish binding so health checks pass before heavy work.
    await asyncio.sleep(STARTUP_WARMUP_DELAY)

    # Always collect fresh data first (no AI tokens needed).
    await run_data_collection()

    # Give the deploy workflow's state restore a moment to land, then skip the
    # warm-up cycle entirely if a recent forecast already exists (restored from
    # the previous container or left over from a same-day run) — a full 21-agent
    # cycle per container swap is pure token burn when history survived.
    await asyncio.sleep(float(os.getenv("STATE_RESTORE_GRACE", "90")))
    try:
        from backend.database import crud
        async with AsyncSessionLocal() as _db:
            latest = await crud.get_latest_horizon_forecast(_db, "12m")
        if latest and latest.published_at:
            from datetime import datetime as _dt
            age_h = (_dt.utcnow() - latest.published_at).total_seconds() / 3600
            if age_h < float(os.getenv("WARMUP_SKIP_IF_FRESH_HOURS", "4")):
                logger.info(
                    "Startup warm-up skipped — forecast from %.1fh ago present "
                    "(restored or same-day). Next scheduled KST cycle will refresh.",
                    age_h,
                )
                return
    except Exception as e:
        logger.warning("Warm-up freshness check failed (%s); proceeding.", e)

    ok, detail = await verify_auth()
    if not ok:
        logger.error(
            "\n" + "=" * 74 +
            "\n  Claude CLI is NOT authenticated — forecasts & briefings cannot run."
            "\n  Detail     : %s"
            "\n  Auth mode  : %s"
            "\n  → Fix: set ONE of these in the deployment environment, then redeploy:"
            "\n       CLAUDE_CODE_OAUTH_TOKEN  (run `claude setup-token` locally — recommended)"
            "\n       ANTHROPIC_API_KEY        (a pay-per-token Anthropic API key)"
            "\n" + "=" * 74,
            detail, auth_mode(),
        )
        return

    logger.info("Claude CLI authenticated (mode=%s). Running startup cycle + briefing…", auth_mode())
    try:
        await trigger_cycle("startup")
    except Exception as e:
        logger.error("Startup cycle failed: %s", e, exc_info=True)
    try:
        from backend.briefing.pipeline import run_briefing_pipeline
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo
        today_kst = _dt.now(ZoneInfo("Asia/Seoul")).date()
        await run_briefing_pipeline(target_date=today_kst, force=False)
    except Exception as e:
        logger.error("Startup briefing failed: %s", e, exc_info=True)


# ── Free-tier keep-alive (anti-sleep) ────────────────────────────────────────
# Render's free tier spins the container down after ~15 min with no INBOUND
# requests, which kills any long background cycle mid-run ("끊김"). A background
# cycle generates no inbound traffic on its own, so we periodically GET our own
# public URL — that round-trips through Render's router as a real inbound request
# and resets the idle timer. Auto-uses RENDER_EXTERNAL_URL (set by Render); set
# KEEPALIVE_URL to override, or KEEPALIVE_INTERVAL_SEC=0 to disable. No-op when
# no public URL is known (e.g. local dev), so it's safe everywhere.
async def _keepalive_pinger():
    url = os.getenv("KEEPALIVE_URL") or os.getenv("RENDER_EXTERNAL_URL", "")
    interval = int(os.getenv("KEEPALIVE_INTERVAL_SEC", "600"))
    if not url or interval <= 0:
        logger.info("Keep-alive pinger disabled (no public URL or interval<=0).")
        return
    ping_url = url.rstrip("/") + "/health"
    logger.info("Keep-alive pinger active: %s every %ds", ping_url, interval)
    import httpx
    while True:
        await asyncio.sleep(interval)
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                await client.get(ping_url)
        except Exception as e:
            logger.warning("Keep-alive ping failed: %s", e)


async def _fail_orphaned_runs():
    """Mark run_log rows stuck in 'running' as failed at boot.

    A container kill (deploy swap, OOM, health-check SIGKILL) leaves the
    in-flight run's row 'running' forever, so the UI shows a phantom cycle
    that never finishes. A fresh process cannot have a running cycle, so
    anything still 'running' here is dead by definition.
    """
    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(text(
                "UPDATE run_log SET status = 'failed' WHERE status = 'running'"
            ))
            await db.commit()
            if res.rowcount:
                logger.warning("Marked %d orphaned running cycle(s) as failed.", res.rowcount)
    except Exception as e:
        logger.warning("Orphaned-run cleanup failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await _fail_orphaned_runs()
    _restore_admin_weights()
    init_scheduler(trigger_cycle, publish_morning_forecast, graceful_shutdown, run_data_collection)
    if os.getenv("RUN_CYCLE_ON_STARTUP", "true").lower() in ("1", "true", "yes", "on"):
        asyncio.create_task(_startup_warmup())
    else:
        asyncio.create_task(run_data_collection())
    asyncio.create_task(_keepalive_pinger())
    logger.info("Fed-Watcher started. Model: %s", settings.MODEL_ID)
    yield
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass


app = FastAPI(title="Fed-Watcher", docs_url="/docs", redoc_url=None, lifespan=lifespan, redirect_slashes=False)
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityMiddleware)
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(admin_router)
app.include_router(briefing_router)
app.include_router(trading_router)
app.include_router(accuracy_router)
app.include_router(state_router)


@app.get("/health")
async def health():
    from backend.data.collector import get_latest_snapshot
    from backend.claude_cli import last_auth_status, auth_mode
    snap = get_latest_snapshot()
    auth_ok, auth_detail = last_auth_status()  # cached — never spawns a process
    return {
        "status": "ok",
        "model": settings.MODEL_ID,
        "data_last_collected": snap.get("collected_at"),
        "agent_count": 21,
        "claude_auth": {
            "ok": auth_ok,            # null until the first cycle/startup check runs
            "mode": auth_mode(),
            "detail": auth_detail,
        },
    }


@app.post("/api/internal/shutdown")
async def internal_shutdown(request: Request):
    if getattr(request.state, "role", None) != "admin":
        raise HTTPException(403, "Admin access required")
    asyncio.create_task(graceful_shutdown())
    return {"status": "shutting_down"}


# --- Serve the statically-exported Next.js frontend (unified single-service deploy) ---
# The Docker image copies the `next export` output to /app/frontend/out. Mounted LAST,
# so every API router/route registered above takes precedence; all other paths (HTML
# pages and /_next/* assets) are served as static files. SecurityMiddleware treats these
# non-/api, non-/auth paths as a public shell (client-side handles login redirects).
from fastapi.staticfiles import StaticFiles  # noqa: E402

_FRONTEND_DIR = os.getenv(
    "FRONTEND_DIST",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "out"),
)
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
    logger.info(f"Serving static frontend from {_FRONTEND_DIR}")
else:
    logger.warning(f"Frontend dist not found at {_FRONTEND_DIR}; UI will not be served")
