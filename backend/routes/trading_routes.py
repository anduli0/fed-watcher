"""
Trading / track-record / today-at-a-glance endpoints.

- /api/trading      : mock portfolio built from each cycle's 12M rate call
- /api/track-record : published forecasts vs subsequent market-implied moves
- /api/today        : KST date, today's material event, schedule, latest run
"""
import os

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.database.init_db import get_db
from backend.database.models import MockTrade, HorizonForecast, FeedbackEntry, RunLog
from backend.data.cache import data_cache
from backend.mock_trading.portfolio import Position
from backend.mock_trading.simulator import calculate_pnl

router = APIRouter(prefix="/api")

KST = ZoneInfo("Asia/Seoul")

# Same proxy the feedback loop uses: 2Y Treasury for the 12M call.
_PROXY_SERIES = "GS2"


async def _proxy_observations() -> list[dict]:
    """Daily GS2 observations (date asc). Cached like /api/macro/series."""
    cache_key = f"macro_history_{_PROXY_SERIES}"
    cached = data_cache.get(cache_key, ttl_seconds=4 * 3600)
    if cached:
        return cached["data"]
    import httpx
    from backend.config import settings
    params = {
        "series_id": _PROXY_SERIES, "api_key": settings.FRED_API_KEY,
        "file_type": "json", "limit": 730, "sort_order": "desc",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://api.stlouisfed.org/fred/series/observations", params=params)
        r.raise_for_status()
    obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
    obs.reverse()
    data = [{"date": o["date"], "value": float(o["value"])} for o in obs]
    payload = {"series_id": _PROXY_SERIES, "data": data[-365:]}
    data_cache.set(cache_key, payload)
    return payload["data"]


def _value_on_or_before(obs: list[dict], day: str) -> float | None:
    """Latest observation value on/before YYYY-MM-DD (obs sorted asc)."""
    val = None
    for o in obs:
        if o["date"] <= day:
            val = o["value"]
        else:
            break
    return val


# ── Mock trading ────────────────────────────────────────────────────────────

# Trade-plan desk: map the current horizon calls onto treasury/USD positions.
# duration ≈ price sensitivity per 100bps; horizon window = expected time to target.
_PLAN_INSTRUMENTS = [
    # (instrument, driving horizon, duration, yield source series)
    ("2Y_TREASURY", "12m", 2.0, "GS2"),
    ("10Y_TREASURY", "3y", 8.0, "GS10"),
    ("TLT", "10y", 18.0, "GS10"),
    ("USD", "12m", 1.0, None),
]
_ACCOUNT_CAPITAL = float(os.getenv("ACCOUNT_CAPITAL_USD", "100000"))
_RISK_FRACTION = float(os.getenv("POSITION_RISK_FRACTION", "0.25"))


async def _build_plan(db: AsyncSession) -> dict:
    from backend.database.models import HorizonForecast
    from backend.database import crud

    horizons = {}
    for h in ("6m", "12m", "3y", "10y"):
        f = await crud.get_latest_horizon_forecast(db, h)
        if f:
            horizons[h] = f

    yields = {}
    try:
        obs2 = await _proxy_observations()
        yields["GS2"] = obs2[-1]["value"] if obs2 else None
    except Exception:
        yields["GS2"] = None
    try:
        import httpx
        from backend.config import settings
        cached = data_cache.get("macro_history_GS10", ttl_seconds=4 * 3600)
        if cached:
            yields["GS10"] = cached["data"][-1]["value"]
        else:
            params = {"series_id": "GS10", "api_key": settings.FRED_API_KEY,
                      "file_type": "json", "limit": 5, "sort_order": "desc"}
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    "https://api.stlouisfed.org/fred/series/observations", params=params)
                r.raise_for_status()
            obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
            yields["GS10"] = float(obs[0]["value"]) if obs else None
    except Exception:
        yields["GS10"] = None

    window_days = {"6m": 183, "12m": 365, "3y": 1095, "10y": 3650}
    rows = []
    for instrument, h, dur, ysrc in _PLAN_INSTRUMENTS:
        f = horizons.get(h)
        if not f or f.published_delta is None:
            continue
        delta = float(f.published_delta)
        if abs(delta) < 12.5:
            direction = "flat"
        elif instrument == "USD":
            direction = "long" if delta > 0 else "short"
        else:
            direction = "short" if delta > 0 else "long"
        cur = yields.get(ysrc) if ysrc else None
        target = round(cur + delta / 100.0, 2) if cur is not None else None
        expected_return_pct = round(dur * abs(delta) * 0.01, 2) if direction != "flat" else 0.0
        rows.append({
            "instrument": instrument,
            "driving_horizon": h,
            "direction": direction,
            "predicted_delta_bps": delta,
            "confidence": f.confidence,
            "current_yield": cur,
            "target_yield": target,
            "duration": dur,
            "expected_return_pct": expected_return_pct,
            "expected_days_to_target": window_days[h],
            "position_notional_usd": round(_ACCOUNT_CAPITAL * _RISK_FRACTION, 0),
        })
    return {
        "account_capital_usd": _ACCOUNT_CAPITAL,
        "risk_fraction": _RISK_FRACTION,
        "positions": rows,
        "note": (
            "확률적 금리 예측에서 파생된 모델·연구·모의매매용 산출물입니다. "
            "듀레이션·베타·DV01은 곡선/최저인도채권에 따라 변하는 단순 추정치이며, "
            "실주문 전 브로커 실시간 데이터로 재계산하세요."
        ),
    }


