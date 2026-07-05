"""
Accuracy / self-review / backtest endpoints — parity with the reference build.

- /api/accuracy/summary : maturity ledger — each published horizon call tracked
  against the realized fed funds rate (DFF) until its window matures
- /api/accuracy/quality : per-cycle process self-review scores + critique
- /api/backtest/skill   : mechanical directional engine backtested on FRED
  history (reference / lower bound on live skill; no AI involved)
"""
import json
from datetime import datetime, timedelta, date

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from backend.config import settings
from backend.database.init_db import get_db
from backend.database.models import HorizonForecast, AgentOutput, RunLog, HORIZONS
from backend.data.cache import data_cache

router = APIRouter(prefix="/api")

WINDOW_DAYS = {"6m": 183, "12m": 365, "3y": 1095, "10y": 3650}

FRED_OBS = "https://api.stlouisfed.org/fred/series/observations"


async def _series_daily(series_id: str, limit: int = 800) -> list[dict]:
    """Daily observations (date asc), cached 4h."""
    cache_key = f"acc_hist_{series_id}"
    cached = data_cache.get(cache_key, ttl_seconds=4 * 3600)
    if cached:
        return cached
    params = {
        "series_id": series_id, "api_key": settings.FRED_API_KEY,
        "file_type": "json", "limit": limit, "sort_order": "desc",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(FRED_OBS, params=params)
        r.raise_for_status()
    obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
    obs.reverse()
    data = [{"date": o["date"], "value": float(o["value"])} for o in obs]
    data_cache.set(cache_key, data)
    return data


async def _series_monthly(series_id: str, start: str = "2004-01-01") -> list[dict]:
    """Monthly observations (date asc) since `start`, cached 24h."""
    cache_key = f"acc_hist_m_{series_id}"
    cached = data_cache.get(cache_key, ttl_seconds=24 * 3600)
    if cached:
        return cached
    params = {
        "series_id": series_id, "api_key": settings.FRED_API_KEY,
        "file_type": "json", "observation_start": start,
        "frequency": "m", "aggregation_method": "eop", "limit": 100000,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(FRED_OBS, params=params)
        r.raise_for_status()
    obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
    data = [{"date": o["date"], "value": float(o["value"])} for o in obs]
    data_cache.set(cache_key, data)
    return data


def _value_on_or_before(obs: list[dict], day: str) -> float | None:
    val = None
    for o in obs:
        if o["date"] <= day:
            val = o["value"]
        else:
            break
    return val


# ── Maturity ledger (적중기록의 본체) ─────────────────────────────────────────

@router.get("/accuracy/summary")
async def accuracy_summary(db: AsyncSession = Depends(get_db)):
    """Each horizon's latest published call tracked against realized DFF."""
    today = date.today()
    try:
        dff = await _series_daily("DFF")
    except Exception:
        dff = []
    dff_now = dff[-1]["value"] if dff else None

    result = await db.execute(
        select(HorizonForecast)
        .where(HorizonForecast.is_published == True)  # noqa: E712
        .order_by(HorizonForecast.published_at)
    )
    forecasts = list(result.scalars().all())

    # Latest call per horizon → live tracking row
    latest: dict[str, HorizonForecast] = {}
    for f in forecasts:
        latest[f.horizon] = f

    tracking = []
    for h in HORIZONS:
        f = latest.get(h)
        if not f or not f.published_at:
            continue
        issued = f.published_at.date()
        elapsed = (today - issued).days
        window = WINDOW_DAYS[h]
        dff_at_issue = _value_on_or_before(dff, issued.isoformat()) if dff else None
        realized = (
            round((dff_now - dff_at_issue) * 100, 1)
            if (dff_now is not None and dff_at_issue is not None) else None
        )
        tracking.append({
            "horizon": h,
            "predicted_delta_bps": f.published_delta,
            "signal": f.signal,
            "confidence": f.confidence,
            "dff_realized_so_far_bps": realized,
            "elapsed_days": elapsed,
            "window_days": window,
            # Long horizons outlive any realistic DFF grading window
            "gradeable_vs_dff": h in ("6m", "12m"),
        })

    # Maturity ledger: first call of each (horizon, issue-date)
    seen: set[tuple[str, str]] = set()
    ledger = []
    for f in forecasts:
        if not f.published_at:
            continue
        key = (f.horizon, f.published_at.date().isoformat())
        if key in seen:
            continue
        seen.add(key)
        issued = f.published_at.date()
        matures = issued + timedelta(days=WINDOW_DAYS[f.horizon])
        matured = today >= matures
        entry = {
            "horizon": f.horizon,
            "issued": issued.isoformat(),
            "matures_on": matures.isoformat(),
            "predicted_delta_bps": f.published_delta,
            "status": "matured" if matured else "pending",
            "days_remaining": max(0, (matures - today).days),
        }
        if matured and dff:
            y0 = _value_on_or_before(dff, issued.isoformat())
            y1 = _value_on_or_before(dff, matures.isoformat())
            if y0 is not None and y1 is not None:
                realized = round((y1 - y0) * 100, 1)
                entry["dff_realized_bps"] = realized
                pred = f.published_delta or 0.0
                if abs(pred) < 12.5:
                    entry["hit"] = abs(realized) < 25.0
                else:
                    entry["hit"] = (pred * realized) > 0
        ledger.append(entry)
    ledger = ledger[-40:]

    # DFF context: move over the last 30 days
    dff_move_30d = None
    if dff and len(dff) > 1:
        past = _value_on_or_before(dff, (today - timedelta(days=30)).isoformat())
        if past is not None and dff_now is not None:
            dff_move_30d = round((dff_now - past) * 100, 1)

    matured_entries = [e for e in ledger if e["status"] == "matured" and "hit" in e]
    return {
        "as_of": today.isoformat(),
        "matured_count": len(matured_entries),
        "matured_hits": sum(1 for e in matured_entries if e["hit"]),
        "dff_now": dff_now,
        "dff_realized_move_bps": dff_move_30d,
        "dff_flat": abs(dff_move_30d) < 5 if dff_move_30d is not None else None,
        "tracking": tracking,
        "maturity_ledger": list(reversed(ledger)),
    }


# ── Per-cycle process self-review ────────────────────────────────────────────

def _sign(x: float, band: float = 12.5) -> int:
    if x >= band:
        return 1
    if x <= -band:
        return -1
    return 0


def _quality_for_run(hf_by_h: dict, agents: list[AgentOutput], prev_by_h: dict | None):
    """Deterministic process-quality scores for one cycle."""
    deltas = [hf_by_h[h].published_delta or 0.0 for h in HORIZONS if h in hf_by_h]
    # Term-structure coherence: penalize sign zigzags across adjacent horizons
    signs = [_sign(d) for d in deltas]
    flips = sum(
        1 for a, b in zip(signs, signs[1:])
        if a != 0 and b != 0 and a != b
    )
    term_coherence = round(max(0.0, 1.0 - flips / max(1, len(signs) - 1)), 4)

    # Signal consistency: published signal label matches the delta's sign
    ok = tot = 0
    for h in HORIZONS:
        f = hf_by_h.get(h)
        if not f:
            continue
        tot += 1
        expect = "hawkish" if (f.published_delta or 0) >= 25 else \
                 "dovish" if (f.published_delta or 0) <= -25 else "neutral"
        if f.signal == expect:
            ok += 1
    signal_consistency = round(ok / tot, 4) if tot else None

    # Consensus: share of agents whose 12m sign matches the published 12m sign
    consensus = None
    f12 = hf_by_h.get("12m")
    if f12 is not None and agents:
        pub_sign = _sign(f12.published_delta or 0.0)
        votes = [_sign(a.rate_path_delta_bps or 0.0) for a in agents]
        if votes:
            consensus = round(sum(1 for v in votes if v == pub_sign) / len(votes), 4)

    # Calibration: confidence should not exceed agent agreement by much
    calibration = None
    if f12 is not None and consensus is not None:
        gap = abs((f12.confidence or 0.0) - consensus)
        calibration = round(max(0.0, 1.0 - gap), 4)

    # Prior coherence: penalize large unexplained jumps vs the previous cycle
    prior_coherence = None
    if prev_by_h:
        jumps = []
        for h in HORIZONS:
            f, p = hf_by_h.get(h), prev_by_h.get(h)
            if f is not None and p is not None:
                jumps.append(abs((f.published_delta or 0) - (p.published_delta or 0)))
        if jumps:
            prior_coherence = round(max(0.0, 1.0 - (sum(jumps) / len(jumps)) / 100.0), 4)

    parts = [v for v in (term_coherence, signal_consistency, calibration,
                         consensus, prior_coherence) if v is not None]
    overall = round(sum(parts) / len(parts), 3) if parts else None

    # Templated critique on the weakest dimension
    critique = None
    dims = {
        "term_coherence": (term_coherence,
            "직전 사이클의 기간구조가 지그재그였다(부호가 6m→12m→3y→10y에서 반전). "
            "다음 예측에선 각 호라이즌이 경제적으로 일관된 경로를 이루도록 하라."),
        "calibration": (calibration,
            "발표 신뢰도가 에이전트 합의 수준과 크게 어긋난다. "
            "합의가 약할 때는 신뢰도를 낮춰 보고하라."),
        "consensus": (consensus,
            "에이전트 합의가 약한 채로 방향이 발표됐다. "
            "소수 의견의 근거를 다음 사이클에서 재검증하라."),
        "signal_consistency": (signal_consistency,
            "발표 시그널 라벨이 델타 부호와 불일치했다. 라벨 규칙을 재확인하라."),
        "prior_coherence": (prior_coherence,
            "직전 사이클 대비 발표치가 급변했다. 변경 사유를 명시적으로 정당화하라."),
    }
    scored = [(k, v, m) for k, (v, m) in dims.items() if v is not None]
    if scored:
        worst = min(scored, key=lambda x: x[1])
        if worst[1] < 0.85:
            critique = f"[PROCESS SELF-REVIEW · {worst[0]} {worst[1]:.2f}] {worst[2]}"

    return {
        "overall": overall,
        "term_coherence": term_coherence,
        "calibration": calibration,
        "signal_consistency": signal_consistency,
        "consensus": consensus,
        "prior_coherence": prior_coherence,
        "critique": critique,
    }


@router.get("/accuracy/quality")
async def accuracy_quality(db: AsyncSession = Depends(get_db)):
    runs_res = await db.execute(
        select(RunLog).where(RunLog.status == "completed")
        .order_by(desc(RunLog.id)).limit(12)
    )
    runs = list(runs_res.scalars().all())[::-1]  # oldest→newest

    trend = []
    prev_by_h: dict | None = None
    for run in runs:
        hf_res = await db.execute(
            select(HorizonForecast).where(HorizonForecast.run_id == run.id)
        )
        hf_by_h = {f.horizon: f for f in hf_res.scalars().all()}
        if not hf_by_h:
            continue
        ag_res = await db.execute(
            select(AgentOutput).where(AgentOutput.run_id == run.id)
        )
        agents = list(ag_res.scalars().all())
        q = _quality_for_run(hf_by_h, agents, prev_by_h)
        q["run_id"] = run.id
        q["at"] = run.completed_at.isoformat() if run.completed_at else None
        trend.append(q)
        prev_by_h = hf_by_h

    overalls = [t["overall"] for t in trend if t["overall"] is not None]
    return {
        "as_of": date.today().isoformat(),
        "n_cycles": len(trend),
        "latest": trend[-1] if trend else None,
        "mean_overall": round(sum(overalls) / len(overalls), 3) if overalls else None,
        "trend": trend,
    }


# ── Mechanical backtest (reference / lower bound) ────────────────────────────

@router.get("/backtest/skill")
async def backtest_skill():
    cached = data_cache.get("backtest_skill", ttl_seconds=24 * 3600)
    if cached:
        return cached

    NEUTRAL_BAND = 25.0     # bps: |predicted| below this = "no directional call"
    DEADBAND = 10.0         # bps: market-implied moves below this = flat
    ZLB = 0.5               # % DFF below this = zero-lower-bound month

    try:
        dff = await _series_monthly("DFF")
        gs2 = await _series_monthly("GS2")
        cpi = await _series_monthly("CPIAUCSL")
    except Exception as e:
        return {"error": f"FRED unavailable: {e}"}

    by_date = {}
    for row in dff:
        by_date.setdefault(row["date"], {})["dff"] = row["value"]
    for row in gs2:
        by_date.setdefault(row["date"], {})["gs2"] = row["value"]
    for row in cpi:
        by_date.setdefault(row["date"], {})["cpi"] = row["value"]
    months = sorted(d for d, v in by_date.items() if "dff" in v and "gs2" in v)

    def cpi_yoy(i: int) -> float | None:
        if i < 12:
            return None
        a = by_date.get(months[i], {}).get("cpi")
        b = by_date.get(months[i - 12], {}).get("cpi")
        if a is None or b is None or b == 0:
            return None
        return (a / b - 1.0) * 100.0

    def evaluate(horizon_m: int, excl_zlb: bool, target: str):
        n = hits = n_dir = hits_dir = 0
        for i in range(12, len(months) - horizon_m):
            row = by_date[months[i]]
            if excl_zlb and row["dff"] < ZLB:
                continue
            fwd = by_date.get(months[i + horizon_m], {})
            if target not in fwd or target not in row:
                continue
            realized = (fwd[target] - row[target]) * 100.0

            # Market-implied signal: 2Y-DFF spread as the expectations proxy
            implied = (row["gs2"] - row["dff"]) * 100.0
            # Taylor tilt: inflation gap pushes the implied path
            yoy = cpi_yoy(i)
            if yoy is not None:
                implied += (yoy - 2.0) * 10.0
            sig = 0 if abs(implied) < DEADBAND else (1 if implied > 0 else -1)

            realized_sig = 0 if abs(realized) < NEUTRAL_BAND else (1 if realized > 0 else -1)
            n += 1
            if sig == realized_sig:
                hits += 1
            if sig != 0 and realized_sig != 0:
                n_dir += 1
                if sig == realized_sig:
                    hits_dir += 1
        return {
            "n": n,
            "hit_rate": round(hits / n, 3) if n else None,
            "hit_rate_directional_only": round(hits_dir / n_dir, 3) if n_dir else None,
            "n_directional": n_dir,
        }

    payload = {
        "as_of_note": (
            "Backtest of the MECHANICAL directional engine (market-implied 2Y-DFF "
            "spread + inflation-gap tilt), NOT the live 21-agent ensemble. "
            "Reference/lower bound on live skill."
        ),
        "data_range": {
            "start": months[0][:7] if months else None,
            "end": months[-1][:7] if months else None,
            "n_decision_months": max(0, len(months) - 24),
        },
        "knobs": {
            "neutral_band_bps": NEUTRAL_BAND,
            "market_deadband_bps": DEADBAND,
            "zlb_dff_pct": ZLB,
            "horizons_m": [6, 12],
        },
        "headline_excl_zlb": {
            "label": "All months excl. zero-lower-bound (DFF>=0.5%)",
            "DFF_6m": evaluate(6, True, "dff"),
            "DFF_12m": evaluate(12, True, "dff"),
            "GS2_6m": evaluate(6, True, "gs2"),
            "GS2_12m": evaluate(12, True, "gs2"),
        },
        "all_months": {
            "label": "All months incl. ZLB",
            "DFF_6m": evaluate(6, False, "dff"),
            "DFF_12m": evaluate(12, False, "dff"),
        },
    }
    data_cache.set("backtest_skill", payload)
    return payload
