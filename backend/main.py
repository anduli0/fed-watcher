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
async def trigger_cycle(cycle_type: str = "scheduled"):
    """Run a full Orchestrator cycle (uses latest collected data; no fresh scraping)."""
    from backend.agents.orchestrator import run_full_cycle, HORIZONS
    from backend.agents.base_agent import AgentContext
    from backend.data.collector import get_latest_snapshot, collect_web_data
    from backend.stabilizer.event_calendar import get_today_event
    from backend.stabilizer.forecast_stabilizer import stabilize
    from backend.stabilizer.change_justifier import justify_change
    from backend.mock_trading.feedback_loop import get_negative_examples, generate_feedback
    from backend.database import crud

    logger.info("Starting cycle: %s", cycle_type)

    # Ensure we have data — collect now if cache is empty
    snapshot = get_latest_snapshot()
    if snapshot["macro_snapshot"] is None:
        logger.info("No cached data; running collector first…")
        await collect_web_data()
        snapshot = get_latest_snapshot()

    async with AsyncSessionLocal() as db:
        event = await get_today_event()
        neg_examples = await get_negative_examples(db)

        ctx = AgentContext(
            macro_snapshot_text=snapshot["macro_text"],
            speeches_text=snapshot["speeches_text"],
            fomc_minutes_texts=snapshot["minutes"],
            beige_book_text=snapshot["beige_book"],
            regional_stances_text=snapshot["regional_text"],
            cme_probabilities=snapshot["cme"],
            negative_examples=neg_examples,
            material_event=event.get("label") if event else None,
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

        # ── Stabilize and persist all 4 horizons ──
        # Always publish immediately — cloud is always-on, no "morning publish" gate needed
        immediate_publish = True
        report_ko = result.get("report_ko", result.get("report_text", ""))
        report_en = result.get("report_en", "")
        for h in HORIZONS:
            agg = result["horizons"][h]
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

            justification = None
            if stabilized.changed:
                try:
                    justification = await justify_change(
                        stabilized.published_delta, prev_delta, event, result["agent_results"]
                    )
                except Exception:
                    justification = None

            # Determine signal from published delta
            sig = "hawkish" if stabilized.published_delta >= 25 else \
                  "dovish" if stabilized.published_delta <= -25 else "neutral"

            await crud.save_horizon_forecast(db, {
                "run_id": run.id,
                "horizon": h,
                "target_date": date.today().isoformat(),
                "raw_delta_bps": stabilized.raw_delta,
                "smoothed_delta": stabilized.smoothed_delta,
                "published_delta": stabilized.published_delta,
                "confidence": agg["confidence"],
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

    logger.info(
        "Cycle done. 6m %+.0f / 12m %+.0f / 3y %+.0f / 10y %+.0f bps · revised: %s",
        result["horizons"]["6m"]["weighted_delta_bps"],
        result["horizons"]["12m"]["weighted_delta_bps"],
        result["horizons"]["3y"]["weighted_delta_bps"],
        result["horizons"]["10y"]["weighted_delta_bps"],
        result.get("collaboration", {}).get("agents_revised", []),
    )


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    _restore_admin_weights()
    init_scheduler(trigger_cycle, publish_morning_forecast, graceful_shutdown, run_data_collection)
    asyncio.create_task(run_data_collection())
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


@app.get("/health")
async def health():
    from backend.data.collector import get_latest_snapshot
    snap = get_latest_snapshot()
    return {
        "status": "ok",
        "model": settings.MODEL_ID,
        "data_last_collected": snap.get("collected_at"),
        "agent_count": 21,
    }


@app.post("/api/internal/shutdown")
async def internal_shutdown(request: Request):
    if getattr(request.state, "role", None) != "admin":
        raise HTTPException(403, "Admin access required")
    asyncio.create_task(graceful_shutdown())
    return {"status": "shutting_down"}