@router.get("/trading")
async def get_trading(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MockTrade).order_by(desc(MockTrade.created_at)).limit(200)
    )
    trades = list(result.scalars().all())

    # Current mark for open-position valuation
    obs = []
    try:
        obs = await _proxy_observations()
    except Exception:
        pass
    mark = obs[-1]["value"] if obs else None

    open_pos, closed = [], []
    for t in trades:
        row = {
            "id": t.id,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "instrument": t.instrument,
            "direction": t.direction,
            "entry_rate": t.entry_rate,
            "exit_rate": t.exit_rate,
            "pnl_pct": t.pnl,
            "rationale": t.rationale,
        }
        if t.exit_rate is None:
            if mark is not None and t.entry_rate is not None:
                row["unrealized_pnl_pct"] = calculate_pnl(
                    Position(t.instrument, t.direction, t.entry_rate, t.rationale or ""),
                    current_rate=mark, entry_rate=t.entry_rate,
                )
                row["current_rate"] = mark
            open_pos.append(row)
        else:
            closed.append(row)

    realized = [c["pnl_pct"] for c in closed if c["pnl_pct"] is not None]
    wins = sum(1 for p in realized if p > 0)
    try:
        plan = await _build_plan(db)
    except Exception:
        plan = None
    return {
        "plan": plan,
        "open_positions": open_pos,
        "closed_trades": closed[:100],
        "summary": {
            "open_count": len(open_pos),
            "closed_count": len(closed),
            "realized_pnl_pct": round(sum(realized), 4) if realized else 0.0,
            "wins": wins,
            "losses": sum(1 for p in realized if p < 0),
            "win_rate": round(wins / len(realized), 3) if realized else None,
            "mark_series": _PROXY_SERIES,
            "mark": mark,
        },
    }


# ── Treasury trading desk — positions by maturity (2Y/5Y/10Y/30Y) ────────────

# (label, spot instrument, futures sym, futures name, cash mod-duration,
#  futures DV01 $/bp per contract, fed-path beta, yield series, horizon blend)
# fed-path beta = how much this maturity's yield moves per bp of the committee's
# cumulative Fed-path call (front-end tracks the Fed closely; long-end far less).
# DV01/duration figures are round CTD-based estimates — recompute live before any
# real order (see disclaimer).
_DESK = [
    ("2Y",  "US 2Y Note",  "ZT", "2Y T-Note Future",  1.9,   33.0, 0.85, "GS2",  [("6m", 0.55), ("12m", 0.45)]),
    ("5Y",  "US 5Y Note",  "ZF", "5Y T-Note Future",  4.4,   46.0, 0.60, "GS5",  [("12m", 0.55), ("3y", 0.45)]),
    ("10Y", "US 10Y Note", "ZN", "10Y T-Note Future", 8.0,   67.0, 0.42, "GS10", [("3y", 0.55), ("10y", 0.45)]),
    ("30Y", "US 30Y Bond", "ZB", "30Y T-Bond Future", 17.5, 145.0, 0.30, "GS30", [("10y", 1.0)]),
]
_NEUTRAL_BAND_BPS = 8.0      # |expected yield move| below this → stand aside
_MIN_CONFIDENCE = 0.40       # weighted forecast confidence gate
_STOP_BPS = 20.0             # adverse yield move that trips the stop
_RISK_FRACTION_PER_POS = 0.01  # 1% of equity risked per maturity


async def _latest_yield(series_id: str) -> float | None:
    """Latest value for a treasury-yield FRED series, cached like the charts."""
    cache_key = f"macro_history_{series_id}"
    cached = data_cache.get(cache_key, ttl_seconds=4 * 3600)
    if cached and cached.get("data"):
        return cached["data"][-1]["value"]
    import httpx
    from backend.config import settings
    try:
        params = {"series_id": series_id, "api_key": settings.FRED_API_KEY,
                  "file_type": "json", "limit": 5, "sort_order": "desc"}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://api.stlouisfed.org/fred/series/observations", params=params)
            r.raise_for_status()
        obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
        return float(obs[0]["value"]) if obs else None
    except Exception:
        return None


