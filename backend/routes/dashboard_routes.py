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

async def _current_dff() -> float | None:
    """Latest effective Fed Funds Rate (%) — anchor for implied rate levels."""
    try:
        from backend.data.fred_client import fetch_series
        s = await fetch_series("DFF")
        return s.latest_value
    except Exception:
        return None


def _synth_today(ref: dict | None, dff: float | None) -> dict:
    """'Today' horizon = the current policy rate itself (zero forward change).
    An anchor point for the term structure, not a forecast."""
    base = dict(ref) if ref else {}
    base.update({
        "horizon": "today",
        "published_delta_bps": 0.0,
        "smoothed_delta_bps": 0.0,
        "confidence": 0.99,
        "signal": "neutral",
        "dispersion_bps": 0.0,
        "band_low_bps": 0.0,
        "band_high_bps": 0.0,
        "trigger_event": None,
        "change_justification": "현행 기준금리 — 예측 곡선의 기준점",
        "synthetic": True,
    })
    if dff is not None:
        base["implied_rate_pct"] = round(dff, 2)
    return base


def _synth_3m(six_m: dict | None, dff: float | None) -> dict | None:
    """'3-month' horizon interpolated between today (0bps) and the 6-month call
    (~91/183 of the way). A near-term point on the same curve the agents draw."""
    if not six_m:
        return None
    frac = 0.5  # 91d / 183d ≈ 0.497
    d6 = six_m.get("published_delta_bps") or 0.0
    s6 = six_m.get("smoothed_delta_bps") or 0.0
    delta = round(d6 * frac, 1)
    disp = six_m.get("dispersion_bps")
    row = dict(six_m)
    row.update({
        "horizon": "3m",
        "published_delta_bps": delta,
        "smoothed_delta_bps": round(s6 * frac, 1),
        "confidence": round((six_m.get("confidence") or 0.5) * 0.95, 3),
        "signal": _delta_to_signal(delta),
        "dispersion_bps": round(disp * frac, 1) if disp is not None else None,
        "band_low_bps": round(delta - disp * frac, 1) if disp is not None else None,
        "band_high_bps": round(delta + disp * frac, 1) if disp is not None else None,
        "change_justification": "6개월 콜에서 보간한 근월 추정",
        "synthetic": True,
    })
    if dff is not None:
        row["implied_rate_pct"] = round(dff + delta / 100.0, 2)
    return row


@router.get("/forecast/horizons")
async def get_all_horizons(db: AsyncSession = Depends(get_db)):
    """Latest published forecast across the full term structure. The four
    analytical horizons (6m/12m/3y/10y) come from the 21-agent committee; two
    anchor points — 'today' (current rate) and '3m' (near-term, interpolated) —
    are derived so the front end can draw a complete curve. Each row also carries
    the implied rate *level* = current Fed Funds + delta."""
    from backend.routes.accuracy_routes import horizon_dispersion
    dff = await _current_dff()
    out: dict = {}
    disp_cache: dict[int, dict[str, float]] = {}
    for h in HORIZONS:
        f = await crud.get_latest_horizon_forecast(db, h)
        if not f:
            out[h] = None
            continue
        row = _serialize_horizon(f)
        if f.run_id not in disp_cache:
            disp_cache[f.run_id] = await horizon_dispersion(db, f.run_id)
        d = disp_cache[f.run_id].get(h)
        row["dispersion_bps"] = d
        pub = f.published_delta or 0.0
        row["band_low_bps"] = round(pub - d, 1) if d is not None else None
        row["band_high_bps"] = round(pub + d, 1) if d is not None else None
        if dff is not None:
            row["implied_rate_pct"] = round(dff + pub / 100.0, 2)
        out[h] = row

    # Derived anchor points — always present so the curve renders immediately.
    out["today"] = _synth_today(out.get("12m") or out.get("6m"), dff)
    out["3m"] = _synth_3m(out.get("6m"), dff)
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

VALID_SERIES = {
    "DFF", "GS2", "GS5", "GS10", "GS30", "T5YIE", "T10YIE", "T10Y2Y",
    "CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE", "UNRATE", "ICSA", "RSAFS",
    "MICH", "A191RL1Q225SBEA", "SOFR", "PAYEMS",
}


@router.get("/macro/indicators")
async def get_macro_indicators_route():
    """Rate-relevant US indicators for the Today tab: latest reading, prior,
    direction, policy meaning, and next scheduled release date."""
    from backend.data.macro_calendar import get_macro_indicators
    try:
        return await get_macro_indicators()
    except Exception:
        return {"as_of": None, "indicators": []}


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
