from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import httpx
import time
import json
from backend.database.init_db import get_db
from backend.database.models import AgentOutput, RunLog, HorizonForecast, HORIZONS
from backend.database import crud
from backend.config import settings
from backend.data.cache import data_cache

router = APIRouter(prefix="/api")

_last_trigger: float = 0
TRIGGER_COOLDOWN = 120


def _delta_to_signal(delta: float) -> str:
    if delta >= 25: return "hawkish"
    if delta <= -25: return "dovish"
    return "neutral"


def _serialize_horizon(f: HorizonForecast) -> dict:
    return {
        "horizon": f.horizon,
        "published_at": f.published_at.isoformat() if f.published_at else None,
        "published_delta_bps": f.published_delta,
        "smoothed_delta_bps": f.smoothed_delta,
        "confidence": f.confidence,
        "signal": _delta_to_signal(f.published_delta or 0),
        "trigger_event": f.trigger_event,
        "unchanged_streak_days": f.unchanged_streak_days,
        "change_justification": f.change_justification,
    }


# ── Multi-horizon forecast endpoints ───────────────────────────────────────

@router.get("/forecast/horizons")
async def get_all_horizons(db: AsyncSession = Depends(get_db)):
    """Return latest published forecast for all 4 horizons."""
    out = {}
    for h in HORIZONS:
        f = await crud.get_latest_horizon_forecast(db, h)
        out[h] = _serialize_horizon(f) if f else None
    return out


@router.get("/forecast/horizon/{horizon}")
async def get_horizon(horizon: str, db: AsyncSession = Depends(get_db)):
    if horizon not in HORIZONS:
        raise HTTPException(404, f"Unknown horizon: {horizon}")
    f = await crud.get_latest_horizon_forecast(db, horizon)
    if not f:
        return {"status": "no_forecast"}
    return _serialize_horizon(f)


@router.get("/forecast/horizon/{horizon}/history")
async def get_horizon_history(horizon: str, db: AsyncSession = Depends(get_db)):
    if horizon not in HORIZONS:
        raise HTTPException(404, f"Unknown horizon: {horizon}")
    history = await crud.get_horizon_history(db, horizon, limit=30)
    return [
        {
            "date": f.target_date,
            "published_delta_bps": f.published_delta,
            "confidence": f.confidence,
            "change_justification": f.change_justification,
            "unchanged_streak_days": f.unchanged_streak_days,
        }
        for f in history
    ]


@router.get("/forecast/report")
async def get_derivation_report(lang: str = "ko", db: AsyncSession = Depends(get_db)):
    """Master derivation report — pass ?lang=en for English, ?lang=ko for Korean."""
    report = await crud.get_latest_report(db, lang=lang)
    return {"report": report or ""}


# ── Backward-compat (12m) ──────────────────────────────────────────────────

@router.get("/forecast")
async def get_forecast(db: AsyncSession = Depends(get_db)):
    forecast = await crud.get_latest_published_forecast(db)
    if not forecast:
        from backend.claude_cli import last_auth_status
        auth_ok, _ = last_auth_status()
        if auth_ok is False:
            msg = ("Forecast engine is not authenticated — an operator must set "
                   "CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY on the backend.")
        else:
            msg = "Generating the first forecast — check back in a few minutes."
        return {"status": "no_forecast", "message": msg}
    return {
        "published_at": forecast.published_at,
        "published_delta_bps": forecast.published_delta,
        "smoothed_delta_bps": forecast.smoothed_delta,
        "confidence": forecast.confidence,
        "signal": _delta_to_signal(forecast.published_delta),
        "trigger_event": forecast.trigger_event,
        "unchanged_streak_days": forecast.unchanged_streak_days,
        "change_justification": forecast.change_justification,
    }


@router.get("/forecast/history")
async def get_forecast_history(db: AsyncSession = Depends(get_db)):
    history = await crud.get_forecast_history(db, limit=30)
    return [
        {
            "date": f.target_date,
            "published_delta_bps": f.published_delta,
            "confidence": f.confidence,
            "change_justification": f.change_justification,
            "unchanged_streak_days": f.unchanged_streak_days,
        }
        for f in history
    ]


# ── Agent status ────────────────────────────────────────────────────────────