async def get_trading_desk(equity: float = 1_000_000.0, db: AsyncSession = None) -> dict:
    """Map the committee's rate-path curve onto long/short positions across the
    2Y / 5Y / 10Y / 30Y Treasury complex, with spot & futures legs, targets,
    stops and sizing. Bonds move inverse to yields: a dovish (yields-down) call
    is a LONG. All greeks are estimates — see disclaimer."""
    from backend.database import crud

    horizons = {}
    for h in ("6m", "12m", "3y", "10y"):
        f = await crud.get_latest_horizon_forecast(db, h)
        if f and f.published_delta is not None:
            horizons[h] = f

    fed_funds = await _latest_yield("GS2")  # placeholder; overwritten by DFF below
    try:
        from backend.data.fred_client import fetch_series
        dff = await fetch_series("DFF")
        fed_funds = dff.latest_value
    except Exception:
        fed_funds = None

    positions = []
    for label, spot, fsym, fname, mod_dur, dv01, beta, yseries, blend in _DESK:
        # blended committee delta + confidence over this maturity's driving horizons
        wsum = dsum = csum = 0.0
        parts = []
        for h, w in blend:
            f = horizons.get(h)
            if not f:
                continue
            dsum += w * float(f.published_delta)
            csum += w * float(f.confidence or 0.0)
            wsum += w
            parts.append(f"{w:.2f}·{h}")
        if wsum == 0:
            continue
        blended_delta = dsum / wsum
        confidence = round(csum / wsum, 3)
        horizon_basis = " + ".join(parts)

        expected_dy = round(blended_delta * beta, 1)   # yield move in bps
        cur = await _latest_yield(yseries)
        target = round(cur + expected_dy / 100.0, 2) if cur is not None else None

        raw_dir = "long" if expected_dy < 0 else "short" if expected_dy > 0 else "neutral"
        direction, reason = raw_dir, None
        if abs(expected_dy) < _NEUTRAL_BAND_BPS:
            direction, reason = "neutral", f"within neutral band (±{_NEUTRAL_BAND_BPS:.0f}bps)"
        elif confidence < _MIN_CONFIDENCE:
            direction, reason = "neutral", f"forecast confidence {confidence:.0%} < {_MIN_CONFIDENCE:.0%}"

        # price impact of holding the cash bond long (positive when yields fall)
        spot_move = round(-mod_dur * expected_dy / 100.0, 2)
        target_risk = equity * _RISK_FRACTION_PER_POS
        contracts = 0
        risk_dollars = 0.0
        if direction != "neutral":
            contracts = max(1, round(target_risk / (_STOP_BPS * dv01)))
            risk_dollars = round(contracts * _STOP_BPS * dv01)
        face = contracts * 100_000

        if direction == "long":       # betting yields fall → stop if they rise
            stop_yield = round(cur + _STOP_BPS / 100.0, 2) if cur is not None else None
        elif direction == "short":
            stop_yield = round(cur - _STOP_BPS / 100.0, 2) if cur is not None else None
        else:
            stop_yield = None

        positions.append({
            "label": label,
            "spot_instrument": spot,
            "direction": direction,
            "raw_direction": raw_dir,
            "reason": reason,
            "current_yield": cur,
            "target_yield": target if direction != "neutral" else None,
            "expected_dy_bps": expected_dy,
            "confidence": confidence,
            "horizon_basis": horizon_basis,
            "fed_path_beta": beta,
            "cash_mod_duration": mod_dur,
            "spot_face_value": face,
            "spot_price_move_pct": spot_move if direction != "neutral" else None,
            "futures_symbol": fsym,
            "futures_name": fname,
            "futures_contracts": contracts,
            "futures_dv01": dv01,
            "futures_price_move_pct": spot_move if direction != "neutral" else None,
            "stop_yield": stop_yield,
            "take_profit_yield": target if direction != "neutral" else None,
            "stop_bps": _STOP_BPS,
            "risk_dollars": risk_dollars,
        })

    return {
        "as_of": datetime.now(KST).date().isoformat(),
        "fed_funds": round(fed_funds, 2) if fed_funds is not None else None,
        "equity": equity,
        "positions": positions,
        "disclaimer": (
            "Not investment advice. Model/research/paper-trading output derived from a "
            "probabilistic rate-path forecast. Duration, beta and DV01 are simple estimates "
            "that shift with the curve and cheapest-to-deliver; recompute with live broker "
            "data before any real order. Futures leverage can lose more than the margin posted."
        ),
    }


@router.get("/trading/desk")
async def trading_desk_route(equity: float = 1_000_000.0, db: AsyncSession = Depends(get_db)):
    equity = max(10_000.0, min(float(equity or 1_000_000.0), 1_000_000_000.0))
    try:
        return await get_trading_desk(equity=equity, db=db)
    except Exception as e:
        return {"as_of": None, "fed_funds": None, "equity": equity,
                "positions": [], "disclaimer": f"desk unavailable: {e}"}


# ── Track record (적중기록) ──────────────────────────────────────────────────

@router.get("/track-record")
async def get_track_record(db: AsyncSession = Depends(get_db)):
    """
    Daily hit record for the 12M call: the last published forecast of each day
    vs the subsequent change in the 2Y Treasury yield (market-implied proxy —
    the same outcome proxy the agent feedback loop trains against).
    """
    result = await db.execute(
        select(HorizonForecast)
        .where(HorizonForecast.horizon == "12m")
        .where(HorizonForecast.is_published == True)  # noqa: E712
        .order_by(HorizonForecast.published_at)
    )
    forecasts = list(result.scalars().all())

    # Last forecast per calendar day
    by_day: dict[str, HorizonForecast] = {}
    for f in forecasts:
        if f.published_at:
            by_day[f.published_at.date().isoformat()] = f
    days = sorted(by_day.keys())

    obs = []
    try:
        obs = await _proxy_observations()
    except Exception:
        pass

    records = []
    hits = misses = 0
    abs_errors = []
    for i, day in enumerate(days):
        f = by_day[day]
        predicted = f.published_delta or 0.0
        next_day = days[i + 1] if i + 1 < len(days) else None
        y0 = _value_on_or_before(obs, day) if obs else None
        y1 = _value_on_or_before(obs, next_day) if (obs and next_day) else (
            obs[-1]["value"] if obs else None
        )
        move_bps = round((y1 - y0) * 100, 1) if (y0 is not None and y1 is not None) else None

        hit: bool | None = None
        if move_bps is not None:
            if abs(move_bps) < 1.0 and next_day is not None:
                hit = None  # market flat — not scored
            elif abs(predicted) < 12.5:
                hit = abs(move_bps) < 10.0 if next_day is not None else None  # neutral call
            else:
                hit = (predicted * move_bps) > 0 if next_day is not None else None

        if hit is True:
            hits += 1
        elif hit is False:
            misses += 1
        if move_bps is not None and next_day is not None:
            abs_errors.append(abs(move_bps - predicted))

        records.append({
            "date": day,
            "predicted_bps": predicted,
            "signal": f.signal,
            "confidence": f.confidence,
            "market_move_bps": move_bps if next_day is not None else None,
            "hit": hit,
            "pending": next_day is None,
        })

    scored = hits + misses
    # Per-agent divergence counts from the feedback loop
    agg = await db.execute(
        select(FeedbackEntry.agent_id, func.count(FeedbackEntry.id))
        .group_by(FeedbackEntry.agent_id)
        .order_by(desc(func.count(FeedbackEntry.id)))
        .limit(5)
    )
    agent_misses = [{"agent_id": a, "miss_count": c} for a, c in agg.all()]

    return {
        "records": list(reversed(records))[:60],
        "stats": {
            "total_days": len(days),
            "scored": scored,
            "hits": hits,
            "misses": misses,
            "hit_rate": round(hits / scored, 3) if scored else None,
            "avg_abs_error_bps": round(sum(abs_errors) / len(abs_errors), 1) if abs_errors else None,
            "proxy_series": _PROXY_SERIES,
        },
        "agent_misses": agent_misses,
    }


# ── Today at a glance ────────────────────────────────────────────────────────

@router.get("/today")
async def get_today(db: AsyncSession = Depends(get_db)):
    from backend.stabilizer.event_calendar import get_today_event

    now_kst = datetime.now(KST)
    event = None
    try:
        event = await get_today_event()
    except Exception:
        pass

    result = await db.execute(select(RunLog).order_by(desc(RunLog.id)).limit(1))
    run = result.scalar_one_or_none()

    return {
        "date_kst": now_kst.date().isoformat(),
        "time_kst": now_kst.strftime("%H:%M"),
        "weekday_kst": now_kst.weekday(),  # 0=Mon
        "event": event,
        "schedule_kst": {
            "forecast_cycles": ["00:30", "05:00", "12:30", "16:30", "20:30"],
            "daily_briefing": "07:30",
            "data_collection": "every 30 min",
        },
        "latest_run": {
            "id": run.id,
            "status": run.status,
            "cycle_type": run.cycle_type,
            "started_at": run.started_at.isoformat() if run and run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run and run.completed_at else None,
        } if run else None,
    }