@router.get("/agents/status")
async def get_agent_status(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RunLog).where(RunLog.status == "completed").order_by(desc(RunLog.id)).limit(1)
    )
    latest_run = result.scalar_one_or_none()
    if not latest_run:
        return []

    # Use round-2 outputs if available (revised), otherwise round-1
    result = await db.execute(
        select(AgentOutput).where(AgentOutput.run_id == latest_run.id).order_by(desc(AgentOutput.round))
    )
    outputs = list(result.scalars().all())

    # Dedupe — prefer round 2 over round 1 for same agent_id
    seen = set()
    deduped = []
    for o in outputs:
        if o.agent_id not in seen:
            seen.add(o.agent_id)
            deduped.append(o)

    return [
        {
            "agent_id": o.agent_id,
            "agent_name": o.agent_name,
            "signal": o.signal,
            "rate_path_delta_bps": o.rate_path_delta_bps,
            "horizons": json.loads(o.horizons_json) if o.horizons_json else {},
            "confidence": o.confidence,
            "limited_mode": o.limited_mode,
            "duration_ms": o.duration_ms,
            "round": o.round,
            "last_run": latest_run.completed_at,
        }
        for o in deduped
    ]


# ── FRED chart data ────────────────────────────────────────────────────────

VALID_SERIES = {"DFF", "GS2", "GS10", "T5YIE", "T10Y2Y", "CPIAUCSL", "PCEPI", "UNRATE", "SOFR", "PAYEMS"}


@router.get("/macro/series/{series_id}")
async def get_macro_series(series_id: str):
    if series_id not in VALID_SERIES:
        raise HTTPException(404, f"Unknown series: {series_id}")
    cache_key = f"macro_history_{series_id}"
    cached = data_cache.get(cache_key, ttl_seconds=4 * 3600)
    if cached:
        return cached
    params = {
        "series_id": series_id, "api_key": settings.FRED_API_KEY,
        "file_type": "json", "limit": 730, "sort_order": "desc",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://api.stlouisfed.org/fred/series/observations", params=params)
        r.raise_for_status()
    obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
    obs.reverse()
    data = [{"date": o["date"], "value": float(o["value"])} for o in obs]
    payload = {"series_id": series_id, "data": data[-365:]}
    data_cache.set(cache_key, payload)
    return payload


# ── Manual cycle trigger (rate-limited) ────────────────────────────────────

@router.post("/trigger-cycle")
async def trigger_cycle_endpoint(request: Request):
    global _last_trigger
    from backend.main import trigger_cycle, _cycle_lock

    # A cycle is already in flight (startup warm-up or a scheduled slot) —
    # tell the caller instead of silently no-oping via the cycle guard.
    if _cycle_lock.locked():
        return {
            "status": "already_running",
            "message": "A forecast cycle is already running — results publish when it completes.",
        }

    role = getattr(request.state, "role", None)
    if role != "admin":
        elapsed = time.time() - _last_trigger
        if elapsed < TRIGGER_COOLDOWN:
            remaining = int(TRIGGER_COOLDOWN - elapsed)
            raise HTTPException(429, f"Rate limited. Try again in {remaining}s.")
    _last_trigger = time.time()
    import asyncio
    asyncio.create_task(trigger_cycle("forced"))
    return {"status": "triggered", "message": "Cycle running. Refresh in 2–4 min (21 agents × 2 rounds)."}


@router.get("/activity")
async def get_activity(after_id: int = 0):
    """Real-time activity events from collectors and agents."""
    from backend.data.activity_log import get_events_since, get_latest
    events = get_events_since(after_id) if after_id > 0 else get_latest(20)
    return [
        {
            "id": e.id,
            "ts": e.ts,
            "source": e.source,
            "agent": e.agent,
            "message": e.message,
            "color": e.color,
            "status": e.status,
        }
        for e in events
    ]


@router.get("/weights/adaptive")
async def get_adaptive_weights():
    """Current adaptive weight multipliers computed from accuracy history + event."""
    from backend.agents.orchestrator import _ADAPTIVE_MULTIPLIERS, ALL_AGENTS, _WEIGHT_OVERRIDES
    return [
        {
            "agent_id": a.agent_id,
            "agent_name": a.agent_name,
            "base_weight": a.weight,
            "override": _WEIGHT_OVERRIDES.get(a.agent_id),
            "adaptive_multiplier": _ADAPTIVE_MULTIPLIERS.get(a.agent_id, 1.0),
            "effective_weight": round(
                _WEIGHT_OVERRIDES.get(a.agent_id, a.weight) *
                _ADAPTIVE_MULTIPLIERS.get(a.agent_id, 1.0) *
                (1.5 if a.agent_id == 10 else 1.0),
                3
            ),
        }
        for a in ALL_AGENTS
    ]


@router.post("/trigger-collect")
async def trigger_collect_endpoint(request: Request):
    """Manually trigger web data collection (no AI tokens)."""
    from backend.main import run_data_collection
    import asyncio
    asyncio.create_task(run_data_collection())
    return {"status": "collecting", "message": "Web data sweep running in background."}
